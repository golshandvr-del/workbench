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
FOLDER_MODE = "folder"         # 5.12.0: "src/pkg/" → every file under it (expanded by resolve, capped)
MAX_FOLDER_FILES = 20
# 5.12.0 (owner audit B2): what real chats write instead of ``files``
FILE_LIST_KEYS = ("files", "required_files", "requested_files", "files_needed", "needed_files", "context_files",
                  "file_requests", "requests", "paths", "file_paths", "files_requested")
PATH_KEYS = ("path", "file", "filename", "file_path", "name")
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
    fixes: list[str] = field(default_factory=list)              # 5.12.0: what the forgiving reader corrected
    handoff_id: str = ""


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
    """The JSON body of a context request, or ``None``. Copy damage (5.12.0) is repaired first."""
    m = BLOCK_RE.search(text or "")
    if m:
        return m.group(1)
    from .intake.normalize import normalize
    t = normalize(text or "").text
    m = BLOCK_RE.search(t)
    if m:
        return m.group(1)
    m = re.search(r"(?s)<<<AIWB_CONTEXT_REQUEST>>>\s*(\{.*\})", t)   # end marker lost (cut off / copy)
    if m:
        return m.group(1)
    s = t.strip()
    fence = re.match(r"(?s)^`{3,}\s*(?:json)?\s*\n(.*?)\n`{3,}\s*$", s)
    if fence:
        s = fence.group(1).strip()
    if s.startswith("{") and '"AIWB_CONTEXT_REQUEST"' in s:
        return s
    return None


def _loads(body: str, fixes: list[str]) -> Any:
    body = body.strip()
    fence = re.match(r"(?s)^`{3,}\s*(?:json)?\s*\n(.*?)\n`{3,}$", body)
    if fence:
        body = fence.group(1)
    try:
        return json.loads(body)
    except json.JSONDecodeError as first:
        from .intake.normalize import normalize_json_text
        n = normalize_json_text(body)
        try:
            data = json.loads(n.text)
        except json.JSONDecodeError:
            raise ContextRequestError(f"The context request JSON is invalid: {first.msg} (line {first.lineno}).") from None
        fixes.append("JSON repaired (" + ", ".join(n.fixes[:4]) + ")")
        return data


def _item(raw: Any, i: int, fixes: list[str]) -> RequestedItem:
    """One requested file. Forgiving (5.12.0): a bare string, ``file``/``filename`` for ``path``, a folder path."""
    if isinstance(raw, str):
        raw = {"path": raw}
        fixes.append(f"files[{i}] was a plain path → full file")
    if not isinstance(raw, dict):
        raise ContextRequestError(f"files[{i}] must be a path or an object with a path.")
    key = next((k for k in PATH_KEYS if isinstance(raw.get(k), str) and raw[k].strip()), "")
    if not key:
        raise ContextRequestError(f"files[{i}] needs a path.")
    if key != "path":
        fixes.append(f"files[{i}].{key} read as path")
    path = raw[key].strip().strip("`'\"").replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    mode = str(raw.get("mode") or "").strip().lower().replace("-", "_").replace(" ", "_")
    mode = {"full": "full_file", "file": "full_file", "whole": "full_file", "whole_file": "full_file",
            "complete": "full_file", "lines": "range", "line_range": "range", "ranges": "range",
            "function": "symbol", "class": "symbol", "directory": FOLDER_MODE, "dir": FOLDER_MODE,
            "listing": FOLDER_MODE}.get(mode, mode)
    if path.endswith("/") or mode == FOLDER_MODE:
        if mode and mode != FOLDER_MODE:
            fixes.append(f"files[{i}] {path} is a folder → every file in it")
        else:
            fixes.append(f"files[{i}] {path} is a folder → every file in it (max {MAX_FOLDER_FILES})")
        return RequestedItem(path.rstrip("/") + "/", FOLDER_MODE, [], "", bool(raw.get("required", True)),
                             str(raw.get("reason", ""))[:500])
    if not mode:
        mode = "range" if raw.get("ranges") or raw.get("start_line") else ("symbol" if raw.get("symbol") else "full_file")
    if mode not in MODES:
        fixes.append(f"files[{i}].mode {raw.get('mode')!r} unknown → full file")
        mode = "full_file"
    ranges: list[tuple[int, int]] = []
    if mode == "range":
        raw_ranges = raw.get("ranges")
        if not raw_ranges and raw.get("start_line"):
            raw_ranges = [{"start_line": raw.get("start_line"), "end_line": raw.get("end_line", raw.get("start_line"))}]
        if not isinstance(raw_ranges, list) or not raw_ranges:
            fixes.append(f"files[{i}] asked for a range without lines → full file")
            mode = "full_file"
        else:
            for r in raw_ranges[:10]:
                if isinstance(r, (list, tuple)) and len(r) == 2:
                    r = {"start_line": r[0], "end_line": r[1]}
                if not isinstance(r, dict):
                    raise ContextRequestError(f"files[{i}].ranges entries must be objects.")
                a, b = r.get("start_line", r.get("start")), r.get("end_line", r.get("end"))
                if isinstance(a, str) and a.isdigit():
                    a = int(a)
                if isinstance(b, str) and b.isdigit():
                    b = int(b)
                ranges.append((_int(a, "start_line"), _int(b, "end_line")))
    symbol = str(raw.get("symbol", "")).strip() if mode == "symbol" else ""
    if mode == "symbol" and not re.fullmatch(r"[A-Za-z_][\w.]{0,120}", symbol):
        fixes.append(f"files[{i}] asked for a symbol without a valid name → full file")
        mode, symbol = "full_file", ""
    return RequestedItem(path, mode, ranges, symbol, bool(raw.get("required", True)), str(raw.get("reason", ""))[:500])


