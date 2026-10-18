"""V2 attempts: one model try for one task revision (roadmap 1.17.0 / 1.18.0).

The attempt ID is shared with the Response Inbox registry (``att-…``), so a
pasted answer is matched by the same ``AIWB_ATTEMPT_ID`` line. A late answer
for an older attempt is kept but never replaces the active attempt (``stale``).
"""
from __future__ import annotations

from typing import Any

from ..inbox import AttemptRegistry
from .models import MACHINES, SCHEMA_VERSION, ModelError, check_transition, now_utc
from .store import ProjectStore, emit, require


class AttemptService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.inbox_attempts = AttemptRegistry(store.root)

    def list(self, task_id: str = "") -> list[dict[str, Any]]:
        items = self.store.load()["attempts"].values()
        return sorted([a for a in items if not task_id or a.get("task_id") == task_id], key=lambda a: a["created_at"])

    def get(self, attempt_id: str) -> dict[str, Any] | None:
        return self.store.load()["attempts"].get(attempt_id)

    def active_for(self, task_id: str) -> dict[str, Any] | None:
        t = self.store.load()["tasks"].get(task_id) or {}
        aid = t.get("active_attempt_id")
        return self.get(aid) if aid else None

    def create(self, task_id: str, *, agent_id: str = "", handoff_id: str = "", kind: str = "implementation",
               parent_attempt_id: str = "", expected_paths: list[str] | None = None,
               base_revision: str = "") -> dict[str, Any]:
        state = self.store.load()
        task = state["tasks"].get(task_id)
        if task is None:
            raise ModelError(f"task {task_id} does not exist")
        if task["status"] in ("done", "cancelled", "superseded"):
            raise ModelError(f"{task_id} is {task['status']}; create a new task or revision instead")
        inbox_att = self.inbox_attempts.new(task_id=task_id, task_revision=str(task["task_revision"]),
                                            base_revision=base_revision, kind=kind,
                                            parent_attempt_id=parent_attempt_id, expected_paths=expected_paths or [])
        with self.store.transaction("create attempt") as s:
            t = require(s, "tasks", task_id)
            prev = t.get("active_attempt_id")
            att = {"schema_version": SCHEMA_VERSION, "attempt_id": inbox_att.attempt_id, "task_id": task_id,
                   "task_revision": t["task_revision"], "agent_id": agent_id or t.get("owner_agent_id", ""),
                   "handoff_id": handoff_id, "kind": kind, "parent_attempt_id": parent_attempt_id,
                   "expected_paths": list(expected_paths or []), "status": "created",
                   "base_state_revision": int(s["state_revision"]), "base_revision": base_revision,
                   "response_ids": [], "created_at": now_utc(), "updated_at": now_utc(), "legacy": False}
            s["attempts"][att["attempt_id"]] = att
            t["active_attempt_id"] = att["attempt_id"]
            if prev and prev in s["attempts"] and s["attempts"][prev]["status"] not in ("accepted", "rejected", "abandoned", "stale"):
                self._move(s, prev, "stale", f"superseded by {att['attempt_id']}")
            emit(s, "attempt_created", attempt_id=att["attempt_id"], task_id=task_id, kind=kind)
            if t["status"] in ("ready", "needs_decision", "in_review", "validation_pending", "done"):
                old = t["status"]
                check_transition("task", old, "in_progress")
                t["status"] = "in_progress"
                emit(s, "task_status", task_id=task_id, old=old, new="in_progress", why="attempt started")
        return att

    def mark(self, attempt_id: str, status: str, why: str = "") -> dict[str, Any]:
        with self.store.transaction(f"attempt {attempt_id} -> {status}") as s:
            self._move(s, attempt_id, status, why)
            return s["attempts"][attempt_id]

    @staticmethod
    def _move(s: dict[str, Any], attempt_id: str, status: str, why: str) -> None:
        a = require(s, "attempts", attempt_id)
        check_transition("attempt", a["status"], status)
        if a["status"] == status:
            return
        old = a["status"]
        a["status"] = status
        a["updated_at"] = now_utc()
        emit(s, "attempt_status", attempt_id=attempt_id, old=old, new=status, why=why[:300])

    def export(self, attempt_id: str) -> dict[str, Any]:
        """Prompt was copied for the user: created/prompt_ready → exported → waiting_response."""
        with self.store.transaction("export attempt") as s:
            a = require(s, "attempts", attempt_id)
            for step in ("prompt_ready", "exported", "waiting_response"):
                if a["status"] == step:
                    continue
                if step in MACHINES["attempt"][a["status"]]:
                    self._move(s, attempt_id, step, "prompt exported")
            return a

    def attach_response(self, attempt_id: str, response_id: str, *, parsed: bool) -> dict[str, Any]:
        """Link an Inbox response. A late answer for a non-active attempt is kept as 'stale'."""
        with self.store.transaction("attach response") as s:
            a = require(s, "attempts", attempt_id)
            if response_id not in a["response_ids"]:
                a["response_ids"].append(response_id)
            task = s["tasks"].get(a["task_id"]) or {}
            is_active = task.get("active_attempt_id") == attempt_id
            if a["status"] in ("created", "prompt_ready"):
                self._move(s, attempt_id, "exported", "response arrived")
            if a["status"] in ("exported", "waiting_response", "parse_failed"):
                self._move(s, attempt_id, "response_received", f"response {response_id}")
            if a["status"] == "response_received":
                self._move(s, attempt_id, "parsed" if parsed else "parse_failed", "")
            if not is_active and a["status"] not in ("accepted", "rejected", "abandoned", "stale") and \
                    "stale" in MACHINES["attempt"][a["status"]]:
                self._move(s, attempt_id, "stale", "late answer: a newer attempt is active")
            emit(s, "attempt_response", attempt_id=attempt_id, response_id=response_id, active=is_active)
            return a

    def repair_depth(self, attempt_id: str) -> int:
        """Consecutive repair rounds ending at this attempt (bounded fix loop, spec §15)."""
        state = self.store.load()
        depth, cur = 0, state["attempts"].get(attempt_id)
        while cur and cur.get("kind") == "repair" and cur.get("status") != "accepted":
            depth += 1
            cur = state["attempts"].get(cur.get("parent_attempt_id", ""))
        return depth
