"""Files from whatever a chat model returned (roadmap 5.10.0, audit A13).

The guided loop (stage → smart check → accept → write) reads one canonical shape: ``<<<AIWB_FILE path="…">>>`` blocks
plus an optional ``<<<AIWB_HANDOFF>>>`` manifest. Models — and the user's choice in the New Project wizard — deliver
files in other shapes too. This module turns each of them into that canonical text, so everything after it (scope
check, copy-damage check, preview, backup, restore) stays one code path:

* **AIWB blocks** — as they are; escaped / HTML-entity / smart-quoted markers are repaired first (chat copy damage);
* **Markdown** — a code fence labelled by the line before it (``**src/a.py**``, ``### src/a.py``, `` `src/a.py` ``,
  ``File: src/a.py``, "Here is `src/a.py`:"), by the fence info (```` ```python title="src/a.py" ````, ```` ```src/a.py ````)
  or by a first-line comment (``# file: src/a.py``). An unlabelled fence is never given a guessed name;
* **Strict JSON** — ``{"files": [{"path", "content"}], "handoff": {…}}`` (also ``workbench-v1`` objects, ``files`` as a
  ``{path: content}`` dictionary, ``content`` as a list of lines, a manifest given at the top level);
* **ZIP** — a downloaded archive (``Load ZIP…``), read in memory with the limits of 1.x: at most 12 MB, 100 files,
  512 KB per file, 8 MB in total, text files only, no unsafe paths, ``AIWB_HANDOFF.json`` as the manifest.

Every repair or skipped item is returned as a short line for the user (a fix is never hidden). Pure: no disk writes,
no Tk.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any

MAX_FILES = 100
MAX_FILE = 512 * 1024
MAX_TOTAL = 8 * 1024 * 1024
MAX_ZIP = 12 * 1024 * 1024

FILE_HEAD = re.compile(r'(?m)^\s*<<<AIWB_FILE\s+(.*?)\s*>>>\s*$')
MAN_RE = re.compile(r"(?s)<<<AIWB_HANDOFF>>>\s*(.*?)\s*<<<AIWB_END_HANDOFF>>>")
ATTEMPT_RE = re.compile(r"(?m)^\s*\**AIWB_ATTEMPT_ID\**:\s*\**\s*([A-Za-z0-9_.:-]+)")
_FENCE_OPEN = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([^`\n]*)$")
_KNOWN_NO_EXT = {"Dockerfile", "Makefile", "LICENSE", "NOTICE", "Procfile", "Justfile", "Gemfile", "Rakefile",
                 "README", "CHANGELOG", "CODEOWNERS", ".gitignore", ".gitattributes", ".editorconfig", ".env.example",
                 ".dockerignore", ".npmrc", ".prettierrc", ".eslintrc"}
_MANIFEST_KEYS = ("schema_version", "handoff_id", "task_id", "task_revision", "attempt_id", "outcome", "summary",
                  "completed_items", "unresolved_items", "assumptions", "decision_requests", "validation_claims",
                  "recommended_next_action")
_ZIP_NOISE = ("__MACOSX/", ".DS_Store", "Thumbs.db", "desktop.ini")
_ZIP_MANIFESTS = ("AIWB_HANDOFF.json", "aiwb_handoff.json", "handoff.json", "AIWB_RESPONSE.json", "manifest.json")
_CONTENT_KEYS = ("content", "body", "code", "text", "source", "contents", "data")
_PATH_KEYS = ("path", "file", "filename", "file_path", "name", "relative_path")

FORMAT_LABELS = {"aiwb": "AIWB file blocks", "markdown": "Markdown code blocks", "json": "Strict JSON",
                 "zip": "ZIP archive", "": "no files"}


@dataclass
class Extracted:
    files: list[dict[str, str]] = field(default_factory=list)   # [{"path", "content"}]
    format: str = ""                                             # aiwb | markdown | json | zip | ""
    manifest: dict[str, Any] | None = None
    attempt_id: str = ""
    fixes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def label(self) -> str:
        return FORMAT_LABELS.get(self.format, self.format)


# --------------------------------------------------------------------------- paths

def clean_path(value: str) -> str:
    """A relative project path from a label, or "" when it does not look like one (never guessed from code)."""
    v = (value or "").strip()
    v = re.sub(r"\s+(?:—|–|-{1,2})\s+.*$", "", v).strip()            # "src/a.py — the game loop"
    v = re.sub(r"\s+\((?:new|updated|modified|created|changed|full|complete)[^)]*\)$", "", v, flags=re.I).strip()
    v = v.strip("`'\"*_ :").strip()
    v = v.replace("\\", "/")
    while v.startswith("./"):
        v = v[2:]
    if not v or len(v) > 300 or "://" in v or any(c in v for c in "<>|?*\x00\n\t") or " " in v:
        return ""
    base = v.rsplit("/", 1)[-1]
    if not (re.search(r"\.[A-Za-z0-9][A-Za-z0-9_+-]{0,15}$", base) or base in _KNOWN_NO_EXT):
        return ""
    if re.fullmatch(r"\d+(\.\d+)+", base):                               # "1.2.3" is a version, not a file
        return ""
    return v


def safe_path(path: str) -> str:
    """Relative, no ``..``, no drive letter, nothing under ``.git`` / ``.workbench``; "" when unsafe."""
    p = (path or "").strip().replace("\\", "/")
    if not p or p.startswith("/") or re.match(r"^[A-Za-z]:", p) or "\x00" in p:
        return ""
    parts = [x for x in p.split("/") if x not in ("", ".")]
    if not parts or any(x == ".." for x in parts) or parts[0] in (".git", ".workbench"):
        return ""
    return "/".join(parts)


def _label_path(line: str) -> str:
    """The path a Markdown line labels (the line just before a code fence)."""
    s = line.strip()
    if not s or len(s) > 400:
        return ""
    s = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", s)                     # list bullets / numbering
    m = re.match(r"^(?:#{1,6}\s*)?(?:\*\*|__)?\s*(?:file(?:\s*(?:path|name))?|filename|path|new file|updated file|"
                 r"modified file|create|update|contents of|save as|location)\s*(?:\*\*|__)?\s*[:：]\s*(.+?)$", s, re.I)
    if m:
        return clean_path(m.group(1))
    m = re.search(r"[`'\"]([^`'\"\s]+)[`'\"]\s*(?:\((?:[^)]*)\))?\s*[:：]?\s*(?:\*\*)?$", s)
    if m and re.match(r"^(?:here(?:'s| is| are)|below is|code for|contents? of|create|update|and|now|then|finally|"
                      r"next|the file|file|in|for|implementation|updated|new|add)\b", s, re.I):
        p = clean_path(m.group(1))
        if p:
            return p
    h = re.match(r"^#{1,6}\s+(.+?)\s*#*$", s)
    if h:
        s = h.group(1)
    s = re.sub(r"^(?:\*\*|__)(.+?)(?:\*\*|__)\s*[:：]?$", r"\1", s).strip()
    s = re.sub(r"^\d+[.)]\s+", "", s)
    s = s.rstrip(":：").strip()
    if s.startswith("`") and s.endswith("`"):
        s = s.strip("`")
    return clean_path(s)


def _info_path(info: str) -> str:
    """A path in the fence info string: ```python title="src/a.py"``` · ```src/a.py``` · ```python:src/a.py```."""
    i = (info or "").strip()
    if not i:
        return ""
    m = re.search(r"""(?:title|file|filename|path)\s*=\s*["']?([^"'\s]+)""", i, re.I)
    if m:
        return clean_path(m.group(1))
    m = re.match(r"^[A-Za-z0-9_+#-]+[:\s]+(\S+)$", i)
    if m and ("/" in m.group(1) or "." in m.group(1)):
        return clean_path(m.group(1))
    if "/" in i or re.search(r"\.[A-Za-z0-9]{1,8}$", i):
        return clean_path(i)
    return ""


def _comment_path(first: str) -> str:
    """``# file: src/a.py`` / ``// src/app.ts`` / ``<!-- index.html -->`` as the first code line."""
    s = first.strip()
    m = re.match(r"^(?:#|//|--|;|/\*|<!--)\s*(?:(?:file(?:\s*(?:path|name))?|path|filename)\s*[:：]\s*)?(\S+?)\s*(?:\*/|-->)?$",
                 s, re.I)
    if not m:
        return ""
    p = clean_path(m.group(1))
    labelled = re.search(r"(?i)\b(?:file|path|filename)\s*[:：]", s)
    return p if p and (labelled or "/" in p) else ""


# --------------------------------------------------------------------------- AIWB blocks

def _aiwb_files(text: str) -> tuple[list[dict[str, str]], bool]:
    from ..v2.diagnose import parse_files
    files, open_last = parse_files(text)
    return [{"path": f["path"], "content": f["body"]} for f in files], open_last


# --------------------------------------------------------------------------- Markdown

def markdown_files(text: str) -> tuple[list[dict[str, str]], list[str], bool]:
    """``(files, fixes, truncated)`` from labelled Markdown code fences (CommonMark fence rules)."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    files: list[dict[str, str]] = []
    fixes: list[str] = []
    unlabelled = 0
    truncated = False
    i = 0
    while i < len(lines):
        m = _FENCE_OPEN.match(lines[i])
        if not m or (m.group(2)[0] == "`" and "`" in m.group(3)):
            i += 1
            continue
        indent, fence, info = m.group(1), m.group(2), m.group(3).strip()
        j = i + 1
        body: list[str] = []
        closed = False
        while j < len(lines):
            c = re.match(r"^\s*(`{3,}|~{3,})\s*$", lines[j])
            if c and c.group(1)[0] == fence[0] and len(c.group(1)) >= len(fence):
                closed = True
                break
            body.append(lines[j][len(indent):] if indent and lines[j].startswith(indent) else lines[j])
            j += 1
        # the label: the fence info, else the nearest non-empty line before the fence (two at most), else line 1
        path = _info_path(info)
        if not path:
            k, seen = i - 1, 0
            while k >= 0 and seen < 2:
                if lines[k].strip():
                    seen += 1
                    if re.match(r"^\s*(?:language|lang|file type)\s*[:：]", lines[k], re.I):
                        k -= 1
                        continue
                    path = _label_path(lines[k])
                    break
                k -= 1
        if not path and body:
            path = _comment_path(body[0])
        if path:
            if not closed:
                truncated = True
            content = "\n".join(body)
            if content and not content.endswith("\n"):
                content += "\n"
            if any(f["path"] == path for f in files):
                files = [f for f in files if f["path"] != path]
                fixes.append(f"{path} was given twice — the last version is used")
            files.append({"path": path, "content": content})
        elif info.lower() not in ("json", "jsonc", "text", "txt", "bash", "sh", "shell", "console", "powershell",
                                  "ps", "cmd", "bat", "output", "log", "diff", "mermaid") and body:
            unlabelled += 1
        i = j + 1
    if unlabelled and files:
        fixes.append(f"{unlabelled} code block(s) without a file name were ignored (names are never guessed)")
    return files, fixes, truncated


# --------------------------------------------------------------------------- Strict JSON

def _manifest_from(data: dict[str, Any]) -> dict[str, Any] | None:
    for k in ("handoff", "manifest", "AIWB_HANDOFF", "delivery", "report"):
        if isinstance(data.get(k), dict):
            return {kk: vv for kk, vv in data[k].items()}
    top = {k: data[k] for k in _MANIFEST_KEYS if k in data and k not in ("schema_version",)}
    return top if any(k in top for k in ("summary", "outcome", "completed_items", "unresolved_items")) else None


def _json_file_items(files: Any, fixes: list[str], problems: list[str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if isinstance(files, dict):
        items = [{"path": k, "content": v} if not isinstance(v, dict) else {"path": k, **v} for k, v in files.items()]
        fixes.append("files: a dictionary {path: content} was read as a list")
    elif isinstance(files, list):
        items = files
    else:
        return out
    for n, it in enumerate(items):
        if not isinstance(it, dict):
            problems.append(f"files[{n}] is not an object — skipped")
            continue
        path = next((str(it[k]) for k in _PATH_KEYS if isinstance(it.get(k), str) and it[k].strip()), "")
        action = str(it.get("action") or it.get("op") or "write").lower()
        if action in ("delete", "remove", "rm"):
            problems.append(f"{path or f'files[{n}]'}: delete is not applied by the guided loop — skipped")
            continue
        content: Any = None
        for k in _CONTENT_KEYS:
            if k in it:
                content = it[k]
                if k != "content":
                    fixes.append(f"files[{n}]: used \"{k}\" as \"content\"")
                break
        if isinstance(content, list) and all(isinstance(x, str) for x in content):
            content = "\n".join(content)
            fixes.append(f"files[{n}].content: a list of lines was joined")
        if not path or not isinstance(content, str):
            problems.append(f"files[{n}] has no path or no text content — skipped")
            continue
        if content and not content.endswith("\n"):
            content += "\n"
        out.append({"path": path.strip().replace("\\", "/"), "content": content})
    return out


def json_files(text: str) -> tuple[list[dict[str, str]], dict[str, Any] | None, str, list[str], list[str], bool]:
    """``(files, manifest, attempt_id, fixes, problems, truncated)`` from one JSON object with a ``files`` list."""
    from . import lenient
    fixes: list[str] = []
    problems: list[str] = []
    bodies = [b for b in lenient.fenced_json_blocks(text) if re.search(r"[\"\u201c]files[\"\u201d]\s*:", b)]
    found = lenient.find_object(text, keys=("files",))
    if found.text:
        bodies.append(found.text)
    if not bodies:
        return [], None, "", fixes, problems, bool(found.truncated)
    for body in bodies:
        b = body.strip()
        if not b.startswith("{"):
            f = lenient.find_object(b, keys=("files",))
            b = f.text or b
        data, lf, err = lenient.loads(b)
        if not isinstance(data, dict):
            if err:
                problems.append(f"the JSON answer is {err}")
            continue
        fixes += [f"JSON repaired: {x}" for x in lf]
        files = _json_file_items(data.get("files"), fixes, problems)
        if not files and not isinstance(data.get("files"), (list, dict)):
            continue
        manifest = _manifest_from(data)
        att = str(data.get("attempt_id") or (manifest or {}).get("attempt_id") or "")
        return files, manifest, att, fixes, problems, False
    return [], None, "", fixes, problems, False


# --------------------------------------------------------------------------- ZIP

def zip_files(data: bytes, *, name: str = "answer.zip") -> Extracted:
    """Text files and the manifest of a downloaded ZIP, read in memory with the 1.x limits."""
    ex = Extracted(format="zip")
    if not data:
        ex.problems.append("the ZIP file is empty")
        return ex
    if len(data) > MAX_ZIP:
        ex.problems.append(f"the ZIP is larger than {MAX_ZIP // (1024 * 1024)} MB")
        return ex
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError, OSError) as exc:
        ex.problems.append(f"{name} is not a readable ZIP ({exc})")
        return ex
    with z:
        infos = [i for i in z.infolist() if not i.is_dir() and not any(n in i.filename for n in _ZIP_NOISE)]
        noise = len([i for i in z.infolist() if not i.is_dir()]) - len(infos)
        if noise:
            ex.fixes.append(f"{noise} system file(s) (__MACOSX, .DS_Store…) ignored")
        names = [i.filename.replace("\\", "/") for i in infos]
        # one top folder that is itself the project root (it holds README/package.json/…) → strip it
        tops = {n.split("/", 1)[0] for n in names}
        strip = ""
        if len(tops) == 1 and all("/" in n for n in names):
            top = next(iter(tops))
            roots = {"README.md", "readme.md", "package.json", "pyproject.toml", "requirements.txt", ".gitignore",
                     "build.gradle", "build.gradle.kts", "settings.gradle", "Cargo.toml", "go.mod", "index.html",
                     *_ZIP_MANIFESTS}
            if any(n.split("/", 1)[1] in roots for n in names):
                strip = top + "/"
                ex.fixes.append(f"the ZIP's top folder \"{top}/\" was taken as the project root")
        total = 0
        for info, raw_name in zip(infos, names):
            rel = raw_name[len(strip):] if strip and raw_name.startswith(strip) else raw_name
            base = rel.rsplit("/", 1)[-1]
            if info.file_size > MAX_FILE:
                ex.problems.append(f"{rel} is larger than {MAX_FILE // 1024} KB — skipped")
                continue
            if total + info.file_size > MAX_TOTAL:
                ex.problems.append(f"the files exceed {MAX_TOTAL // (1024 * 1024)} MB in total — the rest was skipped")
                break
            try:
                raw = z.read(info)
            except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as exc:
                ex.problems.append(f"{rel} could not be read ({exc}) — skipped")
                continue
            if len(raw) > MAX_FILE:
                ex.problems.append(f"{rel} is larger than {MAX_FILE // 1024} KB — skipped")
                continue
            total += len(raw)
            if base in _ZIP_MANIFESTS and "/" not in rel and ex.manifest is None:
                try:
                    m = json.loads(raw.decode("utf-8-sig"))
                    if isinstance(m, dict):
                        ex.manifest = _manifest_from(m) or m
                        ex.attempt_id = str(m.get("attempt_id") or "")
                        continue
                except (ValueError, UnicodeDecodeError):
                    pass
            if b"\x00" in raw[:8192]:
                ex.problems.append(f"{rel} is a binary file — skipped (only text files are read)")
                continue
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                try:
                    text = raw.decode("cp1252")
                    ex.fixes.append(f"{rel} was not UTF-8 — read as Windows-1252")
                except UnicodeDecodeError:
                    ex.problems.append(f"{rel} is not a text file — skipped")
                    continue
            if not safe_path(rel):
                ex.problems.append(f"{rel} is an unsafe path — skipped")
                continue
            if len(ex.files) >= MAX_FILES:
                ex.problems.append(f"more than {MAX_FILES} files — the rest was skipped")
                break
            ex.files.append({"path": safe_path(rel), "content": text.replace("\r\n", "\n")})
    if not ex.files and not ex.problems:
        ex.problems.append("the ZIP holds no text files")
    return ex


# --------------------------------------------------------------------------- the one entry point

def _manifest_in(text: str) -> tuple[dict[str, Any] | None, str]:
    m = MAN_RE.search(text or "")
    if not m:
        return None, ""
    return None, m.group(0)


def extract(text: str) -> Extracted:
    """Every file the answer delivers, in whatever format it came, plus its manifest block and attempt id."""
    raw = (text or "").replace("\r\n", "\n")
    ex = Extracted()
    am = ATTEMPT_RE.search(raw)
    ex.attempt_id = am.group(1) if am else ""
    files, open_last = _aiwb_files(raw)
    cand = raw
    if not files:
        try:
            from .normalize import normalize
            n = normalize(raw)
            if n.changed:
                f2, o2 = _aiwb_files(n.text)
                if f2:
                    files, open_last, cand = f2, o2, n.text
                    ex.fixes.append("the AIWB markers were damaged by the chat app (" +
                                    ", ".join(x.split(":")[0] for x in n.fixes) + ") — repaired")
        except Exception:  # noqa: BLE001 - extraction must never fail
            pass
    if files:
        ex.files, ex.format, ex.truncated = files, "aiwb", open_last
        if not ex.attempt_id:
            am = ATTEMPT_RE.search(cand)
            ex.attempt_id = am.group(1) if am else ""
        return ex
    jf, man, att, jfix, jprob, jtrunc = json_files(raw)
    if jf:
        ex.files, ex.format, ex.manifest, ex.fixes, ex.problems = jf, "json", man, jfix, jprob
        ex.attempt_id = ex.attempt_id or att
        return ex
    mf, mfix, mtrunc = markdown_files(raw)
    if mf:
        ex.files, ex.format, ex.fixes, ex.truncated = mf, "markdown", mfix, mtrunc
        return ex
    ex.problems += jprob
    ex.truncated = jtrunc
    return ex


def fence_for(body: str) -> str:
    """A backtick fence longer than any backtick run inside ``body`` (at least four)."""
    runs = [len(m.group(0)) for m in re.finditer(r"`{3,}", body or "")]
    return "`" * max(4, (max(runs) + 1) if runs else 4)


def to_aiwb_text(ex: Extracted, *, original: str = "") -> str:
    """The canonical answer text: attempt line, one AIWB block per file, the manifest; ``original`` kept below."""
    out: list[str] = []
    if ex.attempt_id:
        out.append(f"AIWB_ATTEMPT_ID: {ex.attempt_id}")
        out.append("")
    for f in ex.files:
        fence = fence_for(f["content"])
        body = f["content"][:-1] if f["content"].endswith("\n") else f["content"]
        out += [f'<<<AIWB_FILE path="{f["path"]}" action="write">>>', fence, body, fence, "<<<AIWB_END_FILE>>>", ""]
    has_block = bool(MAN_RE.search(original or ""))
    if ex.manifest and not has_block:
        out += ["<<<AIWB_HANDOFF>>>", json.dumps(ex.manifest, ensure_ascii=False, indent=1), "<<<AIWB_END_HANDOFF>>>"]
    elif has_block:
        out.append(MAN_RE.search(original).group(0))
    if original.strip():
        out += ["", "--- original answer (kept for the record; not read for files) ---",
                re.sub(r"(?m)^(\s*)<<<", r"\1‹‹‹", original)]
    return "\n".join(out).rstrip() + "\n"


def canonical(text: str) -> tuple[str, Extracted]:
    """``(text the guided loop reads, what was found)``. AIWB answers come back unchanged (unless repaired)."""
    ex = extract(text)
    if ex.format == "aiwb" and not ex.fixes:
        return text, ex
    if not ex.files:
        return text, ex
    return to_aiwb_text(ex, original=text or ""), ex


def canonical_zip(data: bytes, *, name: str = "answer.zip") -> tuple[str, Extracted]:
    ex = zip_files(data, name=name)
    if not ex.files:
        return "", ex
    return to_aiwb_text(ex), ex
