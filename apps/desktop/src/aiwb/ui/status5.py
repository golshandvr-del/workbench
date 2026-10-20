"""Status-bar facts of the 5.x shell (roadmap 5.1.0): "● 5 agents running · Milestone V0.1.0 … Autosaved".

Pure functions over the V2 project state (no Tk), so the numbers are tested and the bar never guesses.
Reading the state never writes it.
"""
from __future__ import annotations

from typing import Any

OPEN_HANDOFF = ("prepared", "prompt_exported", "response_received", "parsed", "reconciled", "stale",
                "reconciliation_required")
WORKING_TASK = ("in_progress", "in_review", "validation_pending")


def running_agents(state: dict[str, Any]) -> list[str]:
    """AIs that are working now: they own a task in progress or have an open hand-off (one chat each)."""
    agents = state.get("agents", {}) or {}
    tasks = state.get("tasks", {}) or {}
    out: set[str] = set()
    for t in tasks.values():
        if t.get("status") in WORKING_TASK and t.get("owner_agent_id"):
            out.add(str(t["owner_agent_id"]))
    for h in (state.get("handoffs", {}) or {}).values():
        if h.get("status") in OPEN_HANDOFF:
            owner = h.get("agent_id") or (tasks.get(h.get("task_id", "")) or {}).get("owner_agent_id")
            if owner:
                out.add(str(owner))
    return sorted(a for a in out if not agents or a in agents)


def current_milestone(state: dict[str, Any]) -> str:
    """The milestone being worked on: the first planned milestone, else the newest unreleased version label."""
    ms = sorted((state.get("milestones", {}) or {}).values(), key=lambda m: str(m.get("milestone_id", "")))
    for m in ms:
        if m.get("status") == "planned":
            return str(m.get("title") or m.get("milestone_id") or "")
    vs = sorted((state.get("versions", {}) or {}).values(), key=lambda v: str(v.get("version_id", "")))
    open_v = [v for v in vs if v.get("status") not in ("released", "withdrawn")]
    if open_v:
        return str(open_v[0].get("label") or "")
    return str(vs[-1].get("label") or "") if vs else ""


def summary(state: dict[str, Any] | None) -> dict[str, Any]:
    """Everything the status bar shows, as data (``text`` is the left-hand sentence)."""
    if state is None:
        return {"running": 0, "milestone": "", "live": False, "text": "No project open"}
    n = len(running_agents(state))
    milestone = current_milestone(state)
    head = f"{n} agent{'s' if n != 1 else ''} running" if n else "No agents running"
    text = head + (f"  ·  Milestone {milestone}" if milestone else "")
    return {"running": n, "milestone": milestone, "live": n > 0, "text": text}
