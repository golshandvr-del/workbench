"""Find and read the JSON object inside a chat answer, whatever the chat app did to it (roadmap 5.10.0, audit A12).

Models wrap JSON in prose, in a ```json fence, in our markers (sometimes escaped or with a missing ``>``), add ``//``
or ``#`` comments, trailing commas, smart quotes or Python literals, and chat apps cut long answers off. This module
only *locates* and *loads*; it never guesses content:

* :func:`find_object` — the text of the first balanced top-level ``{…}`` that (optionally) contains certain keys;
  reports when an object was opened but never closed (cut-off answer).
* :func:`loads` — ``json.loads`` first, then the conservative repairs of :mod:`aiwb.intake.normalize` plus ``#``
  comment lines; returns the object and the list of repairs that were needed.

Every repair is returned to the caller, which shows it to the user (a fix is never hidden).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_FENCE_JSON = re.compile(r"(?ims)^[ \t]*(`{3,}|~{3,})[ \t]*(?:json|jsonc|javascript|js)?[ \t]*\n(.*?)^[ \t]*\1[ \t]*$")


@dataclass
class Found:
    text: str = ""            # the object text ("" when none)
    start: int = -1
    end: int = -1
    truncated: bool = False   # an object was opened and never closed
    fixes: list[str] = field(default_factory=list)


def _balanced_end(s: str, start: int) -> int:
    """Index just after the ``}`` closing the ``{`` at ``start``; -1 when the text ends first (string aware)."""
    depth = 0
    in_str = False
    quote = ""
    i, n = start, len(s)
    while i < n:
        c = s[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == quote or (quote == '"' and c in "\u201d"):
                in_str = False
        elif c in "\"\u201c":
            in_str, quote = True, '"'
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def find_object(text: str, *, keys: tuple[str, ...] = (), start: int = 0) -> Found:
    """The first top-level JSON object at or after ``start`` mentioning every key in ``keys`` (as ``"key"``)."""
    s = text or ""
    i = s.find("{", start)
    truncated = False
    while i >= 0:
        end = _balanced_end(s, i)
        if end < 0:
            body = s[i:]
            if all(re.search(r"[\"\u201c\u201d]" + re.escape(k) + r"[\"\u201c\u201d]\s*:", body) for k in keys):
                truncated = True
                break
            i = s.find("{", i + 1)
            continue
        body = s[i:end]
        if all(re.search(r"[\"\u201c\u201d]" + re.escape(k) + r"[\"\u201c\u201d]\s*:", body) for k in keys):
            return Found(body, i, end)
        i = s.find("{", end)
    return Found(truncated=truncated)


def fenced_json_blocks(text: str) -> list[str]:
    """Bodies of ```json fences (also ~~~ and unlabeled fences whose body starts with ``{``)."""
    out = []
    for m in _FENCE_JSON.finditer(text or ""):
        body = m.group(2)
        if body.lstrip().startswith("{"):
            out.append(body)
    return out


def _strip_hash_comments(body: str) -> tuple[str, int]:
    lines, n = [], 0
    for line in body.split("\n"):
        if line.lstrip().startswith("#"):
            n += 1
            continue
        lines.append(line)
    return "\n".join(lines), n


def loads(body: str) -> tuple[Any, list[str], str]:
    """``(data, fixes, error)``: the parsed value, the repairs applied, or an error message (data is None)."""
    try:
        return json.loads(body), [], ""
    except (json.JSONDecodeError, ValueError) as exc:
        first = exc
    fixes: list[str] = []
    cand, n = _strip_hash_comments(body)
    if n:
        fixes.append(f"json_hash_comments:{n}")
        try:
            return json.loads(cand), fixes, ""
        except (json.JSONDecodeError, ValueError):
            pass
    from .normalize import normalize, normalize_json_text
    nn = normalize(cand)
    if nn.changed:
        cand = nn.text
        fixes += nn.fixes
        try:
            return json.loads(cand), fixes, ""
        except (json.JSONDecodeError, ValueError):
            pass
    r = normalize_json_text(cand)
    if r.changed:
        try:
            return json.loads(r.text), fixes + r.fixes, ""
        except (json.JSONDecodeError, ValueError):
            pass
    msg = getattr(first, "msg", str(first))
    pos = f" (line {first.lineno}, column {first.colno})" if isinstance(first, json.JSONDecodeError) else ""
    return None, fixes, f"not valid JSON: {msg}{pos}"
