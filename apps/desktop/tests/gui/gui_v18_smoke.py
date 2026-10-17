"""GUI integration smoke test for GPT ZIP intake and shared review/apply flow."""
from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
import zipfile
from pathlib import Path
from unittest.mock import patch

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_idle, wait_for_project_ready


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v18-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "GPT ZIP Project"
        project.mkdir()
        artifact = Path(temp) / "response.zip"
        control = {
            "protocol": wb.PROTOCOL_V2,
            "task_id": "V18-GUI-SMOKE",
            "summary": "Import a minimal Python utility from a GPT ZIP.",
            "actions": [],
            "next_steps": ["Review output from the imported script."],
            "completion_status": "in_progress",
        }
        with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("AIWB_RESPONSE.json", json.dumps(control))
            archive.writestr("README.md", "# ZIP smoke\n\nRun `python src/main.py`.\n")
            archive.writestr("src/main.py", "print('gpt-zip-ok')\n")
        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            wb.messagebox.showinfo = lambda *args, **kwargs: None
            wb.messagebox.showwarning = lambda *args, **kwargs: None
            wb.messagebox.showerror = lambda *args, **kwargs: None
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            root.update()

            # Planning stage should accurately record JSON even when implementation is configured for ZIP.
            app.task_text.insert("1.0", "Design a tiny engineering helper before implementation.")
            app.output_format_var.set(wb.OUTPUT_FORMAT_GPT_ZIP)
            app.profile_vars["prompt_stage"].set("Architecture + file manifest plan")
            app.build_prompt()
            planning_state = wb.load_task_state(project)
            assert planning_state["last_output_format"] == wb.OUTPUT_FORMAT_JSON
            assert planning_state["last_selected_output_format"] == wb.OUTPUT_FORMAT_GPT_ZIP
            app.profile_vars["prompt_stage"].set("Implementation / build")

            with patch.object(wb.filedialog, "askopenfilename", return_value=str(artifact)):
                app.load_response_file()
            assert app.loaded_zip_path == artifact
            assert not (project / "src" / "main.py").exists(), "loading must not write ZIP contents"

            # Analyze must use archive bytes, not parse the explanatory UI marker as text.
            app.preview_response()
            root.update()
            assert app.pending_response_recorded is True
            assert app.pending_response_format == "GPT ZIP artifact package"
            assert sorted(change.path for change in app.pending_changes) == ["README.md", "src/main.py"]
            assert not (project / "src" / "main.py").exists(), "preview must remain read-only"

            with patch.object(wb.messagebox, "askyesno", return_value=True):
                app.apply_pending_changes(app.pending_diff_window)
            root.update()
            wait_for_idle(app, root)
            assert (project / "src" / "main.py").read_text(encoding="utf-8") == "print('gpt-zip-ok')\n"
            assert not (project / "AIWB_RESPONSE.json").exists(), "control manifest must never be written as a project file"
            state = wb.load_task_state(project)
            snapshot = wb.read_project_json(project, "latest_model_response.json", {})
            assert state["latest_response_format"] == "GPT ZIP artifact package"
            assert snapshot["source_artifact"]["filename"] == "response.zip"
            assert len(snapshot["source_artifact"]["sha256"]) == 64
            print("v1.8 GPT ZIP intake + review/apply GUI integration: PASS")
            app.on_close()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    main()
