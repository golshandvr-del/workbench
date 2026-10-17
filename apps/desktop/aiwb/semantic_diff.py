"""Structured, conservative semantic change summaries with a text-diff fallback.

This module never executes source code. Language parsing is intentionally best-effort;
results include confidence and a fallback reason instead of pretending all languages
have a compiler-grade AST implementation.
"""
from __future__ import annotations
import ast
import csv
import difflib
import io
import json
import re
from collections import Counter
from pathlib import PurePosixPath
from typing import Any

MAX_SEMANTIC_CHARS = 256_000


def _python_symbols(text: str) -> dict[str, list[str]]:
    tree = ast.parse(text)
    result: dict[str, list[str]] = {"imports": [], "definitions": [], "classes": [], "functions": [], "assignments": []}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result["imports"].extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result["imports"].append("." * (node.level or 0) + (node.module or "") + ":" + ",".join(alias.name for alias in node.names))
        elif isinstance(node, ast.ClassDef):
            result["classes"].append(node.name)
            result["definitions"].append(f"class {node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["functions"].append(node.name)
            result["definitions"].append(f"function {node.name}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    result["assignments"].append(target.id)
    for key in result:
        result[key] = sorted(set(result[key]), key=str.casefold)
    return result


def _python_fingerprints(text: str) -> dict[str, str]:
    """Fingerprint named definitions so edits to an existing function/class are visible."""
    tree = ast.parse(text)
    result: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            result[f"class {node.name}"] = ast.dump(node, annotate_fields=True, include_attributes=False)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "async function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            result[f"{kind} {node.name}"] = ast.dump(node, annotate_fields=True, include_attributes=False)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    result[f"assignment {target.id}"] = ast.dump(node, annotate_fields=True, include_attributes=False)
    return result


def _json_flatten(value: Any, path: str = "$") -> dict[str, str]:
    """Flatten a JSON value into stable paths and canonical values."""
    out: dict[str, str] = {}
    if isinstance(value, dict) and value:
        for key in sorted(value, key=lambda x: str(x).casefold()):
            safe_key = str(key).replace("~", "~0").replace("/", "~1")
            out.update(_json_flatten(value[key], f"{path}/{safe_key}"))
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            out.update(_json_flatten(item, f"{path}/{index}"))
    else:
        out[path] = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return out


def _json_semantic_changes(before: str, after: str) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]], list[str]]:
    old = _json_flatten(json.loads(before))
    new = _json_flatten(json.loads(after))
    old_paths, new_paths = set(old), set(new)
    added = sorted(new_paths - old_paths)
    removed = sorted(old_paths - new_paths)
    changed = [f"{path}: {old[path]} -> {new[path]}" for path in sorted(old_paths & new_paths) if old[path] != new[path]]
    warnings = ["Array locations use numeric indexes; insertion or reordering may appear as several path-level changes."]
    return (({"json_paths": added} if added else {}), ({"json_paths": removed} if removed else {}),
            ({"json_values": changed} if changed else {}), warnings)


