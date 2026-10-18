"""GUI smoke for 1.16.2: repair prompt with Inbox evidence and the Diagnostics bundle window."""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
import zipfile
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready
from aiwb import inbox


def block(path: str, body: str, end: bool = True) -> str:
    s = f'<<<AIWB_FILE path="{path}" action="write" body="raw">>>\n{body}\n'
    return s + ("<<<AIWB_END_FILE>>>\n" if end else "")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-repair-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Repair Project"
        project.mkdir()
        (project / "main.py").write_text("SECRET_SOURCE = 1\n", encoding="utf-8")
        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.task_text.insert("1.0", "Add a and b")
            app.build_prompt()
            root.update()
            aid = inbox.declared_attempt_id(app.prompt_output.get("1.0", "end-1c"))
            broken = f"AIWB_ATTEMPT_ID: {aid}\n" + block("a.py", "A = 1") + block("b.py", "B", end=False)
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", broken)
            app.preview_response()
            root.update()
            captured: list[str] = []
            orig = wb.build_repair_prompt
            wb.build_repair_prompt = lambda *a, **k: captured.append(orig(*a, **k)) or captured[-1]
            app.show_repair_prompt(failure_stage="import", error="cut off", raw_response=broken)
            root.update()
            wb.build_repair_prompt = orig
            prompt = captured[-1]
            new_aid = inbox.declared_attempt_id(prompt)
            assert new_aid and new_aid != aid, "repair must be a new attempt"
            child = inbox.AttemptRegistry(project).get(new_aid)
            assert child.kind == "repair" and child.parent_attempt_id == aid
            assert "- a.py" in prompt and "b.py" in prompt and "A = 1" not in prompt

            app.show_diagnostics_bundle()
            root.update()
            entries = app.diagnostics_state["entries"]
            blob = "\n".join(e.content for e in entries)
            assert "SECRET_SOURCE" not in blob and str(project) not in blob
            out = Path(temp) / "diag.zip"
            wb.diagnostics_service.write_bundle(entries, out)
            assert zipfile.ZipFile(out).namelist()[0] == "report.json"
            app.diagnostics_window.destroy()
            print("PASS: repair prompt + diagnostics bundle GUI smoke")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
