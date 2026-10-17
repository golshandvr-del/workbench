"""GUI regression for the v1.10 legacy context-plan schema seen in user reports."""
from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
import conversation_store as history
from gui_smoke_helpers import wait_for_project_ready


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v112-context-plan-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "IMU Station"
        project.mkdir()
        files = [
            "Build-IMU-Station-Installer.cmd", "README.md", "requirements.txt",
            "app/main.py", "app/protocol.py", "firmware/esp32_mpu6050/esp32_mpu6050.ino",
            "installer/app_readme.md", "installer/build_installer.ps1", "installer/generate_icon.py",
            "installer/README.md", "installer/setup_gui.py", "installer/uninstall.ps1", "tests/test_protocol.py",
        ]
        for relative in files:
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# fixture: {relative}\n", encoding="utf-8")

        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            wb.messagebox.showinfo = lambda *args, **kwargs: None
            wb.messagebox.showwarning = lambda *args, **kwargs: None
            observed_errors: list[tuple[str, str]] = []
            wb.messagebox.showerror = lambda title, message, **kwargs: observed_errors.append((str(title), str(message)))
            wb.messagebox.askyesno = lambda *args, **kwargs: True
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            root.update()

            # This matches the legacy shape from the reported GPT/Gemini conversation:
            # `requests` with `mode=whole_file`, plus metadata not present in the new v1 schema.
            response = {
                "protocol": "workbench-plan-v1",
                "task_id": "imu-installer-context",
                "summary": "The current prompt omitted actual file contents, so inspect exact project files first.",
                "requests": [
                    {"path": rel, "mode": "whole_file", "reason": f"Review {rel} before making changes."}
                    for rel in files
                ],
                "manual_attachments": [],
                "next_steps": ["Add the requested local files to the next prompt."],
                "completion_status": "in_progress",
            }
            raw = json.dumps(response, ensure_ascii=False)
            detected = wb.detect_model_response_format(raw)
            assert detected.startswith("workbench-plan-v1"), detected
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", raw)
            app.import_context_plan()
            root.update()

            selected = set(app.file_tree.selection())
            assert selected == set(files), f"Only {len(selected)}/{len(files)} requested files selected: {selected}"
            entries = history.list_history(project)
            assert len(entries) == 1 and entries[0]["model_output"] == raw
            normalized = entries[0]["normalized_output"]
            assert len(normalized["requested_context_files"]) == len(files)
            assert normalized["completion_status"] == "in_progress"
            assert app.profile_vars["prompt_stage"].get() == "Implementation / build"
            plan_diagnostics = wb.diagnose_model_response(raw, project)
            assert "context plan" in plan_diagnostics["format"]
            assert plan_diagnostics["requested_context_file_count"] == len(files)
            assert not any("No files were applied" in x for x in plan_diagnostics["findings"])

            # A later malformed plan is rejected, but the exact attempt is retained and identifiable.
            bad_response = dict(response)
            bad_response["unexpected_field"] = "must be rejected"
            bad_raw = json.dumps(bad_response, ensure_ascii=False)
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", bad_raw)
            app.import_context_plan()
            root.update()
            assert observed_errors and observed_errors[-1][0] == "Context plan rejected"
            assert "Response SHA-256" in observed_errors[-1][1]
            assert "unexpected_field" in observed_errors[-1][1]
            entries = history.list_history(project)
            rejected_entry = entries[-1]
            assert rejected_entry["model_output"] == bad_raw
            assert rejected_entry["response_status"] == "Context plan rejected"
            assert "Unknown top-level keys" in rejected_entry.get("import_error", "")
            print("legacy context-plan migration + file selection + rejection identity/history: PASS")
            app.on_close()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    main()
