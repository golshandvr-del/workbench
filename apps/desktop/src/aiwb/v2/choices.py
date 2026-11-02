"""Clear forms for step inputs (roadmap 5.17.0, R5): the question, the options and the recommendation.

Before 5.17 a decision was asked with a one-line ``askstring("Your decision")`` box: the user never saw the question
the AI asked, nor the options, nor what the project manager recommended. This module is pure (no Tk): it turns a
Guide step and one of its actions into a **form spec** that :mod:`aiwb.ui.action_form` draws as one window.

* :func:`decision_choices` — ``{"question", "options", "recommended"}`` for a decision (a ``decision:Dn`` record, or a
  task that waits for a decision: its ``blocked_reason`` and the latest handoff's ``decision_requests``).
* :func:`parse_options` — options written inside a free-text question ("Options: A, B", bullets, "(a) … (b) …",
  "A or B?"), and a "Recommended: X" hint.
* :func:`form_spec` — every field the action needs, each with a kind (``choice`` radio buttons + "Other answer…",
  ``yesno`` for passed/failed, ``entry`` one line, ``note`` optional reason with a default), in one spec.
"""
from __future__ import annotations

import re
from typing import Any

OTHER = "__other__"          # the radio value of "Other answer…"
MAX_OPTIONS = 8
MAX_OPTION_LEN = 160

LABELS = {"goal": "What should this project achieve? (one or two sentences)", "name": "Project name",
          "platform": "Platform / technology", "constraints": "Constraints",
          "ais": "How many AI chats can you use at the same time? (1-12)", "note": "Note",
          "reason": "Reason", "rationale": "Why? (kept in the decision log)", "choice": "Your decision",
          "result": "Result", "run_id": "Test/CI run id or link", "commit_sha": "Commit SHA of the release",
          "tag": "Tag (default v<version>)", "title": "Milestone title", "label": "Version (e.g. 1.2.0)",
          "idea": "Your idea"}
DEFAULTS = {"rationale": "decided in the guided loop", "reason": ""}
YESNO = {"result": (("passed", "Passed"), ("failed", "Failed"))}

_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)]|\(?[a-hA-H]\))\s+(.+?)\s*$")
_INLINE_LETTERS = re.compile(r"\(([a-hA-H1-8])\)\s*([^()]+?)(?=\s*(?:\([a-hA-H1-8]\)|$))")
_OPTIONS_LINE = re.compile(r"\b(?:options?|choices?|alternatives?)\s*[:：]\s*(.+)", re.I)
_RECOMMEND = re.compile(r"\b(?:recommended|recommendation|i recommend|we recommend|suggested|suggest(?:ion)?)"
                        r"\s*(?:[:：-]|is|would be)?\s*(.+)", re.I)


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip().strip("\"'`").strip()
    s = re.sub(r"[.;,]+$", "", s).strip()
    return s[:MAX_OPTION_LEN]


