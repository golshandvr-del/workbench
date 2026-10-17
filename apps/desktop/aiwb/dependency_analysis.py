"""Conservative static dependency mapping for common application languages.

Analysis is path/import heuristic only: no project code is executed, and unresolved
references remain explicit rather than being presented as a complete build graph.
"""
from __future__ import annotations
import ast
import os
import re
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SKIP_DIRS = {".git", ".workbench", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", "bin", "obj"}
MAX_FILES = 3000
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 24 * 1024 * 1024
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".java", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".kts", ".scala"}


def _module_key(path: str) -> str:
    stem = path.replace("\\", "/")
    suffix = PurePosixPath(stem).suffix.casefold()
    if suffix == ".py" and PurePosixPath(stem).name == "__init__.py": stem = str(PurePosixPath(stem).parent)
    else: stem = str(PurePosixPath(stem).with_suffix(""))
    return stem.strip("./").replace("/", ".").casefold()


def _python_imports(path: str, text: str) -> list[str]:
    try: tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError): return []
    current = _module_key(path)
    package = current.split(".")[:-1]
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): result.extend(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                keep = max(0, len(package) - node.level + 1)
                base = package[:keep]
                module_name = ".".join(base + ([module] if module else []))
            else: module_name = module
            result.append(module_name.casefold())
            result.extend((module_name + "." + alias.name).casefold() for alias in node.names if alias.name != "*")
    return result


def _references(path: str, text: str) -> list[str]:
    suffix = PurePosixPath(path).suffix.casefold()
    refs: list[str] = []
    if suffix == ".py": return _python_imports(path, text)
    patterns: list[str] = []
    if suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}:
        patterns = [r"(?:from\s*|import\s*\(|require\s*\()\s*['\"]([^'\"]+)['\"]"]
    elif suffix in {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"}:
        patterns = [r"(?m)^\s*#\s*include\s*[\"<]([^\">]+)[\">]"]
    elif suffix in {".java", ".kt", ".kts", ".scala"}:
        patterns = [r"(?m)^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;?"]
    elif suffix == ".cs":
        patterns = [r"(?m)^\s*using\s+([\w.]+)\s*;"]
    elif suffix == ".go":
        patterns = [r"(?m)^\s*import\s+(?:\w+\s+)?\"([^\"]+)\""]
    elif suffix == ".rs":
        patterns = [r"(?m)^\s*mod\s+([A-Za-z_]\w*)\s*;", r"(?m)^\s*use\s+([A-Za-z0-9_:]+)"]
    elif suffix in {".rb", ".php"}:
        patterns = [r"(?m)^\s*(?:require|require_once|include|include_once)\s*\(?\s*['\"]([^'\"]+)['\"]"]
    for pattern in patterns:
        refs.extend(match.group(1).replace("\\", "/").casefold() for match in re.finditer(pattern, text))
    return refs


def scan_dependency_graph(root: Path, *, max_files: int = MAX_FILES) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    files: dict[str, str] = {}
    total = 0
    truncated: list[str] = []
    for current, dirs, names in os.walk(root, followlinks=False):
        base = Path(current)
        dirs[:] = sorted([d for d in dirs if d.casefold() not in SKIP_DIRS and not (base / d).is_symlink()], key=str.casefold)
        for name in sorted(names, key=str.casefold):
            path = base / name
            if path.is_symlink() or path.suffix.casefold() not in SOURCE_SUFFIXES: continue
            try:
                size = path.stat().st_size
                rel = path.relative_to(root).as_posix()
                if size > MAX_FILE_BYTES or total + size > MAX_TOTAL_BYTES:
                    truncated.append(rel); continue
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError, ValueError):
                continue
            files[rel] = text; total += size
            if len(files) >= min(max_files, MAX_FILES):
                truncated.append("<file-count-limit>"); break
        if len(files) >= min(max_files, MAX_FILES): break
    key_to_paths: dict[str, list[str]] = defaultdict(list)
    basename_to_paths: dict[str, list[str]] = defaultdict(list)
    for rel in files:
        key_to_paths[_module_key(rel)].append(rel)
        basename_to_paths[PurePosixPath(rel).name.casefold()].append(rel)
    forward: dict[str, set[str]] = {path: set() for path in files}
    unresolved: dict[str, list[str]] = defaultdict(list)
    for rel, text in files.items():
        suffix = PurePosixPath(rel).suffix.casefold()
        for ref in _references(rel, text):
            ref = ref.strip().strip(".").replace("\\", "/")
            possible: list[str] = []
            if suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".rb", ".php"}:
                candidate = (PurePosixPath(rel).parent / ref)
                candidate_str = str(candidate).replace("\\", "/")
                possible.extend([candidate_str, candidate_str + ".py", candidate_str + ".js", candidate_str + ".jsx", candidate_str + ".ts", candidate_str + ".tsx", candidate_str + ".c", candidate_str + ".h", candidate_str + ".cpp"])
                possible.extend(str(candidate / index) for index in ("index.js", "index.ts", "index.tsx"))
                matches = [p for p in files if p in possible]
            else:
                key = ref.replace("::", ".").casefold()
                matches = key_to_paths.get(key, [])
                if not matches:
                    tail = key.rsplit(".", 1)[-1]
                    matches = [p for p in files if PurePosixPath(p).stem.casefold() == tail or PurePosixPath(p).name.casefold() == tail]
            matches = [p for p in matches if p != rel]
            if matches:
                forward[rel].update(matches)
            elif ref and not ref.startswith(("http:", "https:", "node:", "react", "vue", "angular", "std", "system", "java.", "kotlin.", "github.com/", "golang.org/")):
                unresolved[rel].append(ref)
    reverse: dict[str, set[str]] = defaultdict(set)
    for source, targets in forward.items():
        for target in targets: reverse[target].add(source)
    return {"root": str(root), "files_scanned": len(files), "bytes_scanned": total,
            "forward": {k: sorted(v, key=str.casefold) for k, v in forward.items()},
            "reverse": {k: sorted(v, key=str.casefold) for k, v in reverse.items()},
            "unresolved": {k: sorted(set(v), key=str.casefold)[:100] for k, v in unresolved.items() if v},
            "truncated": truncated[:200], "coverage_note": "Static import/path heuristics are incomplete; dynamic imports, generated code, reflection, external packages, framework conventions, and build-system semantics may be missed."}


