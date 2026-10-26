"""GUI smoke for workflow tracking and the timeline (roadmap 2.5.0 stages 5, 6; Gate B, D).

Workspace: a ready task → Prepare prompt → Copy (copied, not sent) → "I sent this
prompt" (waiting) → Prepare again warns and can be declined → Overview shows
"n of m" and separate indicators → Timeline: lanes, milestone (accept refused
while open, forced accept recorded), version proposed → local → tagged →
released only with real facts; filters / language switch do not write state.
"""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready
from aiwb.v2.workflow import task_stage


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-wf-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Workflow project"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.open_project_workbench()
            w = app.workspace_window
            ctl = w.wc.ctl
            w.top.geometry("1366x768+0+0")
            p = ctl.project
            acc = p.resources.add_account({"display_name": "GPT paid", "provider": "GPT"})
            p.resources.bind_chat("agent-implementer", acc["account_profile_id"], chat_name="impl chat")
            tids = []
            for i in range(3):
                t = p.tasks.create({"title": f"Part {i}", "objective": "o", "owner_agent_id": "agent-implementer",
                                    "scope": {"include": [f"p{i}/**"]}, "acceptance_criteria": ["ok"]})
                p.tasks.transition(t["task_id"], "ready")
                tids.append(t["task_id"])
            tid = tids[0]
            w.wc.select("task", tid)
            w.show("tasks")
            root.update()
            assert w.task_tree.set(tid, "stage"), "workflow column empty"
            out = w.inspector_action("start_task")
            assert out and w.last_handoff_id
            stage = lambda: task_stage(ctl.state(), tid)["stage"]  # noqa: E731
            assert stage() == "prompt_prepared", stage()
            w.do_copy()
            assert stage() == "prompt_copied", stage()
            assert "does not mean it was sent" in w.status_var.get()
            w.wc.select("task", tid)
            w.show("tasks")
            labels = [b.cget("text") for b in w.insp_actions.winfo_children()]
            assert "I sent this prompt" in labels, labels
            assert w.inspector_action("confirm_sent")
            st = task_stage(ctl.state(), tid)
            assert st["stage"] == "waiting_for_response" and st["account_profile_id"] == acc["account_profile_id"], st
            n_att = len(ctl.state()["attempts"])
            assert w.inspector_action("start_task", confirm=False) is None
            assert len(ctl.state()["attempts"]) == n_att, "declined warning still created an attempt"

            w.show("overview")
            root.update()
            assert any("Waiting for test/build" in line for line in w.progress_details), w.progress_details
            assert "0 of 3 tasks verified" in w.progress_var.get(), w.progress_var.get()

            # 5.13.0 (B3): no Timeline section — lanes are a read model, milestones/versions live on the map
            lanes = w.wc.timeline_lanes()
            assert "agent-implementer" in lanes, list(lanes)
            m = w.dialog_milestone({"title": "MVP", "task_ids": tids[:2], "target_date": "2026-12-01"})
            assert m and any(r["milestone_id"] == m["milestone_id"] for r in w.wc.milestone_rows())
            assert w.accept_selected_milestone(m["milestone_id"], force=False) is None
            assert "open tasks" in w.status_var.get()
            assert w.accept_selected_milestone(m["milestone_id"], force=True)["status"] == "accepted"
            v = w.dialog_version({"label": "1.0.0"})
            assert v and "not released" in w.status_var.get()
            assert w.dialog_advance_version(v["version_id"], "released", {}) is None
            assert w.dialog_advance_version(v["version_id"], "local", {"commit_sha": "abcdef1"})["status"] == "local"
            assert w.dialog_advance_version(v["version_id"], "tagged", {"tag": "v1.0.0"})["status"] == "tagged"
            assert w.dialog_advance_version(v["version_id"], "released", {"run_id": "123"})["status"] == "released"
            assert next(r for r in w.wc.version_rows() if r["version_id"] == v["version_id"])["status"] == "released"
            app.shell.show("home")
            root.update()
            app.refresh_mission(app.status_state(), force=True)
            labels = [c["label"] for c in app.mission.model["columns"]]
            assert any("1.0.0" in lb for lb in labels), labels  # the version is a column on the Mission Map
            app.shell.show("workbench")
            root.update()

            rev = ctl.state()["state_revision"]
            res = w.wc.timeline_page(0, families=["version"])
            assert res["total"] >= 4, res["total"]
            w.wc.set_language("fa")
            w.show("timeline")  # an old key: opens Plan & Tasks
            assert w.wc.section == "plan", w.wc.section
            w.show("tasks")
            w.show("overview")
            root.update()
            assert "از" in w.progress_var.get()
            w.wc.set_language("en")
            assert ctl.state()["state_revision"] == rev, "view/filter/language changed project state"
            w.close()
            print("Workflow/timeline smoke passed: prepare/copy/sent distinct · duplicate-start warning · "
                  "progress indicators · lanes · milestone · version facts · no state writes from views")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
