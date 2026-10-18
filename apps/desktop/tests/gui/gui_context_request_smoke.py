"""GUI smoke for 1.16.3: an AIWB_CONTEXT_REQUEST answer opens the request window, refuses
unsafe/sensitive items, prepares inline + ZIP context and never writes project files."""
from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
import zipfile
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready
from aiwb import inbox


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-ctxreq-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Ctx Project"
        project.mkdir()
        (project / "app.py").write_text("def run():\n    return 42\n", encoding="utf-8")
        (project / ".env").write_text("TOKEN=supersecret\n", encoding="utf-8")
        root = tk.Tk()
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.task_text.insert("1.0", "Fix run()")
            app.build_prompt()
            root.update()
            prompt = app.prompt_output.get("1.0", "end-1c")
            assert "AIWB_CONTEXT_REQUEST" in prompt, "capability manifest must describe context requests"
            aid = inbox.declared_attempt_id(prompt)
            req = {"schema_version": "1.0", "type": "AIWB_CONTEXT_REQUEST", "attempt_id": aid, "reason": "need run()",
                   "files": [{"path": "app.py", "mode": "symbol", "symbol": "run"}, {"path": ".env"},
                             {"path": "../outside.txt"}, {"path": "gone.py", "required": False}],
                   "questions": ["Which Python version?"]}
            raw = f"AIWB_ATTEMPT_ID: {aid}\n<<<AIWB_CONTEXT_REQUEST>>>\n{json.dumps(req)}\n<<<AIWB_END_CONTEXT_REQUEST>>>\n"
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", raw)
            app.preview_response()
            root.update()
            w = app.context_request_window
            st = [i.status for i in w.items]
            assert st == ["ready", "refused_sensitive", "refused_unsafe", "missing"], st
            text = w.do_inline()
            assert "return 42" in text and "supersecret" not in text and "Which Python version?" in text
            new_aid = inbox.declared_attempt_id(text)
            assert new_aid and new_aid != aid
            assert inbox.AttemptRegistry(project).get(new_aid).parent_attempt_id == aid
            assert root.clipboard_get() == text
            out = w.do_zip(str(Path(temp) / "pack.zip"))
            names = zipfile.ZipFile(out).namelist()
            assert "AIWB_CONTEXT_MANIFEST.json" in names and not any(".env" in n for n in names), names
            recs = inbox.InboxStore(project).list()
            assert recs and recs[0].status == "context_request", [r.status for r in recs]
            assert sorted(p.name for p in project.iterdir() if not p.name.startswith(".workbench")) == [".env", "app.py"]
            assert not app.pending_changes
            hist = wb.read_execution_history(project)
            events = hist.get("events", hist) if isinstance(hist, dict) else hist
            assert any(e.get("type") == "context_pack_prepared" for e in events)
            w.close()
            print("PASS: context request GUI smoke")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
