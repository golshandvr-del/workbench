#!/usr/bin/env python3
"""GUI smoke for v1.14.8 Sync & Build window: real Git + bare remote, fake GitHub."""
from __future__ import annotations

import argparse
import hashlib
import io
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import zipfile
from pathlib import Path


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-dir", default=None, help="defaults to PYTHONPATH (run_all.py) or the repo src")
    args = ap.parse_args()
    if args.app_dir:
        sys.path.insert(0, args.app_dir)
    else:
        sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))  # after PYTHONPATH entries
    sys.path.append(str(Path(__file__).resolve().parents[1]))  # repo tests/ (fake GitHub helpers)
    from aiwb.git import GitService, GitSyncService
    from aiwb.github import orchestrator as orc
    from aiwb.github.actions import GitHubActionsService, RepositoryOperationGuard
    from aiwb.github.api_client import GitHubApiClient
    from aiwb.github.artifacts import GitHubDispatchService
    from aiwb.github.sync_build_window import SyncBuildWindow
    from test_orchestrator import FakeGitHub, WF, TOKEN

    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        remote, work = base / "remote.git", base / "work"
        git(base, "init", "-q", "--bare", "-b", "main", str(remote))
        git(base, "init", "-q", "-b", "main", str(work))
        git(work, "config", "user.email", "t@example.com"); git(work, "config", "user.name", "T")
        (work / "a.txt").write_text("1\n"); git(work, "add", "a.txt"); git(work, "commit", "-q", "-m", "init")
        git(work, "remote", "add", "origin", str(remote)); git(work, "switch", "-q", "-c", "work")
        git(work, "push", "-q", "-u", "origin", "work")
        (work / "a.txt").write_text("2\n"); (work / "x.env").write_text("S=1\n")
        gh = FakeGitHub()
        client = GitHubApiClient(transport=gh.transport)
        actions = GitHubActionsService(client, write_transport=gh.write)
        o = orc.SyncBuildOrchestrator(
            sync=GitSyncService(GitService()), actions=actions,
            dispatch=GitHubDispatchService(actions, request=gh.request, stream=gh.stream), git_root=work,
            project_subpath="", owner="o", repo="r", repository_id=99, branch="work", workflow_file=WF,
            artifact_pattern="", get_token=lambda: TOKEN, store=orc.RecordStore(base / "ops.json"),
            is_sensitive=lambda p: p.endswith(".env"), guard=RepositoryOperationGuard(), sleep=lambda _s: time.sleep(0.05))
        root = tk.Tk(); root.withdraw()
        dl = base / "dl"
        w = SyncBuildWindow(root, o, default_message="workbench: smoke", ask_directory=lambda **_k: str(dl),
                            confirm=lambda *a, **k: True, ci_timeout=20, ci_interval=0.05)

        def pump(cond, timeout=20.0) -> None:
            end = time.time() + timeout
            while time.time() < end:
                root.update()
                if cond():
                    return
                time.sleep(0.02)
            raise AssertionError("timeout; state=" + o.state + " log=" + w.log.get("1.0", "end"))

        w.do_check(); pump(lambda: not w.busy and o.state == orc.REVIEW_REQUIRED)
        assert w.selected == {"a.txt"}, w.selected  # sensitive not preselected
        assert str(w.btn_go.cget("state")) == "normal"
        w.do_go()
        pump(lambda: o.git.pushed)
        sha = o.git.commit_sha
        assert str(w.btn_check.cget("state")) == "disabled"  # busy while waiting for CI
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as zf:
            zf.writestr("app.bin", b"x")
        blob = data.getvalue(); gh.blobs[9] = blob
        gh.artifacts[801] = [{"id": 9, "name": "app", "size_in_bytes": len(blob), "expired": False,
                              "digest": "sha256:" + hashlib.sha256(blob).hexdigest(),
                              "workflow_run": {"id": 801, "head_sha": sha, "repository_id": 99}}]
        gh.add_run(801, sha, "work")
        pump(lambda: not w.busy and o.state == orc.BUILD_PASSED)
        assert str(w.btn_download.cget("state")) == "normal"
        w.do_download(); pump(lambda: not w.busy and o.state == orc.ARTIFACT_VERIFIED)
        assert "Done" in w.next_var.get()
        assert "x.env" in git(work, "status", "--porcelain")
        w.close(); root.destroy()
    print("PASS: Sync & Build window smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
