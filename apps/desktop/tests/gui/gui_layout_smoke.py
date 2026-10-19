"""Gate 3.1.0 — robust layout (roadmap 3.x, problem P2).

At 1024x640, 1280x720 and 1920x1080, in English (the only supported UI language for now), every page of the
single window shows each button fully: none is squeezed below its requested width or
clipped by an ancestor. A dialog wider/taller than the screen is fitted to the work area.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))


def main() -> None:
    tmp = tempfile.mkdtemp()
    os.environ["LOCALAPPDATA"] = tmp + "/appdata"
    import AI_Workbench as wb
    from aiwb.ui import layout
    from gui_smoke_helpers import wait_for_project_ready

    proj = Path(tmp) / "proj"
    proj.mkdir()
    (proj / "main.py").write_text("print(1)\n", encoding="utf-8")
    root = tk.Tk()
    app = wb.WorkbenchApp(root)
    app.set_workspace(proj, focus_project=True)
    wait_for_project_ready(app, root, proj)
    app.prefs.set_mode("advanced")
    failures = []
    for lang in ("en",):  # English-only product scope (see ROADMAP: language policy)
        app.prefs.set_lang(lang)
        for size in ("1024x640", "1280x720", "1920x1080"):
            root.geometry(size + "+0+0")
            for page in app.shell.visible_pages():
                app.shell.show(page)
                for _ in range(8):
                    root.update()
                    time.sleep(0.01)
                bad = layout.outside_window(root)
                if bad:
                    failures.append((lang, size, page, bad[:3]))
    assert not failures, failures
    dlg = tk.Toplevel(root)
    dlg.geometry("5000x4000+3000+3000")
    dlg.minsize(4000, 3000)
    for _ in range(10):
        root.update()
        time.sleep(0.01)
    _x, _y, aw, ah = layout.work_area(root)
    layout.keep_on_screen(dlg)
    root.update()
    assert dlg.winfo_width() <= aw and dlg.winfo_height() <= ah, (dlg.winfo_width(), dlg.winfo_height(), aw, ah)
    assert dlg.minsize()[0] <= aw and dlg.minsize()[1] <= ah, dlg.minsize()
    dlg.destroy()
    root.destroy()
    print("Layout smoke passed: no squeezed/clipped button on any page at 1024x640, 1280x720, 1920x1080 (EN); oversized dialog fitted to the work area")


if __name__ == "__main__":
    main()
