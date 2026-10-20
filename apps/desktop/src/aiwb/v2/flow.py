"""The owner's algorithm (roadmap 4.x, contract ``project-flow.v1``).

The flowchart in ``docs/specs/flowchart/owner_algorithm.pdf`` is the product's main loop. This module holds its
nodes and edges (identical to ``packages/contracts/fixtures/flow/project-flow.v1.json`` — a test keeps them in sync)
and derives *where the project is* in that flowchart from the state alone. It adds no state machine of its own: the
phase is computed from tasks, handoffs, proposals and ``settings.flow`` (start, completion, archive).

Node kinds: ``app`` (done by the app), ``user`` (copy / paste / approve), ``github`` (the app prepares it, the user
authorises it).
"""
from __future__ import annotations

from typing import Any

from .models import ModelError, now_utc

PHASES = ("start", "repo", "brief", "charter_prompt", "charter_review", "split", "dispatch", "collect", "check",
          "troubleshoot", "approve", "integrate", "status_report", "pm_decision", "publish", "complete",
          "expand_or_archive", "archived")

NODES: tuple[tuple[str, str, str, str], ...] = (
    ("F1", "Start project", "user", "start"),
    ("F2", "Start timeline", "app", "start"),
    ("F3", "Create repository or update the existing one", "github", "repo"),
    ("F4", "Get name, specification and number of available AIs", "app", "brief"),
    ("F5", "Design the project-manager prompt", "app", "charter_prompt"),
    ("F6", "Give the prompt to the project-manager AI", "user", "charter_prompt"),
    ("F7", "Bring the project-manager output back", "user", "charter_prompt"),
    ("F8", "Check the project-manager output (roadmap) carefully", "app", "charter_review"),
    ("F9", "Split the project into parallel paths", "app", "split"),
    ("F10", "Generate a suitable prompt for every AI", "app", "dispatch"),
    ("F11", "Give every AI its prompt", "user", "dispatch"),
    ("F12", "Bring every AI's output back", "user", "collect"),
    ("F13", "Is the output acceptable?", "app", "check"),
    ("F14", "Smart problem detection", "app", "troubleshoot"),
    ("F15", "Build the troubleshooting prompt", "app", "troubleshoot"),
    ("F16", "User approval", "user", "approve"),
    ("F17", "Add to the project files and update the timeline", "app", "integrate"),
    ("F18", "Design the status prompt for the project manager", "app", "status_report"),
    ("F19", "Give the status prompt to the project manager", "user", "status_report"),
    ("F20", "Bring the project-manager output back", "user", "status_report"),
    ("F21", "Did the project manager define an emergency task?", "app", "pm_decision"),
    ("F22", "Save the changes on GitHub", "github", "publish"),
    ("F23", "Is a release needed?", "github", "publish"),
    ("F24", "Publish the new version", "github", "publish"),
    ("F25", "Is any roadmap stage left?", "app", "pm_decision"),
    ("F26", "Announce completion and update the timeline", "app", "complete"),
    ("F27", "Expand the project?", "user", "expand_or_archive"),
    ("F28", "Archive the project", "app", "archived"),
)

EDGES: tuple[tuple[str, str, str], ...] = (
    ("F1", "F2", ""), ("F1", "F3", ""), ("F1", "F4", ""), ("F4", "F5", ""), ("F5", "F6", ""), ("F6", "F7", ""),
    ("F7", "F8", ""), ("F8", "F9", ""), ("F9", "F10", ""), ("F10", "F11", ""), ("F11", "F12", ""), ("F12", "F13", ""),
    ("F13", "F14", "no"), ("F14", "F15", ""), ("F15", "F11", ""), ("F13", "F16", "yes"), ("F16", "F17", ""),
    ("F17", "F18", ""), ("F18", "F19", ""), ("F19", "F20", ""), ("F20", "F21", ""), ("F21", "F10", "yes"),
    ("F21", "F22", "no"), ("F22", "F23", ""), ("F23", "F24", "yes"), ("F23", "F25", "no"), ("F24", "F25", ""),
    ("F25", "F10", "yes"), ("F25", "F26", "no"), ("F26", "F27", ""), ("F27", "F1", "yes"), ("F27", "F28", "no"),
)

TROUBLESHOOT_ATTEMPTS = 3
BRIEF_FIELDS = ("name", "goal", "platform", "constraints", "ais")
_NODE = {n[0]: n for n in NODES}
_OPEN_H = ("prepared", "prompt_exported", "response_received", "parsed")
_CHECK_H = ("reconciled", "stale", "reconciliation_required")


def node(node_id: str) -> dict[str, str]:
    n = _NODE[node_id]
    return {"id": n[0], "title": n[1], "kind": n[2], "phase": n[3]}


def as_contract() -> dict[str, Any]:
    """The flow as a ``project-flow.v1`` document."""
    return {"schema_version": "1.0", "flow_id": "owner-algorithm", "source": "docs/specs/flowchart/owner_algorithm.pdf",
            "phases": list(PHASES), "nodes": [node(n[0]) for n in NODES],
            "edges": [{"from": a, "to": b, **({"when": w} if w else {})} for a, b, w in EDGES],
            "limits": {"troubleshoot_attempts": TROUBLESHOOT_ATTEMPTS}}


