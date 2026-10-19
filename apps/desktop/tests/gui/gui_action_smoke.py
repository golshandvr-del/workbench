"""End-to-end GUI smoke test: prompt -> response -> preview -> apply -> queued run -> handoff."""
import json
import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch
from gui_smoke_helpers import wait_for_idle, wait_for_project_ready

with tempfile.TemporaryDirectory() as tmp:
    os.environ["LOCALAPPDATA"] = str(Path(tmp) / "AppData")
    import AI_Workbench as wb

    root = tk.Tk()
    app = wb.WorkbenchApp(root)
    root.update()
    wb.messagebox.showinfo = lambda *args, **kwargs: None
    wb.messagebox.showwarning = lambda *args, **kwargs: None
    wb.messagebox.showerror = lambda *args, **kwargs: None

    project = Path(tmp) / "Action Smoke Project"
    project.mkdir()
    app.set_workspace(project, focus_project=True)
    wait_for_project_ready(app, root, project)
    root.update()
    app.task_text.insert("1.0", "Create main.py, run it, and capture the actual output.")
    app.build_prompt()
    state = wb.load_task_state(project)
    assert state["task_text"].startswith("Create main.py")
    assert state["task_id"].startswith("task-")

    command = f'"{sys.executable}" -c "print(13579)"'
    payload = {
        "protocol": wb.PROTOCOL_V2,
        "task_id": "MODEL-CLAIMED-TASK",
        "summary": "Create a runnable file and then execute a harmless smoke command.",
        "files": [{"path": "src/main.py", "action": "write", "content": "def main():\n    return 13579\n\nif __name__ == \"__main__\":\n    print(main())\n"}],
        "actions": [{"id": "smoke", "purpose": "Emit a numeric smoke-test result", "command": command, "working_directory": ".", "timeout_seconds": 30}],
        "next_steps": ["Inspect the exact command result."],
        "completion_status": "in_progress",
    }
    app.response_input.insert("1.0", json.dumps(payload))
    app.preview_response()
    root.update()
    assert app.pending_changes and app.pending_changes[0].path == "src/main.py"
    assert len(app.pending_actions) == 1
    assert (project / ".workbench" / "latest_model_response.json").is_file()
    recorded_state = wb.load_task_state(project)
    assert recorded_state["task_id"] == state["task_id"]
    assert recorded_state["model_reported_task_id"] == "MODEL-CLAIMED-TASK"

    with patch.object(wb.messagebox, "askyesno", return_value=True):
        app.apply_pending_changes(app.pending_diff_window)
    root.update()
    wait_for_idle(app, root)
    assert (project / "src" / "main.py").is_file()
    queue_items = wb.load_action_queue(project)
    assert len(queue_items) == 1 and queue_items[0]["status"] == "Pending"
    assert queue_items[0]["source_task_id"] == state["task_id"]
    assert not any(event.get("type") == "action_finished" for event in wb.read_execution_history(project))

    result = wb.execute_queued_actions(project, [queue_items[0]["queue_id"]])
    assert result["results"][0]["status"] == "Passed"
    assert "13579" in result["results"][0]["output"]
    handoff = wb.build_continuation_handoff_text(project, include_response_contents=True)
    assert "13579" in handoff
    assert "current file matches model output" in handoff
    assert "action_finished" in handoff

    # A malformed response must leave a durable rejection event rather than disappearing silently.
    app.response_input.delete("1.0", "end")
    app.response_input.insert("1.0", "this is not a supported model response")
    app.preview_response()
    root.update()
    assert any(event.get("type") == "model_response_rejected" for event in wb.read_execution_history(project))

    # If the exact validated response cannot be durably archived, applying must be blocked.
    blocked_payload = {
        "protocol": wb.PROTOCOL_V2,
        "task_id": "ANOTHER-MODEL-ID",
        "summary": "This change must not be applied when the response archive cannot be saved.",
        "files": [{"path": "must_not_apply.py", "action": "write", "content": "print('should not exist')\n"}],
        "actions": [],
        "next_steps": [],
        "completion_status": "in_progress",
    }
    app.response_input.delete("1.0", "end")
    app.response_input.insert("1.0", json.dumps(blocked_payload))
    with patch.object(app, "_record_model_response", side_effect=OSError("simulated metadata disk error")):
        app.preview_response()
    root.update()
    assert app.pending_response_recorded is False
    with patch.object(wb.messagebox, "askyesno", return_value=True):
        app.apply_pending_changes(app.pending_diff_window)
    assert not (project / "must_not_apply.py").exists()
    if app.pending_diff_window is not None:
        app.pending_diff_window.destroy()
        app.pending_diff_window = None

    # Ensure Git install/update controls exist in the Git tab.
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    from aiwb.ui import actions as ui_actions  # 3.3.0: rarely used commands live in the More ▾ menu
    button_texts = ui_actions.all_commands([app.git_tab])
    assert "Install Git" in button_texts and "Update Git" in button_texts, button_texts
    root.destroy()
print("Action pipeline GUI integration: PASS")
