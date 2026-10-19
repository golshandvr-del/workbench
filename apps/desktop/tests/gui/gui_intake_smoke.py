"""Gate 3.2.0 GUI smoke — reliable intake through the real Response page.

* A ChatGPT-style copy (smart quotes, escaped markers, NBSP, outer fence) previews
  the right file without writing it.
* A truncated answer puts a precise "continue" prompt on the clipboard and never
  writes anything.
* The default output format is AIWB file blocks.
"""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-intake-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Intake Project"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            wb.messagebox.askyesno = lambda *a, **k: True
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            assert app.output_format_var.get() == wb.OUTPUT_FORMAT_GEMINI, app.output_format_var.get()

            messy = ("Sure, here you go:\n\n````\n"
                     "\\<\\<\\<AIWB\\_FILE path=\u201csrc/hello.py\u201d action=\u201cwrite\u201d body=\u201craw\u201d\\>\\>\\>\r\n"
                     "print('hello')\u00a0# hi\r\n"
                     "\\<\\<\\<AIWB\\_END\\_FILE\\>\\>\\>\r\n````\n")
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", messy)
            app.preview_response()
            root.update()
            assert app.pending_changes and [c.path for c in app.pending_changes] == ["src/hello.py"], app.status_var.get()
            assert "cleaned" in app.pending_response_format, app.pending_response_format
            assert not (project / "src" / "hello.py").exists(), "preview must not write files"
            if app.pending_diff_window is not None:
                app.pending_diff_window.destroy()
                app.pending_diff_window = None

            cut = ('<<<AIWB_FILE path="a.py" action="write" body="raw">>>\nA = 1\n<<<AIWB_END_FILE>>>\n'
                   '<<<AIWB_FILE path="b.py" action="write" body="raw">>>\nB = ')
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", cut)
            app.preview_response()
            root.update()
            clip = root.clipboard_get()
            assert "cut off" in clip and '"b.py"' in clip and "a.py" in clip, clip
            assert "cut off" in app.status_var.get(), app.status_var.get()
            assert not (project / "a.py").exists() and not (project / "b.py").exists()
        finally:
            root.destroy()
    print("Intake smoke passed: messy chat copy cleaned and previewed; truncated answer -> continue prompt; default format = AIWB blocks")


if __name__ == "__main__":
    main()
