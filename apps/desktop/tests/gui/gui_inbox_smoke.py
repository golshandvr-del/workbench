"""GUI smoke for the v1.16 Response Inbox: attempt ID in prompt, raw capture before
validation, partial salvage, reparse and repair prompt — through the real app."""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready
from aiwb import inbox


def block(path: str, body: str, end: bool = True) -> str:
    s = f'<<<AIWB_FILE path="{path}" action="write" body="raw">>>\n{body}\n'
    return s + ("<<<AIWB_END_FILE>>>\n" if end else "")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-inbox-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Inbox Project ü"
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
            app.task_text.insert("1.0", "Add two helper modules")
            app.profile_vars["prompt_stage"].set("Implementation / build")
            app.build_prompt()
            root.update()
            prompt = app.prompt_output.get("1.0", "end-1c")
            aid = inbox.declared_attempt_id(prompt)
            assert aid, "prompt must carry AIWB_ATTEMPT_ID"
            att = inbox.AttemptRegistry(project).get(aid)
            assert att and att.task_id, "attempt must be linked to the task"

            broken = f"AIWB_ATTEMPT_ID: {aid}\n" + block("a.py", "A = 1") + block("b.py", "B = 2", end=False)
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", broken)
            app.preview_response()
            root.update()
            store = inbox.InboxStore(project)
            recs = store.list()
            assert len(recs) == 1 and store.read_text(recs[0].response_id) == broken, "raw must be kept verbatim"
            assert recs[0].status == "partial", recs[0].status
            assert "Inbox" in app.status_var.get(), app.status_var.get()
            assert not (project / "a.py").exists(), "import must not write files"

            app.open_response_inbox()
            root.update()
            w = app.inbox_window
            assert w.selected_id() == recs[0].response_id
            out = w.do_reparse()
            assert out.salvage_paths == ["a.py"], out.salvage_paths
            text = w.repair_text()
            assert "b.py" in text and aid in text and "do NOT resend" in text, text
            loaded = []
            w.load_text = loaded.append
            w.do_load()
            assert loaded == [broken]

            good = f"AIWB_ATTEMPT_ID: {aid}\n" + block("a.py", "A = 1") + block("b.py", "B = 2")
            app.response_input.delete("1.0", "end")
            app.response_input.insert("1.0", good)
            app.preview_response()
            root.update()
            assert store.list()[0].status == "parsed"
            assert app.pending_changes and sorted(c.path for c in app.pending_changes) == ["a.py", "b.py"]
            print("PASS: Response Inbox GUI smoke")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
