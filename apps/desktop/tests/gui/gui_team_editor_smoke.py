"""Roadmap 5.9.0 gate (real widgets): the start form for an existing folder, Edit team…, and an older project.

1. *Add existing folder* → the Workbench's **Start the project…** opens the wizard window (no folder fields) with
   the project name prefilled; the goal and a team of two named AIs are typed in; *Start the project* records both
   in one step — no chained question dialogs (audit A8) — and the next step is the charter prompt.
2. **Agents › Team › Edit team…**: rename an AI, add one, remove one; the Mission Map lanes follow at once.
3. An **older project** (template AIs installed before 5.9.0) opens untouched; *Edit team…* offers
   *Remove unused template AIs* and removes only the ones without work.
"""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
import traceback
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


def pump(root, n=5):
    for _ in range(n):
        root.update()


def open_workbench(app, root, project: Path):
    app.set_workspace(project, focus_project=True)
    wait_for_project_ready(app, root, project)
    app.open_project_workbench()
    for _ in range(400):  # compare with app.workspace: Windows may resolve the temp folder differently (8.3 names)
        ws = getattr(app, "workspace_window", None)
        if ws is not None and getattr(ws, "_project_root", None) in (str(app.workspace), str(project)):
            return ws
        pump(root, 2)
    raise AssertionError("the Workbench did not open")


def set_count(root, table, n: int) -> None:
    box = table.count_box
    box.focus_force()
    pump(root)
    box.delete(0, "end")
    box.insert(0, str(n))
    box.event_generate("<Return>")
    pump(root)


def main() -> None:
    from aiwb.ui import mission_model
    from aiwb.v2 import V2Project
    with tempfile.TemporaryDirectory(prefix="aiwb-team-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        root = tk.Tk()
        root.geometry("1366x800+0+0")
        errors: list[str] = []
        root.report_callback_exception = lambda *a: errors.append("".join(traceback.format_exception(*a)))
        asked: list[str] = []
        for name in ("askstring", "askinteger"):
            setattr(wb.simpledialog, name, (lambda n: lambda *a, **k: asked.append(n))(name))
        boxes: list[tuple] = []
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(wb.messagebox, name, (lambda n: lambda *a, **k: boxes.append((n, a)))(name))
        try:
            app = wb.WorkbenchApp(root)
            pump(root)
            # 1) an existing folder: Start the project… = the wizard window in start mode
            folder = Path(temp) / "Existing Tool"
            folder.mkdir()
            (folder / "main.py").write_text("print(1)\n", encoding="utf-8")
            ws = open_workbench(app, root, folder)
            card = app.home_card  # 5.11.0: the step's button lives on Home's Next-step card
            card.refresh()
            assert card.next_btn.cget("text").startswith("Start the project"), card.next_btn.cget("text")
            card.next_btn.invoke()
            pump(root, 10)
            form = ws.start_form
            assert form.win.winfo_exists() and form.mode == "start"
            assert form.vars["name"].get() == "Existing Tool", form.vars["name"].get()
            assert not [c for c in walk(form.pages[0]) if c.winfo_class() == "TButton" and c.cget("text") == "Browse…"], \
                "no folder fields in start mode"
            form.goal_text.insert("1.0", "Turn the script into a small command-line tool")
            form.next_btn.invoke()
            pump(root)
            set_count(root, form.team, 2)
            rows = form.team.entries()
            rows[1]["name"].set("Coder")
            rows[2]["name"].set("Checker")
            rows[2]["role"].set("Reviewer / tester")
            form.next_btn.invoke()
            pump(root)
            assert form.next_btn.cget("text") == "Start the project"
            form.next_btn.invoke()
            pump(root, 10)
            assert not form.win.winfo_exists(), form.error_var.get()
            assert not asked, f"chained question dialogs were opened: {asked}"
            st = ws.wc.ctl.state()
            enabled = {a: v for a, v in st["agents"].items() if v.get("enabled", True)}
            assert set(enabled) == {"agent-project-manager", "agent-coder", "agent-checker"}, sorted(st["agents"])
            assert enabled["agent-checker"]["role"] == "reviewer"
            assert st["settings"]["goal"].startswith("Turn the script")
            card.refresh()
            assert card.next_btn.cget("text") == "Copy the charter prompt", card.next_btn.cget("text")

            # 2) Agents › Team › Edit team…: rename, add, remove — through the real table
            app.shell.show("agents")
            pump(root, 5)
            app.agents_team_bar.buttons["Edit team…"].invoke()
            pump(root, 5)
            ed = app.team_editor
            table = ed["table"]
            set_count(root, table, 2)
            rows = table.entries()
            rows[1]["name"].set("Core coder")             # rename agent-coder (its id stays)
            rows[2]["name"].set("UI coder")               # the reviewer row becomes a new developer
            rows[2]["role"].set("Developer")
            set_count(root, table, 3)
            table.entries()[3]["name"].set("Docs writer")
            save = next(c for c in walk(ed["win"]) if c.winfo_class() == "TButton" and c.cget("text") == "Save team")
            save.invoke()
            pump(root, 10)
            assert not ed["win"].winfo_exists(), ed["error"].get()
            st = ws.wc.ctl.state()
            lanes = [ln["name"] for ln in mission_model.build(st)["lanes"]]
            assert lanes == ["Core coder", "UI coder", "Docs writer"], lanes
            assert st["agents"]["agent-coder"]["name"] == "Core coder"
            app.shell.show("home")
            pump(root, 10)
            drawn = [app.mission.itemcget(i, "text") for i in app.mission.find_withtag("lane_name")]
            assert drawn == [mission_model.short_name(n) for n in lanes], drawn

            # 3) an older project: template AIs from before 5.9.0, opened untouched, removal offered
            old = Path(temp) / "Old Project"
            old.mkdir()
            V2Project(old, old.name).open()                 # 5.8.0 behaviour: installs the template AIs
            before = sorted(V2Project(old).store.load()["agents"])
            assert "agent-architect" in before, before
            ws = open_workbench(app, root, old)
            assert sorted(ws.wc.ctl.state()["agents"]) == before, "an older project is opened untouched"
            app.shell.show("agents")
            pump(root, 5)
            app.agents_team_bar.buttons["Edit team…"].invoke()
            pump(root, 5)
            ed = app.team_editor
            drop = next(c for c in walk(ed["win"]) if c.winfo_class() == "TButton"
                        and c.cget("text").startswith("Remove unused template AIs"))
            drop.invoke()
            pump(root, 10)
            left = sorted(a for a, v in ws.wc.ctl.state()["agents"].items() if v.get("enabled", True))
            assert left == ["agent-project-manager"], left
            assert not errors, "\n".join(errors)
            assert not [b for b in boxes if b[0] == "showerror"], boxes
        finally:
            root.destroy()
    print("Team (5.9.0): start form = wizard window for an existing folder, Edit team rename/add/remove with named "
          "lanes, older project untouched + unused templates removed on request: PASS")


if __name__ == "__main__":
    main()
