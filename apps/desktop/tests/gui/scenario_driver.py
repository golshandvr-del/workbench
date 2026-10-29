"""Shared driver for the roadmap 5.15.0 scenario gate (S1–S9): drive the app like a person, with REAL widgets.

Not a smoke itself (``run_all.py`` only runs ``gui_*smoke.py``). Each scenario script does::

    with scenario_home("s1") as home:
        d = Driver(tk.Tk(), "s1")
        app = d.start()
        ...
        d.finish()          # no callback error, no modal dialog, no error box
        d.say("S1 ...: PASS")

What it counts and refuses (the 5.8.0 lesson A15: a smoke that hands inputs to the code proves nothing):

* every click (``click`` / ``click_menu``) and every paste (``paste`` = Ctrl+V into a Text through the REAL
  clipboard with ``<<Paste>>``; ``type_paste`` = text inserted + ``<<Modified>>`` for panels that only listen to that);
* a modal Toplevel that was not expected (``allow_windows``) is recorded and closed: a failure at ``finish``;
* ``messagebox.showerror`` is a failure; ``showinfo``/``showwarning`` are recorded (a scenario may assert none);
  ``askyesno``/``askokcancel`` answer *yes* and are recorded.

``AIWB_SCREENSHOT_DIR=dir`` writes ``<scenario>_<name>.png`` per ``shot`` (needs ImageMagick ``import``).
"""
from __future__ import annotations

import contextlib
import hashlib
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
from typing import Any, Iterator

import AI_Workbench as wb

REPO = Path(__file__).resolve().parents[4]
ANSWERS = REPO / "apps/desktop/tests/fixtures/answers"
CHARTER = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"
F4 = "````"


@contextlib.contextmanager
def scenario_home(name: str) -> Iterator[Path]:
    """A fresh user profile: settings (LOCALAPPDATA), HOME, USERPROFILE and Documents live in a temp folder."""
    with tempfile.TemporaryDirectory(prefix=f"aiwb-{name}-") as temp:
        home = Path(temp)
        os.environ["LOCALAPPDATA"] = str(home / "appdata")
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
        (home / "Documents").mkdir()
        yield home


def block(path: str, body: str) -> str:
    """One AIWB file block (four-backtick fence) as a chat writes it."""
    return f'<<<AIWB_FILE path="{path}" action="write">>>\n{F4}\n{body}{F4}\n<<<AIWB_END_FILE>>>\n'


def digest(folder: Path) -> dict[str, str]:
    """Every project file (not .workbench / .git) → sha256: the before/after picture of a folder."""
    out = {}
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder).as_posix()
        if p.is_file() and not rel.startswith((".workbench/", ".git/")):
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def walk(w: tk.Misc) -> Iterator[tk.Misc]:
    for c in w.winfo_children():
        yield c
        yield from walk(c)


def menu_labels(menu: tk.Menu) -> list[str]:
    end = menu.index("end")
    return [] if end is None else [menu.entrycget(i, "label") for i in range(end + 1)]


def windows_copy(text: str) -> str:
    """What a copy from a rendered chat on Windows puts on the clipboard: CRLF line ends."""
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def handoff_manifest(h: dict[str, Any], summary: str = "done", outcome: str = "complete") -> dict[str, Any]:
    return {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": h["task_id"],
            "task_revision": h["task_revision"], "attempt_id": h["attempt_id"], "outcome": outcome,
            "summary": summary, "completed_items": [summary] if outcome == "complete" else [],
            "unresolved_items": [] if outcome == "complete" else [summary], "validation_claims": ["tests pass"]}


def guided_answer(h: dict[str, Any], files: dict[str, str], summary: str = "done") -> str:
    """A complete guided answer: attempt id, file blocks, the handoff manifest."""
    body = "".join(block(p, c) for p, c in files.items())
    return (f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n" + body + "<<<AIWB_HANDOFF>>>\n"
            + json.dumps(handoff_manifest(h, summary)) + "\n<<<AIWB_END_HANDOFF>>>\n")


