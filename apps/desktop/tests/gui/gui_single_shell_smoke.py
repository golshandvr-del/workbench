"""Gate 3.0.0 — single shell (roadmap 3.x, ADR-009).

* The Project Workbench opens as a page of the main window: no Toplevel is created.
* One theme for everything: switching to dark changes the main window, the classic
  pages and the Workbench at once; Fluent (Sun Valley) is the element theme.
* One language and one mode: the Workbench has no own selectors; changing the
  application language relabels the rail and the Workbench navigation (RTL mirrors
  the rail); Simple hides the expert pages, Advanced shows them.
* View preferences never change project state.
* No hard-coded colours remain in the main window module.
"""
from __future__ import annotations

import os
import re
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready


def toplevels(root: tk.Misc) -> list[tk.Misc]:
    out, stack = [], list(root.winfo_children())  # Toplevel windows (combobox popdowns excluded)
    while stack:
        w = stack.pop()
        if isinstance(w, tk.Toplevel) and w.winfo_class() != "ComboboxPopdown" and "popdown" not in str(w):
            out.append(str(w))
        stack.extend(w.winfo_children())
    return out


def main() -> None:
    src = Path(wb.__file__).read_text(encoding="utf-8")
    assert not re.findall(r"#[0-9A-Fa-f]{6}", src), "hard-coded colours in AI_Workbench.py"
    with tempfile.TemporaryDirectory(prefix="aiwb-shell-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Shell project"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            style = ttk.Style(root)
            assert style.theme_use() == "sun-valley-light", style.theme_use()
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            before = set(toplevels(root))
            app.shell.show("workbench")
            for _ in range(5):
                root.update()
            w = app.workspace_window
            assert w is not None and w.embedded, "Workbench must be embedded"
            assert not (set(toplevels(root)) - before), ("opening the Workbench created a window", toplevels(root))
            assert w.win.winfo_toplevel() is root
            assert not w.mode_box.winfo_ismapped() and not w.lang_box.winfo_ismapped() and not w.theme_box.winfo_ismapped()
            ctl = w.wc.ctl
            rev, n = ctl.project.store.revision, ctl.project.store.ledger.count()
            # theme: one switch for the whole application
            app.prefs.set_theme("dark")
            root.update()
            assert style.theme_use() == "sun-valley-dark"
            assert str(root.cget("background")).lower() == "#1c1c1c"
            assert app.shell.assets.theme == "midnight"
            assert w.wc.theme == "dark"
            assert style.lookup("WS.TFrame", "background") == style.lookup("TFrame", "background")
            app.prefs.set_theme("light")
            # language: rail + workbench relabel, rail mirrors
            app.prefs.set_lang("fa")
            root.update()
            assert app.shell.nav["home"].text == "Home"  # 5.x rail labels: English-only product policy
            assert w.nav["overview"].cget("text") == "نمای کلی", w.nav["overview"].cget("text")
            assert app.shell.rail.pack_info()["side"] == "right"
            app.prefs.set_lang("en")
            root.update()
            assert app.shell.rail.pack_info()["side"] == "left"
            # mode: simple hides expert pages, advanced shows them; one source of truth
            app.prefs.set_mode("simple")
            root.update()
            assert list(app.shell.nav) == ["home", "projects", "agents", "history", "settings"], list(app.shell.nav)
            assert all(b.winfo_ismapped() for b in app.shell.nav.values()), "5.x rail: five fixed destinations"
            assert "git" not in app.shell.visible_pages() and "workbench" in app.shell.visible_pages()
            assert w.wc.mode == "simple" and ctl.mode == "simple"
            app.prefs.set_mode("advanced")
            root.update()
            assert "git" in app.shell.visible_pages()
            assert ctl.mode == "advanced"
            # settings persisted application-wide
            assert app.settings_data["ui_mode"] == "advanced" and app.settings_data["ui_theme"] == "light"
            # existing calls that select a page directly keep the rail in sync
            app.notebook.select(app.response_tab)
            root.update()
            assert app.shell.current == "response" and app.shell.nav_var.get() == "agents"  # Agents › Tools
            assert app.shell.rail.current == "agents"
            # 5.x toolbar + status bar
            assert [b.text for b in app.shell.toolbar.buttons.values()] == ["New Project", "Open", "Save", "Run"]
            facts = app.shell.refresh_status()
            assert facts["text"].endswith("running") or "Milestone" in facts["text"], facts
            app.shell.nav["projects"].invoke()
            root.update()
            assert app.shell.current == "workbench"
            assert (ctl.project.store.revision, ctl.project.store.ledger.count()) == (rev, n), "view change wrote state"
            print("Single shell smoke passed: Workbench embedded (no Toplevel) · one Fluent theme · one language (RTL rail) · "
                  "one Simple/Advanced mode · settings persisted · no hard-coded colours")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