def flow_settings(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("settings", {}).get("flow") or {}


def _sent(state: dict[str, Any], h: dict[str, Any]) -> bool:
    att = state.get("attempts", {}).get(h.get("attempt_id", "")) or {}
    return bool((att.get("workflow") or {}).get("sent_confirmed_at"))


def current(state: dict[str, Any]) -> dict[str, Any]:  # noqa: C901 — one ordered table of the flowchart
    """Where the project is in the owner's flowchart: node, phase, why, and the nodes already passed."""
    fs = flow_settings(state)
    st = state.get("settings", {})
    tasks = state.get("tasks", {})
    handoffs = list(state.get("handoffs", {}).values())
    guide = st.get("guide") or {}

    def at(nid: str, why: str) -> dict[str, Any]:
        n = node(nid)
        return {**n, "node": nid, "why": why, "cycle": int(fs.get("cycle", 1) or 1),
                "started": bool(fs.get("started_at")), "repo": dict(fs.get("repo") or {})}

    if fs.get("archived_at"):
        return at("F28", "The project is archived (read-only).")
    if fs.get("completed_at"):
        return at("F27", "Every roadmap stage is done. Expand the project or archive it.")
    goal = str(st.get("goal", "")).strip()
    if not goal:
        return at("F4" if fs.get("started_at") else "F1",
                  "Give the project a name, a goal and the number of AIs you can use.")
    pending = [p for p in state.get("proposals", {}).values() if p.get("status") == "pending"]
    if not tasks:
        if pending:
            return at("F8", "The project manager's charter was read; check it before anything is created.")
        if guide.get("manager_sent_at"):
            return at("F7", "Paste the project manager's whole answer (the charter).")
        if guide.get("manager_copied_at"):
            return at("F6", "Send the charter prompt to your project-manager chat.")
        return at("F5", "The project-manager prompt is ready to copy.")
    if pending:
        return at("F21", "The project manager answered; check the plan (emergency tasks first).")
    if any(h.get("status") in _CHECK_H for h in handoffs):
        return at("F13", "An AI's answer was read; check whether it is acceptable.")
    if guide.get("continue"):
        return at("F15", "The last answer was cut off; a continue prompt is ready.")
    open_h = [h for h in handoffs if h.get("status") in _OPEN_H]
    if open_h:
        if all(_sent(state, h) for h in open_h):
            return at("F12", "Bring every AI's answer back and paste it.")
        return at("F11", "Give every AI its prompt (copy, send, then tap 'I sent it').")
    if any(t.get("status") in ("in_review", "validation_pending") for t in tasks.values()):
        return at("F16", "Approve the checked work (review / verification).")
    if any(t.get("status") in ("needs_decision", "blocked") and not str(t.get("blocked_reason", "")).startswith("waiting for")
           for t in tasks.values()):
        return at("F21", "A task waits for a decision or is blocked.")
    if any(t.get("status") in ("ready", "in_progress") for t in tasks.values()):
        return at("F10", "Prompts for the next parallel tasks can be generated.")
    if any(t.get("status") in ("draft", "proposed") for t in tasks.values()):
        return at("F9", "The roadmap was split into tasks; approve them to start the parallel paths.")
    versions = list(state.get("versions", {}).values())
    milestones = list(state.get("milestones", {}).values())
    if any(m.get("status") == "planned" and m.get("task_ids") for m in milestones):
        return at("F25", "All tasks of a roadmap stage are done; accept the milestone.")
    if any(v.get("status") not in ("released", "withdrawn") and v.get("milestone_ids") and
           all((state.get("milestones", {}).get(x) or {}).get("status") == "accepted" for x in v["milestone_ids"])
           for v in versions):
        return at("F24", "A roadmap version is complete; publish it.")
    last = fs.get("last_decision") or {}
    if last.get("route") == "complete" and not any(t.get("status") not in ("done", "cancelled", "superseded")
                                                    for t in tasks.values()):
        return at("F26", "The project manager says no roadmap stage is left; announce completion.")
    if int(state.get("state_revision", 0)) > int(guide.get("manager_seen_revision", 0)):
        return at("F18", "Report the new state to the project manager.")
    return at("F25", "Ask the project manager whether any roadmap stage is left.")


def path_so_far(state: dict[str, Any]) -> list[str]:
    """Node ids passed in the current cycle, in flowchart order (for the phase bar)."""
    cur = current(state)["node"]
    order = [n[0] for n in NODES]
    return order[: order.index(cur)]


# ------------------------------------------------------------------ actions on settings.flow

def start_project(store: Any, brief: dict[str, Any]) -> dict[str, Any]:
    """F1 → F2 → F4: record the start (once per cycle), the brief and the number of AIs; emit ``project_started``."""
    from .store import emit
    from .team import MAX_PARALLEL_CHATS
    goal = str(brief.get("goal", "")).strip()
    if not goal:
        raise ModelError("goal is required")
    ais_raw = str(brief.get("ais", "") or "").strip()
    ais = 0
    if ais_raw:
        try:
            ais = int(ais_raw)
        except ValueError:
            raise ModelError("number of AIs must be a whole number") from None
        if not 1 <= ais <= MAX_PARALLEL_CHATS:
            raise ModelError(f"number of AIs must be between 1 and {MAX_PARALLEL_CHATS}")
    with store.transaction("start project") as s:
        settings = s["settings"]
        fs = settings.setdefault("flow", {})
        first = not fs.get("started_at")
        if first:
            fs["started_at"] = now_utc()
            fs.setdefault("cycle", 1)
        settings["goal"] = goal[:2000]
        b = settings.setdefault("brief", {})
        for k in ("name", "platform", "constraints"):
            v = str(brief.get(k, "") or "").strip()
            if v:
                b[k] = v[:2000]
        if ais:
            settings.setdefault("team", {})["max_parallel_chats"] = ais
        if first:
            emit(s, "project_started", name=b.get("name", ""), cycle=int(fs.get("cycle", 1)),
                 max_parallel_chats=ais or None, importance="major")
        else:
            emit(s, "project_settings_updated", field="brief")
    return flow_settings(store.load())
