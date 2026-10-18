"""Task service and dependency graph (roadmap 1.17.1 / slice 2B).

* Tasks are independent of chats, have stable ``TASK-xxxx`` IDs and revisions.
* Changing objective/scope/criteria creates a new revision (old attempts keep
  their revision) and flags dependants for review.
* The graph rejects self-dependencies, unknown IDs and cycles *before* saving.
* A task is ``ready`` only when every prerequisite is ``done``; cancelling a
  prerequisite never frees a dependant — it becomes ``blocked``.
* Status changes only through :meth:`TaskService.transition` (central machine).
"""
from __future__ import annotations

import copy
import fnmatch
from typing import Any, Iterable

from .models import (CONTRACT_FIELDS, REVISION_FIELDS, SCHEMA_VERSION, ModelError, check_transition,
                     normalize_task, now_utc)
from .store import ProjectStore, emit, next_id, require


def find_cycle(edges: dict[str, list[str]]) -> list[str] | None:
    """Return one dependency cycle as a path (``[a, b, a]``) or None. Iterative DFS."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in edges}
    for start in sorted(edges):
        if colour[start] != WHITE:
            continue
        stack: list[tuple[str, Iterable[str]]] = [(start, iter(edges.get(start, [])))]
        path = [start]
        colour[start] = GREY
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                colour[node] = BLACK
                stack.pop()
                path.pop()
                continue
            if nxt not in colour:
                continue
            if colour[nxt] == GREY:
                return path[path.index(nxt):] + [nxt]
            if colour[nxt] == WHITE:
                colour[nxt] = GREY
                stack.append((nxt, iter(edges.get(nxt, []))))
                path.append(nxt)
    return None


def validate_graph(tasks: dict[str, dict[str, Any]]) -> list[str]:
    """All graph problems as readable messages (empty list = healthy)."""
    problems: list[str] = []
    edges: dict[str, list[str]] = {}
    for tid, t in tasks.items():
        deps = list(t.get("depends_on", []))
        if tid in deps:
            problems.append(f"{tid} depends on itself")
        for d in deps:
            if d not in tasks:
                problems.append(f"{tid} depends on unknown task {d}")
        edges[tid] = [d for d in deps if d in tasks and d != tid]
    cycle = find_cycle(edges)
    if cycle:
        problems.append("dependency cycle: " + " → ".join(cycle))
    return problems


def scopes_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Conservative overlap test of two include-scopes (glob patterns); empty scope = unknown = overlap."""
    ia, ib = a.get("include") or [], b.get("include") or []
    if not ia or not ib:
        return True
    for pa in ia:
        for pb in ib:
            ra, rb = pa.rstrip("*").rstrip("/"), pb.rstrip("*").rstrip("/")
            if fnmatch.fnmatch(pa, pb) or fnmatch.fnmatch(pb, pa) or ra.startswith(rb) or rb.startswith(ra):
                return True
    return False


