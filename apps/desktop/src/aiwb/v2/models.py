"""V2 data model: entities, stable IDs, revisions and central state machines (roadmap 1.17.0 / slice 2A).

Every entity is a plain JSON-serialisable dict with ``schema_version``. Allowed
status transitions live *only* here; services call :func:`check_transition` and
the UI never assigns a status directly.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"

ROLES = ("project_manager", "architect", "implementer", "reviewer", "researcher")

TASK_STATUSES = ("draft", "proposed", "ready", "in_progress", "blocked", "needs_decision", "in_review",
                 "validation_pending", "done", "cancelled", "superseded")
ATTEMPT_STATUSES = ("created", "prompt_ready", "exported", "waiting_response", "response_received", "parse_failed",
                    "parsed", "reconciliation_required", "ready_for_review", "accepted", "rejected", "stale",
                    "abandoned")
HANDOFF_STATUSES = ("prepared", "prompt_exported", "response_received", "parsed", "reconciled", "accepted",
                    "rejected", "superseded", "stale", "reconciliation_required")
HANDOFF_OUTCOMES = ("complete", "partial", "blocked", "needs_decision", "failed")
DECISION_STATUSES = ("proposed", "accepted", "rejected", "superseded")
EVIDENCE_TYPES = ("model_report", "file_change", "test_run", "build_run", "git_operation", "manual_review",
                  "external_artifact")
EVIDENCE_SOURCES = ("workbench_process_runner", "workbench_apply", "github_actions", "git", "user", "model")
PROPOSAL_STATUSES = ("pending", "partially_accepted", "accepted", "rejected", "stale")
TERMINAL_TASK = ("done", "cancelled", "superseded")

_T = {
    "draft": {"proposed", "ready", "blocked", "needs_decision", "cancelled"},
    "proposed": {"draft", "ready", "blocked", "needs_decision", "cancelled"},
    "ready": {"in_progress", "blocked", "needs_decision", "cancelled", "superseded", "draft"},
    "in_progress": {"in_review", "validation_pending", "blocked", "needs_decision", "ready", "cancelled", "superseded"},
    "blocked": {"ready", "needs_decision", "cancelled", "superseded"},
    "needs_decision": {"ready", "blocked", "in_progress", "cancelled", "superseded"},
    "in_review": {"in_progress", "validation_pending", "done", "needs_decision", "blocked", "cancelled"},
    "validation_pending": {"done", "in_progress", "in_review", "needs_decision", "blocked", "cancelled"},
    "done": {"in_progress", "superseded"},
    "cancelled": set(),
    "superseded": set(),
}
_A = {
    "created": {"prompt_ready", "abandoned", "stale"},
    "prompt_ready": {"exported", "response_received", "abandoned", "stale"},
    "exported": {"waiting_response", "response_received", "abandoned", "stale"},
    "waiting_response": {"response_received", "abandoned", "stale"},
    "response_received": {"parse_failed", "parsed", "stale", "abandoned"},
    "parse_failed": {"response_received", "parsed", "abandoned", "stale"},
    "parsed": {"reconciliation_required", "ready_for_review", "stale", "rejected"},
    "reconciliation_required": {"ready_for_review", "rejected", "stale", "abandoned"},
    "ready_for_review": {"accepted", "rejected", "stale"},
    "accepted": set(),
    "rejected": set(),
    "stale": {"ready_for_review", "rejected", "abandoned"},
    "abandoned": set(),
}
_H = {
    "prepared": {"prompt_exported", "superseded", "rejected"},
    "prompt_exported": {"response_received", "superseded", "rejected", "stale"},
    "response_received": {"parsed", "rejected", "stale", "superseded"},
    "parsed": {"reconciled", "reconciliation_required", "rejected", "stale", "superseded"},
    "reconciliation_required": {"reconciled", "rejected", "superseded"},
    "stale": {"reconciled", "rejected", "superseded"},
    "reconciled": {"accepted", "rejected", "superseded"},
    "accepted": {"superseded"},
    "rejected": set(),
    "superseded": set(),
}
_D = {"proposed": {"accepted", "rejected"}, "accepted": {"superseded"}, "rejected": set(), "superseded": set()}

MACHINES: dict[str, dict[str, set[str]]] = {"task": _T, "attempt": _A, "handoff": _H, "decision": _D}

ID_PATTERNS = {
    "task": re.compile(r"^TASK-\d{4,}$"),
    "agent": re.compile(r"^agent-[a-z0-9][a-z0-9-]{0,62}$"),
    "handoff": re.compile(r"^HO-\d{4,}$"),
    "decision": re.compile(r"^DEC-\d{4,}$"),
    "evidence": re.compile(r"^EV-\d{4,}$"),
    "proposal": re.compile(r"^PROP-\d{4,}$"),
    "artifact": re.compile(r"^ART-\d{4,}$"),
    "account_profile": re.compile(r"^ACC-\d{4,}$"),
    "chat_binding": re.compile(r"^CHAT-\d{4,}$"),
    "milestone": re.compile(r"^MS-\d{4,}$"),
    "version": re.compile(r"^VER-\d{4,}$"),
    "attempt": re.compile(r"^att-\d{8}-\d{6}-[0-9a-f]{8}$|^legacy-[A-Za-z0-9_.-]{1,80}$"),
}
PREFIX = {"task": "TASK", "handoff": "HO", "decision": "DEC", "evidence": "EV", "proposal": "PROP", "artifact": "ART",
          "account_profile": "ACC", "chat_binding": "CHAT", "milestone": "MS", "version": "VER"}


class ModelError(ValueError):
    """Invalid entity, ID or transition. Message is user-presentable."""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def check_transition(kind: str, current: str, new: str) -> None:
    machine = MACHINES[kind]
    if current not in machine:
        raise ModelError(f"unknown {kind} status {current!r}")
    if new not in machine:
        raise ModelError(f"unknown {kind} status {new!r}")
    if new != current and new not in machine[current]:
        allowed = ", ".join(sorted(machine[current])) or "none (terminal)"
        raise ModelError(f"{kind} cannot go from '{current}' to '{new}'. Allowed: {allowed}.")


def valid_id(kind: str, value: Any) -> bool:
    return isinstance(value, str) and bool(ID_PATTERNS[kind].match(value))


def _strs(v: Any, name: str, limit: int = 200, item_len: int = 2000) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > limit or not all(isinstance(x, str) for x in v):
        raise ModelError(f"{name} must be a list of strings (max {limit})")
    return [x.strip()[:item_len] for x in v if x.strip()]


def _text(v: Any, name: str, required: bool = False, limit: int = 4000) -> str:
    if v is None or v == "":
        if required:
            raise ModelError(f"{name} is required")
        return ""
    if not isinstance(v, str):
        raise ModelError(f"{name} must be text")
    return v.strip()[:limit]


def normalize_agent(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ModelError("agent must be an object")
    aid = data.get("agent_id")
    if not valid_id("agent", aid):
        raise ModelError("agent_id must look like 'agent-implementer' (lowercase letters, digits, '-')")
    role = data.get("role")
    if role not in ROLES:
        raise ModelError(f"role must be one of {', '.join(ROLES)}")
    instr = data.get("instructions", [])
    if isinstance(instr, str):
        instr = [line for line in instr.splitlines()]
    return {
        "schema_version": SCHEMA_VERSION,
        "agent_id": aid,
        "revision": int(data.get("revision", 1)),
        "name": _text(data.get("name"), "name", True, 120),
        "role": role,
        "purpose": _text(data.get("purpose"), "purpose", False, 1000),
        "instructions": _strs(instr, "instructions", 60, 1000),
        "preferred_model_label": _text(data.get("preferred_model_label"), "preferred_model_label", False, 80),
        "input_contract": _text(data.get("input_contract"), "input_contract", False, 1000),
        "output_contract": _text(data.get("output_contract") or "aiwb-handoff-v1", "output_contract", False, 120),
        "allowed_task_types": _strs(data.get("allowed_task_types"), "allowed_task_types", 20, 60),
        "review_policy": _text(data.get("review_policy"), "review_policy", False, 120),
        "escalation_rules": _strs(data.get("escalation_rules"), "escalation_rules", 20, 200),
        "template_id": _text(data.get("template_id"), "template_id", False, 80),
        "enabled": bool(data.get("enabled", True)),
        "created_at": data.get("created_at") or now_utc(),
        "updated_at": data.get("updated_at") or now_utc(),
    }


ACCEPTANCE_POLICIES = ("evidence_required", "review_and_evidence", "manual_review")
DEFAULT_APPROVALS = ("review",)


def normalize_task(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the *editable* task fields. IDs/revisions/status are owned by the service."""
    if not isinstance(data, dict):
        raise ModelError("task must be an object")
    scope = data.get("scope") or {}
    if not isinstance(scope, dict):
        raise ModelError("scope must be an object with include/exclude lists")
    criteria = _strs(data.get("acceptance_criteria"), "acceptance_criteria", 50, 1000)
    policy = data.get("acceptance_policy") or "review_and_evidence"
    if policy not in ACCEPTANCE_POLICIES:
        raise ModelError(f"acceptance_policy must be one of {', '.join(ACCEPTANCE_POLICIES)}")
    pr = data.get("priority") or "medium"
    risk = data.get("risk_level") or "medium"
    if pr not in ("low", "medium", "high", "critical") or risk not in ("low", "medium", "high"):
        raise ModelError("priority must be low|medium|high|critical and risk_level low|medium|high")
    deps = data.get("depends_on") or []
    if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
        raise ModelError("depends_on must be a list of task IDs")
    return {
        "title": _text(data.get("title"), "title", True, 200),
        "objective": _text(data.get("objective"), "objective", True, 4000),
        "task_type": _text(data.get("task_type") or "implementation", "task_type", False, 60),
        "owner_agent_id": _text(data.get("owner_agent_id"), "owner_agent_id", False, 64),
        "reviewer_agent_ids": _strs(data.get("reviewer_agent_ids"), "reviewer_agent_ids", 10, 64),
        "depends_on": list(dict.fromkeys(d.strip() for d in deps if d.strip())),
        "scope": {"include": _strs(scope.get("include"), "scope.include", 100, 300),
                  "exclude": _strs(scope.get("exclude"), "scope.exclude", 100, 300)},
        "acceptance_criteria": criteria,
        "acceptance_policy": policy,
        "deliverables": _strs(data.get("deliverables"), "deliverables", 30, 200),
        "context_refs": _strs(data.get("context_refs"), "context_refs", 50, 300),
        "priority": pr,
        "risk_level": risk,
        "required_approvals": _strs(data.get("required_approvals") or list(DEFAULT_APPROVALS), "required_approvals", 5, 30),
        "origin": data.get("origin") if data.get("origin") in ("manual", "manager_proposal", "playbook", "migration", "companion") else "manual",
    }


# Fields whose change creates a new task revision (spec 10.2) and flags dependants (10.4).
REVISION_FIELDS = ("title", "objective", "scope", "acceptance_criteria", "deliverables", "acceptance_policy",
                   "required_approvals", "task_type")
CONTRACT_FIELDS = ("objective", "scope", "acceptance_criteria", "deliverables")
