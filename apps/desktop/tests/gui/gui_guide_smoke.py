"""GUI smoke for the guided loop (roadmap 3.5.0 Gate).

Home shows the active project's next step. In the Project Workbench the Next-step strip always has
a primary button and a More menu for the other actions; the Overview lists the queue of each AI.
Driven only through the strip (``do_next``) and the queue: goal → charter prompt copied → "I sent it"
→ charter pasted → plan accepted → task prompt prepared and copied → the queue shows each AI.
"""
from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready

FIXTURE = Path(__file__).resolve().parents[4] / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-guide-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Guide"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        root.geometry("1280x720+0+0")
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.open_project_workbench()
            w = app.workspace_window
            ctl = w.wc.ctl
            root.update()
            # empty project: the strip asks for the goal (form step), never a dead end
            assert "Start the project" in w.next_var.get(), w.next_var.get()
            assert str(w.next_btn.cget("text")).startswith("Start the project"), w.next_btn.cget("text")
            out = w.guide_action("design", "design", {"goal": "Offline todo app for desktop and mobile"})
            assert out and "AIWB_PROJECT_CHARTER" in out["prompt"]
            root.update()
            assert "Project Charter" in w.next_var.get(), w.next_var.get()
            # primary = copy → clipboard; More holds the rest
            out = w.do_next()
            assert root.clipboard_get() == out["prompt"] and "AIWB_PROJECT_CHARTER" in out["prompt"]
            more = [w.next_menu.entrycget(i, "label") for i in range(w.next_menu.index("end") + 1)]
            assert "I sent it" in more and "Paste the charter" in more, more
            w.guide_action("charter", "sent", {})
            good = json.loads(FIXTURE.read_text(encoding="utf-8"))
            good["base_state_revision"] = ctl.state()["state_revision"]
            text = "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(good) + "\n<<<AIWB_END_PROJECT_CHARTER>>>\n"
            out = w.guide_action("charter", "paste", {"text": text})
            assert out["kind"] == "proposal", out
            root.update()
            assert "Review the plan" in w.next_var.get(), w.next_var.get()
            assert w.next_btn.cget("text") == "Accept all valid changes"
            w.do_next()
            assert len(ctl.state()["tasks"]) == 3
            # queue of each AI on the Overview
            w.show("overview")
            root.update()
            agents = [w.queue_tree.item(i, "text") for i in w.queue_tree.get_children()]
            assert "agent-core-dev" in agents, agents
            core_step = w.queue_tree.get_children("q:agent-core-dev")[0]
            out = w.do_queue_selected(core_step)
            assert out and "AIWB_ATTEMPT_ID" in out["prompt"], out
            root.update()
            assert "Copy the prompt" in w.next_var.get(), w.next_var.get()
            out = w.do_next()
            assert root.clipboard_get() == out["prompt"]
            root.update()
            assert "Send the copied prompt" in w.next_var.get(), w.next_var.get()
            w.do_next()
            root.update()
            assert "Paste agent-core-dev's answer" in w.next_var.get(), w.next_var.get()
            # strip stays inside the window
            for wd in (1024, 1280):
                root.geometry(f"{wd}x640+0+0")
                root.update()
                assert w.next_btn.winfo_rootx() + w.next_btn.winfo_width() <= root.winfo_rootx() + root.winfo_width() + 2
            # Home: next step card
            app.shell.show("home")
            root.update()
            assert "Paste agent-core-dev's answer" in app.home_next_var.get(), app.home_next_var.get()
        finally:
            root.destroy()
    print("PASS: guided loop GUI smoke - next-step strip, More menu, per-AI queue, Home card")


if __name__ == "__main__":
    main()
