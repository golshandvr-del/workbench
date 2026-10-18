"""Phase-3 gate GUI smoke (Future Roadmap §22, §28): every flow in BOTH views over one controller —
publish with network failure, queue recovery after reopening, Last Published vs Local Revision,
broken proposal rejected, blocked / needs-decision tasks, mode switch without data change."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from aiwb.v2.controller import ProjectsController
from aiwb.v2.projects_window import ProjectsWindow
from aiwb.v2.publisher import GitHubStateClient, StatePublisher

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_v2_flow import FakeGitHub  # noqa: E402


def make(root: Path, gh: FakeGitHub, now: list[float]) -> ProjectsController:
    ctl = ProjectsController(root, make_pipeline=wb.make_inbox_pipeline)
    with ctl.project.store.transaction("enable publish") as s:
        s["settings"]["publish"]["enabled"] = True
    ctl.publisher = StatePublisher(ctl.project.store, clock=lambda: now[0],
                                   client_factory=lambda: GitHubStateClient("tok", "o", "r", transport=gh),
                                   source_info=lambda: {"repository": "o/r", "branch": "main", "commit_sha": "abc",
                                                        "local_changes_pending": False, "local_changes_count": 0})
    return ctl


def run(mode: str, root_tk: tk.Tk, temp: Path) -> None:
    project = temp / f"proj-{mode}"
    project.mkdir()
    gh, now = FakeGitHub(), [1000.0]
    ctl = make(project, gh, now)
    ctl.set_mode(mode)
    w = ProjectsWindow(root_tk, ctl, clipboard=lambda t: None)
    root_tk.update()
    assert w.mode_var.get() == mode
    # 5/7: plan proposal with a broken op and a cycle-free graph; broken op cannot be applied
    w.do_plan("Gate demo")
    rev = ctl.project.store.revision
    r = w.do_import("<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps({"schema_version": "1.0", "base_state_revision": rev,
        "summary": "plan", "operations": [
            {"operation": "create_task", "temporary_ref": "a", "title": "Core", "objective": "c", "owner_role": "implementer"},
            {"operation": "create_task", "temporary_ref": "b", "title": "UI", "objective": "u", "owner_role": "implementer",
             "depends_on_refs": ["a"]},
            {"operation": "delete_everything"}]}) + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>")
    assert r.kind == "proposal", r
    assert w.do_proposal([2]) is None, "invalid op refused"
    assert not ctl.project.tasks.list()
    w.do_proposal([0, 1])
    tasks = {t["title"]: t["task_id"] for t in ctl.project.tasks.list()}
    # 12: blocked + needs-decision tasks are visible with words, in this view
    assert "Blocked" in w.tree.item(tasks["UI"])["values"][0]
    ctl.project.decisions.propose("Pick storage", "?", affected_task_ids=[tasks["Core"]])
    w.refresh()
    assert "Needs your decision" in w.tree.item(tasks["Core"])["values"][0]
    assert "Decision needed" in w.warn_var.get()
    # 11 + 9: Last Published vs Local Revision; network failure keeps the queue
    assert "Not published yet" in w.pub_var.get(), w.pub_var.get()
    gh.fail = [(503, {})]
    out = w.do_publish()
    assert out.get("kind") == "network", out
    assert "Not published yet" in w.pub_var.get()
    w.close()
    # 10: reopen the program → queue recovered from disk, then published
    ctl2 = make(project, gh, now)
    assert ctl2.mode == mode, "view preference survives reopening"
    assert ctl2.publisher.pending
    now[0] += 1000
    w2 = ProjectsWindow(root_tk, ctl2, clipboard=lambda t: None)
    assert w2.do_publish()["status"] == "published"
    assert "Published: up to date" in w2.pub_var.get(), w2.pub_var.get()
    assert f"local revision {ctl2.project.store.revision}" in w2.pub_var.get()
    # 8: switching view changes no data
    rev = ctl2.project.store.revision
    other = "simple" if mode == "advanced" else "advanced"
    w2.mode_var.set(other)
    w2._mode_changed()
    root_tk.update()
    assert ctl2.project.store.revision == rev
    assert not ctl2.publisher.pending, "view switch does not create a publish"
    w2.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-gate3-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        root = tk.Tk()
        try:
            for mode in ("simple", "advanced"):
                run(mode, root, Path(temp))
            print("PASS: phase-3 gate GUI smoke in simple and advanced views")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
