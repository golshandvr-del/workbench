"""Roadmap 5.15.0 scenario S9: answers copied from the RENDERED chat on Windows (line-end ``\\``, escaped ``_``, CRLF).

Selecting a rendered ChatGPT answer on Windows and pressing Ctrl+C puts Markdown hard breaks on the clipboard: every
line outside a code block ends with ``\\`` and ``_`` outside code is escaped (``AIWB\\_FILE``), code blocks stay
verbatim, line ends are CRLF (owner audit B1). REAL widgets and the real clipboard:

1. guided project → the charter answer as a Windows copy → Charter ✓ (copy damage repaired) → Accept → tasks exist;
2. Prepare → the task answer (AIWB file blocks + handoff manifest) as a Windows copy → Accept → the file is on disk
   byte for byte (the code block was not touched by the repair);
3. Quick — one AI chat → the files answer as a Windows copy → Check → Apply → both files on disk byte for byte.
"""
from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path

from scenario_driver import (Driver, block, charter_answer, guided_answer, menu_labels, new_guided_project,
                             open_handoff, run, scenario_home)

CORE = {"src/core/todo_model.py": "class Todo:\n    def __init__(self, title: str) -> None:\n        self.title = title\n"}
QUICK = {"hello_app.py": "from greet_util import greet\n\nprint(greet('world'))\n",
         "greet_util.py": "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n"}


def rendered_copy(text: str) -> str:
    """Ctrl+C on a rendered chat answer in Windows: ``\\`` hard breaks + escaped ``_`` outside code, CRLF line ends."""
    out, fence = [], ""
    for line in text.split("\n"):
        m = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence:
            out.append(line)
            if m and m.group(1) == fence:
                fence = ""
            continue
        if m:
            fence = m.group(1)
            out.append(line)
            continue
        out.append(line.replace("_", "\\_") + "\\" if line.strip() else line)
    return "\r\n".join(out)


def main() -> None:
    with scenario_home("s9"):
        d = Driver(tk.Tk(), "s9")
        try:
            app = d.start()

            # 1) guided: the charter as a Windows copy
            card = new_guided_project(d, app, "Todo", "A command-line todo app", ["Core dev", "CLI dev", "QA"])
            ctl = app.workspace_window.wc.ctl
            charter = rendered_copy("Here is the plan.\n\n" + charter_answer(app) + "\n")
            assert "AIWB\\_PROJECT\\_CHARTER>>>\\" in charter, charter[:200]
            d.use_answer(card, charter, "Charter ✓")
            d.shot("01_charter_windows_copy")
            d.step(card, "Accept")
            assert ctl.state()["tasks"], "the repaired charter made no tasks"

            # 2) the task answer as a Windows copy → Accept → the file on disk, byte for byte
            d.step(card, "Prepare")
            h = open_handoff(app)
            answer = rendered_copy("Here are the files.\n\n" + guided_answer(h, CORE, "core model"))
            assert "<<<AIWB\\_FILE" in answer and "AIWB\\_ATTEMPT\\_ID" in answer, answer[:200]
            d.use_answer(card, answer, "✓")
            accept = next((lbl for lbl in card.labels() if lbl.startswith("Accept")), None)
            assert accept, f"no Accept after the Windows copy: {card.title_var.get()!r} {card.labels()}"
            d.step(card, accept)
            for p, c in CORE.items():
                target = Path(app.workspace) / p
                assert target.is_file(), f"{p} is not on disk"
                assert target.read_bytes() == c.encode("utf-8"), f"{p} changed: {target.read_bytes()!r}"
            d.shot("02_task_windows_copy_applied")

            # 3) Quick: the files answer as a Windows copy → Check → Apply
            menu = app.shell.toolbar.menus["new"]
            assert "Quick — one AI chat…" in menu_labels(menu), menu_labels(menu)
            d.clicks.append("New Project ▾")
            d.click_menu(menu, "Quick — one AI chat…")
            form = app.quick_form
            form["name"].set("Hello Windows copy")
            qw = form["create"]()
            d.clicks.append("Create")
            d.pump(500)
            assert qw is not None, form["error"].get()
            folder = Path(app.workspace)
            qw.task_box.insert("1.0", "A hello app: hello_app.py uses greet_util.greet")
            d.click(qw.prompt_btn)
            text = rendered_copy("Here are the files.\n\n" + "".join(block(p, c) for p, c in QUICK.items()))
            d.paste(qw.paste.box, text)
            d.wait_line(qw.paste, "Files ✓")
            d.click(qw.paste.ok_btn)
            states = {i["path"]: i["status"] for i in qw.items}
            assert states == {p: "new" for p in QUICK}, states
            d.click(qw.apply_btn)
            for p, c in QUICK.items():
                assert (folder / p).read_bytes() == c.encode("utf-8"), f"{p}: {(folder / p).read_bytes()!r}"
            d.shot("03_quick_windows_copy_applied")
            d.finish()
        finally:
            d.destroy()
    d.say(f"S9 Windows rendered copy (line-end \\, escaped _, CRLF): charter -> accepted; task answer -> file on disk "
          f"byte for byte; Quick -> Apply 2 files; {len(d.clicks)} clicks + {d.pastes} pastes: PASS")


if __name__ == "__main__":
    run(main)