def _uniq(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for i in items:
        c = _clean(i)
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out[:MAX_OPTIONS]


def _split_list(s: str) -> list[str]:
    parts = re.split(r"\s*(?:;|\||,|\s/\s|\bor\b)\s*", s.rstrip("?.! "))
    return [p for p in parts if p.strip()]


def parse_options(text: str) -> tuple[list[str], str]:
    """Options and a recommendation written inside a question. Never invents: returns ``([], "")`` when unsure."""
    text = str(text or "")
    recommended = ""
    body_lines: list[str] = []
    for line in text.splitlines():
        m = _RECOMMEND.search(line)
        if m and not recommended:
            recommended = _clean(m.group(1))
            line = line[:m.start()]
        body_lines.append(line)
    body = "\n".join(body_lines)
    bullets = [m.group(1) for m in (_BULLET.match(x) for x in body.splitlines()) if m]
    if len(bullets) >= 2:
        return _uniq(bullets), recommended
    m = _OPTIONS_LINE.search(body)
    if m:
        opts = _uniq(_split_list(m.group(1)))
        if len(opts) >= 2:
            return opts, recommended
    letters = [m.group(2) for m in _INLINE_LETTERS.finditer(body)]
    if len(letters) >= 2:
        return _uniq(letters), recommended
    # "Should the calculator use A or B?" — only short, simple alternatives of one sentence
    for sentence in re.split(r"(?<=[?])\s+|\n", body):
        if "?" not in sentence or not re.search(r"\bor\b", sentence, re.I):
            continue
        q = sentence.strip().rstrip("?")
        q = re.sub(r"^(?:which|what)\b[^:]*:\s*", "", q, flags=re.I)
        q = re.sub(r"^(?:should|shall|do|does|will|would|can|could|is|are)\b.*?\b(?:use|be|choose|pick|go with|"
                   r"have|support|keep|make it|show|display|include|add|allow|store|save)\s+", "", q, flags=re.I)
        opts = _uniq(re.split(r"\s*,\s*|\s+or\s+", q, flags=re.I))
        lead = re.compile(r"^(?:should|shall|do|does|will|would|can|could|is|are|which|what|how|why|when|where)\b", re.I)
        if 2 <= len(opts) <= 4 and all(len(o) <= 60 and not lead.match(o) for o in opts):
            return opts, recommended
    return [], recommended


def _match(recommended: str, options: list[str]) -> str:
    """The option the recommendation names (exact, prefix or contained), else the recommendation itself."""
    r = _clean(recommended)
    if not r:
        return ""
    low = r.lower()
    for o in options:
        if o.lower() == low:
            return o
    for o in options:
        ol = o.lower()
        if low.startswith(ol) or ol.startswith(low) or (len(ol) >= 3 and re.search(r"\b" + re.escape(ol) + r"\b", low)):
            return o
    return r


def _latest_handoff(state: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    hs = [h for h in (state.get("handoffs") or {}).values() if h.get("task_id") == task_id]
    return max(hs, key=lambda h: (str(h.get("created_at", "")), str(h.get("handoff_id", "")))) if hs else None


def decision_choices(step: dict[str, Any], state: dict[str, Any] | None) -> dict[str, Any]:
    """``{"question", "options", "recommended"}`` for a decision step (empty options when none are known)."""
    state = state or {}
    key = str(step.get("key", ""))
    kind, ref = key.split(":", 1) if ":" in key else (key, "")
    question, options, recommended = str(step.get("explain") or step.get("title") or ""), [], ""
    if kind == "decision":
        d = (state.get("decisions") or {}).get(ref) or {}
        question = str(d.get("problem") or d.get("title") or question)
        title = str(d.get("title") or "")
        if title and title.lower() not in question.lower():
            question = f"{title}\n\n{question}" if question else title
        options = _uniq([str(o) for o in d.get("options") or []])
        recommended = str(d.get("recommendation") or "")
        if not options:
            options, rec2 = parse_options(question)
            recommended = recommended or rec2
    elif kind == "task":
        t = (state.get("tasks") or {}).get(ref) or {}
        h = _latest_handoff(state, ref) or {}
        asks = [str(x) for x in (h.get("decision_requests") or []) if str(x).strip()]
        question = "\n".join(asks) if asks else str(t.get("blocked_reason") or question)
        options, recommended = parse_options(question)
        # an open proposed decision for the same task carries the manager's options
        for d in sorted((state.get("decisions") or {}).values(), key=lambda d: str(d.get("decision_id", ""))):
            if ref in (d.get("affected_task_ids") or []) and d.get("options") and d.get("status") == "proposed":
                options = _uniq([str(o) for o in d["options"]])
                recommended = str(d.get("recommendation") or recommended)
    else:
        options, recommended = parse_options(question)
    recommended = _match(recommended, options)
    if recommended and recommended not in options and len(options) < MAX_OPTIONS:
        options = [recommended] + options
    return {"question": question.strip(), "options": options, "recommended": recommended}


def form_spec(step: dict[str, Any], action: dict[str, Any], state: dict[str, Any] | None = None,
              optional: tuple[str, ...] = ()) -> dict[str, Any]:
    """The whole form of one action: title, question, and one field per input it needs (``text`` excluded:
    a whole model answer goes through the paste box)."""
    fields: list[dict[str, Any]] = []
    question = ""
    for need in action.get("needs") or []:
        if need == "text":
            continue
        f: dict[str, Any] = {"need": need, "label": LABELS.get(need, need.replace("_", " ").capitalize()),
                             "optional": need in optional, "default": DEFAULTS.get(need, "")}
        if need == "choice":
            ch = step.get("choices") or decision_choices(step, state)
            question = ch.get("question", "")
            f.update(kind="choice", options=list(ch.get("options") or []), recommended=ch.get("recommended", ""))
        elif need in YESNO:
            f.update(kind="yesno", options=[v for v, _ in YESNO[need]], option_labels=dict(YESNO[need]),
                     recommended=YESNO[need][0][0])
        elif need in ("rationale", "reason", "note", "idea"):
            f.update(kind="note")
        else:
            f.update(kind="entry")
        if f["optional"] and not f["label"].endswith("(optional)"):
            f["label"] += " (optional)"
        fields.append(f)
    if not question:
        question = str(step.get("question") or step.get("explain") or "")
    return {"title": str(action.get("label") or "").rstrip("…").rstrip("."), "step_title": str(step.get("title", "")),
            "question": question.strip(), "fields": fields}


def initial_values(spec: dict[str, Any]) -> dict[str, str]:
    """What the form shows before the user touches it: the recommended option is pre-selected."""
    out: dict[str, str] = {}
    for f in spec["fields"]:
        if f["kind"] in ("choice", "yesno"):
            out[f["need"]] = f.get("recommended") or (f["options"][0] if f.get("options") else "")
        else:
            out[f["need"]] = f.get("default", "")
    return out


def validate(spec: dict[str, Any], values: dict[str, str]) -> tuple[dict[str, str], str]:
    """``(inputs, "")`` ready for ``Guide.perform``, or ``({}, message)`` naming the first missing field."""
    out: dict[str, str] = {}
    for f in spec["fields"]:
        v = str(values.get(f["need"], "")).strip()
        if not v and not f["optional"]:
            return {}, f"{f['label']}: please choose or write an answer."
        out[f["need"]] = v
    return out, ""
