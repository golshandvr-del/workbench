"""Typed, UI-independent value objects for local Git operations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class GitStatusEntry:
    """One entry from Git's NUL-delimited porcelain-v1 status output.

    ``status`` is the two-character XY status exactly as emitted by Git. ``path``
    is kept byte-decoded but otherwise unchanged; leading/trailing whitespace,
    newlines, Unicode and unusual but valid path characters must not be stripped.
    """

    status: str
    path: str

    @property
    def index_status(self) -> str:
        return self.status[0] if self.status else " "

    @property
    def worktree_status(self) -> str:
        return self.status[1] if len(self.status) > 1 else " "

    @property
    def is_untracked(self) -> bool:
        return self.status == "??"

    @property
    def is_deleted(self) -> bool:
        return "D" in self.status

    def as_legacy_tuple(self) -> tuple[str, str]:
        """Preserve the tuple format consumed by the v1.14.0 GUI."""
        return (self.status, self.path)


@dataclass(frozen=True, slots=True)
class GitStatusSnapshot:
    """Immutable snapshot of the local repository state at one observation time."""

    root: Path
    is_repo: bool
    branch: str
    remote: str
    entries: tuple[GitStatusEntry, ...] = ()

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(entry.path for entry in self.entries)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return the stable v1.14.0 shape for existing UI/report code."""
        return {
            "is_repo": self.is_repo,
            "branch": self.branch,
            "remote": self.remote,
            "entries": [entry.as_legacy_tuple() for entry in self.entries],
        }