def _regex_symbols(text: str, language: str) -> dict[str, list[str]]:
    patterns: dict[str, dict[str, str]] = {
        "js": {"imports": r"(?m)^\s*(?:import\s+.*?\s+from\s+|import\s*\(|require\s*\()\s*['\"]([^'\"]+)", "definitions": r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="},
        "c": {"imports": r"(?m)^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]", "definitions": r"(?m)^\s*(?:static\s+)?(?:inline\s+)?[\w:*&<>]+\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"},
        "java": {"imports": r"(?m)^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;", "definitions": r"^\s*(?:public|protected|private|static|final|abstract|synchronized|\s)+\s*(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)|^\s*(?:public|protected|private|static|final|abstract|\s)+[\w<>\[\], ?]+\s+([A-Za-z_$][\w$]*)\s*\([^;]*\)\s*(?:throws[^{}]+)?\{"},
        "cs": {"imports": r"(?m)^\s*using\s+([\w.]+)\s*;", "definitions": r"^\s*(?:public|internal|private|protected|static|abstract|sealed|partial|\s)+\s*(?:class|interface|enum|record|struct)\s+([A-Za-z_@]\w*)|^\s*(?:public|internal|private|protected|static|virtual|override|async|\s)+[\w<>\[\], ?]+\s+([A-Za-z_@]\w*)\s*\([^;]*\)\s*(?:=>|\{)"},
        "go": {"imports": r"(?m)^\s*(?:import\s+\(?\s*)[\w.]*\s*\"([^\"]+)\"", "definitions": r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(|^\s*type\s+([A-Za-z_]\w*)\s+(?:struct|interface|[\w.*\[\]])"},
        "rust": {"imports": r"(?m)^\s*use\s+([^;]+);", "definitions": r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*\(|^\s*(?:pub\s+)?(?:struct|enum|trait|type|mod)\s+([A-Za-z_]\w*)"},
    }
    spec = patterns.get(language, {})
    result = {"imports": [], "definitions": []}
    for name, pattern in spec.items():
        found: list[str] = []
        for match in re.finditer(pattern, text, flags=re.MULTILINE):
            found.extend(group for group in match.groups() if group)
        result[name] = sorted(set(found), key=str.casefold)
    return result


def _csv_semantic_changes(before: str, after: str) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]], list[str]]:
    def parse(text: str) -> tuple[list[str], list[dict[str, str]]]:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        columns = reader.fieldnames
        if not columns or any(not name for name in columns) or len(set(columns)) != len(columns):
            raise ValueError("CSV needs a header row with non-empty, unique column names.")
        rows = []
        for index, row in enumerate(reader, start=1):
            if index > 5000:
                raise ValueError("CSV exceeds the 5,000-row semantic analysis limit.")
            if None in row:
                raise ValueError(f"CSV row {index + 1} has more cells than the header.")
            rows.append({name: str(row.get(name) or "") for name in columns})
        return list(columns), rows

    old_cols, old_rows = parse(before)
    new_cols, new_rows = parse(after)
    added: dict[str, list[str]] = {}
    removed: dict[str, list[str]] = {}
    modified: dict[str, list[str]] = {}
    new_columns = sorted(set(new_cols) - set(old_cols), key=str.casefold)
    old_columns = sorted(set(old_cols) - set(new_cols), key=str.casefold)
    if new_columns: added["columns"] = new_columns
    if old_columns: removed["columns"] = old_columns
    shared_columns = [name for name in old_cols if name in set(new_cols)]
    key_col = next((name for name in old_cols if name.casefold() in {"id", "uuid", "key", "slug"} and name in new_cols), None)
    old_keys = [row[key_col] for row in old_rows] if key_col else []
    new_keys = [row[key_col] for row in new_rows] if key_col else []
    if key_col and all(old_keys) and all(new_keys) and len(set(old_keys)) == len(old_keys) and len(set(new_keys)) == len(new_keys):
        old_map = {row[key_col]: row for row in old_rows}
        new_map = {row[key_col]: row for row in new_rows}
        add_keys = sorted(set(new_map) - set(old_map))
        remove_keys = sorted(set(old_map) - set(new_map))
        if add_keys: added["rows"] = [f"{key_col}={value}" for value in add_keys]
        if remove_keys: removed["rows"] = [f"{key_col}={value}" for value in remove_keys]
        cell_changes = []
        for row_key in sorted(set(old_map) & set(new_map)):
            for name in shared_columns:
                old_value, new_value = old_map[row_key].get(name, ""), new_map[row_key].get(name, "")
                if old_value != new_value:
                    cell_changes.append(f"{key_col}={row_key}, {name}: {old_value!r} -> {new_value!r}")
        if cell_changes: modified["cells"] = cell_changes
        warnings = [f"CSV rows matched by unique '{key_col}' values; cell comparisons cover columns present in both versions."]
    else:
        def signature(row: dict[str, str]) -> str:
            return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        old_count, new_count = Counter(map(signature, old_rows)), Counter(map(signature, new_rows))
        added_rows: list[str] = []
        removed_rows: list[str] = []
        for item in sorted(set(old_count) | set(new_count)):
            delta = new_count[item] - old_count[item]
            if delta > 0: added_rows.extend([item] * delta)
            if delta < 0: removed_rows.extend([item] * (-delta))
        if added_rows: added["rows"] = added_rows
        if removed_rows: removed["rows"] = removed_rows
        warnings = ["No unique id/uuid/key/slug column was detected; each edited row appears as one removed row plus one added row."]
    return added, removed, modified, warnings


def _language(path: str) -> str:
    suffix = PurePosixPath(path).suffix.casefold()
    if suffix == ".py": return "python"
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}: return "js"
    if suffix in {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"}: return "c"
    if suffix == ".java": return "java"
    if suffix in {".cs", ".xaml.cs"}: return "cs"
    if suffix == ".go": return "go"
    if suffix == ".rs": return "rust"
    if suffix == ".json": return "json"
    if suffix == ".csv": return "csv"
    return "text"


def analyze_semantic_diff(path: str, before: str, after: str) -> dict[str, Any]:
    """Return structural changes where supported and a bounded unified diff summary."""
    before = before[:MAX_SEMANTIC_CHARS]
    after = after[:MAX_SEMANTIC_CHARS]
    lang = _language(path)
    result: dict[str, Any] = {"path": path, "language": lang, "confidence": "heuristic", "added": {}, "removed": {}, "modified": {}, "warnings": [], "unified_diff": ""}
    try:
        if lang == "python":
            old, new = _python_symbols(before), _python_symbols(after)
            old_fingerprints, new_fingerprints = _python_fingerprints(before), _python_fingerprints(after)
            result["confidence"] = "Python AST"
            changed_definitions = sorted(name for name in set(old_fingerprints) & set(new_fingerprints) if old_fingerprints[name] != new_fingerprints[name])
            if changed_definitions:
                result["modified"]["definitions"] = changed_definitions
        elif lang in {"json", "csv"}:
            compare = _json_semantic_changes if lang == "json" else _csv_semantic_changes
            added, removed, modified, warnings = compare(before, after)
            result["confidence"] = "JSON structural paths" if lang == "json" else "CSV keyed rows"
            result["added"].update(added)
            result["removed"].update(removed)
            result["modified"].update(modified)
            result["warnings"].extend(warnings)
            old = new = {}
        elif lang in {"js", "c", "java", "cs", "go", "rust"}:
            old, new = _regex_symbols(before, lang), _regex_symbols(after, lang)
            result["warnings"].append("Structural symbols were inferred by regular expressions, not a compiler-grade parser.")
        else:
            old = new = {}
            result["warnings"].append("No structural parser is configured for this file type; showing text diff only.")
        for category in sorted(set(old) | set(new)):
            old_set, new_set = set(old.get(category, [])), set(new.get(category, []))
            if old_set - new_set: result["removed"][category] = sorted(old_set - new_set, key=str.casefold)
            if new_set - old_set: result["added"][category] = sorted(new_set - old_set, key=str.casefold)
    except (SyntaxError, ValueError, RecursionError, re.error, json.JSONDecodeError) as exc:
        result["warnings"].append(f"Structural parsing failed; falling back to text diff: {type(exc).__name__}: {exc}")
    diff = difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="")
    result["unified_diff"] = "\n".join(list(diff)[:4000])[:80_000]
    result["truncated"] = len(before) >= MAX_SEMANTIC_CHARS or len(after) >= MAX_SEMANTIC_CHARS
    return result


def format_semantic_report(report: dict[str, Any]) -> str:
    lines = [f"Semantic change report: {report.get('path', '')}", f"Language: {report.get('language', 'unknown')} · parser confidence: {report.get('confidence', 'unknown')}"]
    for category, label in (("added", "Added"), ("removed", "Removed"), ("modified", "Modified")):
        payload = report.get(category, {})
        if not payload:
            lines.append(f"{label} structural items: none detected")
        else:
            lines.append(label + " structural items:")
            for kind, values in payload.items():
                lines.append(f"  {kind}: " + ", ".join(values[:60]))
    for warning in report.get("warnings", []): lines.append("Warning: " + warning)
    if report.get("truncated"): lines.append("Warning: source excerpt truncated to stay within analysis limits.")
    lines += ["", "Bounded unified diff:", str(report.get("unified_diff", "")) or "(no textual differences detected)"]
    return "\n".join(lines)
