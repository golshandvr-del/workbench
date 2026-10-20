"""Roadmap 5.1.0 gate: the 5.x shell (toolbar · icon rail · live status bar).

* Toolbar, rail and status bar follow ``structure5`` (the tables ``docs/UI_TREE.md`` is checked against).
* At 1024x640, 1280x720, 1600x900 and 1920x1080, in Midnight and Daylight, every toolbar button and rail item is
  fully inside the window and no button on any page is squeezed or clipped.
* Every rail destination opens its page; expert pages light up Agents (Agents › Tools).
* Toolbar Save / Run work without a project; the status bar shows the V2 facts (agents running, milestone).
* Changing theme or page never writes project state.
* ``AIWB_SCREENSHOT_DIR=dir`` writes ``shell_midnight.png`` / ``shell_daylight.png`` (needs ImageMagick ``import``).
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
from aiwb.ui import layout, structure5
from gui_smoke_helpers import wait_for_project_ready

SIZES = ("1024x640", "1280x720", "1600x900", "1920x1080")


def settle(root: tk.Tk, n: int = 6) -> None:
    for _ in range(n):
        root.update()
        time.sleep(0.01)


def inside(root: tk.Tk, w: tk.Misc) -> bool:
    rx, ry = root.winfo_rootx(), root.winfo_rooty()
    x, y = w.winfo_rootx() - rx, w.winfo_rooty() - ry
    return (w.winfo_ismapped() and x >= 0 and y >= 0 and x + w.winfo_width() <= root.winfo_width() + 1
            and y + w.winfo_height() <= root.winfo_height() + 1)


def shot(root: tk.Tk, name: str) -> None:
    out = os.environ.get("AIWB_SCREENSHOT_DIR")
    if not out or not shutil.which("import"):
        return
    Path(out).mkdir(parents=True, exist_ok=True)
    settle(root, 10)
    subprocess.run(["import", "-window", str(root.winfo_id()), str(Path(out) / name)], check=False, timeout=30)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v5-shell-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Shell five"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            sh = app.shell
            # structure = UI tree
            assert [b.text for b in sh.toolbar.buttons.values()] == [t[1] for t in structure5.TOOLBAR]
            assert [k for k in sh.nav] == [r[0] for r in structure5.RAIL]
            assert [sh.nav[r[0]].text for r in structure5.RAIL] == [r[1] for r in structure5.RAIL]
            menu = sh.toolbar.menus["new"]
            assert [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)] == \
                [c[1] for c in structure5.TOOLBAR[0][3]]
            # no project: Save / Run are safe and explain themselves
            sh.toolbar.buttons["save"].invoke()
            assert "Settings saved" in app.status_var.get(), app.status_var.get()
            sh.toolbar.buttons["run"].invoke()
            assert "Open or create a project" in app.status_var.get(), app.status_var.get()
            assert sh.refresh_status()["text"] == "No project open"
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.prefs.set_mode("advanced")
            sh.show("workbench")
            settle(root, 10)
            ctl = app.workspace_window.wc.ctl
            rev, n = ctl.project.store.revision, ctl.project.store.ledger.count()
            facts = sh.refresh_status()
            assert facts["text"] in ("No agents running",) or "running" in facts["text"], facts
            assert sh.statusbar.saved_var.get() == "Saved"
            # every destination opens its page; tools map to Agents
            for dest in sh.nav:
                sh.nav[dest].invoke()
                settle(root, 3)
                assert sh.rail.current == dest and sh.nav_var.get() == dest, (dest, sh.rail.current)
            for key, _label in structure5.TOOLS:
                app.agents_tool_buttons[key].invoke()
                settle(root, 2)
                assert sh.current == key and sh.rail.current == "agents", (key, sh.current)
            failures = []
            for theme in ("dark", "light"):
                app.prefs.set_theme(theme)
                settle(root)
                want = "midnight" if theme == "dark" else "daylight"
                assert sh.assets.theme == want
                from aiwb.ui.tokens5 import palette5
                assert str(sh.toolbar.cget("background")).lower() == palette5(want)["panel"]
                assert str(sh.statusbar.cget("background")).lower() == palette5(want)["panel"]
                for size in SIZES:
                    root.geometry(size + "+0+0")
                    settle(root)
                    for w in list(sh.toolbar.buttons.values()) + list(sh.nav.values()) + [sh.statusbar.facts]:
                        if not inside(root, w):
                            failures.append((theme, size, "chrome", getattr(w, "key", str(w))))
                    for page in sh.visible_pages():
                        sh.show(page)
                        settle(root, 4)
                        bad = layout.outside_window(root)
                        if bad:
                            failures.append((theme, size, page, bad[:3]))
                root.geometry("1280x720+0+0")
                sh.show("home")
                shot(root, f"shell_{want}.png")
            assert not failures, failures
            assert (ctl.project.store.revision, ctl.project.store.ledger.count()) == (rev, n), "view change wrote state"
            print("v5.1.0 shell smoke passed: toolbar/rail = UI tree · 5 destinations + Tools -> Agents · "
                  f"{len(SIZES)} sizes × Midnight/Daylight, nothing clipped · Save/Run safe · live status bar · "
                  "no state written")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
