"""Right-click menu of a Mission Map task circle, as data (roadmap 5.4.0; no Tk).

The four items come from :data:`structure5.TASK_MENU` (COPY PROMPT · SEND PROMPT · GET AI RESPONSE · MARK AS DONE).
An item is **enabled only when the Guide offers a matching action for that task right now** — the menu never invents
a transition the Guide would refuse. :func:`items` returns, for every item, the Guide step key and action id to run,
the inputs that action still needs, and a one-line hint that explains why an item is disabled.
"""
from __future__ import annotations

from typing import Any

from .structure5 import TASK_MENU

# Order of preference when one item could run several Guide actions for the same task.
PREFERENCE: dict[str, tuple[str, ...]] = {
    "copy_prompt": ("copy", "prepare"),
    "send_prompt": ("sent",),
    "get_response": ("paste",),
    "mark_done": ("accept_handoff", "approve", "validation_passed", "waive_validation"),
}

DISABLED_HINT: dict[str, str] = {
    "copy_prompt": "No prompt to copy for this task now.",
    "send_prompt": "Copy the prompt first.",
    "get_response": "No prompt is waiting for an answer.",
    "mark_done": "Nothing to accept for this task yet.",
}


def step_task(step: dict[str, Any]) -> str:
    """The task a Guide step belongs to ('' when it is not about one task)."""
    if step.get("task_id"):
        return str(step["task_id"])
    key = str(step.get("key", ""))
    return key.split(":", 1)[1] if key.startswith("task:") else ""


def items(steps: list[dict[str, Any]], task_id: str) -> list[dict[str, Any]]:
    """Menu rows for ``task_id`` given the Guide's current ``steps`` (in rank order)."""
    mine = [s for s in steps if step_task(s) == task_id]
    out = []
    for item_id, label, icon, allowed in TASK_MENU:
        pref = PREFERENCE.get(item_id, allowed)
        found: tuple[dict[str, Any], dict[str, Any]] | None = None
        for action_id in pref:
            if action_id not in allowed and action_id != "prepare":
                continue
            for s in mine:
                act = next((a for a in s.get("actions", []) if a["id"] == action_id), None)
                if act is not None:
                    found = (s, act)
                    break
            if found:
                break
        row = {"id": item_id, "label": label, "icon": icon, "enabled": found is not None, "step": "",
               "action": "", "needs": [], "hint": DISABLED_HINT.get(item_id, "")}
        if found:
            s, act = found
            row.update(step=s["key"], action=act["id"], needs=list(act.get("needs", [])), hint=act["label"])
        out.append(row)
    return out


def first_enabled(rows: list[dict[str, Any]]) -> int:
    """Index of the first enabled row (-1 when none) — where keyboard focus starts."""
    return next((i for i, r in enumerate(rows) if r["enabled"]), -1)


def move(rows: list[dict[str, Any]], index: int, delta: int) -> int:
    """Next enabled row from ``index`` in direction ``delta`` (wraps; stays put when nothing is enabled)."""
    n = len(rows)
    if n == 0 or not any(r["enabled"] for r in rows):
        return -1
    i = index
    for _ in range(n):
        i = (i + delta) % n
        if rows[i]["enabled"]:
            return i
    return index
