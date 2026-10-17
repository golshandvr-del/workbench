"""End-to-end GUI smoke for v1.5 diagnostics, workflow state, and tree/diff preview."""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v15-smoke-") as temp:
        base = Path(temp)
        os.environ["LOCALAPPDATA"] = str(base / "appdata")
        project = base / "project"
        project.mkdir()
        root = tk.Tk()
        app = wb.WorkbenchApp(root)
        app.set_workspace(project)
        wait_for_project_ready(app, root, project)
        response = '''<<<AIWB_FILE action="write" path="src/new.py">>>
```python
print("hello v1.5")
```
<<<AIWB_END_FILE>>>'''
        app.response_input.insert("1.0", response)
        app.preview_response()
        root.update_idletasks()
        root.update()
        state = wb.load_task_state(project)
        assert state.get("workflow_stage") == "Validated", state
        assert app.pending_response_recorded is True
        assert app.pending_diff_window is not None and app.pending_diff_window.winfo_exists()
        trees = [w for w in walk(app.pending_diff_window) if isinstance(w, tk.ttk.Treeview)]
        assert trees, "Proposed file tree is not rendered"
        file_tree = next((t for t in trees if "file_0" in t.get_children()), None)
        assert file_tree is not None, [t.get_children() for t in trees]
        assert file_tree.item("file_0", "text") == "src/new.py"
        diffs = [w for w in walk(app.pending_diff_window) if isinstance(w, tk.Text)]
        assert any("hello v1.5" in w.get("1.0", "end-1c") for w in diffs), "Selected file diff is not rendered"
        diagnostics = wb.diagnose_model_response(response, project)
        assert diagnostics["success"] and diagnostics["file_count"] == 1
        repair = wb.build_repair_prompt(project, error="expected smoke error", failure_stage="test", format_name=wb.OUTPUT_FORMAT_GEMINI)
        assert "expected smoke error" in repair and "AIWB_FILE" in repair

        # A failed new import must invalidate the previous good preview and expose diagnostics.
        app.response_input.delete("1.0", "end")
        app.response_input.insert("1.0", '<<<AIWB_FILE path="src/broken.py" action="write">>>\nno end marker')
        app.preview_response()
        root.update_idletasks()
        root.update()
        state = wb.load_task_state(project)
        assert state.get("workflow_stage") == "Import Failed", state
        assert app.pending_payload is None and app.pending_changes is None
        assert app.pending_diff_window is None
        history = wb.read_execution_history(project)
        assert any(e.get("type") == "import_diagnostics_generated" and not e.get("success") for e in history)

        # The clipboard Paste path must also open diagnostics when format detection itself fails.
        root.clipboard_clear()
        root.clipboard_append("unstructured response with no file manifest")
        root.update()
        app.paste_response()
        root.update_idletasks()
        root.update()
        root.update_idletasks()
        root.update()
        state = wb.load_task_state(project)
        assert state.get("workflow_stage") == "Import Failed", state
        history = wb.read_execution_history(project)
        assert any(e.get("type") == "model_response_rejected" for e in history)
        assert any(e.get("type") == "import_diagnostics_generated" and not e.get("success") for e in history)
        for top in list(root.winfo_children()):
            if isinstance(top, tk.Toplevel):
                top.destroy()
        app.on_close()
        print("v1.5 diagnostics/workflow/tree-diff GUI integration: PASS")


if __name__ == "__main__":
    main()
