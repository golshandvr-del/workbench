#!/usr/bin/env python3
"""GUI smoke for the v1.14.6 Build Center window (needs a display).

Uses a fake GitHub transport (no network): checks workflow discovery with
dispatch state, stale binding warning, run list, HEAD correlation that refuses
to present an older commit's run, failed-step rendering, Cancel gating and that
the Tk loop keeps running while a slow request is in flight.
"""
from __future__ import annotations

import base64
import json
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))

import tkinter as tk  # noqa: E402

from aiwb.github.actions import GitHubActionsService, PollPolicy  # noqa: E402
from aiwb.github.api_client import GitHubApiClient, HttpResponse  # noqa: E402
from aiwb.github.build_center import BuildCenterWindow  # noqa: E402

TOKEN = "github_pat_" + "S" * 40
OLD, NEW = "1" * 40, "2" * 40


def j(value: object, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {}, json.dumps(value).encode())


def b64(text: str) -> HttpResponse:
    return j({"encoding": "base64", "content": base64.b64encode(text.encode()).decode()})


def run(i: int, sha: str, status: str, conclusion: str | None) -> dict:
    t = f"2026-10-17T1{i}:00:00Z"
    return {"id": 100 + i, "workflow_id": 1, "name": "CI", "event": "push", "status": status, "conclusion": conclusion,
            "head_branch": "feat", "head_sha": sha, "run_number": i, "run_attempt": 1, "created_at": t, "updated_at": t,
            "run_started_at": t, "html_url": f"https://github.com/o/r/actions/runs/{100 + i}"}


class Fake:
    def __init__(self) -> None:
        self.slow = threading.Event()
        self.calls: list[str] = []
        self.runs = [run(1, OLD, "completed", "failure"), run(2, OLD, "completed", "cancelled")]

    def __call__(self, url: str, headers: dict, timeout: float) -> HttpResponse:
        self.calls.append(url)
        if self.slow.is_set():
            time.sleep(1.0)
        path = urlsplit(url).path
        if path == "/repos/o/r/actions/workflows":
            return j({"workflows": [
                {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active", "html_url": "https://github.com/o/r"},
                {"id": 2, "name": "Release", "path": ".github/workflows/release.yml", "state": "active", "html_url": "https://github.com/o/r"},
            ]})
        if path.endswith("/ci.yml"):
            return b64("on:\n  push:\n  workflow_dispatch:\n")
        if path.endswith("/release.yml"):
            return b64("on:\n  push:\n    tags: ['v*']\n")
        if path.endswith("/runs"):
            return j({"workflow_runs": self.runs})
        if path.endswith("/jobs"):
            return j({"jobs": [{"id": 5, "name": "build", "status": "completed", "conclusion": "failure", "html_url": "https://github.com/o/r/job/5",
                                "steps": [{"number": 3, "name": "unit tests", "status": "completed", "conclusion": "failure"}]}]})
        return j({}, 404)


def pump(root: tk.Tk, win: BuildCenterWindow, seconds: float = 15.0) -> None:
    end = time.time() + seconds
    time.sleep(0.02)
    while time.time() < end:
        root.update()
        if not win.busy:
            return
        time.sleep(0.02)
    raise SystemExit("FAIL: Build Center did not finish in time")


def main() -> int:
    root = tk.Tk()
    errors: list[object] = []
    root.report_callback_exception = lambda *e: errors.append(e)
    fake = Fake()
    head = [NEW]
    selected: list[str] = []
    opened: list[str] = []
    win = BuildCenterWindow(
        root, owner="o", repo="r", branch="feat", get_token=lambda: TOKEN,
        service=GitHubActionsService(GitHubApiClient(transport=fake)),
        workflow_file=".github/workflows/old-name.yml", local_head_sha=lambda: head[0],
        on_select_workflow=selected.append, policy=PollPolicy(min_interval=0.0), open_url=opened.append,
    )
    try:
        pump(root, win)
        rows = {win.wf_tree.item(i, "text"): win.wf_tree.item(i, "values") for i in win.wf_tree.get_children()}
        assert rows["CI"][2] == "yes" and rows["Release"][2] == "no", rows
        assert "no longer exists" in win.warn_var.get(), win.warn_var.get()
        assert len(win.run_tree.get_children()) == 2
        assert "NOT the result of your latest changes" in win.correlation_var.get(), win.correlation_var.get()
        assert str(win.btn_cancel.cget("state")) == "disabled"

        # choose CI as main workflow -> star, warning cleared
        win.wf_tree.selection_set("1"); root.update(); pump(root, win)
        win._select_workflow()
        assert selected == [".github/workflows/ci.yml"], selected
        assert win.wf_tree.item("1", "text").startswith("★") and win.warn_var.get() == "", win.warn_var.get()

        # failed run -> jobs + failed step
        win.run_tree.selection_set("101:1"); root.update(); pump(root, win)
        job_rows = win.job_tree.get_children()
        assert job_rows and win.job_tree.get_children(job_rows[0]), "failed step not rendered"
        win.job_tree.selection_set(job_rows[0]); win._open_job()
        assert opened == ["https://github.com/o/r/job/5"], opened

        # new push -> running run for HEAD; cancel enabled; UI stays live while slow
        fake.runs = [run(3, NEW, "in_progress", None)] + fake.runs
        fake.slow.set()
        win.refresh_runs()
        ticks = 0
        end = time.time() + 10
        while win.busy and time.time() < end:
            root.update(); ticks += 1; time.sleep(0.01)
        assert ticks > 20, f"Tk loop starved during slow request ({ticks} ticks)"
        fake.slow.clear()
        assert "→ run 103" in win.correlation_var.get(), win.correlation_var.get()
        win.run_tree.selection_set("103:1"); root.update(); pump(root, win)
        assert str(win.btn_cancel.cget("state")) == "normal"
        assert errors == [], errors
    finally:
        win.close()
        root.destroy()
    print("PASS: Build Center window smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
