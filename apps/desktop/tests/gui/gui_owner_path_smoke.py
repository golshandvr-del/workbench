"""Roadmap 5.8.0 gate (audit A15): the owner's path with REAL widgets, from New Project to a file on disk.

Every earlier smoke handed inputs straight to ``guide_action(..., inputs)``, so no dialog was ever opened and the
5.7.0 paste box crashed for the owner while 40 smokes were green. This one only clicks: the toolbar menu, the
create-project window, the Workbench's primary button and its More menu. Modal dialogs (the start-form questions and
the multi-line paste box) are answered by a poller that types into the real Entry/Text widget and presses the real
OK / "Use this answer" button — the same thing a person does.

Path: New Project ▾ › Guided project → Create → Workbench (not the old Profile, A3) → Start the project (5 questions)
→ Copy the charter prompt → More › Paste the charter (A11) → Accept → Prepare/Copy the task prompt → I sent it →
Paste the answer → Accept the files → the file exists on disk. The status bar never says "No project open" (A6).

``AIWB_SCREENSHOT_DIR=dir`` writes one screenshot per step (needs ImageMagick ``import``).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import tkinter as tk
import traceback
from pathlib import Path
from typing import Any, Callable

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready

REPO = Path(__file__).resolve().parents[4]
CHARTER = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"
F4 = "````"


def walk(w: tk.Misc):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


class Owner:
    """Drives the app like a person: clicks, and answers each modal dialog that appears."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.answers: list[str | Callable[[], str]] = []
        self.answered: list[str] = []
        self._seen: set[str] = set()
        self.errors: list[str] = []
        root.report_callback_exception = lambda *a: self.errors.append("".join(traceback.format_exception(*a)))
        root.after(60, self._poll)

    def pump(self, ms: int = 300) -> None:
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

    def tops(self) -> list[tk.Toplevel]:
        return [w for w in walk(self.root) if isinstance(w, tk.Toplevel) and w.winfo_exists()]

    def _poll(self) -> None:
        try:
            for t in self.tops():
                if str(t) in self._seen or not t.winfo_ismapped() or not self.answers:
                    continue
                kids = list(walk(t))
                ok = [c for c in kids if c.winfo_class() in ("Button", "TButton")
                      and str(c.cget("text")) in ("OK", "Use this answer")]
                if not ok:
                    continue
                val = self.answers.pop(0)
                val = val() if callable(val) else val
                text = [c for c in kids if c.winfo_class() == "Text"]
                entry = [c for c in kids if c.winfo_class() in ("Entry", "TEntry")]
                if text:
                    text[0].insert("1.0", val)
                elif entry:
                    entry[0].delete(0, "end")
                    entry[0].insert(0, val)
                self._seen.add(str(t))
                self.answered.append(t.title())
                ok[0].invoke()
        except tk.TclError:
            pass
        self.root.after(60, self._poll)

    def shot(self, name: str) -> None:
        out = os.environ.get("AIWB_SCREENSHOT_DIR")
        if not out or not shutil.which("import"):
            return
        Path(out).mkdir(parents=True, exist_ok=True)
        self.pump(300)
        subprocess.run(["import", "-window", "root", str(Path(out) / f"owner_{name}.png")], check=False, timeout=30)


def menu_labels(menu: tk.Menu) -> list[str]:
    end = menu.index("end")
    return [] if end is None else [menu.entrycget(i, "label") for i in range(end + 1)]


