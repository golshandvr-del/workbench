"""One History for the whole project (roadmap 5.13.0, owner audit B3; pure, no Tk).

5.13.0 rule: **Home = now and next, History = the past.** The Workbench's Timeline tab is gone, so the project's
events (tasks, answers accepted, milestones, versions, releases …) are listed in History next to the prompts and
answers, in one tree with one "Show" filter:

* ``all`` — every prompt/answer step, then the project's events;
* ``prompts`` — every prompt step; ``answers`` — only steps that have an answer; ``saved`` — saved checkpoints;
* ``events`` — the project's events except milestones/versions; ``versions`` — milestones, versions, releases.

Reading never writes: the rows are built from the conversation index and the ledger records as they are.
"""
from __future__ import annotations

from typing import Any, Iterable

KINDS: tuple[tuple[str, str], ...] = (
    ("all", "All"),
    ("prompts", "Prompts"),
    ("answers", "Answers"),
    ("saved", "Saved"),
    ("events", "Events"),
    ("versions", "Versions"),
)
LABELS = {k: v for k, v in KINDS}
KEY_OF_LABEL = {v: k for k, v in KINDS}
SHOWS_STEPS = ("all", "prompts", "answers", "saved")
SHOWS_EVENTS = ("all", "events", "versions")

# what the user reads — the ledger's event types in plain words (unknown types fall back to their own words)
EVENT_WORDS = {
    "project_started": "Project started", "charter_accepted": "Plan accepted", "project_settings_updated": "Project details changed",
    "project_expanded": "Project extended", "project_completed": "Project completed", "project_reopened": "Project reopened",
    "project_archived": "Project archived",
    "agents_installed": "Team set up", "agent_created": "AI added", "agent_updated": "AI changed", "team_edited": "Team changed",
    "team_settings_changed": "Team settings changed", "agent_note_changed": "AI note changed",
    "agent_templates_removed": "Template AIs removed",
    "account_profile_added": "Account added", "account_profile_updated": "Account changed",
    "chat_binding_added": "Chat linked", "chat_binding_updated": "Chat changed",
    "task_created": "Task created", "task_status": "Task status changed", "task_updated": "Task changed",
    "task_flagged": "Task flagged", "task_flag_cleared": "Task flag cleared", "task_escalated": "Task sent to the project manager",
    "attempt_created": "Prompt prepared", "attempt_status": "Prompt status changed", "attempt_response": "Answer pasted",
    "prompt_copied": "Prompt copied", "user_confirmed_sent": "Prompt sent",
    "handoff_prepared": "Prompt prepared", "handoff_exported": "Prompt copied", "handoff_ingested": "Answer read",
    "files_integrated": "Files written to the project", "repair_prepared": "Fix prompt prepared",
    "troubleshooting_prompt": "Troubleshooting prompt prepared",
    "context_request_received": "Files asked for", "context_request_on_handoff": "Files asked for",
    "context_pack_prepared": "Files prepared", "context_marked_sent": "Files sent",
    "decision_proposed": "Decision asked", "decision_superseded": "Decision replaced", "pm_decision": "Project manager decided",
    "proposal_imported": "Change proposed", "proposal_reviewed": "Change reviewed",
    "evidence_recorded": "Result recorded", "validation_waived": "Accepted on review",
    "milestone_created": "Milestone created", "milestone_updated": "Milestone changed", "milestone_dropped": "Milestone dropped",
    "milestone_accepted": "Milestone accepted",
    "version_proposed": "Version proposed", "version_created": "Version recorded", "version_withdrawn": "Version withdrawn",
    "release_published": "Release recorded", "github_prepared": "GitHub step prepared", "github_failed": "GitHub step failed",
}


def has_answer(meta: dict[str, Any]) -> bool:
    """A prompt step that has a recorded answer (any recorded response status)."""
    return bool(str(meta.get("response_status") or "").strip())


def filter_steps(entries: Iterable[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    """Conversation index rows shown for ``kind`` (empty for the event-only kinds)."""
    if kind not in SHOWS_STEPS:
        return []
    rows = list(entries)
    if kind == "answers":
        rows = [e for e in rows if has_answer(e)]
    elif kind == "saved":
        rows = [e for e in rows if bool(e.get("project_history_saved"))]
    return rows


def event_families(kind: str) -> list[str]:
    """Ledger families to query for ``kind`` ([] = all families; None-like kinds return [])."""
    return ["version"] if kind == "versions" else []


def event_rows(records: Iterable[dict[str, Any]], kind: str, names: dict[str, str] | None = None
               ) -> list[dict[str, Any]]:
    """Ledger records (newest first) → rows ``{id, when, title, detail, family}`` for ``kind``.

    ``names`` maps agent ids to the names the user gave, so the past speaks the user's words too (B4).
    """
    if kind not in SHOWS_EVENTS:
        return []
    names = names or {}
    out = []
    for rec in records:
        fam = str(rec.get("family") or "other")
        if kind == "events" and fam == "version":
            continue
        if kind == "versions" and fam != "version":
            continue
        etype = str(rec.get("event_type") or "change")
        title = EVENT_WORDS.get(etype) or etype.replace("_", " ").capitalize()
        refs = rec.get("refs") or {}
        bits = []
        for key in ("task_id", "milestone_id", "version_id"):
            if refs.get(key):
                bits.append(str(refs[key]))
        for key in ("agent_id", "to_agent_id"):
            if refs.get(key):
                bits.append(names.get(str(refs[key])) or str(refs[key]))
                break
        after, before = rec.get("after") or {}, rec.get("before") or {}
        new = after.get("new") or after.get("status")
        if new:
            bits.append(f"{before.get('status')} → {new}" if before.get("status") else str(new))
        when = str(rec.get("timestamp_utc") or "")
        out.append({"id": str(rec.get("event_id") or ""), "when": when.replace("T", " ").rstrip("Z")[:16],
                    "title": title, "detail": " · ".join(bits), "family": fam})
    return out
