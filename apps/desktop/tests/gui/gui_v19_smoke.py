"""GUI integration smoke test for linked prompt history, context requests, and error repairs."""
from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_idle, wait_for_project_ready
import conversation_store as history


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v19-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Linked Workflow Project"
        project.mkdir()
        src = project / "src"
        src.mkdir()
        (src / "main.py").write_text("alpha\nbeta\ngamma\ndelta\n", encoding="utf-8")

        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            wb.messagebox.showinfo = lambda *args, **kwargs: None
            wb.messagebox.showwarning = lambda *args, **kwargs: None
            wb.messagebox.showerror = lambda *args, **kwargs: None
            wb.messagebox.askyesno = lambda *args, **kwargs: True
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            root.update()
            app.task_text.insert("1.0", "Improve the parser using exact existing behavior")
            app.profile_vars["prompt_stage"].set("Request exact context files")
            app.output_format_var.set(wb.OUTPUT_FORMAT_GPT_ZIP)
            app.build_prompt()
            root.update()
            entries = history.list_history(project)
            assert len(entries) == 1 and entries[0]["label"] == "Start"
            start_id = entries[0]["id"]
            assert "workbench-plan-v2" in entries[0]["prompt_text"]
            assert entries[0]["output_format"] == wb.OUTPUT_FORMAT_JSON, "planning prompts must record JSON as actual transport"

            context_plan = {
                "protocol": "workbench-plan-v1", "task_id": "parser-context", "summary": "Need exact parser lines",
                "requested_context_files": [],
                "requested_context_ranges": [{"path": "src/main.py", "start_line": 2, "end_line": 3, "reason": "inspect handling"}],
                "requested_user_uploads": [{"name": "scope.png", "reason": "binary reference", "purpose": "compare observed output"}],
                "proposed_files": [], "external_requirements": [], "clarifying_questions": [], "assumptions": [],
            }
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", json.dumps(context_plan))
            app.import_context_plan()
            root.update()
            assert history.get_history_entry(project, start_id)["normalized_output"]["protocol"] == "workbench-plan-v1"
            wait_for_idle(app, root)
            wait_for_project_ready(app, root, project)
            app.build_prompt()
            root.update()
            entries = history.list_history(project)
            assert len(entries) == 2 and entries[1]["label"] == "Step 1"
            assert "2: beta" in entries[1]["prompt_text"] and "3: gamma" in entries[1]["prompt_text"]
            assert "scope.png" in entries[1]["prompt_text"] and "the user must upload" in entries[1]["prompt_text"]
            assert entries[1]["requested_context_ranges"][0]["included_line_range"] == "2-3"

            model_payload = {
                "protocol": wb.PROTOCOL_V2, "task_id": "parser-fix", "summary": "Add a tiny output file",
                "files": [{"path": "result.txt", "action": "write", "content": "ok\n"}],
                "actions": [], "next_steps": [], "completion_status": "in_progress",
            }
            raw_model_output = json.dumps(model_payload)
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", raw_model_output)
            app.preview_response()
            root.update()
            entries = history.list_history(project)
            step = history.get_history_entry(project, entries[-1]["id"])
            assert step["model_output"] == raw_model_output
            assert step["response_status"] == "Validated; awaiting review/apply"
            # Report a real-world failure for that response and make sure it is attached to the same step.
            history.record_manual_error(project, step["id"], stage="Test failure", details="Expected 5, got 4", file_path="src/main.py", steps="Run parser test")
            app._refresh_history_view(select_id=step["id"])
            app.show_repair_prompt(failure_stage="Test failure", error="Expected 5, got 4", format_name=wb.OUTPUT_FORMAT_GPT_ZIP)
            root.update()
            entries = history.list_history(project)
            assert len(entries) == 3 and entries[-1]["kind"] == "repair" and entries[-1]["label"] == "Step 2"
            assert history.get_history_entry(project, step["id"])["manual_error"]["details"] == "Expected 5, got 4"
            state = wb.load_task_state(project)
            assert state["active_prompt_entry_id"] == entries[-1]["id"]
            assert app.history_tree.get_children(), "history tree should be populated"
            handoff = wb.build_continuation_handoff_text(project)
            assert "Expected 5, got 4" in handoff, "active repair handoff must retain parent-step failure evidence"
            app.history_filter_var.set("Repair")
            app._refresh_history_view()
            visible_entries = [child for task_iid in app.history_tree.get_children() for child in app.history_tree.get_children(task_iid)]
            assert len(visible_entries) == 1 and "Repair" in app.history_tree.item(visible_entries[0], "text")
            app._clear_history_filter()
            original_prompt = history.get_history_entry(project, start_id)["prompt_text"]
            revision = app._create_history_prompt_revision(start_id, original_prompt + "\n\nUSER-EDITED REVISION TEST")
            assert revision["parent_entry_id"] == start_id and revision["kind"] == "prompt-revision"
            revision_iid = "entry-" + revision["id"]
            assert app.history_tree.parent(revision_iid) == "entry-" + start_id, "linked revisions should appear under their source step"
            assert history.get_history_entry(project, start_id)["prompt_text"] == original_prompt
            assert "USER-EDITED REVISION TEST" in history.get_history_entry(project, revision["id"])["prompt_text"]
            revised_state = wb.load_task_state(project)
            assert revised_state["active_prompt_entry_id"] == revision["id"]
            assert revised_state["workflow_stage"] == "Prompt Ready"

            # Context requests must never leak when the user starts an unrelated task.
            state["requested_context_ranges"] = [{"path": "src/main.py", "start_line": 2, "end_line": 3, "reason": "old task only"}]
            state["requested_user_uploads"] = [{"name": "old-task-only.pdf", "reason": "prior task artifact", "purpose": "must not leak"}]
            state["unresolved_context_requests"] = ["old-task-only.pdf was unavailable for the previous task"]
            wb.save_task_state(project, state)
            app._set_text(app.task_text, "Start an unrelated task with no inherited files")
            app.build_prompt()
            root.update()
            entries = history.list_history(project)
            newest = entries[-1]
            assert newest["label"] == "Start", "new task should start a new step sequence"
            assert "2: beta" not in newest["prompt_text"] and "3: gamma" not in newest["prompt_text"]
            assert "old-task-only.pdf" not in newest["prompt_text"], "manual upload request leaked across tasks"
            assert newest["requested_context_ranges"] == [] and newest["requested_user_uploads"] == []
            cleared_state = wb.load_task_state(project)
            assert not cleared_state.get("requested_context_ranges") and not cleared_state.get("requested_user_uploads")
            print("v1.9 linked prompt history + context-range handoff + repair + task-isolation flow: PASS")
            # Close dialogs created by repair prompts before closing the app.
            for child in root.winfo_children():
                if isinstance(child, tk.Toplevel):
                    try:
                        child.destroy()
                    except tk.TclError:
                        pass
            app.on_close()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    main()
