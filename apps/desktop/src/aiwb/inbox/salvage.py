"""Partial output recovery (roadmap 1.16.1).

When strict parsing of AIWB blocks fails for the whole response, every block
that is complete *on its own* is re-parsed with the same strict parser
(injected by the host) and kept; broken, cut-off, duplicate or unsafe blocks
are reported, never guessed. A focused repair prompt asks only for what is
missing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

HEADER = re.compile(r'^\s*<<<AIWB_(FILE|COMMAND)\b.*>>>\s*$')
PATH_ATTR = re.compile(r'''path\s*=\s*(?:"([^"]*)"|'([^']*)')''')
END_FILE = "<<<AIWB_END_FILE>>>"
END_COMMAND = "<<<AIWB_END_COMMAND>>>"


@dataclass
class SalvageResult:
    complete: dict[str, str] = field(default_factory=dict)   # path -> content
    broken: dict[str, str] = field(default_factory=dict)     # path -> reason
    duplicates: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    payload_files: list[dict[str, Any]] = field(default_factory=list)  # strict-parser entries for complete blocks

    @property
    def any_recovered(self) -> bool:
        return bool(self.complete)


def basic_path_problem(path: str) -> str:
    """Conservative fallback; the host passes its full validator (same rules as import)."""
    parts = path.replace("\\", "/").split("/")
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path) or any(p in ("", ".", "..") for p in parts):
        return "path is not a safe relative path"
    return ""


def _raw_parse(segment: str) -> dict[str, Any]:
    lines = segment.splitlines()
    m = PATH_ATTR.search(lines[0])
    if not m:
        raise ValueError("header has no path")
    end = next(i for i, l in enumerate(lines) if l.strip() == END_FILE)
    body = lines[1:end]
    return {"files": [{"path": (m.group(1) or m.group(2) or "").strip(),
                       "content": "\n".join(body) + ("\n" if body else "")}]}


def split_segments(text: str) -> list[tuple[str, str, bool]]:
    """Return ``(kind, segment_text, closed)`` for each AIWB block in order."""
    lines = (text or "").splitlines()
    heads = [i for i, l in enumerate(lines) if HEADER.match(l)]
    out = []
    for n, start in enumerate(heads):
        stop = heads[n + 1] if n + 1 < len(heads) else len(lines)
        kind = "FILE" if "<<<AIWB_FILE" in lines[start] else "COMMAND"
        marker = END_FILE if kind == "FILE" else END_COMMAND
        end = next((i for i in range(start + 1, stop) if lines[i].strip() == marker), None)
        seg = "\n".join(lines[start:(end + 1) if end is not None else stop])
        out.append((kind, seg, end is not None))
    return out


def salvage_aiwb_blocks(text: str, expected: Iterable[str] = (), *,
                        parse_block: Callable[[str], dict[str, Any]] = _raw_parse,
                        path_problem: Callable[[str], str] = basic_path_problem,
                        redact: Callable[[str], str] = lambda s: s) -> SalvageResult:
    res = SalvageResult()
    seen: dict[str, int] = {}
    good: dict[str, dict[str, Any]] = {}
    for kind, seg, closed in split_segments(text):
        if kind != "FILE":
            continue  # commands are never salvaged; they need a clean response
        m = PATH_ATTR.search(seg.splitlines()[0])
        path = (m.group(1) or m.group(2) or "").strip() if m else ""
        if not path:
            continue
        seen[path] = seen.get(path, 0) + 1
        if not closed:
            res.broken[path] = "block is cut off (no end marker)"
            continue
        problem = path_problem(path)
        if problem:
            res.broken[path] = redact(problem)
            continue
        try:
            payload = parse_block(seg)
            files = [f for f in payload.get("files", []) if isinstance(f, dict)]
            if len(files) != 1:
                raise ValueError("block did not yield exactly one file")
        except Exception as exc:  # noqa: BLE001 - strict parser errors are reported, not raised
            res.broken[path] = redact(str(exc))[:300]
            continue
        good[path] = files[0]
    for path, count in seen.items():
        if count > 1:
            res.duplicates.append(path)
            good.pop(path, None)
            res.broken.pop(path, None)
    for path, entry in good.items():
        res.complete[path] = str(entry.get("content", ""))
        res.payload_files.append(entry)
    res.duplicates.sort()
    exp = set(expected)
    res.missing = sorted(p for p in exp if p not in res.complete and p not in res.broken and p not in res.duplicates)
    return res


def repair_prompt(res: SalvageResult, *, attempt_id: str = "", task: str = "") -> str:
    """Ask only for the files that could not be recovered."""
    need = sorted(set(res.broken) | set(res.duplicates) | set(res.missing))
    lines = []
    if attempt_id:
        lines.append(f"AIWB_ATTEMPT_ID: {attempt_id}")
    lines.append("Your previous answer could only be partly imported by AI Workbench.")
    if task:
        lines += ["", "Task (unchanged): " + task.strip()[:2000]]
    if res.complete:
        lines += ["", "Already received correctly — do NOT resend:"] + [f"- {p}" for p in sorted(res.complete)]
    if need:
        lines += ["", "Resend ONLY these files, each complete:"]
        for p in need:
            why = res.broken.get(p) or ("sent more than once" if p in res.duplicates else "missing")
            lines.append(f"- {p}  ({why})")
    lines += ["", "Use one block per file: `<<<AIWB_FILE path=\"…\" action=\"write\" body=\"raw\">>>`, the complete file text, "
              "then `<<<AIWB_END_FILE>>>` on its own line. Put the AIWB_ATTEMPT_ID line first. "
              "Do not claim that anything was run or tested."]
    return "\n".join(lines)