class Driver:
    """Drives the app like a person: counts clicks and pastes, records dialogs, boxes and callback errors."""

    # the app's own working windows (title prefixes): not popups, the scenario drives them
    WORK_WINDOWS = ("Create a new project", "New Quick project", "Quick — one AI chat", "Make it a multi-AI project")

    def __init__(self, root: tk.Tk, scenario: str, allow_windows: tuple[str, ...] = WORK_WINDOWS) -> None:
        self.root = root
        self.scenario = scenario
        self.allow_windows = set(allow_windows)
        self.clicks: list[str] = []
        self.pastes = 0
        self.dialogs: list[str] = []
        self.errors: list[str] = []
        self.boxes: list[tuple[str, tuple]] = []
        self.shots: list[str] = []
        self._seen: set[str] = set()
        root.geometry("1366x800+0+0")
        self._hook(root)
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(wb.messagebox, name, (lambda n: lambda *a, **k: self.boxes.append((n, a)))(name))
        for name in ("askyesno", "askokcancel"):
            setattr(wb.messagebox, name, (lambda n: lambda *a, **k: (self.boxes.append((n, a)), True)[1])(name))

    # -- app lifecycle -------------------------------------------------------------------------------------------
    def _hook(self, root: tk.Tk) -> None:
        root.report_callback_exception = lambda *a: self.errors.append("".join(traceback.format_exception(*a)))
        root.after(60, self._poll)

    def start(self) -> Any:
        app = wb.WorkbenchApp(self.root)
        self._hook(self.root)  # the app sets its own handler; the scenario wants to see every callback error
        self.pump(600)
        return app

    def restart(self, app: Any) -> Any:
        """Close the app the way the window's X does (on_close saves settings) and start it again in a new Tk."""
        old = self.root
        # the old Tk's after() timers would fire in the shared Tcl event loop once it is gone (bgerror noise)
        with contextlib.suppress(tk.TclError):
            for job in old.tk.splitlist(old.tk.call("after", "info")):
                old.after_cancel(job)
        app.on_close()
        with contextlib.suppress(tk.TclError):
            for job in old.tk.splitlist(old.tk.call("after", "info")):
                old.after_cancel(job)
            old.destroy()
        self.root = tk.Tk()
        self.root.geometry("1366x800+0+0")
        self._seen.clear()
        self._hook(self.root)
        return self.start()

    def destroy(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.root.destroy()

    # -- time and windows ----------------------------------------------------------------------------------------
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
                if str(t) in self._seen or not t.winfo_ismapped() or t.title().startswith(tuple(self.allow_windows)):
                    continue
                self._seen.add(str(t))
                self.dialogs.append(t.title())
                t.destroy()
        except tk.TclError:
            pass
        with contextlib.suppress(tk.TclError):
            self.root.after(60, self._poll)

    # -- input -------------------------------------------------------------------------------------------------
    def click(self, widget: Any, what: str = "") -> None:
        assert str(widget.cget("state")) != "disabled", f"{what or widget.cget('text')!r} is disabled"
        self.clicks.append(what or str(widget.cget("text")))
        widget.invoke()
        self.pump(150)

    def click_menu(self, menu: tk.Menu, label: str, what: str = "") -> None:
        labels = menu_labels(menu)
        assert label in labels, f"menu has no {label!r}: {labels}"
        self.clicks.append(what or label)
        menu.invoke(labels.index(label))
        self.pump(150)

    def paste(self, box: tk.Text, value: str) -> None:
        """Ctrl+V: the text goes through the REAL clipboard into the Text with ``<<Paste>>``."""
        self.pastes += 1
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.pump(50)
        box.delete("1.0", "end")
        box.focus_force()
        box.event_generate("<<Paste>>")
        self.pump(100)
        got = box.get("1.0", "end-1c")
        assert got.replace("\r", "") == value.replace("\r", ""), f"the clipboard paste changed the text ({len(got)})"

    def wait_line(self, panel: Any, needle: str, seconds: float = 5) -> str:
        """Wait until the paste panel's live check line shows ``needle``."""
        end, line = time.monotonic() + seconds, ""
        while time.monotonic() < end and needle not in line:
            self.pump(50)
            line = panel.status_var.get()
        assert needle in line, f"live check never showed {needle!r}: {line!r}"
        return line

    def clipboard(self) -> str:
        return self.root.clipboard_get()

    # -- Home card ---------------------------------------------------------------------------------------------
    def step(self, card: Any, label: str) -> None:
        """Press the action ``label`` of Home's Next-step card."""
        b = card.button(label)
        assert b is not None, f"the card has no {label!r} button: {card.labels()} — card: {card.title_var.get()!r}"
        self.click(b, label)
        self.pump(400)

    def use_answer(self, card: Any, text: str, needle: str) -> str:
        """Paste ``text`` into the card's inline paste panel (real clipboard), wait for ``needle``, Use this answer."""
        panel = card.paste
        assert panel.winfo_manager(), f"no paste panel on Home: {card.title_var.get()!r} {card.labels()}"
        self.paste(panel.box, text)
        line = self.wait_line(panel, needle)
        self.click(panel.ok_btn)
        self.pump(500)
        return line

    # -- evidence ----------------------------------------------------------------------------------------------
    def shot(self, name: str) -> None:
        out = os.environ.get("AIWB_SCREENSHOT_DIR")
        if not out or not shutil.which("import"):
            return
        Path(out).mkdir(parents=True, exist_ok=True)
        self.pump(300)
        target = Path(out) / f"{self.scenario}_{name}.png"
        subprocess.run(["import", "-window", "root", str(target)], check=False, timeout=30)
        self.shots.append(target.name)

    def finish(self, allow_info: bool = True) -> None:
        assert not self.errors, "UI callback errors:\n" + "\n".join(self.errors)
        assert not self.dialogs, f"unexpected windows opened on the way: {self.dialogs}"
        bad = [b for b in self.boxes if b[0] == "showerror" or (not allow_info and b[0] != "askyesno")]
        assert not bad, f"message boxes: {bad}"

    def say(self, msg: str) -> None:
        """Print the PASS line; a Windows console (cp1252) cannot print → or …: replace instead of failing."""
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(msg.encode(enc, "replace").decode(enc, "replace"))


# -- shared paths ----------------------------------------------------------------------------------------------
def new_guided_project(d: Driver, app: Any, name: str, goal: str, ai_names: list[str]) -> Any:
    """Toolbar › New Project ▾ › the guided entry → wizard (name, goal, N named AIs) → Create. Returns the card."""
    from gui_smoke_helpers import wait_for_project_ready

    menu = app.shell.toolbar.menus["new"]
    d.clicks.append("New Project ▾")
    d.click_menu(menu, menu_labels(menu)[0])
    d.pump(300)
    wiz = app.project_wizard
    entries = [c for c in walk(wiz.pages[0]) if c.winfo_class() == "TEntry"]
    entries[0].insert(0, name)
    wiz.goal_text.insert("1.0", goal)
    d.click(wiz.next_btn)
    assert wiz.step == 1, wiz.error_var.get()
    box = wiz.team.count_box
    box.focus_force()
    d.pump(100)
    box.delete(0, "end")
    box.insert(0, str(len(ai_names)))
    box.event_generate("<Return>")
    d.pump(200)
    rows = wiz.team.entries()
    assert len(rows) == len(ai_names) + 1, f"{len(rows)} team rows for {len(ai_names)} AIs"
    for row, ai in zip(rows[1:], ai_names):
        row["name"].set(ai)
    d.click(wiz.next_btn)
    assert wiz.next_btn.cget("text") == "Create project", wiz.next_btn.cget("text")
    d.click(wiz.next_btn)
    assert app.workspace is not None, "Create made no project: " + wiz.error_var.get()
    wait_for_project_ready(app, d.root, app.workspace)
    d.pump(1000)
    app.home_card.refresh()
    return app.home_card


def charter_answer(app: Any) -> str:
    """The contract fixture charter, on the project's current state revision, as the project manager answers."""
    data = json.loads(CHARTER.read_text(encoding="utf-8"))
    data["base_state_revision"] = app.workspace_window.wc.ctl.state()["state_revision"]
    return "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(data) + "\n<<<AIWB_END_PROJECT_CHARTER>>>"


def open_handoff(app: Any) -> dict[str, Any]:
    """The handoff whose prompt was prepared/copied and still waits for an answer."""
    hs = app.workspace_window.wc.ctl.state()["handoffs"].values()
    return next(h for h in hs if h["status"] in ("prepared", "prompt_exported"))


def charter_to_first_prompt(d: Driver, app: Any, card: Any) -> dict[str, Any]:
    """Home: paste the charter → Accept → Prepare (copies the task prompt). Returns the open handoff."""
    d.use_answer(card, charter_answer(app), "Charter ✓")
    d.step(card, "Accept")
    d.step(card, "Prepare")
    assert d.clipboard().startswith("AIWB_ATTEMPT_ID:"), d.clipboard()[:80]
    return open_handoff(app)


def run(main: Any) -> None:
    """Script entry: a failure prints its traceback (the runner shows the last line) and exits 1."""
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
