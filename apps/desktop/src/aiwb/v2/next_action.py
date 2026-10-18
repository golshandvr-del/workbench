"""Next Action service (roadmap 1.20.1 / slice 2G, spec §14).

Derived only from local state and policies — never from a model sentence. Each
action has a type, reason, references, whether it needs approval, and its
preconditions. The first one is the primary action; nothing is hidden.
"""
from __future__ import annotations

from typing import Any

PRIORITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _act(type_: str, ref: str, reason: str, *, approval: bool = False, pre: list[str] | None = None,
         rank: int = 50, label: str = "") -> dict[str, Any]:
    return {"type": type_, "reference_id": ref, "reason": reason, "needs_approval": approval,
            "preconditions": pre or [], "rank": rank, "label": label or type_.replace("_", " ")}


def compute_next_actions(state: dict[str, Any], *, publish_pending: bool = False,
                         manager_report_due: bool = False) -> list[dict[str, Any]]:
    tasks = state["tasks"]
    out: list[dict[str, Any]] = []
    for p in state["proposals"].values():
        if p["status"] == "pending":
            out.append(_act("review_proposal", p["proposal_id"],
                            f"manager proposal with {len(p['operations'])} operation(s) waits for review"
                            + (" — it is STALE (state changed since it was written)" if p.get("stale") else ""),
                            approval=True, rank=5))
    for d in state["decisions"].values():
        if d["status"] == "proposed":
            blocked = [t for t in d["affected_task_ids"] if tasks.get(t, {}).get("status") == "needs_decision"]
            out.append(_act("resolve_decision", d["decision_id"],
                            f"decision '{d['title']}' is open" + (f"; {len(blocked)} task(s) wait for it" if blocked else ""),
                            approval=True, rank=8 if blocked else 30))
    for h in state["handoffs"].values():
        if h["status"] in ("reconciled", "stale", "reconciliation_required"):
            why = "answer imported; review and accept or reject the handoff"
            if h["status"] != "reconciled":
                why = "answer is stale/needs reconciliation: " + "; ".join(h.get("stale_reasons", []))[:300]
            missing = [x for x in h["unresolved_items"] if x.startswith("missing file:")]
            if missing:
                why += f" ({len(missing)} expected file(s) missing — request them or record a partial delivery)"
            out.append(_act("review_handoff", h["handoff_id"], why, approval=True, rank=10))
        elif h["status"] == "prompt_exported":
            out.append(_act("import_response", h["handoff_id"],
                            f"prompt for {h['to_agent_id']} was copied; paste the answer into the Inbox", rank=20))
        elif h["status"] == "prepared":
            out.append(_act("copy_prompt", h["handoff_id"], f"handoff prompt for {h['to_agent_id']} is ready to copy", rank=22))
    for t in sorted(tasks.values(), key=lambda t: (PRIORITY.get(t.get("priority", "medium"), 2), t["task_id"])):
        st, tid = t["status"], t["task_id"]
        pr = PRIORITY.get(t.get("priority", "medium"), 2)
        if t.get("flags"):
            out.append(_act("review_task", tid, t["flags"][0], approval=True, rank=12 + pr))
        if st == "validation_pending":
            out.append(_act("run_validation", tid, "changes were reviewed; the required test/build has not been verified yet",
                            pre=["apply approved changes"], rank=14 + pr))
        elif st == "in_review":
            out.append(_act("review_delivery", tid, "delivery waits for your review against the acceptance criteria",
                            approval=True, rank=16 + pr))
        elif st == "in_progress" and not any(h["task_id"] == tid and h["status"] in ("prepared", "prompt_exported", "reconciled", "stale", "reconciliation_required")
                                             for h in state["handoffs"].values()):
            out.append(_act("prepare_handoff", tid, "task is in progress but no prompt/handoff is open", rank=35 + pr))
        elif st == "ready":
            out.append(_act("start_task", tid, f"all prerequisites done; assign to {t.get('owner_agent_id') or 'an agent'} and prepare a handoff",
                            rank=40 + pr))
        elif st == "blocked":
            out.append(_act("unblock_task", tid, t.get("blocked_reason") or "task is blocked", rank=60 + pr))
        elif st in ("draft", "proposed"):
            out.append(_act("approve_task", tid, f"task is {st}; complete it and mark it ready", approval=True, rank=70 + pr))
    if publish_pending:
        out.append(_act("publish_state", "", "local project state is newer than the last published snapshot", rank=80))
    if manager_report_due:
        out.append(_act("manager_update", "", "the project manager has not seen the latest state revision", rank=85))
    if not tasks:
        out.append(_act("plan_project", "", "no tasks yet: prepare the project-manager planning prompt", rank=1))
    out.sort(key=lambda a: (a["rank"], a["reference_id"]))
    return out
