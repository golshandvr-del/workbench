"""Roadmap 5.8.0 gate (audit A15), driven only from Home since 5.11.0 (A7): the owner's path with REAL widgets, from
New Project to a file on disk, with a click count.

Every earlier smoke handed inputs straight to ``guide_action(..., inputs)``, so no dialog was ever opened and the
5.7.0 paste box crashed for the owner while 40 smokes were green. This one only clicks real widgets: the toolbar menu,
the New Project wizard, and Home's Next-step card (its primary button, its More menu and its **inline** paste panel).
Typing and pasting go into the real Entry/Text widgets. Any modal dialog that opens on the way is a failure (5.11.0:
no popup paste box), and so is a click count above the 5.11.0 gate.

Path (5.13.0 gate, owner audit B3–B5): New Project ▾ › Guided project → wizard (Next, Next, Create — Create also
copies the project-manager prompt) → **Home** → paste the charter in the card → Use this answer → Accept → Prepare
(also copies the prompt) → the AI asks for a file: paste its context request → Use this answer → Copy the files for
the chat → paste the real answer → Use this answer → Accept the delivery (also your review) → the file exists on disk
→ Tests/build passed → Accept the milestone. The status bar never says "No project open" (A6).
Gate: ≤ 14 clicks + the pastes (5.11.0: ≤ 12 up to the first file).

``AIWB_SCREENSHOT_DIR=dir`` writes one screenshot per step (needs ImageMagick ``import``).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import traceback
from pathlib import Path
from typing import Any

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready

MAX_CLICKS = 14          # roadmap 5.13.0 gate: New Project → … → milestone accepted in ≤ 14 clicks (+ the pastes)
MAX_CLICKS_FIRST_FILE = 12  # roadmap 5.11.0 gate: New Project → first file on disk
REPO = Path(__file__).resolve().parents[4]
CHARTER = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"
F4 = "````"


def walk(w: tk.Misc):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


class Owner:
    """Drives the app like a person: counts every click, and records any modal dialog (there must be none)."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.clicks: list[str] = []
        self.pastes = 0
        self.dialogs: list[str] = []
        self.errors: list[str] = []
        self._seen: set[str] = set()
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
                if str(t) in self._seen or not t.winfo_ismapped() or t.title() == "Create a new project":
                    continue
                self._seen.add(str(t))
                self.dialogs.append(t.title())
                t.destroy()
        except tk.TclError:
            pass
        self.root.after(60, self._poll)

    def click(self, widget: Any, what: str = "") -> None:
        self.clicks.append(what or str(widget.cget("text")))
        widget.invoke()

    def click_menu(self, menu: tk.Menu, label: str) -> None:
        self.clicks.append(f"More › {label}")
        menu.invoke(menu_labels(menu).index(label))

    def paste(self, text_widget: tk.Text, value: str) -> None:
        """What Ctrl+V does in the card's paste panel (a paste, not a click)."""
        self.pastes += 1
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", value)
        text_widget.edit_modified(True)
        text_widget.event_generate("<<Modified>>")

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


def do_step(o: Owner, card: Any, label: str) -> None:
    """Press the action ``label`` of Home's card: its primary button or one of the step's other buttons (5.13.0: the
    card has no More)."""
    b = card.button(label)
    assert b is not None, f"the card has no {label!r} button: {card.labels()} — card: {card.title_var.get()!r}"
    o.click(b)


