"""Roadmap 5.5.0 gate: the App Map of the real application.

* The map extracted from the running app (Advanced mode, one project open — as ``tools/ui_map.py`` takes it)
  equals the tree in ``docs/UI_MAP.md``; any tab/section/button/menu change without regenerating the map fails.
* The live map passes every balance rule (``ui_map.audit`` is empty).
* Settings › App Map… opens a window that draws every box; the filter narrows it; zoom redraws; Esc closes.
* Extraction only shows pages: the open project's state file is byte-identical afterwards.
* ``AIWB_SCREENSHOT_DIR=dir`` writes ``app_map_midnight.png``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from aiwb.ui import ui_map
from gui_smoke_helpers import wait_for_project_ready

REPO = Path(__file__).resolve().parents[4]


def settle(root: tk.Tk, n: int = 8) -> None:
    for _ in range(n):
        root.update()
        time.sleep(0.02)


def main() -> None:
    sys.path.insert(0, str(REPO / "tools"))
    import ui_map as gen  # tools/ui_map.py — the same document generator
    with tempfile.TemporaryDirectory(prefix="aiwb-v5-map-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Sample project"
        project.mkdir()
        (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
        root = tk.Tk()
        root.geometry("1440x900+0+0")
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
            app.shell.prefs.set_mode("advanced")
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.shell.show("workbench")
            settle(root)
            state = project / ".workbench" / "v2" / "state.json"
            before = state.read_bytes() if state.is_file() else b""
            live = ui_map.extract(app)
            after = state.read_bytes() if state.is_file() else b""
            assert before == after, "extracting the App Map changed the project state"
            assert app.shell.current == "workbench", app.shell.current
            doc = ui_map.parse_markdown((REPO / "docs" / "UI_MAP.md").read_text(encoding="utf-8"))
            if ui_map.to_markdown(doc) != ui_map.to_markdown(live):
                import difflib
                diff = "\n".join(difflib.unified_diff(ui_map.to_markdown(doc).splitlines(),
                                                      ui_map.to_markdown(live).splitlines(), "UI_MAP.md", "live",
                                                      lineterm="", n=1))
                raise AssertionError("docs/UI_MAP.md differs from the live app — run tools/ui_map.py\n" + diff)
            problems = ui_map.audit(live)
            assert not problems, problems
            assert gen.document(live).split("## Tree")[0] in (REPO / "docs" / "UI_MAP.md").read_text(encoding="utf-8")

            app.shell.show("settings")
            settle(root)
            btn = [w for w in _walk(app.settings_tab) if _text(w) == "App Map…"]
            assert len(btn) == 1, "Settings › App Map… missing"
            btn[0].invoke()
            settle(root, 12)
            wins = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and "App Map" in w.title()]
            assert len(wins) == 1, wins
            view = wins[0].view
            total = sum(1 for _ in ui_map.iter_nodes(live)) + 1
            assert view.boxes == total, (view.boxes, total)
            assert len(view.canvas.find_withtag("label")) == total
            view.filter_var.set("Prepare all")
            settle(root)
            assert 1 < view.boxes < total, view.boxes
            view.filter_var.set("")
            view.zoom(1.2)
            settle(root)
            assert view.boxes == total and abs(view.scale - 1.2) < 1e-9
            out = os.environ.get("AIWB_SCREENSHOT_DIR")
            if out and shutil.which("import"):
                Path(out).mkdir(parents=True, exist_ok=True)
                view.zoom(1 / 1.2)
                settle(root, 12)
                w = wins[0]
                geo = f"{w.winfo_width()}x{w.winfo_height()}+{w.winfo_rootx()}+{w.winfo_rooty()}"
                subprocess.run(["import", "-window", "root", "-crop", geo, "+repage",
                                str(Path(out) / "app_map_midnight.png")], check=False, timeout=30)
            wins[0].event_generate("<Escape>")
            settle(root)
            assert not [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and "App Map" in w.title()
                        and w.winfo_exists()]
            print(f"5.5.0 App Map: live == docs/UI_MAP.md ({total} nodes), audit clean, viewer draws/filters/zooms: PASS")
        finally:
            root.destroy()


def _walk(w):
    yield w
    for c in w.winfo_children():
        yield from _walk(c)


def _text(w) -> str:
    try:
        return str(w.cget("text"))
    except tk.TclError:
        return ""


if __name__ == "__main__":
    main()
