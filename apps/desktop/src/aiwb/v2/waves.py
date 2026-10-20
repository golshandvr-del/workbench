"""Parallel paths and waves (roadmap 4.1.0, flowchart F9–F12).

F9 splits the accepted roadmap into *parallel paths*: one lane per AI (the task owner). F10 then generates prompts
for every AI — but, following correction C3 of ``docs/specs/FLOWCHART_ALGORITHM.md``, only for tasks whose
prerequisites are done, and never more open chats than the user said they can follow (``max_parallel_chats``).

* :func:`lanes` — open tasks grouped by owner AI.
* :func:`waves` — open tasks layered by dependency (wave 1 can start now, wave 2 after wave 1, …); dependency
  cycles are reported, never looped over.
* :func:`dispatch` — the dispatch desk: open chats, free chat slots, the tasks that get a prompt now and those
  that wait for a free chat.

Pure functions of the state; nothing here writes.
"""
from __future__ import annotations

from typing import Any

from .models import TERMINAL_TASK

OPEN_HANDOFF = ("prepared", "prompt_exported", "response_received", "parsed", "reconciled", "stale",
                "reconciliation_required")
_STARTABLE = ("ready", "in_progress")


def _owner(state: dict[str, Any], t: dict[str, Any]) -> str:
    o = t.get("owner_agent_id") or ""
    agents = state.get("agents", {})
    if o and o in agents and (agents.get(o) or {}).get("enabled", True):
        return o
    return "agent-implementer" if "agent-implementer" in agents else next(iter(agents), "")


def _open_tasks(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: t for k, t in state.get("tasks", {}).items() if t.get("status") not in TERMINAL_TASK}


def lanes(state: dict[str, Any]) -> dict[str, list[str]]:
    """Open task ids per owner AI (a lane = one AI's chat), in task-id order."""
    out: dict[str, list[str]] = {}
    for tid in sorted(_open_tasks(state)):
        out.setdefault(_owner(state, state["tasks"][tid]), []).append(tid)
    return out


def waves(state: dict[str, Any]) -> dict[str, Any]:
    """Layer the open tasks by dependency. Returns {"waves": [[ids]...], "cycle": [ids], "dead": [ids]}.

    A dependency on a done task is satisfied; on a cancelled/superseded/missing task it is *dead* (the task needs
    re-planning and is left out of the waves).
    """
    tasks = state.get("tasks", {})
    open_ = _open_tasks(state)
    dead = sorted(tid for tid, t in open_.items() for d in t.get("depends_on", [])
                  if d not in tasks or tasks[d].get("status") in ("cancelled", "superseded"))
    left = {tid: {d for d in t.get("depends_on", []) if d in open_} for tid, t in open_.items() if tid not in dead}
    out: list[list[str]] = []
    while left:
        layer = sorted(tid for tid, deps in left.items() if not deps)
        if not layer:
            break
        out.append(layer)
        for tid in layer:
            left.pop(tid)
        for deps in left.values():
            deps.difference_update(layer)
    return {"waves": out, "cycle": sorted(left), "dead": dead}


def max_chats(state: dict[str, Any]) -> int:
    from .team import team_settings
    try:
        return max(1, int(team_settings(state)["max_parallel_chats"]))
    except (TypeError, ValueError):
        return 2


def dispatch(state: dict[str, Any]) -> dict[str, Any]:
    """The dispatch desk (F10–F12).

    ``active``: open handoffs (one chat each); ``slots``: free chats; ``next``: startable tasks that get a prompt
    now (dependency order, one per AI lane first, then the rest); ``queued``: startable tasks waiting for a free chat.
    """
    handoffs = [h for h in state.get("handoffs", {}).values() if h.get("status") in OPEN_HANDOFF]
    busy = {h.get("task_id") for h in handoffs}
    limit = max_chats(state)
    slots = max(0, limit - len(handoffs))
    order = [tid for layer in waves(state)["waves"] for tid in layer]
    startable = [tid for tid in order if state["tasks"][tid].get("status") in _STARTABLE and tid not in busy]
    # fairness across lanes: first one task per AI, then the remaining ones, both in wave order
    first, rest, seen = [], [], set()
    for tid in startable:
        who = _owner(state, state["tasks"][tid])
        (rest if who in seen else first).append(tid)
        seen.add(who)
    pick = (first + rest)[:slots]
    return {"limit": limit, "active": sorted(h["handoff_id"] for h in handoffs), "slots": slots, "next": pick,
            "queued": [t for t in first + rest if t not in pick],
            "owners": {tid: _owner(state, state["tasks"][tid]) for tid in startable}}