def readiness(task: dict[str, Any], tasks: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """Derived readiness for a not-yet-started task: ('ready'|'blocked', reason)."""
    waiting, dead = [], []
    for d in task.get("depends_on", []):
        dep = tasks.get(d)
        if dep is None:
            dead.append(f"{d} (missing)")
        elif dep["status"] in ("cancelled", "superseded"):
            dead.append(f"{d} ({dep['status']})")
        elif dep["status"] != "done":
            waiting.append(d)
    if dead:
        return "blocked", "prerequisite no longer valid: " + ", ".join(dead) + " — re-plan this task"
    if waiting:
        return "blocked", "waiting for " + ", ".join(waiting)
    return "ready", ""


class TaskService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    # -- queries
    def list(self) -> list[dict[str, Any]]:
        return sorted(self.store.load()["tasks"].values(), key=lambda t: t["task_id"])

    def get(self, task_id: str) -> dict[str, Any] | None:
        return self.store.load()["tasks"].get(task_id)

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for t in self.list():
            out.setdefault(t["status"], []).append(t["task_id"])
        return out

    def dependants(self, task_id: str) -> list[str]:
        return [t["task_id"] for t in self.list() if task_id in t.get("depends_on", [])]

    def parallel_candidates(self) -> list[tuple[str, str]]:
        """Pairs of ready tasks that could be worked on at the same time (no dependency, no scope overlap)."""
        ready = [t for t in self.list() if t["status"] == "ready"]
        pairs = []
        for i, a in enumerate(ready):
            for b in ready[i + 1:]:
                if a["task_id"] in b["depends_on"] or b["task_id"] in a["depends_on"]:
                    continue
                if not scopes_overlap(a["scope"], b["scope"]):
                    pairs.append((a["task_id"], b["task_id"]))
        return pairs

    # -- mutations (each one transaction)
    def create(self, data: dict[str, Any], *, status: str = "draft") -> dict[str, Any]:
        with self.store.transaction("create task") as s:
            task = self._create_in(s, data, status=status)
        return task

    def _create_in(self, s: dict[str, Any], data: dict[str, Any], *, status: str = "draft",
                   task_id: str | None = None) -> dict[str, Any]:
        fields = normalize_task(data)
        if fields["owner_agent_id"] and fields["owner_agent_id"] not in s["agents"]:
            raise ModelError(f"owner agent {fields['owner_agent_id']} does not exist")
        for r in fields["reviewer_agent_ids"]:
            if r not in s["agents"]:
                raise ModelError(f"reviewer agent {r} does not exist")
        tid = task_id or next_id(s, "task")
        task = {"schema_version": SCHEMA_VERSION, "task_id": tid, "task_revision": 1, "project_id": s["project_id"],
                **fields, "status": "draft", "revisions": [], "flags": [],
                "base_state_revision": int(s.get("state_revision", 0)), "base_commit_sha": data.get("base_commit_sha", ""),
                "created_at": now_utc(), "updated_at": now_utc()}
        trial = dict(s["tasks"])
        trial[tid] = task
        problems = validate_graph(trial)
        if problems:
            raise ModelError("task graph rejected: " + "; ".join(problems))
        s["tasks"][tid] = task
        emit(s, "task_created", task_id=tid, origin=fields["origin"])
        if status != "draft":
            self._transition_in(s, tid, status, "created")
        return task

    def update(self, task_id: str, changes: dict[str, Any], *, reason: str = "") -> dict[str, Any]:
        """Edit fields. Contract changes create a revision; dependants are flagged."""
        for forbidden in ("task_id", "status", "task_revision", "project_id"):
            if forbidden in changes:
                raise ModelError(f"{forbidden} cannot be edited directly")
        with self.store.transaction("update task") as s:
            cur = require(s, "tasks", task_id)
            editable = {k: cur.get(k) for k in normalize_task({"title": "x", "objective": "x"})}
            merged = normalize_task({**editable, **changes})
            if merged == editable:
                return cur
            if merged["owner_agent_id"] and merged["owner_agent_id"] not in s["agents"]:
                raise ModelError(f"owner agent {merged['owner_agent_id']} does not exist")
            trial = dict(s["tasks"])
            trial[task_id] = {**cur, **merged}
            problems = validate_graph(trial)
            if problems:
                raise ModelError("task graph rejected: " + "; ".join(problems))
            new_rev = any(merged[k] != editable.get(k) for k in REVISION_FIELDS)
            if new_rev:
                snapshot = {k: cur.get(k) for k in REVISION_FIELDS}
                cur.setdefault("revisions", []).append({"task_revision": cur["task_revision"], "at": now_utc(),
                                                        "fields": copy.deepcopy(snapshot), "reason": reason[:500]})
                cur["task_revision"] = int(cur["task_revision"]) + 1
            contract_changed = any(merged[k] != editable.get(k) for k in CONTRACT_FIELDS)
            cur.update(merged)
            cur["updated_at"] = now_utc()
            emit(s, "task_updated", task_id=task_id, task_revision=cur["task_revision"], new_revision=new_rev)
            if contract_changed:
                for t in s["tasks"].values():
                    if task_id in t.get("depends_on", []):
                        flag = f"prerequisite {task_id} changed to revision {cur['task_revision']}; review this task"
                        if flag not in t["flags"]:
                            t["flags"].append(flag)
                            emit(s, "task_flagged", task_id=t["task_id"], flag=flag)
            self._refresh_readiness(s)
        return cur

    def transition(self, task_id: str, new_status: str, reason: str = "") -> dict[str, Any]:
        with self.store.transaction(f"task {task_id} -> {new_status}") as s:
            self._transition_in(s, task_id, new_status, reason)
            self._refresh_readiness(s)
            return s["tasks"][task_id]

    def _transition_in(self, s: dict[str, Any], task_id: str, new_status: str, reason: str) -> None:
        t = require(s, "tasks", task_id)
        check_transition("task", t["status"], new_status)
        if new_status == "ready":
            state, why = readiness(t, s["tasks"])
            if state != "ready":
                raise ModelError(f"{task_id} is not ready: {why}")
        if new_status == "done":
            raise ModelError("tasks become done only through the evidence policy (EvidenceService.evaluate_task)")
        if new_status == t["status"]:
            return
        old = t["status"]
        t["status"] = new_status
        t["updated_at"] = now_utc()
        if new_status == "blocked" and reason:
            t["blocked_reason"] = reason[:500]
        emit(s, "task_status", task_id=task_id, old=old, new=new_status, why=reason[:300])

    def clear_flag(self, task_id: str, flag: str) -> None:
        with self.store.transaction("clear task flag") as s:
            t = require(s, "tasks", task_id)
            if flag in t["flags"]:
                t["flags"].remove(flag)
                emit(s, "task_flag_cleared", task_id=task_id)

    @staticmethod
    def _refresh_readiness(s: dict[str, Any]) -> None:
        """Ready ⇄ blocked when prerequisites change; never touches started/terminal tasks."""
        for t in s["tasks"].values():
            if t["status"] not in ("ready", "blocked") or not t.get("depends_on"):
                continue
            if t["status"] == "blocked" and not str(t.get("blocked_reason", "")).startswith(("waiting for", "prerequisite")):
                continue
            state, why = readiness(t, s["tasks"])
            if state == t["status"] == "blocked" and why != t.get("blocked_reason"):
                t["blocked_reason"] = why
                emit(s, "task_status", task_id=t["task_id"], old="blocked", new="blocked", why=why)
            elif state != t["status"]:
                old = t["status"]
                t["status"] = state
                t["blocked_reason"] = why if state == "blocked" else ""
                t["updated_at"] = now_utc()
                emit(s, "task_status", task_id=t["task_id"], old=old, new=state, why=why or "prerequisites done")
