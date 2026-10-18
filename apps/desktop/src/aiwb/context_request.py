"""AIWB_CONTEXT_REQUEST: model asks for files/ranges/symbols (roadmap 1.16.3).

The model has no file-system access. It can only *ask* with a versioned request:

    <<<AIWB_CONTEXT_REQUEST>>>
    {"schema_version": "1.0", "type": "AIWB_CONTEXT_REQUEST", "attempt_id": "att-…",
     "reason": "…", "files": [{"path": "src/a.py", "mode": "range",
     "ranges": [{"start_line": 10, "end_line": 40}], "required": true, "reason": "…"}],
     "questions": ["…"]}
    <<<AIWB_END_CONTEXT_REQUEST>>>

Workbench validates every item against the project (path safety supplied by the
host, sensitive files, existence, range bounds, Python symbols via ``ast``),
then prepares a context pack — inline text for small requests or a ZIP with a
manifest (path, mode, lines, SHA-256). Preparing is **not** sending: the user
pastes/attaches it in the chat. Nothing is written to the project.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = "1.0"
BLOCK_RE = re.compile(r"(?s)<<<AIWB_CONTEXT_REQUEST>>>\s*(.*?)\s*<<<AIWB_END_CONTEXT_REQUEST>>>")
MODES = ("full_file", "range", "symbol")
MAX_ITEMS = 30
MAX_RANGE_LINES = 500
MAX_FILE_BYTES = 1_000_000
INLINE_LIMIT_CHARS = 60_000
FREE_TEXT_HINT = re.compile(
    r"(?i)\b(?:please\s+)?(?:send|share|provide|paste|upload|attach)\b[^.\n]{0,60}?"
    r"(?:file|contents?|code)\b[^.\n]{0,40}?[`'\"]?([\w./\\-]+\.[A-Za-z0-9]{1,8})[`'\"]?")


class ContextRequestError(ValueError):
    pass


@dataclass
class RequestedItem:
    path: str
    mode: str
    ranges: list[tuple[int, int]] = field(default_factory=list)
    symbol: str = ""
    required: bool = True
    reason: str = ""


@dataclass
class ContextRequest:
    schema_version: str
    attempt_id: str
    task_id: str
    reason: str
    items: list[RequestedItem]
    questions: list[str]
    base_hashes: dict[str, str] = field(default_factory=dict)  # path -> sha256 the model saw (optional)


@dataclass
class ResolvedItem:
    path: str
    mode: str
    status: str                  # ready | missing | refused_unsafe | refused_sensitive | invalid_range | symbol_not_found | too_large | stale
    detail: str = ""
    lines: str = ""              # "a-b" actually included
    content: str = ""
    sha256: str = ""             # of the whole current file
    required: bool = True
    reason: str = ""

    @property
    def deliverable(self) -> bool:
        return self.status in ("ready", "stale") and bool(self.content)


def _int(v: Any, name: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ContextRequestError(f"{name} must be an integer")
    return v


def find_request(text: str) -> str | None:
    m = BLOCK_RE.search(text or "")
    if m:
        return m.group(1)
    s = (text or "").strip()
    fence = re.match(r"(?s)^`{3,}\s*json\s*\n(.*?)\n`{3,}\s*$", s)
    if fence:
        s = fence.group(1).strip()
    if s.startswith("{") and '"AIWB_CONTEXT_REQUEST"' in s:
        return s
    return None


def parse_request(text: str) -> ContextRequest:
    body = find_request(text)
    if body is None:
        raise ContextRequestError("No AIWB_CONTEXT_REQUEST block found.")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ContextRequestError(f"The context request JSON is invalid: {exc.msg} (line {exc.lineno}).") from None
    if not isinstance(data, dict) or data.get("type") != "AIWB_CONTEXT_REQUEST":
        raise ContextRequestError('The request must be an object with "type": "AIWB_CONTEXT_REQUEST".')
    version = str(data.get("schema_version", ""))
    if not version.startswith("1."):
        raise ContextRequestError(f"Unsupported context request schema_version {version!r}; expected 1.x.")
    files = data.get("files", [])
    if not isinstance(files, list) or len(files) > MAX_ITEMS:
        raise ContextRequestError(f"files must be a list of at most {MAX_ITEMS} items.")
    items: list[RequestedItem] = []
    for i, f in enumerate(files):
        if not isinstance(f, dict) or not isinstance(f.get("path"), str) or not f["path"].strip():
            raise ContextRequestError(f"files[{i}] needs a path.")
        mode = f.get("mode", "full_file")
        if mode not in MODES:
            raise ContextRequestError(f"files[{i}].mode must be one of {', '.join(MODES)}.")
        ranges: list[tuple[int, int]] = []
        if mode == "range":
            raw_ranges = f.get("ranges")
            if not isinstance(raw_ranges, list) or not raw_ranges:
                raise ContextRequestError(f"files[{i}] uses mode=range but has no ranges.")
            for r in raw_ranges[:10]:
                if not isinstance(r, dict):
                    raise ContextRequestError(f"files[{i}].ranges entries must be objects.")
                ranges.append((_int(r.get("start_line"), "start_line"), _int(r.get("end_line"), "end_line")))
        symbol = str(f.get("symbol", "")).strip() if mode == "symbol" else ""
        if mode == "symbol" and not re.fullmatch(r"[A-Za-z_][\w.]{0,120}", symbol):
            raise ContextRequestError(f"files[{i}] uses mode=symbol but the symbol name is missing or invalid.")
        items.append(RequestedItem(f["path"].strip().replace("\\", "/"), mode, ranges, symbol,
                                   bool(f.get("required", True)), str(f.get("reason", ""))[:500]))
    questions = [str(q)[:500] for q in data.get("questions", []) if isinstance(q, (str, int, float))][:20]
    if not items and not questions:
        raise ContextRequestError("The context request asks for nothing (no files and no questions).")
    hashes = {str(k): str(v).lower() for k, v in (data.get("base_hashes") or {}).items()} if isinstance(data.get("base_hashes"), dict) else {}
    return ContextRequest(version, str(data.get("attempt_id", ""))[:80], str(data.get("task_id", ""))[:120],
                          str(data.get("reason", ""))[:1000], items, questions, hashes)


def free_text_hints(text: str) -> list[str]:
    """Paths a plain-text answer *seems* to ask for. Suggestions only, never acted on automatically."""
    seen: list[str] = []
    for m in FREE_TEXT_HINT.finditer(text or ""):
        p = m.group(1).replace("\\", "/")
        if p not in seen:
            seen.append(p)
    return seen[:10]


def python_symbol_lines(source: str, symbol: str) -> tuple[int, int] | None:
    """1-based inclusive line span of ``Class``, ``func`` or ``Class.method`` (incl. decorators)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    parts = symbol.split(".")
    nodes: list[ast.AST] = list(tree.body)
    found = None
    for depth, name in enumerate(parts):
        found = next((n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                      and n.name == name), None)
        if found is None:
            return None
        nodes = list(getattr(found, "body", []))
    start = min([found.lineno] + [d.lineno for d in getattr(found, "decorator_list", [])])
    return start, getattr(found, "end_lineno", found.lineno)


