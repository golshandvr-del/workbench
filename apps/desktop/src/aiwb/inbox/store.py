"""Raw response storage — the Inbox (roadmap 1.16.0).

Rule: the raw input is stored byte-for-byte *before* any parsing, with a stable
``response_id``. Parse results are stored separately (append-only) so a parser
bug never destroys the original and a response can be re-parsed later without
asking the model again. Everything lives under ``<project>/.workbench/inbox``,
which is excluded from Git by the app.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
MAX_RAW_BYTES = 12 * 1024 * 1024
MAX_PARSE_RESULTS = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@dataclass
class RawResponse:
    response_id: str
    sha256: str
    size: int
    source: str
    captured_at: str
    attempt_id: str = ""            # attempt the user/app linked at capture time
    declared_attempt_id: str = ""   # AIWB_ATTEMPT_ID found inside the text
    task_id: str = ""
    status: str = "captured"        # captured | parsed | partial | failed
    parse_results: list[dict[str, Any]] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "RawResponse | None":
        try:
            r = RawResponse(
                response_id=str(d["response_id"]), sha256=str(d["sha256"]), size=int(d["size"]),
                source=str(d.get("source", "")), captured_at=str(d.get("captured_at", "")),
                attempt_id=str(d.get("attempt_id", "")), declared_attempt_id=str(d.get("declared_attempt_id", "")),
                task_id=str(d.get("task_id", "")), status=str(d.get("status", "captured")),
                parse_results=[x for x in d.get("parse_results", []) if isinstance(x, dict)],
                schema_version=int(d.get("schema_version", 1)),
            )
        except (KeyError, TypeError, ValueError):
            return None
        return r


class InboxStore:
    def __init__(self, project_root: Path) -> None:
        self.root = Path(project_root) / ".workbench" / "inbox"
        self.raw_dir = self.root / "responses"
        self.index_path = self.root / "index.json"
        self._lock = threading.RLock()

    # -- index
    def _load(self) -> list[RawResponse]:
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("responses", []) if isinstance(data, dict) else []
        return [r for r in (RawResponse.from_dict(x) for x in items if isinstance(x, dict)) if r]

    def _save(self, items: list[RawResponse]) -> None:
        body = {"schema_version": SCHEMA_VERSION, "responses": [asdict(r) for r in items]}
        atomic_write(self.index_path, json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"))

    # -- API
    def capture(self, raw: bytes | str, *, source: str, attempt_id: str = "", declared_attempt_id: str = "",
                task_id: str = "") -> tuple[RawResponse, bool]:
        """Store the raw bytes first. Returns ``(record, duplicate)``; an identical
        response is never stored twice."""
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        if len(data) > MAX_RAW_BYTES:
            raise ValueError("too_large")
        digest = hashlib.sha256(data).hexdigest()
        with self._lock:
            items = self._load()
            for r in items:
                if r.sha256 == digest:
                    return r, True
            rid = "resp-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
            atomic_write(self.raw_dir / f"{rid}.raw", data)
            rec = RawResponse(rid, digest, len(data), source[:200], _now(), attempt_id, declared_attempt_id, task_id)
            items.append(rec)
            self._save(items)
            return rec, False

    def read_raw(self, response_id: str) -> bytes:
        if not response_id.startswith("resp-") or "/" in response_id or "\\" in response_id or ".." in response_id:
            raise ValueError("invalid response id")
        data = (self.raw_dir / f"{response_id}.raw").read_bytes()
        rec = self.get(response_id)
        if rec and hashlib.sha256(data).hexdigest() != rec.sha256:
            raise ValueError("raw response file does not match its recorded SHA-256")
        return data

    def read_text(self, response_id: str) -> str:
        return self.read_raw(response_id).decode("utf-8", errors="replace")

    def get(self, response_id: str) -> RawResponse | None:
        with self._lock:
            return next((r for r in self._load() if r.response_id == response_id), None)

    def update(self, response_id: str, **changes: Any) -> RawResponse | None:
        with self._lock:
            items = self._load()
            for r in items:
                if r.response_id == response_id:
                    for k, v in changes.items():
                        if k in ("response_id", "sha256", "size", "captured_at", "schema_version"):
                            raise ValueError(f"{k} is immutable")
                        setattr(r, k, v)
                    self._save(items)
                    return r
            return None

    def add_parse_result(self, response_id: str, result: dict[str, Any]) -> RawResponse | None:
        """Append a parse result (never overwrites the raw input)."""
        with self._lock:
            items = self._load()
            for r in items:
                if r.response_id == response_id:
                    entry = {"schema_version": SCHEMA_VERSION, "at": _now(), **result}
                    r.parse_results = (r.parse_results + [entry])[-MAX_PARSE_RESULTS:]
                    r.status = str(result.get("status", r.status))
                    self._save(items)
                    return r
            return None

    def list(self) -> list[RawResponse]:
        with self._lock:
            return list(reversed(self._load()))

    def for_attempt(self, attempt_id: str) -> list[RawResponse]:
        return [r for r in self.list() if attempt_id and attempt_id in (r.attempt_id, r.declared_attempt_id)]

    def ids(self) -> Iterable[str]:
        return (r.response_id for r in self.list())