def use_answer(o: Owner, card: Any, text: str, needle: str) -> str:
    """Paste ``text`` into the card's inline paste panel, wait for the live diagnosis, press Use this answer."""
    panel = card.paste
    assert panel.winfo_manager(), f"no paste panel on Home: {card.title_var.get()!r} {card.labels()}"
    o.paste(panel.box, text)
    end, line = time.monotonic() + 4, ""
    while time.monotonic() < end and needle not in line:
        o.pump(50)
        line = panel.status_var.get()
    assert needle in line, f"live diagnosis never showed {needle!r}: {line!r}"
    o.click(panel.ok_btn)
    o.pump(500)
    return line


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
            o.clicks.append("New Project ▾")
            o.click_menu(app.shell.toolbar.menus["new"], menu_labels(app.shell.toolbar.menus["new"])[0])
            o.pump(400)
            assert any(t.title() == "Create a new project" for t in o.tops()), [t.title() for t in o.tops()]
            o.shot("01_create_window")
            # 5.9.0: the one-window wizard — Project · Team · Answers, typed into its real widgets
            wiz = app.project_wizard
            entries = [c for c in walk(wiz.pages[0]) if c.winfo_class() == "TEntry"]
            entries[0].insert(0, "Snake Game")
            wiz.goal_text.insert("1.0", "A small snake game for Windows")
            o.click(wiz.next_btn)
            o.pump(200)
            assert wiz.step == 1, wiz.error_var.get()
            box = wiz.team.count_box
            box.focus_force()
            o.pump(100)
            box.delete(0, "end")
            box.insert(0, "3")
            box.event_generate("<Return>")
            o.pump(200)
            rows = wiz.team.entries()
            assert len(rows) == 4, f"{len(rows)} team rows for 3 AIs"
            for row, name in zip(rows[1:], ("Core dev", "Desktop dev", "Mobile dev")):
                row["name"].set(name)
            o.shot("01b_team")
            o.click(wiz.next_btn)
            o.pump(200)
            assert wiz.next_btn.cget("text") == "Create project", wiz.next_btn.cget("text")
            o.click(wiz.next_btn)
            assert app.workspace is not None, "Create made no project: " + wiz.error_var.get()
            wait_for_project_ready(app, root, app.workspace)
            o.pump(1200)
            # 5.11.0 (A7): Home is the cockpit — not the Workbench, not the 1.x Profile page (A3)
            assert app.shell.current == "home", f"after Create the app shows {app.shell.current!r}, not Home"
            assert not [b for b in boxes if b[0] == "showinfo"], f"no 1.x 'Project created' box: {boxes}"
            # A6: an open project
            app.shell.refresh_status()
            facts = app.shell.statusbar.facts_var.get()
            assert "No project open" not in facts, f"status bar with an open project: {facts!r}"
            ws = app.workspace_window
            assert ws is not None, "the embedded Workbench exists in the background"
            card = app.home_card
            card.refresh()
            o.shot("02_home_start")
            # A8: the team is the user's, the next step is the charter prompt
            st = ws.wc.ctl.state()
            assert sorted(a for a, v in st["agents"].items() if v.get("enabled", True)) == [
                "agent-core-dev", "agent-desktop-dev", "agent-mobile-dev", "agent-project-manager"], sorted(st["agents"])
            assert st["settings"]["team"]["max_parallel_chats"] == 3
            # 3) 5.13.0: Create already copied the charter prompt; the card says so and can copy it again
            assert card.next_btn.cget("text") == "Copy the charter prompt", card.labels()
            assert "Project Charter" in root.clipboard_get(), "Create copies the project-manager prompt"
            assert "copied" in card.message_var.get(), card.message_var.get()
            o.shot("03_charter_copied")
            # 4) paste the charter in the card's own panel (no popup — the 5.7.0 crash lived there, A11)
            data = json.loads(CHARTER.read_text(encoding="utf-8"))
            data["base_state_revision"] = ws.wc.ctl.state()["state_revision"]
            charter = "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(data) + "\n<<<AIWB_END_PROJECT_CHARTER>>>"
            use_answer(o, card, charter, "Charter ✓")
            assert "Imported as PROP-" in card.message_var.get(), card.message_var.get()
            o.shot("04_charter_pasted")
            # 5) Accept the plan
            do_step(o, card, "Accept")
            o.pump(500)
            st = ws.wc.ctl.state()
            assert "agent-core-dev" in st["agents"] and st["tasks"], "charter accepted: agents and tasks exist"
            # 6) Prepare — 5.11.0: also copies the prompt (one click less)
            do_step(o, card, "Prepare")
            o.pump(300)
            prompt = root.clipboard_get()
            assert prompt.startswith("AIWB_ATTEMPT_ID:"), prompt[:80]
            assert "copied" in card.message_var.get(), card.message_var.get()
            o.shot("05_task_prompt_copied")
            # 7) the AI first asks for a file it needs (context request, 5.12.0 B2) → the card turns into the files step
            h = next(h for h in ws.wc.ctl.state()["handoffs"].values() if h["status"] in ("prepared", "prompt_exported"))
            (Path(app.workspace) / "src" / "core").mkdir(parents=True, exist_ok=True)
            (Path(app.workspace) / "src" / "core" / "store.py").write_text("ITEMS = []\n", encoding="utf-8")
            req = {"schema_version": "1.0", "type": "AIWB_CONTEXT_REQUEST", "attempt_id": h["attempt_id"],
                   "reason": "I need the store", "files": [{"path": "src/core/store.py", "mode": "full_file"}],
                   "questions": []}
            use_answer(o, card, f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n<<<AIWB_CONTEXT_REQUEST>>>\n" + json.dumps(req)
                       + "\n<<<AIWB_END_CONTEXT_REQUEST>>>", "Context request ✓")
            assert "asked for 1 file" in card.title_var.get(), (card.title_var.get(), card.labels())
            o.shot("06a_context_request")
            assert card.next_btn.cget("text") == "Copy the files for the chat", card.labels()
            o.click(card.next_btn)
            o.pump(300)
            assert "ITEMS = []" in root.clipboard_get(), "the requested file is on the clipboard"
            o.shot("06b_files_copied")
            # 8) "I sent them" is optional: the paste panel is already on the card → paste the real answer
            assert card.paste.winfo_manager(), (card.title_var.get(), card.labels())
            man = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": h["task_id"],
                   "task_revision": h["task_revision"], "attempt_id": h["attempt_id"], "outcome": "complete",
                   "summary": "core done", "completed_items": ["core"], "unresolved_items": [],
                   "validation_claims": ["tests pass"]}
            answer = (f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n"
                      f'<<<AIWB_FILE path="src/core/snake.py" action="write">>>\n{F4}\nSPEED = 5\n{F4}\n'
                      "<<<AIWB_END_FILE>>>\n<<<AIWB_HANDOFF>>>\n" + json.dumps(man) + "\n<<<AIWB_END_HANDOFF>>>\n")
            use_answer(o, card, answer, "✓")
            o.shot("06c_answer_pasted")
            labels = card.labels()
            assert any(lbl.startswith("Accept") for lbl in labels), f"no Accept after the answer: {labels}"
            do_step(o, card, next(lbl for lbl in labels if lbl.startswith("Accept")))
            o.pump(600)
            target = Path(app.workspace) / "src" / "core" / "snake.py"
            assert target.is_file() and "SPEED = 5" in target.read_text(encoding="utf-8"), "the file is on disk"
            first_file = len(o.clicks)
            o.shot("07_file_written")
            # 9) 5.13.0: accepting the delivery was the review; the card asks what the tests/build really did
            tid = h["task_id"]
            assert ws.wc.ctl.state()["tasks"][tid]["status"] == "validation_pending", ws.wc.ctl.state()["tasks"][tid]
            assert card.title_var.get().startswith("Verify"), (card.title_var.get(), card.labels())
            do_step(o, card, "Tests/build passed")
            o.pump(500)
            assert ws.wc.ctl.state()["tasks"][tid]["status"] == "done", ws.wc.ctl.state()["tasks"][tid]["status"]
            # 10) the milestone of that task is finished: it is the next step (before the next prompts)
            assert card.title_var.get().startswith("Accept milestone"), (card.title_var.get(), card.labels())
            o.shot("08_milestone_ready")
            do_step(o, card, "Accept the milestone")
            o.pump(500)
            ms = ws.wc.ctl.state()["milestones"]
            assert any(m["status"] == "accepted" for m in ms.values()), {k: m["status"] for k, m in ms.items()}
            o.shot("09_milestone_accepted")
            # the whole path stayed on Home, with no popup, no crash, and within the click budget
            assert app.shell.current == "home", f"the path left Home for {app.shell.current!r}"
            assert not o.dialogs, f"modal dialogs opened on the way: {o.dialogs}"
            assert not o.errors, "UI callback errors:\n" + "\n".join(o.errors)
            assert not [b for b in boxes if b[0] == "showerror"], f"error boxes: {boxes}"
            assert first_file <= MAX_CLICKS_FIRST_FILE, f"{first_file} clicks to the first file: {o.clicks}"
            assert len(o.clicks) <= MAX_CLICKS, f"{len(o.clicks)} clicks (max {MAX_CLICKS}): {o.clicks}"
        finally:
            root.destroy()
    msg = (f"Owner path smoke passed (only Home): New Project > wizard (project, 3 named AIs) -> charter prompt copied "
           f"-> inline paste -> accept -> prompt copied -> context request -> files copied -> answer -> accept "
           f"(+ review) -> file on disk ({first_file} clicks) -> tests passed -> milestone accepted in "
           f"{len(o.clicks)} clicks + {o.pastes} pastes (max {MAX_CLICKS}): {' / '.join(o.clicks)}")
    # a Windows console (cp1252) cannot print ▾/…: replace what it cannot encode instead of failing a passed smoke
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(msg.encode(enc, "replace").decode(enc, "replace"))


if __name__ == "__main__":
    main()
