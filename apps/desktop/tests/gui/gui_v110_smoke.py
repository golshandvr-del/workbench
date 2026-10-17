"""GUI smoke test for v1.10 explicit raw-body response intake and safe apply."""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_idle, wait_for_project_ready


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v110-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Raw Body Project"
        project.mkdir()
        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            wb.messagebox.showinfo = lambda *args, **kwargs: None
            wb.messagebox.showwarning = lambda *args, **kwargs: None
            wb.messagebox.showerror = lambda *args, **kwargs: None
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            root.update()

            app.task_text.insert("1.0", "Create a README and main.py smoke example.")
            app.build_prompt()
            exact_prompt = app.prompt_output.get("1.0", "end-1c")
            assert exact_prompt.strip(), "the provenance test needs a real generated prompt"

            # This file's very first line is a Markdown fence. Explicit body="raw"
            # makes it unambiguously content rather than a wrapper fence.
            file_content = '```markdown\n# README starts with a fence\n```\n'
            response = (
                '<<<AIWB_FILE path="README.md" action="write" body="raw">>>\n'
                + file_content + '<<<AIWB_END_FILE>>>\n'
                + '<<<AIWB_FILE path="src/main.py" action="write" body="raw">>>\n'
                + 'print("v110-ok")\n<<<AIWB_END_FILE>>>\n'
            )
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", response)
            app.preview_response()
            root.update()
            assert app.pending_response_format == "AI Workbench file/action blocks"
            assert sorted(change.path for change in app.pending_changes) == ["README.md", "src/main.py"]
            assert next(change for change in app.pending_changes if change.path == "README.md").content == file_content
            assert not (project / "README.md").exists(), "preview must never write project files"
            assert str(app.save_validated_history_button.cget("state")) == "normal"

            # Editing the textbox after validation must immediately revoke the prior preview and checkpoint action.
            app.response_input.insert("end-1c", " ")
            root.update()
            assert app.pending_payload is None and app.pending_changes is None, "editing a validated response must invalidate the prior diff"
            assert str(app.save_validated_history_button.cget("state")) == "disabled"

            # Re-analyze the exact final response before marking it as a curated history checkpoint.
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", response)
            app.preview_response()
            root.update()
            assert app.pending_changes is not None and app.pending_response_recorded
            app.save_validated_turn_to_history()
            active_state = wb.load_task_state(project)
            active_history_id = active_state.get("active_prompt_entry_id", "")
            saved_entry = wb.conversation_store.get_history_entry(project, active_history_id)
            assert saved_entry and saved_entry.get("project_history_saved") is True
            assert saved_entry.get("prompt_text") == exact_prompt, "history must preserve the exact prompt paired with the response"

            with patch.object(wb.messagebox, "askyesno", return_value=True):
                app.apply_pending_changes(app.pending_diff_window)
            root.update()
            wait_for_idle(app, root)
            assert (project / "README.md").read_text(encoding="utf-8") == file_content
            assert (project / "src" / "main.py").read_text(encoding="utf-8") == 'print("v110-ok")\n'
            versions = wb.project_version_store.list_versions(project)
            if len(versions) != 2:
                print("DEBUG status", app.status_var.get())
                print("DEBUG task", wb.load_task_state(project))
                print("DEBUG events", wb.read_execution_history(project)[-10:])
                print("DEBUG history", wb.conversation_store.list_history(project))
            assert len(versions) == 2, versions
            applied_version = versions[-1]
            assert applied_version["version"] == "v1.0.1"
            assert applied_version["source_history_entry_id"] == active_history_id
            linked_entry = wb.conversation_store.get_history_entry(project, active_history_id)
            assert linked_entry["version_record_id"] == applied_version["id"]
            assert linked_entry["project_version"] == applied_version["version"]
            assert applied_version["prompt_sha256"], "version must store prompt provenance hash"
            assert applied_version["response_sha256"], "version must store response provenance hash"

            # A truncated response must discard old pending changes and never be applyable.
            invalid = (
                '<<<AIWB_FILE path="bad.bat" action="write" body="raw">>>\n'
                + 'echo bad\n'
                + '<<<AIWB_FILE path="other.py" action="write" body="raw">>>\n'
                + 'print("not safe")\n<<<AIWB_END_FILE>>>\n'
            )
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", invalid)
            app.show_import_diagnostics = lambda error_override="": None
            app.preview_response()
            root.update()
            assert app.pending_changes is None, "malformed response must invalidate any prior preview"
            assert not (project / "bad.bat").exists() and not (project / "other.py").exists()
            print("v1.11 stale-preview invalidation + explicit checkpoint + prompt/output-linked project version GUI integration: PASS")
            app.on_close()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    main()
