"""Status-bar facts of the 5.x shell (roadmap 5.1.0; 5.13.0: "Waiting for an answer from Coder · Milestone V0.1.0").

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


READY = ("prepared",)                                   # prompt made, not copied yet
WAITING = ("prompt_exported",)                          # copied / sent: the AI's chat has it
TO_CHECK = ("response_received", "parsed", "reconciled", "stale", "reconciliation_required")  # answer pasted


def _name(state: dict[str, Any], aid: str) -> str:
    return str(((state.get("agents") or {}).get(aid) or {}).get("name") or "").strip() or aid


def _who(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def chats(state: dict[str, Any]) -> dict[str, list[str]]:
    """5.13.0 (owner audit B4): the AIs by what is true of their chat — ``waiting`` (has the prompt, no answer yet),
    ``ready`` (prompt made, not copied), ``check`` (answer pasted, the user checks it). Names, not ids."""
    agents = state.get("agents", {}) or {}
    tasks = state.get("tasks", {}) or {}
    out: dict[str, list[str]] = {"waiting": [], "ready": [], "check": []}
    for h in sorted((state.get("handoffs", {}) or {}).values(), key=lambda h: str(h.get("handoff_id", ""))):
        aid = str(h.get("to_agent_id") or h.get("agent_id")
                  or (tasks.get(h.get("task_id", "")) or {}).get("owner_agent_id") or "")
        if not aid or (agents and aid not in agents):
            continue
        st = h.get("status")
        key = "waiting" if st in WAITING else "ready" if st in READY else "check" if st in TO_CHECK else ""
        if key and _name(state, aid) not in out[key]:
            out[key].append(_name(state, aid))
    return out


def summary(state: dict[str, Any] | None) -> dict[str, Any]:
    """Everything the status bar shows, as data (``text`` is the left-hand sentence).

    5.13.0 (owner audit B4): only what is true — "Waiting for an answer from Coder" when Coder's chat has the
    prompt, never "2 agents running" when no AI has anything. ``running`` = AIs whose answer is awaited.
    """
    if state is None:
        return {"running": 0, "milestone": "", "live": False, "text": "No project open"}
    c = chats(state)
    parts = []
    if c["waiting"]:
        parts.append(f"Waiting for an answer from {_who(c['waiting'])}")
    if c["check"]:
        parts.append(f"Check the answer of {_who(c['check'])}")
    if c["ready"]:
        parts.append(f"Prompt ready for {_who(c['ready'])}")
    milestone = current_milestone(state)
    head = "  ·  ".join(parts) or "Nothing waiting"
    text = head + (f"  ·  Milestone {milestone}" if milestone else "")
    n = len(c["waiting"])
    return {"running": n, "milestone": milestone, "live": n > 0, "text": text, "chats": c}