def analyze_project_impact(root: Path, changed_paths: Iterable[str]) -> dict[str, Any]:
    graph = scan_dependency_graph(root)
    changed = sorted({str(p).replace("\\", "/").strip("/") for p in changed_paths if str(p).strip()}, key=str.casefold)
    reverse = graph["reverse"]
    direct: set[str] = set()
    for path in changed: direct.update(reverse.get(path, []))
    # Reverse transitive closure: files that import changed files or import a file
    # that itself depends on a changed file.
    transitive: set[str] = set()
    queue = deque(direct)
    while queue:
        item = queue.popleft()
        if item in transitive or item in changed: continue
        transitive.add(item)
        for parent in reverse.get(item, []):
            if parent not in transitive: queue.append(parent)
    return {"changed_paths": changed, "direct_dependents": sorted(direct, key=str.casefold),
            "transitive_dependents": sorted(transitive - direct, key=str.casefold),
            "unresolved_references_in_changed_files": {p: graph["unresolved"].get(p, []) for p in changed if graph["unresolved"].get(p)},
            "files_scanned": graph["files_scanned"], "truncated": graph["truncated"], "coverage_note": graph["coverage_note"]}


def format_impact_report(report: dict[str, Any]) -> str:
    lines = ["Static dependency / change-impact analysis", f"Changed paths: {', '.join(report.get('changed_paths', [])) or '(none)'}",
             f"Source files scanned: {report.get('files_scanned', 0)}", "", "Direct dependents:"]
    lines.extend(f"  • {path}" for path in report.get("direct_dependents", []))
    if not report.get("direct_dependents"): lines.append("  (none resolved by static analysis)")
    lines += ["", "Transitive dependents:"]
    lines.extend(f"  • {path}" for path in report.get("transitive_dependents", []))
    if not report.get("transitive_dependents"): lines.append("  (none resolved by static analysis)")
    unresolved = report.get("unresolved_references_in_changed_files", {})
    if unresolved:
        lines += ["", "Unresolved references in changed files:"]
        for path, refs in unresolved.items(): lines.append(f"  {path}: {', '.join(refs[:30])}")
    if report.get("truncated"): lines += ["", "Scan limits affected these files/items: " + ", ".join(report["truncated"][:30])]
    lines += ["", "Limitations: " + str(report.get("coverage_note", "")), "", "This report is advisory. It does not prove compilation or runtime correctness."]
    return "\n".join(lines)
