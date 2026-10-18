"""Single local source of truth for V2 project state (roadmap 1.17.0 / slice 2A).

``.workbench/v2/state.json`` holds every V2 entity. All writes go through
:meth:`ProjectStore.transaction`, which loads, lets the caller mutate, bumps
``state_revision`` once, appends events and writes atomically (temp file +
``os.replace``). A failed transaction leaves the file untouched.

Migration is versioned (``db_version``), backed up before upgrading, idempotent
and never deletes old data: unknown fields are preserved, legacy task state and
Response-Inbox attempts are linked as ``legacy`` records.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .models import PREFIX, SCHEMA_VERSION, ModelError, now_utc

DB_VERSION = 1
MAX_EVENTS = 2000
COLLECTIONS = ("agents", "tasks", "attempts", "handoffs", "decisions", "evidence", "proposals", "artifacts")
DEFAULT_SETTINGS = {
    "repair_round_limit": 3,
    "publish": {"enabled": False, "branch": "aiwb-state", "path": ".aiwb", "interval_minutes": 15,
                "include_task_details": True},
}

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve()) if path.parent.exists() else str(path)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def empty_state(project_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "db_version": DB_VERSION,
        "project_id": project_id,
        "created_at": now_utc(),
        "state_revision": 0,
        "counters": {p: 0 for p in PREFIX.values()},
        **{c: {} for c in COLLECTIONS},
        "events": [],
        "settings": copy.deepcopy(DEFAULT_SETTINGS),
        "migrations": [],
    }


class StoreError(RuntimeError):
    pass


class ProjectStore:
    def __init__(self, project_root: Path, project_id: str = "") -> None:
        self.root = Path(project_root)
        self.dir = self.root / ".workbench" / "v2"
        self.path = self.dir / "state.json"
        self.project_id = project_id or self._default_project_id()
        self._lock = _lock_for(self.path)

    def _default_project_id(self) -> str:
        name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in self.root.name.lower()).strip("-")
        return name[:60] or "project"

    # -- read
    def _read_raw(self) -> dict[str, Any] | None:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise StoreError(f"V2 state file is corrupt ({exc}); a backup is kept next to it. "
                             "Restore a backup from .workbench/v2/backups or move the file away.") from exc
        if not isinstance(data, dict):
            raise StoreError("V2 state file is not a JSON object")
        return data

    def load(self) -> dict[str, Any]:
        """Return a deep copy of the current state (migrated in memory if needed; never written here)."""
        with self._lock:
            data = self._read_raw()
            if data is None:
                return empty_state(self.project_id)
            return migrate_state(data, self.project_id)[0]

    @property
    def revision(self) -> int:
        return int(self.load().get("state_revision", 0))

    # -- write
    def _write(self, data: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        if self.dir.is_symlink():
            raise StoreError(".workbench/v2 is a symbolic link; refusing to write")
        fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=str(self.dir))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def backup(self, label: str) -> Path | None:
        if not self.path.exists():
            return None
        bdir = self.dir / "backups"
        bdir.mkdir(parents=True, exist_ok=True)
        target = bdir / f"state-{now_utc().replace(':', '').replace('-', '')}-{label}.json"
        n = 1
        while target.exists():
            target = bdir / f"{target.stem}-{n}.json"
            n += 1
        shutil.copy2(self.path, target)
        return target

    def ensure_migrated(self, *, legacy_loader: Callable[[], dict[str, Any]] | None = None) -> list[str]:
        """Persist migrations (with a backup first). Safe to call any number of times."""
        with self._lock:
            raw = self._read_raw()
            if raw is None:
                state = empty_state(self.project_id)
                notes = ["created"]
            else:
                state, notes = migrate_state(raw, self.project_id)
            legacy = legacy_loader() if legacy_loader else {}
            notes += link_legacy(state, legacy)
            if notes:
                if raw is not None:
                    self.backup("pre-migration")
                state["migrations"].append({"at": now_utc(), "notes": notes, "db_version": DB_VERSION})
                self._write(state)
            return notes

    @contextmanager
    def transaction(self, reason: str) -> Iterator[dict[str, Any]]:
        """Mutate a working copy; on success write once with state_revision + 1."""
        with self._lock:
            raw = self._read_raw()
            state = empty_state(self.project_id) if raw is None else migrate_state(raw, self.project_id)[0]
            before = json.dumps(state, sort_keys=True)
            work = copy.deepcopy(state)
            work["_pending_events"] = []
            yield work
            events = work.pop("_pending_events", [])
            if json.dumps(work, sort_keys=True) == before and not events:
                return
            work["state_revision"] = int(state.get("state_revision", 0)) + 1
            stamp = now_utc()
            for e in events or [{"type": "change"}]:
                e.setdefault("at", stamp)
                e["state_revision"] = work["state_revision"]
                e["reason"] = reason
                work["events"].append(e)
            work["events"] = work["events"][-MAX_EVENTS:]
            self._write(work)


def emit(state: dict[str, Any], event_type: str, **fields: Any) -> None:
    state.setdefault("_pending_events", []).append({"type": event_type, **fields})


def next_id(state: dict[str, Any], kind: str) -> str:
    prefix = PREFIX[kind]
    counters = state.setdefault("counters", {})
    existing = state.get(kind + "s" if kind != "evidence" else "evidence", {})
    n = int(counters.get(prefix, 0)) + 1
    while f"{prefix}-{n:04d}" in existing:
        n += 1
    counters[prefix] = n
    return f"{prefix}-{n:04d}"


def migrate_state(data: dict[str, Any], project_id: str) -> tuple[dict[str, Any], list[str]]:
    """Bring any older/partial state up to DB_VERSION without dropping fields."""
    state = copy.deepcopy(data)
    notes: list[str] = []
    version = state.get("db_version", 0)
    if not isinstance(version, int) or version < 0:
        raise StoreError(f"invalid db_version {version!r}")
    if version > DB_VERSION:
        raise StoreError(f"V2 state was written by a newer AI Workbench (db_version {version} > {DB_VERSION}). "
                         "Update the app; the file was not changed.")
    base = empty_state(state.get("project_id") or project_id)
    for key, default in base.items():
        if key not in state or (key in COLLECTIONS and not isinstance(state[key], dict)):
            if key in state and key in COLLECTIONS:
                state.setdefault("_quarantine", {})[key] = state[key]
                notes.append(f"quarantined malformed '{key}'")
            state[key] = default
            if key not in ("created_at",) and version:
                notes.append(f"added missing '{key}'")
    for k, v in DEFAULT_SETTINGS.items():
        if k not in state["settings"]:
            state["settings"][k] = copy.deepcopy(v)
    if not isinstance(state.get("events"), list):
        state["events"] = []
    for prefix in PREFIX.values():
        state["counters"].setdefault(prefix, 0)
    if version < 1:
        state["db_version"] = 1
        notes.append("migrated to db_version 1")
    return state, notes


def link_legacy(state: dict[str, Any], legacy: dict[str, Any]) -> list[str]:
    """Attach pre-V2 task state and Inbox attempts as legacy records (idempotent)."""
    notes: list[str] = []
    task = legacy.get("task_state") or {}
    legacy_task_id = str(task.get("task_id", "")).strip()
    linked_task = ""
    if legacy_task_id:
        for tid, t in state["tasks"].items():
            if t.get("legacy_task_id") == legacy_task_id:
                linked_task = tid
                break
        if not linked_task:
            linked_task = next_id(state, "task")
            text = str(task.get("task_text", "")).strip() or "Legacy task"
            state["tasks"][linked_task] = {
                "schema_version": SCHEMA_VERSION, "task_id": linked_task, "task_revision": 1,
                "project_id": state["project_id"], "title": text.splitlines()[0][:200], "objective": text[:4000],
                "task_type": "implementation", "owner_agent_id": "", "reviewer_agent_ids": [], "depends_on": [],
                "scope": {"include": [], "exclude": []}, "acceptance_criteria": [], "acceptance_policy": "manual_review",
                "deliverables": [], "context_refs": [], "priority": "medium", "risk_level": "medium",
                "required_approvals": ["review"], "origin": "migration", "status": "in_progress",
                "legacy_task_id": legacy_task_id, "revisions": [], "flags": [],
                "created_at": task.get("task_started_at") or now_utc(), "updated_at": now_utc(),
                "base_state_revision": 0, "base_commit_sha": "",
            }
            notes.append(f"linked legacy task {legacy_task_id} as {linked_task}")
    for att in legacy.get("attempts") or []:
        aid = att.get("attempt_id")
        if not aid or aid in state["attempts"]:
            continue
        tid = linked_task if linked_task and att.get("task_id") == legacy_task_id else ""
        status = {"sent": "exported", "answered": "response_received", "applied": "accepted",
                  "abandoned": "abandoned"}.get(att.get("status"), "exported")
        state["attempts"][aid] = {
            "schema_version": SCHEMA_VERSION, "attempt_id": aid, "task_id": tid, "task_revision": 1 if tid else 0,
            "agent_id": "", "handoff_id": "", "kind": att.get("kind", "implementation"),
            "parent_attempt_id": att.get("parent_attempt_id", ""), "status": status, "legacy": True,
            "legacy_task_id": att.get("task_id", ""), "base_state_revision": 0,
            "base_revision": att.get("base_revision", ""), "response_ids": [],
            "created_at": att.get("created_at") or now_utc(), "updated_at": now_utc(),
        }
        notes.append(f"linked legacy attempt {aid}")
    return notes


def require(state: dict[str, Any], collection: str, entity_id: str) -> dict[str, Any]:
    item = state[collection].get(entity_id)
    if item is None:
        raise ModelError(f"{collection[:-1] if collection != 'evidence' else 'evidence'} {entity_id} does not exist")
    return item
