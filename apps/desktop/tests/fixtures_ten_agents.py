"""Synthetic 10-agent project for Gate C (spec §20): no real accounts, built through the public services
plus explicit fixture edits for states that need a model answer (partial, parse failure, stale).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aiwb.v2.controller import ProjectsController
from aiwb.v2.models import normalize_agent

ROLES = ["project_manager", "architect", "implementer", "implementer", "implementer", "implementer",
         "reviewer", "reviewer", "researcher", "implementer"]


def build(root: Path, *, n_agents: int = 10, tasks_per_agent: int = 2) -> dict[str, Any]:
    ctl = ProjectsController(root)
    p = ctl.project
    with p.store.transaction("fixture agents") as s:
        for i, role in enumerate(ROLES[:n_agents]):
            aid = f"agent-fx-{i:02d}"
            s["agents"][aid] = normalize_agent({"agent_id": aid, "role": role, "name": f"{role} {i}", "template_id": ""})
    accs = [p.resources.add_account({"display_name": f"Account {i}", "provider": "Other"})["account_profile_id"]
            for i in range(4)]
    agents = [f"agent-fx-{i:02d}" for i in range(n_agents)]
    for i, aid in enumerate(agents):
        p.resources.bind_chat(aid, accs[i % len(accs)], chat_name=f"chat {i}")
    tasks: dict[str, list[str]] = {}
    for i, aid in enumerate(agents[1:], 1):
        for k in range(tasks_per_agent):
            t = p.tasks.create({"title": f"{aid} task {k}", "objective": "o", "owner_agent_id": aid,
                                "scope": {"include": [f"m{i}/{k}/**"]}, "acceptance_criteria": ["ok"]})
            p.tasks.transition(t["task_id"], "ready")
            tasks.setdefault(aid, []).append(t["task_id"])
    special: dict[str, str] = {}
    # agent 02: partial answer
    tid = tasks[agents[2]][0]
    h = ctl.start_task(tid)
    ctl.mark_copied(h["handoff_id"])
    ctl.confirm_sent(h["handoff_id"])
    with p.store.transaction("fixture partial") as s:
        s["attempts"][h["attempt_id"]]["status"] = "parsed"
        hh = s["handoffs"][h["handoff_id"]]
        hh.update(status="parsed", outcome="partial", unresolved_items=["tests missing"])
    special["partial"] = tid
    # agent 03: stale handoff
    tid = tasks[agents[3]][0]
    h = ctl.start_task(tid)
    ctl.mark_copied(h["handoff_id"])
    with p.store.transaction("fixture stale") as s:
        s["handoffs"][h["handoff_id"]]["status"] = "stale"
    special["stale"] = tid
    # agent 04: waiting for the user to paste (copied + confirmed sent) — NOT an attention item by default
    tid = tasks[agents[4]][0]
    h = ctl.start_task(tid)
    ctl.mark_copied(h["handoff_id"])
    ctl.confirm_sent(h["handoff_id"])
    special["waiting"] = tid
    # agent 05: parse failure
    tid = tasks[agents[5]][0]
    h = ctl.start_task(tid)
    ctl.mark_copied(h["handoff_id"])
    with p.store.transaction("fixture parse failed") as s:
        s["attempts"][h["attempt_id"]]["status"] = "parse_failed"
    special["parse_failed"] = tid
    # open decision
    d = p.decisions.propose("Pick database", "storage choice", options=["sqlite", "postgres"])
    special["decision"] = d["decision_id"]
    return {"ctl": ctl, "agents": agents, "tasks": tasks, "special": special, "accounts": accs}