def resolve(req: ContextRequest, root: Path, *, path_problem: Callable[[str], str],
            is_sensitive: Callable[[str], bool], allow_sensitive: set[str] | None = None) -> list[ResolvedItem]:
    allow_sensitive = allow_sensitive or set()
    out: list[ResolvedItem] = []
    for it in req.items:
        r = ResolvedItem(it.path, it.mode, "ready", required=it.required, reason=it.reason)
        out.append(r)
        problem = path_problem(it.path)
        if problem:
            r.status, r.detail = "refused_unsafe", problem
            continue
        if is_sensitive(it.path) and it.path not in allow_sensitive:
            r.status, r.detail = "refused_sensitive", "sensitive file (secrets/keys/.env); needs an explicit separate decision"
            continue
        target = root / it.path
        if not target.is_file():
            r.status, r.detail = "missing", "file does not exist in the project"
            continue
        data = target.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            r.status, r.detail = "too_large", f"{len(data):,} bytes; request a range or symbol instead"
            continue
        r.sha256 = hashlib.sha256(data).hexdigest()
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if it.mode == "full_file":
            spans = [(1, max(1, len(lines)))]
        elif it.mode == "range":
            spans = []
            for a, b in it.ranges:
                if a < 1 or b < a or a > len(lines) or b - a + 1 > MAX_RANGE_LINES:
                    r.status = "invalid_range"
                    r.detail = f"lines {a}-{b} invalid (file has {len(lines)} lines; max {MAX_RANGE_LINES} per range)"
                    break
                spans.append((a, min(b, len(lines))))
            if r.status != "ready":
                continue
        else:
            span = python_symbol_lines(text, it.symbol) if it.path.endswith(".py") else None
            if span is None:
                r.status = "symbol_not_found"
                r.detail = (f"symbol {it.symbol!r} not found" if it.path.endswith(".py")
                            else "symbol extraction is only reliable for Python; request a line range instead")
                continue
            spans = [span]
        chunks = []
        for a, b in spans:
            chunks.append("\n".join(f"{n}: {lines[n - 1]}" for n in range(a, b + 1)) if lines else "")
        r.content = "\n…\n".join(chunks)
        r.lines = ", ".join(f"{a}-{b}" for a, b in spans)
        seen = req.base_hashes.get(it.path)
        if seen and seen != r.sha256:
            r.status, r.detail = "stale", "file changed since the model saw it; the CURRENT version is prepared"
    return out


