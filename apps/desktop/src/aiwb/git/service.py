"""Safe, testable local Git command and status services.

This module deliberately knows nothing about Tkinter, Workbench settings, or
GitHub REST API credentials. Git authentication is delegated to Git's configured
credential helper (for example Git Credential Manager). Commands are always argv
based with ``shell=False`` and terminal prompting disabled for predictable GUI use.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .models import GitStatusEntry, GitStatusSnapshot


class GitCommandError(RuntimeError):
    """Safe-to-display failure raised by the Git service boundary."""


_DEFAULT_SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@"),
)


def redact_git_text(text: str) -> str:
    """Minimal fallback redaction for standalone use and unit tests."""
    result = text
    for pattern in _DEFAULT_SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)(https?"):
            result = pattern.sub(r"\1[REDACTED]@", result)
        else:
            result = pattern.sub("[REDACTED_SECRET]", result)
    return result


def quiet_subprocess_kwargs() -> dict[str, int]:
    """Avoid transient console windows when called from the Windows GUI."""
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def find_git_executable() -> str | None:
    """Find Git even if its installer changed PATH after this process started."""
    found = shutil.which("git") or shutil.which("git.exe")
    if found:
        return found
    candidates: list[Path] = []
    for key in ("ProgramFiles", "ProgramW6432"):
        value = os.environ.get(key)
        if value:
            base = Path(value)
            candidates.extend((base / "Git" / "cmd" / "git.exe", base / "Git" / "bin" / "git.exe"))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
        candidates.extend((base / "Programs" / "Git" / "cmd" / "git.exe", base / "Programs" / "Git" / "bin" / "git.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def parse_porcelain_v1_z(raw: str) -> tuple[GitStatusEntry, ...]:
    """Parse ``git status --porcelain=v1 -z`` without trimming path data.

    Workbench asks Git to disable rename detection for this compatibility path,
    so each NUL record is ``XY SP path``. Empty/malformed records are ignored as
    Git output may contain a final empty element after splitting on NUL.
    """
    entries: list[GitStatusEntry] = []
    for item in raw.split("\0"):
        if not item:
            continue
        if len(item) < 4 or item[2] != " ":
            continue
        status, path = item[:2], item[3:]
        if path:
            entries.append(GitStatusEntry(status=status, path=path))
    return tuple(entries)


class GitCommandRunner:
    """Injectable subprocess boundary for local Git commands."""

    def __init__(
        self,
        *,
        executable_provider: Callable[[], str | None] | None = None,
        subprocess_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        env_provider: Callable[[], dict[str, str]] | None = None,
        redactor: Callable[[str], str] | None = None,
        quiet_kwargs_provider: Callable[[], dict[str, int]] | None = None,
    ) -> None:
        self._executable_provider = executable_provider or find_git_executable
        self._subprocess_runner = subprocess_runner or subprocess.run
        self._env_provider = env_provider or (lambda: dict(os.environ))
        self._redact = redactor or redact_git_text
        self._quiet_kwargs_provider = quiet_kwargs_provider or quiet_subprocess_kwargs

    def executable(self) -> str | None:
        return self._executable_provider()

    def version_text(self) -> str:
        exe = self.executable()
        if not exe:
            return "Git not installed or not found"
        try:
            result = self._subprocess_runner(
                [exe, "--version"], capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=10, check=False, shell=False,
                **self._quiet_kwargs_provider(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return self._redact(f"Git found but version check failed: {exc}")
        if result.returncode != 0:
            return self._redact((result.stderr or result.stdout or "Git version check failed").strip())
        return self._redact((result.stdout or "").strip())

    def run(
        self,
        root: Path,
        args: Sequence[str],
        *,
        timeout: int = 30,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if isinstance(args, (str, bytes)) or not all(isinstance(arg, str) for arg in args):
            raise GitCommandError("Git arguments must be a sequence of strings.")
        if any("\x00" in arg for arg in args):
            raise GitCommandError("A Git argument contains an invalid NUL character.")
        try:
            root_arg = os.fspath(root)
        except TypeError as exc:
            raise GitCommandError("Git working root must be a filesystem path.") from exc
        if not isinstance(root_arg, str) or "\x00" in root_arg:
            raise GitCommandError("Git working root contains an invalid NUL character.")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0 or timeout > 3600:
            raise GitCommandError("Git command timeout must be between 1 and 3600 seconds.")
        exe = self.executable()
        if not exe:
            raise GitCommandError("Git was not found. Use the Install Git control in the Git / GitHub tab, or install Git for Windows and restart the app.")
        command = [exe, "-C", root_arg, *args]
        env = dict(self._env_provider())
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            return self._subprocess_runner(
                command,
                input=input_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
                env=env,
                **self._quiet_kwargs_provider(),
            )
        except subprocess.TimeoutExpired as exc:
            raise GitCommandError(f"Git command timed out after {timeout} seconds.") from exc
        except OSError as exc:
            raise GitCommandError(self._redact(f"Git execution failed: {exc}")) from exc


class GitService:
    """Local Git operations used by AI Workbench's GUI and future workflows."""

    def __init__(self, runner: GitCommandRunner | None = None, *, redactor: Callable[[str], str] | None = None) -> None:
        self.runner = runner or GitCommandRunner(redactor=redactor)
        self._redact = redactor or redact_git_text

    def find_executable(self) -> str | None:
        return self.runner.executable()

    def quiet_kwargs(self) -> dict[str, int]:
        return quiet_subprocess_kwargs()

    def version_text(self) -> str:
        return self.runner.version_text()

    def run(self, root: Path, args: Sequence[str], timeout: int = 30, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return self.runner.run(root, args, timeout=timeout, input_text=input_text)

    def require(self, root: Path, args: Sequence[str], timeout: int = 30) -> str:
        result = self.run(root, args, timeout=timeout)
        if result.returncode != 0:
            detail = self._redact((result.stderr or result.stdout or "").strip())
            raise GitCommandError(detail or f"Git exited with code {result.returncode}.")
        return result.stdout.strip()

    @staticmethod
    def parse_status(raw: str) -> tuple[GitStatusEntry, ...]:
        return parse_porcelain_v1_z(raw)

    def status_snapshot(self, root: Path) -> GitStatusSnapshot:
        canonical_root = Path(root).resolve()
        inside = self.run(canonical_root, ["rev-parse", "--is-inside-work-tree"])
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return GitStatusSnapshot(canonical_root, False, "(not a Git repository)", "(none)", ())
        branch_result = self.run(canonical_root, ["branch", "--show-current"])
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "(unknown)"
        remote_result = self.run(canonical_root, ["remote", "get-url", "origin"])
        remote = self._redact(remote_result.stdout.strip()) if remote_result.returncode == 0 else "(origin not configured)"
        status_result = self.run(canonical_root, ["-c", "status.renames=false", "status", "--porcelain=v1", "--untracked-files=all", "-z"])
        if status_result.returncode != 0:
            detail = self._redact(status_result.stderr.strip() or "Failed to read Git status.")
            raise GitCommandError(detail)
        return GitStatusSnapshot(canonical_root, True, branch, remote, self.parse_status(status_result.stdout))

    def status_info(self, root: Path) -> dict[str, object]:
        return self.status_snapshot(root).to_legacy_dict()

    def changed_paths(self, root: Path) -> list[str]:
        # Do not use require(): strip() would corrupt valid leading/trailing
        # whitespace in NUL-delimited status output and damage valid filenames.
        result = self.run(root, ["-c", "status.renames=false", "status", "--porcelain=v1", "--untracked-files=all", "-z"])
        if result.returncode != 0:
            detail = self._redact(result.stderr.strip() or "Failed to read Git status.")
            raise GitCommandError(detail)
        return [entry.path for entry in self.parse_status(result.stdout)]


def parse_git_status_porcelain(raw: str) -> list[tuple[str, str]]:
    """Compatibility adapter preserving the historic tuple-list API."""
    return [entry.as_legacy_tuple() for entry in parse_porcelain_v1_z(raw)]
