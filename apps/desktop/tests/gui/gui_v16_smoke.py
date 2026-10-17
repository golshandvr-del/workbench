"""GUI smoke for v1.6 right-click editing menus and file-runner controls."""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v16-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "project"
        project.mkdir()
        (project / "hello.py").write_text("print('hello from project')\n", encoding="utf-8")

        root = tk.Tk()
        app = wb.WorkbenchApp(root)
        app.set_workspace(project)
        wait_for_project_ready(app, root, project)
        root.update_idletasks()
        root.update()

        # On Windows, Menu.tk_popup enters the native modal menu loop (TrackPopupMenu)
        # and only returns after a real user dismisses the menu, which never happens
        # on an unattended runner. The menu contents/commands are what this smoke
        # verifies, so on Windows posting is replaced by a recorder.
        posted: list[tuple[int, int]] = []
        if os.name == "nt":
            root._aiwb_edit_context_menu.tk_popup = lambda x, y, *a, **k: posted.append((x, y))

        # Right-click in an editable text widget must build a standard context menu.
        app.task_text.delete("1.0", "end")
        app.task_text.insert("1.0", "select me")
        app.task_text.tag_add("sel", "1.0", "1.7")
        app.task_text.focus_force()
        app.task_text.event_generate("<Button-3>", x=8, y=8)
        root.update_idletasks()
        root.update()
        menu = root._aiwb_edit_context_menu
        assert os.name != "nt" or posted, "context menu was not posted"
        labels = [menu.entrycget(index, "label") for index in range(menu.index("end") + 1) if menu.type(index) == "command"]
        assert {"Cut", "Copy", "Paste", "Delete", "Select all", "Undo", "Redo"}.issubset(set(labels)), labels
        copy_index = next(index for index in range(menu.index("end") + 1) if menu.type(index) == "command" and menu.entrycget(index, "label") == "Copy")
        assert menu.entrycget(copy_index, "state") == "normal"
        menu.invoke(copy_index)
        root.update()
        assert root.clipboard_get() == "select "
        menu.unpost()

        # The same binding must work in single-line ttk.Entry widgets as well.
        import tkinter.ttk as ttk
        entry = ttk.Entry(root)
        entry.pack()
        entry.insert(0, "entry copy")
        entry.selection_range(0, 5)
        entry.event_generate("<Button-3>", x=8, y=8)
        root.update_idletasks()
        root.update()
        menu = root._aiwb_edit_context_menu
        copy_index = next(index for index in range(menu.index("end") + 1) if menu.type(index) == "command" and menu.entrycget(index, "label") == "Copy")
        assert menu.entrycget(copy_index, "state") == "normal"
        menu.invoke(copy_index)
        root.update()
        assert root.clipboard_get() == "entry"
        menu.unpost()
        entry.destroy()

        # The Run tab exposes the file-run controls and prepares a real Python command.
        assert hasattr(app, "run_file_var")
        app.run_file_var.set("hello.py")
        spec = wb.build_project_file_run_spec(project, app.run_file_var.get())
        assert spec["kind"] == "python"
        # The app canonicalises paths (Windows temp dirs may be 8.3 short names such as RUNNER~1).
        assert str((project / "hello.py").resolve()) in spec["argv"], spec["argv"]

        # The actual runner is already covered by unit tests; ensure UI lifecycle remains clean.
        app.on_close()
        print("v1.6 right-click context menu + file-runner GUI smoke: PASS")


if __name__ == "__main__":
    main()
