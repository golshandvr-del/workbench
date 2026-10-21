"""Roadmap 5.4.0 gate: the Mission Map right-click menu on the real application.

* Right-click on a ready task opens the floating menu (rounded surface, 4 rows = structure5.TASK_MENU); only
  COPY PROMPT is enabled; the keyboard (Down/Up) stays on enabled rows; Esc closes it and nothing was written.
* COPY PROMPT prepares the prompt, copies it to the clipboard and marks it copied (one Guide transition chain);
  the next menu enables SEND PROMPT; SEND PROMPT records it as sent; GET AI RESPONSE is enabled afterwards.
* Shift+F10 opens the menu for the selected circle. Midnight and Daylight both draw.
* The AI Assistant panel does not exist anywhere (owner decision 2026-10-21).
* ``AIWB_SCREENSHOT_DIR=dir`` writes ``menu_midnight.png`` / ``menu_daylight.png``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from aiwb.ui import structure5
from aiwb.v2.models import normalize_agent
from gui_smoke_helpers import wait_for_project_ready


def settle(root: tk.Tk, n: int = 6) -> None:
    for _ in range(n):
        root.update()
        time.sleep(0.02)


def shot(root: tk.Tk, name: str) -> None:
    out = os.environ.get("AIWB_SCREENSHOT_DIR")
    if not out or not shutil.which("import"):
        return
    Path(out).mkdir(parents=True, exist_ok=True)
    settle(root, 12)
    geo = f"{root.winfo_width()}x{root.winfo_height()}+{root.winfo_rootx()}+{root.winfo_rooty()}"
    subprocess.run(["import", "-window", "root", "-crop", geo, "+repage", str(Path(out) / name)], check=False,
                   timeout=30)


def plan(ctl) -> list[str]:
    p = ctl.project
    with p.store.transaction("smoke agents") as s:
        for i in range(1, 6):
            aid = f"agent-ai-{i}"
            s["agents"][aid] = normalize_agent({"agent_id": aid, "role": "implementer", "name": f"Builder {i}",
                                                "template_id": ""})
    cols: list[list[str]] = [[], [], []]
    for i in range(1, 6):
        for k in range(3):
            t = p.tasks.create({"title": f"Builder {i} step {k + 1}", "objective": "o", "owner_agent_id": f"agent-ai-{i}",
                                "scope": {"include": [f"m{i}/{k}/**"]}, "acceptance_criteria": ["ok"]})
            cols[k].append(t["task_id"])
    for k, label in enumerate(("0.1.0", "0.2.0", "1.0.0")):
        p.timeline.propose_version({"label": label, "task_ids": cols[k]})
    for tid in cols[0]:
        p.tasks.transition(tid, "ready")
    return cols[0]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v5-menu-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Menu five"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        root.geometry("1280x800+0+0")
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
            sh = app.shell
            assert not hasattr(sh, "assistant") and not hasattr(app, "assistant_panel")
            assert "AI Assistant" not in str(structure5.tree())
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            sh.show("workbench")
            settle(root, 10)
            ctl = app.workspace_window.wc.ctl
            first = plan(ctl)
            sh.refresh_status()
            sh.show("home")
            settle(root, 8)
            c = app.mission
            tid = first[1]  # on the dispatch desk now (2 free chats); first[2] waits for a free chat
            assert not any(r["enabled"] for r in app.mission_menu_rows(first[2])), "a queued task offers nothing"
            x, y = c.geo["nodes"][tid]
            wx, wy = int(x - c.canvasx(0)), int(y - c.canvasy(0))
            rev, n = ctl.project.store.revision, ctl.project.store.ledger.count()
            # right-click → floating menu
            c.event_generate("<Button-3>", x=wx, y=wy, rootx=c.winfo_rootx() + wx, rooty=c.winfo_rooty() + wy)
            settle(root, 14)
            menu = app.mission_popup
            assert menu is not None and not menu.closed and menu.top.winfo_viewable()
            assert [r["label"] for r in menu.rows] == [m[1] for m in structure5.TASK_MENU]
            assert [r["enabled"] for r in menu.rows] == [True, False, False, False], menu.rows
            assert menu.index == 0 and menu.canvas.find_withtag("hl") and menu.canvas.find_withtag("surface")
            assert c.selected == tid
            menu.step(1)
            assert menu.index == 0, "keyboard must stay on the only enabled row"
            for theme in ("dark", "light"):
                app.prefs.set_theme(theme)
                settle(root, 4)
                app.mission_menu(tid, c.winfo_rootx() + wx, c.winfo_rooty() + wy)
                settle(root, 14)
                shot(root, f"menu_{'midnight' if theme == 'dark' else 'daylight'}.png")
            app.prefs.set_theme("dark")
            app.mission_popup.top.event_generate("<Escape>")
            settle(root, 4)
            assert app.mission_popup.closed
            assert (ctl.project.store.revision, ctl.project.store.ledger.count()) == (rev, n), "opening wrote state"
            # COPY PROMPT → prepared + copied + clipboard
            app.mission_menu(tid, c.winfo_rootx() + wx, c.winfo_rooty() + wy)
            settle(root, 6)
            app.mission_popup.activate()
            settle(root, 6)
            assert "AIWB" in root.clipboard_get() or len(root.clipboard_get()) > 200, "prompt copied"
            rows = app.mission_menu_rows(tid)
            assert [r["enabled"] for r in rows] == [True, True, True, False], rows
            assert ctl.project.store.revision > rev
            # Shift+F10 on the selected circle opens it again; SEND PROMPT
            c.focus_force()
            settle(root, 4)
            c.event_generate("<Shift-F10>")
            settle(root, 10)
            menu = app.mission_popup
            assert not menu.closed and menu.rows[1]["enabled"], (menu.closed, [r["enabled"] for r in menu.rows], c.selected)
            menu.top.event_generate("<Down>")
            settle(root, 2)
            assert menu.index == 1, menu.index
            menu.top.event_generate("<Return>")
            settle(root, 6)
            rows = app.mission_menu_rows(tid)
            assert [r["id"] for r in rows if r["enabled"]] == ["copy_prompt", "get_response"], rows
            assert app.mission.node(tid)["state"] in ("active", "idle", "attention"), app.mission.node(tid)
            # other tasks unaffected
            assert [r["enabled"] for r in app.mission_menu_rows(first[0])] == [True, False, False, False]
            assert not any(r["enabled"] for r in app.mission_menu_rows(first[2]))
            print("v5.4.0 menu smoke passed: right-click floating menu (4 rows = UI tree) · enabled = Guide · "
                  "keyboard Up/Down/Enter/Esc · Shift+F10 · COPY prepares+copies · SEND records · GET enabled · "
                  "Midnight/Daylight · no AI Assistant")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
