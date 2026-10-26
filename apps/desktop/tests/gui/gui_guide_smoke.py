"""GUI smoke for the guided loop (roadmap 3.5.0 Gate).

5.11.0: Home's Next-step card always has a primary button and a More menu for the other actions (the Workbench strip
only names the step and links to Home); Plan & Tasks lists the queue of each AI. Driven through the card
(``do_next``) and the queue: goal → charter prompt copied → "I sent it" → charter pasted → plan accepted → task prompt
prepared and copied → the queue shows each AI.
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
            app.shell.show("home")
            root.update()
            card = app.home_card
            card.refresh()
            # the Workbench strip names the step and only links to Home (one home per command)
            assert w.next_btn.cget("text") == "Open on Home" and not hasattr(w, "next_menu")
            # empty project: the card asks for the goal (form step), never a dead end
            assert "Start the project" in w.next_var.get(), w.next_var.get()
            assert str(card.next_btn.cget("text")).startswith("Start the project"), card.next_btn.cget("text")
            out = w.guide_action("design", "design", {"goal": "Offline todo app for desktop and mobile"})
            assert out and "AIWB_PROJECT_CHARTER" in out["prompt"]
            root.update()
            assert "Project Charter" in w.next_var.get(), w.next_var.get()
            # primary = copy → clipboard; the other actions are buttons (5.13.0); the paste action is the card's paste panel
            card.refresh()
            out = card.do_next()
            assert root.clipboard_get() == out["prompt"] and "AIWB_PROJECT_CHARTER" in out["prompt"]
            more = card.labels()[1:]
            assert "I sent it" in more and card.paste.winfo_manager(), (more, card.paste.winfo_manager())
            w.guide_action("charter", "sent", {})
            good = json.loads(FIXTURE.read_text(encoding="utf-8"))
            good["base_state_revision"] = ctl.state()["state_revision"]
            text = "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(good) + "\n<<<AIWB_END_PROJECT_CHARTER>>>\n"
            out = w.guide_action("charter", "paste", {"text": text})
            assert out["kind"] == "proposal", out
            root.update()
            assert "Review the plan" in w.next_var.get(), w.next_var.get()
            card.refresh()
            assert card.next_btn.cget("text") == "Accept all valid changes", card.labels()
            card.do_next()
            assert len(ctl.state()["tasks"]) == 3
            # queue of each AI in Plan & Tasks
            w.show("plan")
            root.update()
            agents = [w.queue_tree.item(i, "text") for i in w.queue_tree.get_children()]
            core_name = ctl.state()["agents"]["agent-core-dev"].get("name") or "agent-core-dev"
            assert core_name in agents, agents  # 5.11.0: the AI's name, not its id
            core_step = w.queue_tree.get_children("q:agent-core-dev")[0]
            out = w.do_queue_selected(core_step)
            assert out and "AIWB_ATTEMPT_ID" in out["prompt"], out
            root.update()
            assert "Copy the prompt" in w.next_var.get(), w.next_var.get()
            card.refresh()
            out = card.do_next()
            assert root.clipboard_get() == out["prompt"]
            root.update()
            assert "Send the copied prompt" in w.next_var.get(), w.next_var.get()
            card.refresh()
            card.do_next()
            root.update()
            assert f"Paste {core_name}'s answer" in w.next_var.get(), w.next_var.get()  # 5.13.0 (B4): the name
            # the strip's link stays inside the window
            app.shell.show("workbench")
            for wd in (1024, 1280):
                root.geometry(f"{wd}x640+0+0")
                root.update()
                assert w.next_btn.winfo_rootx() + w.next_btn.winfo_width() <= root.winfo_rootx() + root.winfo_width() + 2
            w.next_btn.invoke()
            root.update()
            assert app.shell.current == "home", app.shell.current
            # Home: next step card
            app.shell.show("home")
            root.update()
            # 5.11.0: the cockpit card names the AI (not its id) and shows the paste panel on the page
            name = ctl.state()["agents"]["agent-core-dev"].get("name") or "agent-core-dev"
            assert f"Paste {name}'s answer" in app.home_next_var.get(), app.home_next_var.get()
            assert app.home_card.paste.winfo_manager(), "the paste panel is on Home"
            # 5.13.0 (B5): no More on the card — "All open steps (N)" lists every open step; picking one shows it,
            # "Back to the next step" returns
            card.refresh()
            assert not any(str(wd.cget("text")) == "More" for wd in card._bar.winfo_children()
                           if wd.winfo_class() == "TMenubutton"), "the card has no More"
            opened = card.model["open"]
            if len(opened) > 1:
                assert card.steps_btn.winfo_manager() and f"({len(opened)})" in card.steps_btn.cget("text")
                menu = card.steps_menu
                rows = [menu.entrycget(i, "label") for i in range(int(menu.index("end")) + 1)
                        if menu.type(i) == "command"]
                assert rows[0].startswith("● "), rows
                first_key = card.model["key"]
                menu.invoke(int(menu.index("end")))   # the last open step
                root.update()
                assert card.model["key"] == opened[-1]["key"] != first_key, (card.model["key"], opened)
                rows = [menu.entrycget(i, "label") for i in range(int(menu.index("end")) + 1)
                        if menu.type(i) == "command"]
                assert rows[0] == "Back to the next step", rows
                menu.invoke(0)
                root.update()
                assert card.model["key"] == first_key
        finally:
            root.destroy()
    print("PASS: guided loop GUI smoke - Home card (button, other actions, paste panel), strip links to Home, per-AI queue")


if __name__ == "__main__":
    main()