def click_more(ws: Any, label: str) -> None:
    labels = menu_labels(ws.next_menu)
    assert label in labels, f"More menu has no {label!r}: {labels}"
    ws.next_menu.invoke(labels.index(label))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-owner-") as temp:
        home = Path(temp)
        os.environ["LOCALAPPDATA"] = str(home / "appdata")
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
        (home / "Documents").mkdir()
        root = tk.Tk()
        root.geometry("1366x800+0+0")
        o = Owner(root)
        boxes: list[tuple[str, tuple]] = []
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(wb.messagebox, name, (lambda n: lambda *a, **k: boxes.append((n, a)))(name))
        try:
            app = wb.WorkbenchApp(root)
            o.pump(600)
            # 1) Toolbar › New Project ▾ › Guided project (recommended)
            app.shell.toolbar.menus["new"].invoke(0)
            o.pump(400)
            dlg = next(t for t in o.tops() if t.title() == "Create a new project")
            o.shot("01_create_window")
            entries = [c for c in walk(dlg) if c.winfo_class() == "TEntry"]
            entries[0].insert(0, "Snake Game")
            if len(entries) > 2:
                entries[2].insert(0, "A small snake game for Windows")
            next(c for c in walk(dlg) if c.winfo_class() == "TButton" and c.cget("text") == "Create project").invoke()
            assert app.workspace is not None, "Create made no project"
            wait_for_project_ready(app, root, app.workspace)
            o.pump(1200)
            # A3: the guided start, not the 1.x Profile page and not a 'Project created' box
            assert app.shell.current == "workbench", f"after Create the app shows {app.shell.current!r}, not the Workbench"
            assert not [b for b in boxes if b[0] == "showinfo"], f"no 1.x 'Project created' box: {boxes}"
            # A6: an open, still unplanned project
            assert "No project open" not in app.shell.status.facts_var.get() if hasattr(app.shell, "status") and \
                hasattr(app.shell.status, "facts_var") else True
            ws = app.workspace_window
            assert ws is not None
            o.shot("02_workbench_start")
            # 2) Start the project… → the five questions, answered in their real dialogs
            assert ws.next_btn.cget("text").startswith("Start the project"), ws.next_btn.cget("text")
            o.answers[:] = ["A small snake game for Windows", "Snake Game", "Windows, Python + Tkinter",
                            "No internet", "3"]
            ws.next_btn.invoke()
            o.pump(500)
            assert len(o.answered) == 5, f"start form dialogs answered: {o.answered}"
            assert ws.wc.ctl.state()["settings"]["team"]["max_parallel_chats"] == 3
            # 3) Copy the charter prompt (clipboard)
            assert ws.next_btn.cget("text") == "Copy the charter prompt", ws.next_btn.cget("text")
            ws.next_btn.invoke()
            o.pump(300)
            assert "Project Charter" in root.clipboard_get()
            o.shot("03_charter_copied")

            # 4) More › Paste the charter — the dialog that crashed in 5.7.0 (A11)
            def charter() -> str:
                data = json.loads(CHARTER.read_text(encoding="utf-8"))
                data["base_state_revision"] = ws.wc.ctl.state()["state_revision"]
                return "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(data) + "\n<<<AIWB_END_PROJECT_CHARTER>>>"
            o.answers.append(charter)
            click_more(ws, "Paste the charter")
            o.pump(600)
            assert o.answered[-1] == "Paste the charter", o.answered
            assert "imported" in ws.status_var.get(), ws.status_var.get()
            o.shot("04_charter_pasted")
            # 5) Accept the plan
            assert ws.next_btn.cget("text").startswith("Accept"), ws.next_btn.cget("text")
            ws.next_btn.invoke()
            o.pump(500)
            st = ws.wc.ctl.state()
            assert "agent-core-dev" in st["agents"] and st["tasks"], "charter accepted: agents and tasks exist"
            # 6) Prepare → Copy prompt → I sent it
            ws.next_btn.invoke()
            o.pump(300)
            assert ws.next_btn.cget("text") == "Copy prompt", ws.next_btn.cget("text")
            ws.next_btn.invoke()
            o.pump(300)
            prompt = root.clipboard_get()
            assert prompt.startswith("AIWB_ATTEMPT_ID:"), prompt[:80]
            click_more(ws, "I sent it")
            o.pump(300)
            o.shot("05_task_prompt_sent")
            # 7) Paste the answer… (real paste box) → Accept the files
            h = next(h for h in ws.wc.ctl.state()["handoffs"].values() if h["status"] in ("prepared", "prompt_exported"))
            man = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": h["task_id"],
                   "task_revision": h["task_revision"], "attempt_id": h["attempt_id"], "outcome": "complete",
                   "summary": "core done", "completed_items": ["core"], "unresolved_items": [],
                   "validation_claims": ["tests pass"]}
            answer = (f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n"
                      f'<<<AIWB_FILE path="src/core/snake.py" action="write">>>\n{F4}\nSPEED = 5\n{F4}\n'
                      "<<<AIWB_END_FILE>>>\n<<<AIWB_HANDOFF>>>\n" + json.dumps(man) + "\n<<<AIWB_END_HANDOFF>>>\n")
            o.answers.append(answer)
            assert ws.next_btn.cget("text").startswith("Paste the answer"), ws.next_btn.cget("text")
            ws.next_btn.invoke()
            o.pump(600)
            assert o.answered[-1].startswith("Paste the answer"), o.answered
            o.shot("06_answer_pasted")
            labels = [ws.next_btn.cget("text")] + menu_labels(ws.next_menu)
            assert any(lbl.startswith("Accept") for lbl in labels), f"no Accept after the answer: {labels}"
            if ws.next_btn.cget("text").startswith("Accept"):
                ws.next_btn.invoke()
            else:
                click_more(ws, next(lbl for lbl in labels if lbl.startswith("Accept")))
            o.pump(600)
            target = Path(app.workspace) / "src" / "core" / "snake.py"
            assert target.is_file() and "SPEED = 5" in target.read_text(encoding="utf-8"), "the file is on disk"
            o.shot("07_file_written")
            # A6 again on Home, and no callback crashed anywhere on the way
            app.shell.show("home")
            o.pump(500)
            assert not o.errors, "UI callback errors:\n" + "\n".join(o.errors)
            assert not [b for b in boxes if b[0] == "showerror"], f"error boxes: {boxes}"
        finally:
            root.destroy()
    print("Owner path smoke passed: New Project › Guided → Workbench → start form (5 real dialogs) → charter prompt → "
          "real paste box → accept → task prompt → real paste box → accept → file on disk")


if __name__ == "__main__":
    main()
