"""Agent Registry (roadmap 1.17.1 / slice 2B).

An agent is a *role*, not a model account: changing ``preferred_model_label``
never changes ``agent_id``. Built-in templates are copied into the project once;
later template updates never silently overwrite a user's profiles.
"""
from __future__ import annotations

import copy
from typing import Any

from .models import ModelError, normalize_agent, now_utc
from .store import ProjectStore, emit, require

TEMPLATE_VERSION = 1

TEMPLATES: dict[str, dict[str, Any]] = {
    "agent-project-manager": {
        "name": "Project Manager", "role": "project_manager",
        "purpose": "Plan the project, propose tasks/dependencies/decisions and analyse progress from the published state.",
        "instructions": [
            "Separate clearly: what you read in the state snapshot, what agents reported, your own inference, and what is unknown.",
            "If you cannot open the GitHub state file, say so explicitly; never pretend you read it.",
            "Never declare a task done; only Workbench marks tasks done from verified evidence.",
            "Return changes only as an AIWB_MANAGER_PROPOSAL block based on the given state_revision.",
        ],
        "allowed_task_types": ["planning", "analysis"], "output_contract": "aiwb-manager-proposal-v1",
        "review_policy": "user_approval_required", "escalation_rules": ["conflicting_decision", "missing_information"],
    },
    "agent-architect": {
        "name": "Architect", "role": "architect",
        "purpose": "Design contracts and architecture for one approved task; record decisions that need approval.",
        "instructions": ["Follow accepted project decisions", "List every assumption and open decision explicitly",
                         "Do not implement unrelated features"],
        "allowed_task_types": ["architecture", "design", "analysis"], "output_contract": "aiwb-handoff-v1",
        "review_policy": "decisions_need_approval", "escalation_rules": ["scope_change", "conflicting_decision"],
    },
    "agent-implementer": {
        "name": "Implementer", "role": "implementer",
        "purpose": "Implement one approved task within its scope.",
        "instructions": ["Follow the accepted project decisions", "Stay inside the task scope",
                         "Do not claim tests passed unless evidence is present",
                         "Report missing information instead of inventing it"],
        "allowed_task_types": ["implementation", "bug_fix", "tests"], "output_contract": "aiwb-handoff-v1",
        "review_policy": "required_for_code_changes",
        "escalation_rules": ["scope_change", "conflicting_decision", "missing_acceptance_criteria"],
    },
    "agent-reviewer": {
        "name": "Reviewer", "role": "reviewer",
        "purpose": "Review a delivered change against the acceptance criteria and report findings with file references.",
        "instructions": ["Check each acceptance criterion separately", "Link every finding to a file or criterion",
                         "Do not rewrite the implementation; propose concrete fixes"],
        "allowed_task_types": ["review", "tests"], "output_contract": "aiwb-handoff-v1",
        "review_policy": "none", "escalation_rules": ["missing_evidence"],
    },
}
BASE_TEMPLATE_IDS = tuple(TEMPLATES)  # the four base roles of 1.17.1


class AgentRegistry:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def list(self, include_disabled: bool = True) -> list[dict[str, Any]]:
        agents = list(self.store.load()["agents"].values())
        return sorted([a for a in agents if include_disabled or a.get("enabled", True)], key=lambda a: a["agent_id"])

    def get(self, agent_id: str) -> dict[str, Any] | None:
        return self.store.load()["agents"].get(agent_id)

    def install_templates(self) -> list[str]:
        """Add missing base agents; existing profiles (even edited ones) are never touched."""
        added: list[str] = []
        with self.store.transaction("install agent templates") as s:
            for tid, tpl in TEMPLATES.items():
                if tid in s["agents"]:
                    continue
                data = {"agent_id": tid, **copy.deepcopy(tpl), "template_id": f"{tid}@{TEMPLATE_VERSION}"}
                s["agents"][tid] = normalize_agent(data)
                added.append(tid)
            if added:
                emit(s, "agents_installed", agent_ids=added)
        return added

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.store.transaction("create agent") as s:
            agent = normalize_agent({**data, "revision": 1, "created_at": None, "updated_at": None})
            if agent["agent_id"] in s["agents"]:
                raise ModelError(f"agent {agent['agent_id']} already exists")
            s["agents"][agent["agent_id"]] = agent
            emit(s, "agent_created", agent_id=agent["agent_id"])
        return agent

    def update(self, agent_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        if "agent_id" in changes and changes["agent_id"] != agent_id:
            raise ModelError("agent_id is stable and cannot be changed; copy the agent instead")
        with self.store.transaction("update agent") as s:
            cur = require(s, "agents", agent_id)
            merged = normalize_agent({**cur, **changes, "agent_id": agent_id})
            if {k: v for k, v in merged.items() if k not in ("updated_at", "revision")} == \
               {k: v for k, v in cur.items() if k not in ("updated_at", "revision")}:
                return cur
            merged["revision"] = int(cur.get("revision", 1)) + 1
            merged["updated_at"] = now_utc()
            merged["created_at"] = cur.get("created_at", merged["created_at"])
            s["agents"][agent_id] = merged
            emit(s, "agent_updated", agent_id=agent_id, revision=merged["revision"])
        return merged

    def copy(self, agent_id: str, new_id: str, name: str = "") -> dict[str, Any]:
        src = self.get(agent_id)
        if src is None:
            raise ModelError(f"agent {agent_id} does not exist")
        data = {k: v for k, v in src.items() if k not in ("agent_id", "revision", "created_at", "updated_at")}
        data.update(agent_id=new_id, name=name or (src["name"] + " (copy)"), template_id="")
        return self.create(data)

    def set_enabled(self, agent_id: str, enabled: bool) -> dict[str, Any]:
        return self.update(agent_id, {"enabled": enabled})
