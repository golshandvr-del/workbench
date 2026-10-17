#!/usr/bin/env python3
"""GUI smoke for the v1.14.5 Git Review & Sync window (needs a display).

Builds a throwaway repo with a local bare remote, opens the real Tk window,
and checks default selection (in-scope only), button gating (push only after
fetch), diff rendering and that no Tk callback raised.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "apps" / "desktop"
sys.path.insert(0, str(APP))

import tkinter as tk  # noqa: E402

from aiwb.git.review_dialog import GitReviewDialog  # noqa: E402
from aiwb.git.service import GitService  # noqa: E402
from aiwb.git.sync import GitSyncService  # noqa: E402


def pump(root: tk.Tk, dialog: GitReviewDialog, seconds: float = 20.0) -> None:
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if not dialog.busy and dialog.plan is not None:
            return
        time.sleep(0.03)
    raise SystemExit("FAIL: review window did not finish in time")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp).resolve()

        def g(*args: str, cwd: Path = t) -> None:
            subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)

        g("init", "-q", "--bare", "-b", "main", str(t / "r.git"))
        g("clone", "-q", str(t / "r.git"), str(t / "w"))
        w = t / "w"
        for k, v in (("user.name", "t"), ("user.email", "t@e"), ("commit.gpgsign", "false")):
            g("config", k, v, cwd=w)
        (w / "a.txt").write_bytes(b"a\n")
        g("add", "a.txt", cwd=w)
        g("commit", "-qm", "a", cwd=w)
        g("switch", "-qc", "feat", cwd=w)
        (w / "proj").mkdir()
        (w / "proj" / "x.py").write_bytes(b"print(1)\n")
        (w / "other.txt").write_bytes(b"o\n")

        root = tk.Tk()
        errors: list[object] = []
        root.report_callback_exception = lambda *e: errors.append(e)
        d = GitReviewDialog(root, w, "proj", GitSyncService(GitService()),
                            in_scope=lambda p: p.startswith("proj/"), context_ids={"task_id": "T-1"})
        try:
            pump(root, d)
            assert d.plan.state == "no_upstream", d.plan.state
            assert d.checked == {"proj/x.py"}, d.checked
            assert str(d.btn_push.cget("state")) == "disabled", "push must require a fetch first"
            assert str(d.btn_commit.cget("state")) == "normal"
            d.refresh(fetch=True)
            pump(root, d)
            assert d.plan.fetched, "fetch did not run"
            assert str(d.btn_commit_push.cget("state")) == "normal"
            d.tree.focus("proj/x.py")
            d._show_diff()
            assert "new file: proj/x.py" in d.diff.get("1.0", "end")
        finally:
            root.destroy()
        if errors:
            print("FAIL: Tk callback exceptions:", errors)
            return 1
    print("PASS: Git Review & Sync window smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
