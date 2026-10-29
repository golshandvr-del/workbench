"""Roadmap 5.15.0 scenario S8: the chat first asks for files (a real GPT context request) → files → the answer.

Guided project with three named AIs, Home only, REAL widgets and the real clipboard. The project already holds the
files GPT will ask for — and a ``.env`` secret it must never get. Charter → Accept → Prepare (the task prompt shows
the exact context-request block) → the owner's REAL GPT answer of the 5.11.0 test
(``docs/audit/owner-5.11/HO-0006_gpt_answer_context_request.txt``, three files and a folder), pasted as a clean copy
→ "Context request ✓ · 4 files" → the card turns into "<AI> asked for 4 files" → Copy the files for the chat (the
clipboard holds the files, the folder expanded, ``.env`` refused) → I sent them → the delivery → Accept → the file is
on disk and the request is closed.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path

from scenario_driver import (F4, REPO, Driver, charter_to_first_prompt, handoff_manifest, new_guided_project, run,
                             scenario_home)

OWNER = REPO / "docs/audit/owner-5.11/HO-0006_gpt_answer_context_request.txt"
OWNER_ATTEMPT = "att-20261023-192855-0ba9959e"
PROJECT_FILES = {"src/contracts/models.py": "class Part:\n    pass\n",
                 "src/contracts/__init__.py": "from .models import Part\n",
                 "docs/contracts/catia-bridge-spec.md": "# Spec\nOpen, read.\n",
                 "src/catia_bridge/session.py": "SESSION = None\n",
                 ".env": "TOKEN=do-not-send\n"}


def main() -> None:
    with scenario_home("s8"):
        d = Driver(tk.Tk(), "s8")
        try:
            app = d.start()
            card = new_guided_project(d, app, "Bridge", "A CATIA bridge with shared contracts",
                                      ["Core dev", "Bridge dev", "QA"])
            folder = Path(app.workspace)
            for p, c in PROJECT_FILES.items():
                (folder / p).parent.mkdir(parents=True, exist_ok=True)
                (folder / p).write_text(c, encoding="utf-8")
            h = charter_to_first_prompt(d, app, card)
            prompt = d.clipboard()
            assert '"type": "AIWB_CONTEXT_REQUEST"' in prompt, "the task prompt shows the exact context request"
            att = h["attempt_id"]

            # the owner's real GPT answer (its attempt id replaced by this project's), a clean copy
            real = OWNER.read_text(encoding="utf-8").replace("\r", "").replace(OWNER_ATTEMPT, att)
            line = d.use_answer(card, real, "Context request ✓")
            assert "4 files" in line, line
            assert "asked for 4 files" in card.title_var.get(), (card.title_var.get(), card.labels())
            d.shot("01_asked_for_files")
            d.step(card, "Copy the files for the chat")
            pack = d.clipboard()
            assert pack.startswith(f"AIWB_ATTEMPT_ID: {att}"), pack[:80]
            for needle in ("class Part:", "from .models import Part", "# Spec", "src/catia_bridge/session.py"):
                assert needle in pack, f"{needle!r} not in the copied files"
            assert "do-not-send" not in pack, "the .env secret reached the clipboard"
            d.step(card, "I sent them")
            d.shot("02_files_sent")

            # the delivery after the files: one five-backtick block around the whole answer, as the rule asks
            ctl = app.workspace_window.wc.ctl
            h = ctl.state()["handoffs"][h["handoff_id"]]
            t = ctl.state()["tasks"][h["task_id"]]
            scope = ((t.get("scope") or {}).get("include") or ["src/**"])[0].rstrip("*").rstrip("/") or "src"
            answer = ("`````text\n" + f"AIWB_ATTEMPT_ID: {att}\n"
                      f'<<<AIWB_FILE path="{scope}/bridge.py" action="write">>>\n{F4}\nfrom contracts import Part\n{F4}\n'
                      "<<<AIWB_END_FILE>>>\n<<<AIWB_HANDOFF>>>\n" + json.dumps(handoff_manifest(h, "bridge"))
                      + "\n<<<AIWB_END_HANDOFF>>>\n`````")
            d.use_answer(card, answer, "✓")
            accept = next((lbl for lbl in card.labels() if lbl.startswith("Accept")), None)
            assert accept, f"no Accept after the delivery: {card.title_var.get()!r} {card.labels()}"
            d.step(card, accept)
            target = folder / scope / "bridge.py"
            assert target.is_file() and "from contracts import Part" in target.read_text(encoding="utf-8"), target
            assert "context_request" not in ctl.state()["handoffs"][h["handoff_id"]], "the request is closed"
            assert (folder / ".env").read_text(encoding="utf-8") == "TOKEN=do-not-send\n"
            d.shot("03_delivery_applied")
            assert app.shell.current == "home", f"the path left Home for {app.shell.current!r}"
            d.finish()
        finally:
            d.destroy()
    d.say(f"S8 owner's real GPT context request -> 'asked for 4 files' -> files copied (folder expanded, .env refused) "
          f"-> sent -> delivery -> file on disk; {len(d.clicks)} clicks + {d.pastes} pastes: PASS")


if __name__ == "__main__":
    run(main)
