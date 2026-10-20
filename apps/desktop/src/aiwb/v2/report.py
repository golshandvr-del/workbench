"""Status report to the project manager and routing of the manager's decision (roadmap 4.4.0, flowchart F18–F21, F25).

* ``status_sections`` (F18): what changed since the manager's last report — files integrated, tasks finished, tasks
  stuck (escalated, blocked, waiting for a decision) and the GitHub / release facts Workbench knows.
* ``status_prompt``: the manager update + those sections + the decision contract (``DECISION_FORMAT``): the
  proposal may name ``emergency_tasks`` (F21, correction C4) and must say ``roadmap_remaining`` (F25).
* ``route`` is the one decision rule, shared with the phone through
  ``packages/contracts/fixtures/report/pm-decision.v1.json``:
  emergency → back to F10 with the emergency first; a stage left (or open work) → next wave (F10); otherwise
  → completion (F26).
* ``apply_decision`` runs inside the review transaction: emergency tasks get priority ``critical`` and the
  ``emergency`` flag; every started or ready task they ``block`` waits for them (``blocked`` with a "waiting for"
  reason, so it resumes by itself once the emergency is done). The decision is recorded in ``settings.flow``.
"""
from __future__ import annotations

from typing import Any

from .models import TERMINAL_TASK, now_utc
from .store import emit

ROUTES = ("emergency", "next_stage", "complete")
_TRUE = ("true", "yes", "y", "1")
_FALSE = ("false", "no", "n", "0", "none")

DECISION_FORMAT = """## Your decision (required in the block)
Add two fields to the AIWB_MANAGER_PROPOSAL JSON:
- "roadmap_remaining": true if any roadmap stage is still left after this plan, false if the project is complete.
- "emergency_tasks": [] normally. Only for an urgent fix that must happen before anything else, list it as
  {"ref": "<temporary_ref of a create_task in this block, or an existing TASK- id>", "blocks": ["TASK-…"]} where
  "blocks" are the running tasks that must wait for it. Workbench gives it top priority and pauses those tasks."""


def parse_remaining(v: Any) -> bool | None:
    """``roadmap_remaining`` as the model wrote it → True / False / None (unknown)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v if v is not None else "").strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    return None


def parse_emergency(v: Any) -> list[dict[str, Any]]:
    """``emergency_tasks`` → [{"ref", "blocks"}] (strings are accepted as bare refs; junk is dropped)."""
    out: list[dict[str, Any]] = []
    for x in (v if isinstance(v, list) else [])[:20]:
        if isinstance(x, str) and x.strip():
            out.append({"ref": x.strip()[:60], "blocks": []})
        elif isinstance(x, dict) and str(x.get("ref") or x.get("task_id") or "").strip():
            blocks = [str(b).strip()[:60] for b in (x.get("blocks") or []) if str(b).strip()][:40]
            out.append({"ref": str(x.get("ref") or x.get("task_id")).strip()[:60], "blocks": blocks})
    return out


def route(emergency: list[Any], remaining: bool | None, open_tasks: int) -> str:
    """The decision rule (F21 → F25): 'emergency' | 'next_stage' | 'complete'."""
    if emergency:
        return "emergency"
    if remaining is False and open_tasks == 0:
        return "complete"
    return "next_stage"


def open_tasks(state: dict[str, Any]) -> list[str]:
    return sorted(tid for tid, t in state.get("tasks", {}).items() if t.get("status") not in TERMINAL_TASK)


def status_sections(state: dict[str, Any]) -> dict[str, list[str]]:
    """F18: facts for the status prompt, all from Workbench's own state (never from model claims)."""
    g = (state.get("settings", {}).get("guide") or {})
    since = str(g.get("manager_seen_at", ""))
    tasks = state.get("tasks", {})
    integrated, finished, stuck, github = [], [], [], []
    for h in sorted(state.get("handoffs", {}).values(), key=lambda h: h.get("handoff_id", "")):
        at = str(h.get("integrated_at", ""))
        if at and at > since:
            files = h.get("integrated_files") or []
            integrated.append(f"{h.get('task_id')} ({h.get('handoff_id')}): {len(files)} file(s)"
                              + (" — " + ", ".join(str(f) for f in files[:8]) if files else ""))
    for tid, t in sorted(tasks.items()):
        if t.get("status") == "done" and str(t.get("updated_at", "")) > since:
            finished.append(f"{tid} — {t.get('title', '')}")
        reason = str(t.get("blocked_reason", ""))
        if t.get("status") == "needs_decision" or (t.get("status") == "blocked" and not reason.startswith("waiting for")):
            stuck.append(f"{tid} — {t.get('title', '')} ({t.get('status')}): {reason or 'no reason recorded'}")
    fs = state.get("settings", {}).get("flow") or {}
    repo = fs.get("repo") or {}
    if repo.get("full_name") or repo.get("url"):
        github.append(f"Repository: {repo.get('full_name') or repo.get('url')}"
                      + (f" (branch {repo['branch']})" if repo.get("branch") else ""))
    for v in sorted(state.get("versions", {}).values(), key=lambda v: v.get("version_id", "")):
        if v.get("status") == "released":
            rel = v.get("release") or {}
            github.append(f"Released {v.get('label')}" + (f" — tag {rel.get('tag')}" if rel.get("tag") else "")
                          + (f", commit {str(rel.get('commit_sha'))[:12]}" if rel.get("commit_sha") else ""))
    if not github:
        github.append("No repository or release recorded yet.")
    return {"integrated": integrated, "finished": finished, "stuck": stuck, "github": github}


