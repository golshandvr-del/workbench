"""Roadmap 5.9.0 gate: the New Project wizard with REAL widgets — 1, 3, 5 and 12 AIs, Persian and English names.

For each size the smoke types into the wizard's real entries, sets the count in the real Spinbox, presses Next /
Create project, then checks: the folder exists, the V2 state holds exactly the user's team (no template agent), the
Mission Map lanes carry the user's names in the user's order, the Workbench's next step is the project-manager
prompt (the start questions are never asked again) and the charter prompt binds the team.
"""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
import traceback
from pathlib import Path

NAMES_FA = ["برنامه‌نویس هسته", "طراح رابط", "آزمونگر"]


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


def pump(root, n=5):
    for _ in range(n):
        root.update()


def run_one(wb, root, app, tmp: Path, workers: int, names: list[str]) -> None:
    app.shell.toolbar.menus["new"].invoke(0)          # New Project ▾ › Guided project (recommended)
    pump(root)
    wiz = app.project_wizard
    assert wiz.win.title() == "Create a new project", wiz.win.title()
    project_name = f"Wizard {workers}"
    # step 1 — Project: type into the real entries
    entries = [c for c in walk(wiz.pages[0]) if c.winfo_class() == "TEntry"]
    entries[0].insert(0, project_name)
    entries[1].delete(0, "end")
    entries[1].insert(0, str(tmp))
    wiz.goal_text.insert("1.0", f"A test project with {workers} AIs")
    combo = next(c for c in walk(wiz.pages[0]) if c.winfo_class() == "TCombobox")
    combo.set("Python desktop application")
    combo.event_generate("<<ComboboxSelected>>")
    pump(root)
    assert wiz.vars["platform"].get().startswith("Windows desktop, Python"), wiz.vars["platform"].get()
    assert not [c for c in walk(wiz.win) if c.winfo_class() == "TButton" and c.cget("text") == "Architecture plan…"], \
        "A2: Architecture plan is not part of creating a project"
    wiz.next_btn.invoke()
    pump(root)
    assert wiz.step == 1, f"Next must go to the Team step: {wiz.error_var.get()}"
    # step 2 — Team: the real Spinbox, then the real name entries
    box = wiz.team.count_box
    box.focus_force()                                  # a real user clicks into the box first
    pump(root)
    box.delete(0, "end")
    box.insert(0, str(workers))
    box.event_generate("<Return>")
    pump(root)
    rows = wiz.team.entries()
    assert len(rows) == workers + 1, f"{len(rows)} rows for {workers} AIs"
    for i, name in enumerate(names[:workers], start=1):
        rows[i]["name"].set(name)
    rows[0]["name"].set("مدیر پروژه" if workers == 3 else "Lead")
    wiz.next_btn.invoke()
    pump(root)
    assert wiz.step == 2, f"Next must go to the Answers step: {wiz.error_var.get()}"
    # step 3 — Answers: AIWB is selected; JSON/ZIP are visible but not selectable yet
    assert wiz.vars["format"].get() == "aiwb"
    assert str(wiz.format_buttons["zip"].cget("state")) == "disabled"
    assert wiz.next_btn.cget("text") == "Create project"
    wiz.next_btn.invoke()
    pump(root, 20)
    assert not wiz.win.winfo_exists(), f"wizard still open: {wiz.error_var.get()}"
    project = (tmp / project_name).resolve()
    assert project.is_dir() and app.workspace == project, "the new project is open"
    deadline = 200
    while (getattr(app, "workspace_window", None) is None
           or getattr(app.workspace_window, "_project_root", None) != str(project)) and deadline:
        pump(root, 2)
        deadline -= 1
    ws = app.workspace_window
    st = ws.wc.ctl.state()
    agents = [a for a in st["agents"].values() if a.get("enabled", True)]
    assert len(agents) == workers + 1, f"{len(agents)} agents for {workers} AIs: {sorted(st['agents'])}"
    assert not {"agent-architect", "agent-implementer", "agent-reviewer"} & set(st["agents"]), "no template agent"
    expected = [n if n else f"Developer {i}" for i, n in enumerate((names + [""] * workers)[:workers], start=1)]
    from aiwb.ui import mission_model
    lanes = [ln["name"] for ln in mission_model.build(st)["lanes"]]
    assert lanes == expected, f"lanes {lanes} != {expected}"
    # no repeated question: the guided Workbench is on the project-manager prompt, not on "Start the project"
    assert ws.next_btn.cget("text") == "Copy the charter prompt", ws.next_btn.cget("text")
    assert st["settings"]["goal"].startswith("A test project")
    ws.next_btn.invoke()
    pump(root)
    prompt = root.clipboard_get()
    assert "Team chosen by the user (binding)" in prompt
    for n in expected:
        assert n in prompt, f"{n!r} missing from the charter prompt"
    # the Mission Map on Home draws the names
    app.shell.show("home")
    pump(root, 10)
    canvas = app.mission
    drawn = [canvas.itemcget(i, "text") for i in canvas.find_withtag("lane_name")]
    assert drawn == [mission_model.short_name(n) for n in expected], f"lane names on the map: {drawn}"
    shot = os.environ.get("AIWB_SCREENSHOT_DIR")
    if shot:
        import subprocess
        Path(shot).mkdir(parents=True, exist_ok=True)
        subprocess.run(["import", "-window", "root", str(Path(shot) / f"wizard_map_{workers}.png")], check=False)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["LOCALAPPDATA"] = str(Path(tmp) / "AppData")
        import AI_Workbench as wb
        root = tk.Tk()
        root.geometry("1366x800+0+0")
        errors: list[str] = []
        root.report_callback_exception = lambda *a: errors.append("".join(traceback.format_exception(*a)))
        boxes = []
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(wb.messagebox, name, (lambda n: lambda *a, **k: boxes.append((n, a)))(name))
        app = wb.WorkbenchApp(root)
        pump(root)
        try:
            # a blocked step shows the reason inline and stays on the step
            app.shell.toolbar.menus["new"].invoke(0)
            pump(root)
            wiz = app.project_wizard
            wiz.next_btn.invoke()
            pump(root)
            assert wiz.step == 0 and "name" in wiz.error_var.get(), wiz.error_var.get()
            wiz.cancel_btn.invoke()
            pump(root)
            for workers, names in ((1, ["Solo dev"]), (3, NAMES_FA), (5, ["Core", "UI", "Tests", "Docs", "Build"]),
                                   (12, [])):
                run_one(wb, root, app, Path(tmp), workers, names)
            assert not errors, "\n".join(errors)
            assert not [b for b in boxes if b[0] == "showerror"], boxes
        finally:
            root.destroy()
    print("New Project wizard (5.9.0): 1/3/5/12 AIs, Persian + English names, no templates, named lanes, "
          "no repeated question: PASS")


if __name__ == "__main__":
    main()