def pack_inline(req: ContextRequest, items: list[ResolvedItem], *, attempt_line: str = "") -> str:
    lines = []
    if attempt_line:
        lines += [attempt_line, ""]
    lines += ["# Context requested by you (prepared by AI Workbench from the local project)",
              "Line numbers are 1-based and part of the listing, not of the file."]
    if req.reason:
        lines.append("Your reason: " + req.reason)
    for r in items:
        if r.deliverable:
            lines += ["", f"## {r.path} ({r.mode}, lines {r.lines}, sha256 {r.sha256[:16]}…)"
                      + (" — NOTE: " + r.detail if r.status == "stale" else ""), "```", r.content, "```"]
    missing = [r for r in items if not r.deliverable]
    if missing:
        lines += ["", "## Not provided"]
        lines += [f"- {r.path}: {r.status} — {r.detail}" for r in missing]
    if req.questions:
        lines += ["", "## Your questions (answers from the user follow, if any)"] + [f"- {q}" for q in req.questions]
    lines += ["", "Continue the task using only this context. If something essential is still missing, send another "
                  "AIWB_CONTEXT_REQUEST. Do not claim anything was run or tested."]
    return "\n".join(lines)


def suggest_delivery(items: list[ResolvedItem]) -> str:
    total = sum(len(r.content) for r in items if r.deliverable)
    files = sum(1 for r in items if r.deliverable and r.mode == "full_file")
    return "zip" if total > INLINE_LIMIT_CHARS or files > 3 else "inline"


def pack_zip(req: ContextRequest, items: list[ResolvedItem], root: Path) -> bytes:
    """ZIP with the requested slices under ``context/`` plus ``AIWB_CONTEXT_MANIFEST.json``."""
    buf = io.BytesIO()
    manifest = {"schema_version": SCHEMA_VERSION, "type": "AIWB_CONTEXT_PACK",
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "attempt_id": req.attempt_id, "reason": req.reason, "questions": req.questions, "files": []}
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for r in items:
            entry = {k: v for k, v in asdict(r).items() if k != "content"}
            if r.deliverable:
                if r.mode == "full_file":
                    data = (root / r.path).read_bytes()
                    name = "context/" + r.path
                else:
                    data = r.content.encode("utf-8")
                    name = "context/" + r.path + f".lines-{r.lines.replace(', ', '_')}.txt"
                zf.writestr(name, data)
                entry["zip_entry"] = name
            manifest["files"].append(entry)
        zf.writestr("AIWB_CONTEXT_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return buf.getvalue()


CAPABILITY_LINE = (
    "- Context Request (AIWB_CONTEXT_REQUEST v1.0): you cannot read local files. To ask for context, answer ONLY with "
    "<<<AIWB_CONTEXT_REQUEST>>> {JSON} <<<AIWB_END_CONTEXT_REQUEST>>>, JSON fields: schema_version \"1.0\", type "
    "\"AIWB_CONTEXT_REQUEST\", attempt_id (from the AIWB_ATTEMPT_ID line), reason, files[] {path, mode "
    "full_file|range|symbol, ranges[{start_line,end_line}] (≤500 lines each), symbol (Python only: func, Class or "
    "Class.method), required, reason}, questions[]. Workbench validates paths, refuses unsafe paths and sensitive "
    "files (.env, keys) unless the user decides otherwise, reports missing files, and prepares an inline listing or "
    "ZIP context pack that the USER pastes/attaches; preparing is not sending."
)
