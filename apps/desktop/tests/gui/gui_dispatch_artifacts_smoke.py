#!/usr/bin/env python3
"""GUI smoke for v1.14.7: Run workflow form + Artifacts dialog (fake GitHub, no network)."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))

import tkinter as tk  # noqa: E402

from aiwb.github import artifacts as ar  # noqa: E402
from aiwb.github.actions import GitHubActionsService, PollPolicy  # noqa: E402
from aiwb.github.api_client import GitHubApiClient, HttpResponse  # noqa: E402
from aiwb.github.build_center import BuildCenterWindow  # noqa: E402

TOKEN = "github_pat_" + "S" * 40
SHA = "3" * 40
WF = """on:
  workflow_dispatch:
    inputs:
      channel:
        type: choice
        required: true
        options: [beta, stable]
      dry_run:
        type: boolean
        default: true
"""


def j(value: object, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {}, json.dumps(value).encode())


def zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("AI_Workbench_Setup.bat", b"@echo off\r\n")
    return buf.getvalue()


ZIP = zip_bytes()
RUN = {"id": 200, "workflow_id": 1, "name": "Build", "event": "push", "status": "completed", "conclusion": "success",
       "head_branch": "main", "head_sha": SHA, "run_number": 9, "run_attempt": 1, "created_at": "2026-10-17T10:00:00Z",
       "updated_at": "2026-10-17T10:05:00Z", "run_started_at": "", "html_url": "https://github.com/o/r/actions/runs/200"}


def get(url: str, headers: dict, timeout: float) -> HttpResponse:
    path = urlsplit(url).path
    if path == "/repos/o/r/actions/workflows":
        return j({"workflows": [{"id": 1, "name": "Build", "path": ".github/workflows/build.yml", "state": "active", "html_url": ""}]})
    if path.endswith("/build.yml"):
        return j({"encoding": "base64", "content": base64.b64encode(WF.encode()).decode()})
    if path.endswith("/runs"):
        return j({"workflow_runs": [RUN]})
    if path.endswith("/artifacts"):
        return j({"artifacts": [
            {"id": 31, "name": "setup", "size_in_bytes": len(ZIP), "expired": False, "expires_at": "2026-12-01T00:00:00Z",
             "digest": "sha256:" + hashlib.sha256(ZIP).hexdigest(), "workflow_run": {"id": 200, "head_sha": SHA, "head_branch": "main"}},
            {"id": 32, "name": "old", "size_in_bytes": 5, "expired": True, "expires_at": "2026-01-01T00:00:00Z", "digest": "",
             "workflow_run": {"id": 200, "head_sha": SHA, "head_branch": "main"}},
        ]})
    return j({}, 404)


posts: list[dict] = []


def request(url: str, method: str, headers: dict, body: bytes | None, timeout: float) -> HttpResponse:
    if url.endswith("/dispatches"):
        posts.append(json.loads(body or b"{}"))
        return HttpResponse(200, {}, json.dumps({"workflow_run_id": 777, "html_url": "https://github.com/o/r/actions/runs/777"}).encode())
    if url.endswith("/zip"):
        return HttpResponse(302, {"Location": "https://productionresultssa1.blob.core.windows.net/x?sig=TMP"}, b"")
    return HttpResponse(404, {}, b"")


def stream(url: str, timeout: float):
    yield ZIP


def pump(root: tk.Tk, cond, seconds: float = 15.0) -> None:
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if cond():
            return
        time.sleep(0.02)
    raise SystemExit("FAIL: condition not reached in time")


def main() -> int:
    root = tk.Tk()
    errors: list[object] = []
    root.report_callback_exception = lambda *e: errors.append(e)
    actions = GitHubActionsService(GitHubApiClient(transport=get))
    dsvc = ar.GitHubDispatchService(actions, request=request, stream=stream)
    downloaded: list = []
    win = BuildCenterWindow(root, owner="o", repo="r", branch="main", get_token=lambda: TOKEN, service=actions,
                            workflow_file=".github/workflows/build.yml", local_head_sha=lambda: SHA,
                            policy=PollPolicy(min_interval=0.0), open_url=lambda u: None, dispatch_service=dsvc,
                            on_artifact_downloaded=lambda a, r: downloaded.append((a.artifact_id, r.verification)))
    tmp = tempfile.TemporaryDirectory()
    try:
        pump(root, lambda: not win.busy and win.workflows)
        assert str(win.btn_dispatch.cget("state")) == "normal", "dispatch should be enabled for workflow_dispatch file"
        win.open_dispatch()
        dlg = win.dispatch_dialog
        pump(root, lambda: dlg.form is not None)
        assert set(dlg.vars) == {"channel", "dry_run"}, dlg.vars
        dlg.vars["channel"].set("")
        dlg.submit()
        assert "required" in dlg.status_var.get(), dlg.status_var.get()
        dlg.vars["channel"].set("stable")
        dlg.vars["dry_run"].set(False)
        dlg.submit()
        pump(root, lambda: dlg.result is not None)
        assert dlg.result.state == "confirmed" and dlg.result.run_id == 777, dlg.result
        assert posts == [{"ref": "main", "inputs": {"channel": "stable", "dry_run": "false"}, "return_run_details": True}], posts
        dlg.close()

        pump(root, lambda: not win.busy)
        win.run_tree.selection_set("200:1"); root.update()
        pump(root, lambda: not win.busy)
        win.open_artifacts()
        ad = win.artifacts_dialog
        ad.ask_directory = lambda: tmp.name
        ad.confirm = lambda t, m: True
        pump(root, lambda: ad.artifacts)
        ad.tree.selection_set("32"); root.update()
        assert str(ad.btn_download.cget("state")) == "disabled", "expired artifact must not be downloadable"
        ad.tree.selection_set("31"); root.update()
        assert str(ad.btn_download.cget("state")) == "normal"
        ad.download()
        pump(root, lambda: 31 in ad.downloads)
        assert downloaded == [(31, "matched")], downloaded
        assert "TMP" not in ad.status_var.get()
        ad.tree.selection_set("31"); root.update()
        ad.extract()
        assert (Path(tmp.name) / "setup-31" / "AI_Workbench_Setup.bat").is_file(), ad.status_var.get()
        assert errors == [], errors
        ad.close()
    finally:
        win.close()
        root.destroy()
        tmp.cleanup()
    print("PASS: dispatch + artifacts GUI smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
