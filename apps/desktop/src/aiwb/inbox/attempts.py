"""Attempt registry: every exported prompt gets a stable ``attempt_id`` (roadmap 1.16.0).

Stored in ``.workbench/inbox/attempts.json``. The prompt carries an identity line
``AIWB_ATTEMPT_ID: att-…`` that the model is asked to repeat, so a pasted answer
can be matched to the task, task revision and project base revision it was
produced for (used for stale / wrong-task detection in 1.16.1).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .store import SCHEMA_VERSION, atomic_write

ATTEMPT_ID_RE = re.compile(r"\batt-\d{8}-\d{6}-[0-9a-f]{8}\b")
DECLARED_RE = re.compile(r"(?im)^[\W_]{0,6}AIWB_ATTEMPT_ID[*_`\s]{0,4}[:=][*_`\s]{0,4}[\"']?(att-\d{8}-\d{6}-[0-9a-f]{8})")
MAX_ATTEMPTS = 500
STATUSES = ("sent", "answered", "applied", "abandoned")


@dataclass
class Attempt:
    attempt_id: str
    task_id: str
    task_revision: str
    base_revision: str
    created_at: str
    kind: str = "implementation"        # implementation | repair | context
    parent_attempt_id: str = ""
    expected_paths: list[str] = field(default_factory=list)
    status: str = "sent"
    schema_version: int = SCHEMA_VERSION


def declared_attempt_id(text: str) -> str:
    m = DECLARED_RE.search(text or "")
    return m.group(1) if m else ""


def prompt_identity_block(attempt: Attempt) -> str:
    return ("AIWB_ATTEMPT_ID: " + attempt.attempt_id + "\n"
            "(Repeat the line above as the first line of your answer so AI Workbench can match it to this task.)")


class AttemptRegistry:
    def __init__(self, project_root: Path) -> None:
        self.path = Path(project_root) / ".workbench" / "inbox" / "attempts.json"
        self._lock = threading.RLock()

    def _load(self) -> list[Attempt]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = []
        for d in data.get("attempts", []) if isinstance(data, dict) else []:
            try:
                out.append(Attempt(**{k: d[k] for k in Attempt.__dataclass_fields__ if k in d}))
            except TypeError:
                continue
        return out

    def _save(self, items: list[Attempt]) -> None:
        body = {"schema_version": SCHEMA_VERSION, "attempts": [asdict(a) for a in items[-MAX_ATTEMPTS:]]}
        atomic_write(self.path, json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"))

    def new(self, *, task_id: str, task_revision: str, base_revision: str, kind: str = "implementation",
            parent_attempt_id: str = "", expected_paths: list[str] | None = None) -> Attempt:
        now = datetime.now(timezone.utc)
        a = Attempt("att-" + now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8], task_id, task_revision,
                    base_revision, now.isoformat(timespec="seconds"), kind, parent_attempt_id,
                    sorted(set(expected_paths or [])))
        with self._lock:
            items = self._load()
            items.append(a)
            self._save(items)
        return a

    def get(self, attempt_id: str) -> Attempt | None:
        with self._lock:
            return next((a for a in self._load() if a.attempt_id == attempt_id), None)

    def latest_for_task(self, task_id: str) -> Attempt | None:
        with self._lock:
            return next((a for a in reversed(self._load()) if a.task_id == task_id), None)

    def mark(self, attempt_id: str, status: str) -> Attempt | None:
        if status not in STATUSES:
            raise ValueError(status)
        with self._lock:
            items = self._load()
            for a in items:
                if a.attempt_id == attempt_id:
                    a.status = status
                    self._save(items)
                    return a
        return None

    def list(self) -> list[Attempt]:
        with self._lock:
            return list(reversed(self._load()))

    def to_dicts(self) -> list[dict[str, Any]]:
        return [asdict(a) for a in self.list()]
