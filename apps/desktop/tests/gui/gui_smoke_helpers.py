"""Shared GUI smoke helpers for progress-backed startup/project preparation."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def wait_for_project_ready(app: Any, tk_root: Any, project: Path, timeout_seconds: float = 15.0) -> None:
    """Pump Tk until asynchronous baseline/Git setup has completed for this project."""
    key = str(project.resolve())
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        tk_root.update()
        state = app.project_version_baseline_state.get(key)
        if state == "ready":
            return
        if state == "failed":
            raise AssertionError(f"Project version baseline failed: {app.status_var.get()}")
        time.sleep(0.01)
    raise AssertionError(f"Project preparation timed out after {timeout_seconds:.1f}s; state={app.project_version_baseline_state.get(key)!r}")


def wait_for_idle(app: Any, tk_root: Any, timeout_seconds: float = 20.0) -> None:
    """Pump Tk until the worker, pending project-version records and follow-up Git refresh settle."""
    deadline = time.monotonic() + timeout_seconds
    # A completion callback may immediately schedule a second worker; require a short stable idle period.
    idle_since: float | None = None
    while time.monotonic() < deadline:
        tk_root.update()
        if not app.busy and app._pending_git_refresh is None and not getattr(app, "_pending_project_version_records", []):
            if idle_since is None:
                idle_since = time.monotonic()
            elif time.monotonic() - idle_since >= 0.25:
                return
        else:
            idle_since = None
        time.sleep(0.01)
    raise AssertionError(f"Background work did not settle after {timeout_seconds:.1f}s; status={app.status_var.get()!r}")
