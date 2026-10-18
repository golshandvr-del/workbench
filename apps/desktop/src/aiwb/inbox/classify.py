"""Lightweight response classification (roadmap 1.16.0).

Only *suggests* parsers, ranked by confidence. It never authorises an import:
strict validation is a separate stage.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

AIWB_HEADER = re.compile(r"(?m)^\s*(?:`{3,}\w*\s*\n\s*)?<<<AIWB_(FILE|COMMAND|DELETE|RENAME|MOVE)\b")
AIWB_END = re.compile(r"(?m)^\s*<<<AIWB_END_(FILE|COMMAND)>>>\s*$")
JSON_PROTOCOL = re.compile(r"""["']protocol["']\s*:\s*["'](workbench-v[123]|workbench-context-[\w.-]+)["']""")
CONTEXT_PROTOCOL = re.compile(r"""["']protocol["']\s*:\s*["']workbench-context""")
CONTEXT_REQUEST = re.compile(r"(?m)^\s*<<<AIWB_CONTEXT_REQUEST>>>|\"type\"\s*:\s*\"AIWB_CONTEXT_REQUEST\"")
MD_FENCE_WITH_PATH = re.compile(r"(?m)^(?:#+\s*|\*\*)?`?[\w./-]+\.\w{1,8}`?(?:\*\*)?\s*:?\s*\n`{3,}")


@dataclass(frozen=True)
class Suggestion:
    parser: str          # aiwb_blocks | json | context_plan | context_request | markdown
    confidence: float
    reason: str


def classify(text: str) -> list[Suggestion]:
    t = (text or "").lstrip("\ufeff")
    out: list[Suggestion] = []
    if CONTEXT_REQUEST.search(t):
        out.append(Suggestion("context_request", 0.95, "AIWB_CONTEXT_REQUEST block"))
    if AIWB_HEADER.search(t):
        out.append(Suggestion("aiwb_blocks", 0.9, "AIWB file/action block header"))
    if CONTEXT_PROTOCOL.search(t):
        out.append(Suggestion("context_plan", 0.85, "workbench-context protocol field"))
    elif JSON_PROTOCOL.search(t):
        out.append(Suggestion("json", 0.85, "workbench protocol field"))
    elif t.strip().startswith("{") or re.search(r"(?im)^\s*`{3,}\s*json\b", t):
        out.append(Suggestion("json", 0.5, "JSON object / fence"))
    if MD_FENCE_WITH_PATH.search(t):
        out.append(Suggestion("markdown", 0.3, "labeled Markdown code fences (best effort)"))
    return sorted(out, key=lambda s: -s.confidence)


def looks_truncated(text: str) -> bool:
    """Unclosed AIWB block, unbalanced fence, or JSON that ends mid-object."""
    t = (text or "").rstrip()
    if not t:
        return False
    heads = len(re.findall(r"(?m)^\s*<<<AIWB_(?:FILE|COMMAND)\b", t))
    ends = len(AIWB_END.findall(t))
    if heads > ends:
        return True
    if len(re.findall(r"(?m)^\s*`{3,}", t)) % 2 == 1:
        return True
    s = t
    m = re.search(r"(?s)`{3,}\s*json\s*\n(.*)$", t)
    if m:
        s = m.group(1).rsplit("```", 1)[0].strip()
    if s.startswith("{"):
        try:
            json.loads(s)
            return False
        except json.JSONDecodeError as exc:
            return exc.pos >= len(s.rstrip()) - 1 or "Unterminated string" in exc.msg
    return False
