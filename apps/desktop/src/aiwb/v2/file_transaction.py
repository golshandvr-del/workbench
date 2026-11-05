"""Shared filesystem boundary for V5.22 Quick and guided deliveries.

Preflight the entire set, keep immutable backup bytes and a durable manifest before
publication, and roll back if publication OR the caller's state commit fails.
Backups are retained on failure for manual recovery; callers never reuse a folder.
This is exception-atomic, not a cross-filesystem/database power-loss transaction.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from aiwb.intake.answer_files import safe_path


class FileTransactionError(ValueError):
    """An actionable file error, including any incomplete rollback paths."""


def sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def checked_path(root: Path, relative: str, *, internal: bool = False) -> Path:
    """Reject links/reparse points, non-directory parents, Windows aliases and escapes."""
    root = Path(root).resolve()
    parts = relative.replace("\\", "/").split("/")
    # Internal backup paths may start with .workbench, but use the same component rules.
    probe = "/".join(["internal", *parts[1:]]) if internal and parts[0] == ".workbench" else relative
    if safe_path(probe) != probe or not parts:
        raise FileTransactionError(f"Unsafe path refused: {relative}")
    current = root
    for index, part in enumerate(parts):
        if current.is_dir():
            twins = [p.name for p in current.iterdir() if p.name.casefold() == part.casefold() and p.name != part]
            if twins:
                raise FileTransactionError(f"Path conflicts with existing Windows name: {relative} ({twins[0]})")
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise FileTransactionError(f"Path goes through a link or junction: {relative}")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise FileTransactionError(f"Path parent is not a folder: {relative}")
    if root not in current.resolve().parents:
        raise FileTransactionError(f"Path escapes the project: {relative}")
    return current


def preflight(root: Path, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Capture exact bytes and enforce preview hashes, duplicates and prefix conflicts."""
    paths: set[str] = set()
    components: dict[str, str] = {}
    rows = []
    for change in changes:
        rel = change["path"]
        key = rel.casefold()
        if key in paths or any(key.startswith(p + "/") or p.startswith(key + "/") for p in paths):
            raise FileTransactionError(f"Conflicting delivered paths: {rel}")
        paths.add(key)
        parts = rel.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            previous = components.setdefault(prefix.casefold(), prefix)
            if previous != prefix:
                raise FileTransactionError(f"Conflicting Windows path spelling: {previous} / {prefix}")
        target = checked_path(root, rel)
        if target.exists() and not target.is_file():
            raise FileTransactionError(f"Destination is not a regular file: {rel}")
        before = target.read_bytes() if target.exists() else None
        if "before_sha" in change and sha(before) != change["before_sha"]:
            raise FileTransactionError(f"{rel} changed since the preview — review again before applying.")
        body = change.get("bytes", change.get("content"))
        after = body.encode("utf-8") if isinstance(body, str) else body
        if after is not None and not isinstance(after, bytes):
            raise FileTransactionError(f"Invalid file content: {rel}")
        rows.append({"path": rel, "before": before, "after": after, "before_sha": sha(before),
                     "after_sha": sha(after), "existed": before is not None})
    return rows


def atomic_bytes(target: Path, content: bytes) -> None:
    """Exclusive, same-folder temporary file; flush before atomic replacement."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".aiwb-", suffix=".aiwb-tmp", dir=target.parent, delete=False) as f:
            temp = Path(f.name)
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, target)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


@contextmanager
def transaction(root: Path, changes: list[dict[str, Any]], backup: Path) -> Iterator[list[dict[str, Any]]]:
    """Publish files and keep rollback active until the caller commits its state.

    Backup manifest records pre/post hashes and exact original files. On crash it
    is independent of application state and available for recovery. A successful
    context exit requires no further filesystem write that could hide a state commit.
    """
    root = Path(root).resolve()
    touched: list[dict[str, Any]] = []
    created_dirs: list[Path] = []
    where = "preflight"
    try:
        rows = preflight(root, changes)
        rel_backup = backup.relative_to(root).as_posix()
        checked_path(root, rel_backup, internal=True)
        backup.mkdir(parents=True, exist_ok=False)
        for row in rows:
            if row["before"] is not None:
                dest = backup / row["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation: original backup bytes must never be replaced.
                with dest.open("xb") as f:
                    f.write(row["before"])
                    f.flush()
                    os.fsync(f.fileno())
        manifest = {"schema_version": 1, "status": "prepared", "files": [
            {k: r[k] for k in ("path", "existed", "before_sha", "after_sha")} for r in rows]}
        # The delivered project may itself contain transaction.json (or any fixed
        # journal name); choose metadata outside the delivered namespace by identity.
        journal = backup / (".aiwb-transaction-" + uuid.uuid4().hex + ".json")
        with journal.open("x", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        # No file in the project is changed until ALL backups are complete.
        for row in rows:
            where = row["path"]
            target = checked_path(root, where)
            current = target.read_bytes() if target.exists() else None
            if sha(current) != row["before_sha"]:
                raise FileTransactionError(f"{where} changed since the preview — review again.")
            if row["after"] is None:
                target.unlink(missing_ok=True)
            else:
                missing = []
                parent = target.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                for parent in reversed(missing):
                    parent.mkdir()
                    created_dirs.append(parent)
                atomic_bytes(target, row["after"])
            touched.append(row)
        where = "saving project state"
        yield rows
    except Exception as exc:
        rollback_errors = []
        for row in reversed(touched):
            try:
                target = checked_path(root, row["path"])
                current = target.read_bytes() if target.exists() else None
                if sha(current) != row["after_sha"]:
                    raise FileTransactionError("changed during rollback; kept newer bytes")
                if row["before"] is None:
                    target.unlink(missing_ok=True)
                else:
                    atomic_bytes(target, row["before"])
            except Exception as rollback_exc:
                rollback_errors.append(f"{row['path']}: {rollback_exc}")
        for parent in reversed(created_dirs):
            try:
                parent.rmdir()
            except OSError:
                pass  # Do not remove directories containing concurrent user files.
        detail = (" Rollback incomplete: " + "; ".join(rollback_errors)) if rollback_errors else " No partial file changes retained."
        raise FileTransactionError(f"Could not write {where}: {exc}.{detail} Backups: {backup}. Close programs using the files and retry.") from exc