def parse_request(text: str) -> ContextRequest:
    """Read a context request. Forgiving like the 5.10.0 charter reader (5.12.0, owner audit B2): ``type`` may be
    missing when the markers are there, the file list may be called ``required_files`` & co., items may be plain
    paths or folders. Every correction is listed in ``fixes``; only a request that asks for nothing is refused."""
    body = find_request(text)
    if body is None:
        raise ContextRequestError("No AIWB_CONTEXT_REQUEST block found.")
    fixes: list[str] = []
    data = _loads(body, fixes)
    if isinstance(data, list):
        data = {"files": data}
        fixes.append("a bare list was read as files")
    if not isinstance(data, dict):
        raise ContextRequestError("The context request must be a JSON object.")
    if data.get("type") != "AIWB_CONTEXT_REQUEST":
        if data.get("type") not in (None, ""):
            fixes.append(f"type {data.get('type')!r} → AIWB_CONTEXT_REQUEST")
        else:
            fixes.append('"type" was missing (the markers say what it is)')
    version = str(data.get("schema_version", "1.0") or "1.0")
    if not version.startswith("1"):
        raise ContextRequestError(f"Unsupported context request schema_version {version!r}; expected 1.x.")
    if version in ("1", "1.0.0"):
        fixes.append(f"schema_version {data.get('schema_version')!r} → \"1.0\"")
    key = next((k for k in FILE_LIST_KEYS if k in data and data[k] not in (None, "")), "files")
    files = data.get(key, [])
    if key != "files":
        fixes.append(f'"{key}" read as "files"')
    if isinstance(files, (str, dict)):
        files = [files]
        fixes.append(f'"{key}" was a single item → list')
    if not isinstance(files, list):
        raise ContextRequestError(f'"{key}" must be a list of paths.')
    if len(files) > MAX_ITEMS:
        fixes.append(f"{len(files)} files asked → the first {MAX_ITEMS}")
        files = files[:MAX_ITEMS]
    items = [_item(f, i, fixes) for i, f in enumerate(files)]
    raw_q = data.get("questions", [])
    if isinstance(raw_q, str):
        raw_q = [raw_q]
    questions = [str(q)[:500] for q in raw_q if isinstance(q, (str, int, float)) and str(q).strip()][:20]
    if not items and not questions:
        raise ContextRequestError("The context request asks for nothing (no files and no questions).")
    hashes = {str(k): str(v).lower() for k, v in (data.get("base_hashes") or {}).items()} if isinstance(data.get("base_hashes"), dict) else {}
    attempt = str(data.get("attempt_id", "") or "")
    if not attempt:
        m = re.search(r"(?m)^\s*AIWB_ATTEMPT_ID:\s*(att-[\w-]+)", text or "")
        if m:
            attempt = m.group(1)
            fixes.append("attempt_id taken from the AIWB_ATTEMPT_ID line")
    return ContextRequest("1.0" if version in ("1", "1.0.0") else version, attempt[:80],
                          str(data.get("task_id", ""))[:120], str(data.get("reason", "") or data.get("requested_action", ""))[:1000],
                          items, questions, hashes, fixes, str(data.get("handoff_id", ""))[:40])


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


def _structurally_unsafe(p: str) -> bool:
    parts = p.split("/")
    return (not p or p.startswith("/") or ":" in p or ".." in parts or "\x00" in p)


def resolve(req: ContextRequest, root: Path, *, path_problem: Callable[[str], str],
            is_sensitive: Callable[[str], bool], allow_sensitive: set[str] | None = None) -> list[ResolvedItem]:
    allow_sensitive = allow_sensitive or set()
    out: list[ResolvedItem] = []
    for it in req.items:
        r = ResolvedItem(it.path, it.mode, "ready", required=it.required, reason=it.reason)
        out.append(r)
        if _structurally_unsafe(it.path):
            r.status, r.detail = "refused_unsafe", "path must be relative, inside the project, without '..'"
            continue
        if is_sensitive(it.path):
            if it.path not in allow_sensitive:
                r.status, r.detail = "refused_sensitive", "sensitive file (secrets/keys/.env); needs an explicit separate decision"
                continue
        else:
            problem = path_problem(it.path)
            if problem:
                r.status, r.detail = "refused_unsafe", problem
                continue
        try:
            if not (root / it.path).resolve().is_relative_to(root.resolve()):
                r.status, r.detail = "refused_unsafe", "path resolves outside the project"
                continue
        except OSError:
            r.status, r.detail = "refused_unsafe", "path cannot be resolved"
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
