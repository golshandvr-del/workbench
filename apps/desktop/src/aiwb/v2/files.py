"""Project files: stage delivered files, integrate them after the user's approval (roadmap 4.3.0, flowchart F16–F17).

* ``stage`` keeps the files of a pasted answer on its handoff (``staged_files``) — only safe paths inside the task's
  allowed paths; nothing touches the disk.
* ``integrate`` runs after the user accepted the delivery (F16): every staged file is written into the project
  folder atomically, the old content is kept under ``.workbench/v2/backups/<handoff>/`` and ``files_integrated`` goes
  to the timeline (F17). The staged bodies are dropped from the state afterwards (path + sha256 stay).
* ``safe_path`` is the one rule for every write and every ZIP entry: relative, no ``..``, no drive letter, nothing
  under ``.git`` / ``.workbench``. The phone (``core/Files.kt``) checks the same fixture
  ``packages/contracts/fixtures/files/safe-paths.v1.json``.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import zipfile
import uuid

from aiwb.intake.answer_files import safe_path
from .file_transaction import FileTransactionError, transaction
from .models import ModelError
from pathlib import Path
from typing import Any

from .diagnose import _in_scope, parse_files, task_paths
from .models import now_utc
from .store import emit

MAX_FILE = 512 * 1024
MAX_TOTAL = 8 * 1024 * 1024
RESERVED = (".git", ".workbench")


def stage(store: Any, handoff_id: str, text: str) -> list[dict[str, Any]]:
    """Keep the safe, in-scope files of a pasted answer on the handoff (replacing earlier staging)."""
    files, _open = parse_files(text)
    with store.transaction("stage files") as s:
        h = s["handoffs"][handoff_id]
        allowed = task_paths(s["tasks"].get(h["task_id"]) or {})
        staged: list[dict[str, Any]] = []
        total = 0
        for f in files:
            p = safe_path(f["path"])
            body = f["body"] + ("\n" if f["body"] and not f["body"].endswith("\n") else "")
            size = len(body.encode("utf-8"))
            if not p or not _in_scope(p, allowed) or not body.strip() or size > MAX_FILE or total + size > MAX_TOTAL:
                continue
            total += size
            staged = [x for x in staged if x["path"] != p]
            staged.append({"path": p, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "size": size,
                           "content": body})
        h["staged_files"] = staged
        return [{k: v for k, v in x.items() if k != "content"} for x in staged]


def integrate(store: Any, root: Path, handoff_id: str, *, accept_reason: str | None = None) -> list[str]:
    """Publish all staged files, then commit integration and optional acceptance together.

    File/state failures roll back published files and retain the open handoff bodies
    for retry. Acceptance uses the same lifecycle rules as the direct service API.
    """
    from .handoff import HandoffService
    root = Path(root).resolve()
    if safe_path(handoff_id) != handoff_id or "/" in handoff_id:
        raise ModelError("Invalid handoff backup identity")
    h = store.load()["handoffs"].get(handoff_id)
    if h is None:
        raise ModelError(f"Unknown handoff {handoff_id}")
    staged = [x for x in h.get("staged_files") or [] if x.get("content") is not None]
    if not staged and accept_reason is None:
        return []
    backup = root / ".workbench" / "v2" / "backups" / handoff_id
    if backup.exists():
        backup = backup.with_name(handoff_id + "-" + uuid.uuid4().hex)
    try:
        with transaction(root, staged, backup):
            written = [f["path"] for f in staged]
            # This state commit is INSIDE the filesystem rollback boundary.
            with store.transaction("integrate and accept files") as s:
                hh = s["handoffs"][handoff_id]
                if hh != h:
                    raise ModelError("The delivery changed during integration; review it again")
                if accept_reason is not None:
                    HandoffService.resolve_state(s, handoff_id, True, accept_reason)
                hh["staged_files"] = [{k: v for k, v in x.items() if k != "content"} for x in hh.get("staged_files") or []]
                hh["integrated_files"] = written
                hh["integration_backup"] = backup.relative_to(root).as_posix()
                hh["integrated_at"] = now_utc()
                emit(s, "files_integrated", handoff_id=handoff_id, task_id=hh["task_id"], paths=written[:50],
                     count=len(written), importance="major")
        return written
    except (OSError, FileTransactionError) as exc:
        raise ModelError(str(exc)) from exc


def list_files(root: Path) -> list[dict[str, Any]]:
    """Project files (without .git / .workbench), sorted, with sizes."""
    root = Path(root)
    out = []
    for f in sorted(root.rglob("*")):
        if f.is_file():
            rel = f.relative_to(root).as_posix()
            if safe_path(rel) == rel:
                out.append({"path": rel, "size": f.stat().st_size})
    return out


def zip_files(root: Path) -> bytes:
    """Every project file as one ZIP (deterministic order and timestamps)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in list_files(root):
            info = zipfile.ZipInfo(f["path"], date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, (Path(root) / f["path"]).read_bytes())
    return buf.getvalue()


def unzip_files(root: Path, data: bytes) -> list[str]:
    """Extract a ZIP into ``root``; refuses the whole archive if any entry is unsafe (zip-slip)."""
    root = Path(root).resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        bad = [n for n in names if safe_path(n) != n.strip("/")]
        if bad:
            raise ValueError(f"unsafe ZIP entries: {', '.join(bad[:5])}")
        if sum(i.file_size for i in z.infolist()) > MAX_TOTAL * 4:
            raise ValueError("ZIP too large")
        for n in names:
            t = root / safe_path(n)
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_bytes(z.read(n))
    return [safe_path(n) for n in names]