def status_prompt(state: dict[str, Any], update: str) -> str:
    """F18: the manager update with the status sections and the decision contract."""
    sec = status_sections(state)
    lines = [update, "", "## Since your last report (from Workbench, not from model claims)"]
    for head, key in (("Files added to the project", "integrated"), ("Tasks finished", "finished"),
                      ("Stuck tasks (need your plan)", "stuck"), ("GitHub / releases", "github")):
        lines += ["", f"### {head}"] + [f"- {x}" for x in sec[key][:40]] + ([] if sec[key] else ["- none"])
    lines += ["", "## What I need now",
              "Every planned task is finished or waiting. Propose the next step: fixes for stuck work, tasks for the "
              "next roadmap stage, or say that the project is "
              "complete. Answer with one AIWB_MANAGER_PROPOSAL block (it may contain zero operations only if "
              "roadmap_remaining is false).", "", DECISION_FORMAT]
    return "\n".join(lines)


def apply_decision(s: dict[str, Any], p: dict[str, Any], created: dict[str, str]) -> dict[str, Any]:
    """Inside the review transaction: mark emergencies, pause what they block, record the route."""
    emergency = []
    paused = []
    for e in p.get("emergency_tasks") or []:
        tid = created.get(e["ref"], e["ref"])
        t = s["tasks"].get(tid)
        if not t or t.get("status") in TERMINAL_TASK:
            continue
        t["priority"] = "critical"
        if "emergency" not in t.setdefault("flags", []):
            t["flags"].append("emergency")
        emergency.append(tid)
        for b in e.get("blocks") or []:
            bt = s["tasks"].get(created.get(b, b))
            if not bt or bt["task_id"] == tid or bt.get("status") not in ("ready", "in_progress", "blocked"):
                continue
            if tid not in bt["depends_on"]:
                bt["depends_on"].append(tid)
            old = bt["status"]
            if old == "blocked" and not str(bt.get("blocked_reason", "")).startswith("waiting for"):
                continue
            bt["status"] = "blocked"
            bt["blocked_reason"] = f"waiting for {tid} (emergency)"
            bt["updated_at"] = now_utc()
            paused.append(bt["task_id"])
            emit(s, "task_status", task_id=bt["task_id"], old=old, new="blocked", why=bt["blocked_reason"])
    remaining = p.get("roadmap_remaining")
    r = route(emergency, remaining, len(open_tasks(s)))
    fs = s["settings"].setdefault("flow", {})
    fs["last_decision"] = {"route": r, "proposal_id": p["proposal_id"], "emergency": emergency, "paused": paused,
                           "roadmap_remaining": remaining, "at": now_utc()}
    if remaining is not None:
        fs["roadmap_remaining"] = remaining
    emit(s, "pm_decision", proposal_id=p["proposal_id"], route=r, emergency=emergency, paused=paused,
         importance="major")
    return fs["last_decision"]
