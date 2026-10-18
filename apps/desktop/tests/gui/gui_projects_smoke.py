"""GUI smoke for V2 Projects window (roadmap 1.20.1 / 2.0.0 / 2.1.0): plan → proposal review → handoff prompt →
answer via the Inbox → accept → review → done; Simple and Advanced views over the same data."""
from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready
from aiwb import inbox


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-projects-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Projekt ä"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.open_projects()
            root.update()
            w = app.projects_window
            assert "planning prompt" in w.next_var.get().lower(), w.next_var.get()
            prompt = w.do_plan("Todo app")
            assert "AIWB_MANAGER_PROPOSAL" in prompt
            assert w.do_copy() == root.clipboard_get()
            rev = w.ctl.project.store.revision
            answer = ("<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps({"schema_version": "1.0", "base_state_revision": rev,
                      "summary": "plan", "operations": [
                          {"operation": "create_task", "temporary_ref": "a", "title": "Core", "objective": "core",
                           "owner_role": "implementer", "acceptance_policy": "manual_review"},
                          {"operation": "frobnicate"}]}) + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>")
            r = w.do_import(answer)
            assert r.kind == "proposal", r
            assert inbox.InboxStore(project).list(), "answer must be captured raw first"
            assert not w.ctl.project.tasks.list(), "nothing changes before review"
            out = w.do_proposal([0])
            assert out["status"] in ("accepted", "partially_accepted"), out
            (tid,) = [t["task_id"] for t in w.ctl.project.tasks.list()]
            assert w.ctl.project.tasks.get(tid)["status"] == "ready"
            simple_rows = w.tree.get_children()
            assert simple_rows == (tid,)
            assert "Ready to start" in w.tree.item(tid)["values"][0]
            w.tree.selection_set(tid)
            h = w.do_start(tid)
            assert "NO access to earlier chats" in w.prompt_text.get("1.0", "end-1c")
            w.do_copy()
            ho = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": tid, "task_revision": 1,
                  "attempt_id": h["attempt_id"], "outcome": "complete", "summary": "done core",
                  "validation_claims": ["tests pass"]}
            r = w.do_import(f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n<<<AIWB_HANDOFF>>>\n{json.dumps(ho)}\n<<<AIWB_END_HANDOFF>>>")
            assert r.kind == "handoff" and r.reference_id == h["handoff_id"], r
            w.do_resolve(True)
            assert w.ctl.project.tasks.get(tid)["status"] == "in_review"
            assert "review" in w.next_var.get().lower() or w.ctl.next_action() is not None
            # advanced view shows the same task with internals, no different data
            w.mode_var.set("advanced")
            w._mode_changed()
            assert w.tree.get_children() == simple_rows
            details = w.detail.get("1.0", "end-1c")
            assert "Handoff " + h["handoff_id"] in details and "Evidence" in details, details
            assert w.ctl.mode == "advanced"
            root.update()
            assert w.adv.winfo_manager(), "advanced panels shown"
            assert "agent-architect" in w.adv_text["Agents"].get("1.0", "end-1c")
            assert h["handoff_id"] in w.adv_text["Attempts"].get("1.0", "end-1c")
            assert "locally only" in w.adv_text["Publish"].get("1.0", "end-1c")
            res = w.do_review(True, tid)
            assert res["status"] == "done", res
            assert "Done (verified)" in w.tree.item(tid)["values"][0] or w.ctl.mode == "advanced"
            rev_before = w.ctl.project.store.revision
            w.mode_var.set("simple")
            w._mode_changed()
            root.update()
            assert not w.adv.winfo_manager(), "simple view hides internals"
            assert w.ctl.project.store.revision == rev_before, "switching views changes no data"
            assert "rev " not in str(w.tree.item(tid)["values"])
            bad = w.do_import("<<<AIWB_HANDOFF>>>\n" + json.dumps({**ho, "handoff_id": "HO-9999", "attempt_id": "att-x"}) +
                              "\n<<<AIWB_END_HANDOFF>>>")
            assert bad.kind == "rejected", bad
            assert w.do_publish()["status"] == "disabled", "no binding → local only"
            rev_lang = w.ctl.project.store.revision
            w.lang_var.set("fa")
            w._lang_changed()
            root.update()
            assert "انجام‌شده" in w.tree.item(tid)["values"][0], w.tree.item(tid)["values"]
            assert w.next_frame.cget("text") == "قدم بعدی"
            assert w.ctl.project.store.revision == rev_lang, "language switch changes no data"
            w.lang_var.set("en")
            w._lang_changed()
            assert sorted(p.name for p in project.iterdir() if p.name != ".workbench") == ["main.py"]
            w.close()
            print("PASS: Projects (multi-agent) GUI smoke, simple + advanced")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
