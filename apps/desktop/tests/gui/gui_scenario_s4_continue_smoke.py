"""Roadmap 5.15.0 scenario S4: a guided answer is cut off → Continue → the rest → every file lands on disk.

Home only, REAL widgets and the real clipboard. Guided project → charter → Prepare → the chat's answer stops in the
middle of its second file → the card turns into "The last answer was cut off" with the continue prompt → Copy
continue prompt (it says the first file arrived complete: do not resend it) → the chat sends only the rest (the
second file + the handoff manifest, no attempt id) → Use this answer → Accept → BOTH files are on disk.

Before 5.15.0 the first file was lost here: the rest replaced the cut-off answer (found by this scenario).
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path

from scenario_driver import (F4, Driver, block, charter_to_first_prompt, handoff_manifest, new_guided_project, run,
                             scenario_home)

FIRST = "src/core/model.py"
SECOND = "src/core/store.py"


def main() -> None:
    with scenario_home("s4"):
        d = Driver(tk.Tk(), "s4")
        try:
            app = d.start()
            card = new_guided_project(d, app, "Todo", "A command-line todo app", ["Core dev", "CLI dev", "QA"])
            h = charter_to_first_prompt(d, app, card)

            # 1) the answer stops in the middle of the second file
            cut = (f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n" + block(FIRST, "class Todo:\n    pass\n")
                   + f'<<<AIWB_FILE path="{SECOND}" action="write">>>\n{F4}\nimport json\n\n\ndef load(')
            d.paste(card.paste.box, cut)
            d.pump(500)
            d.click(card.paste.ok_btn)
            d.pump(500)
            assert card.title_var.get().startswith("The last answer was cut off"), (card.title_var.get(), card.labels())
            assert not (Path(app.workspace) / FIRST).exists(), "a cut-off answer wrote a file"
            d.shot("01_cut_off")

            # 2) copy the continue prompt: it names the complete file and asks for the rest only
            d.step(card, "Copy continue prompt")
            prompt = d.clipboard()
            assert "cut off" in prompt and FIRST in prompt, prompt[:600]

            # 3) the chat sends only the rest (no attempt id, the first file not resent) → linked → Accept
            rest = (block(SECOND, "import json\n\n\ndef load(path):\n    return json.load(open(path))\n")
                    + "<<<AIWB_HANDOFF>>>\n" + json.dumps(handoff_manifest(h, "core done")) + "\n<<<AIWB_END_HANDOFF>>>\n")
            d.use_answer(card, rest, "✓")
            ho = app.workspace_window.wc.ctl.state()["handoffs"][h["handoff_id"]]
            staged = sorted(f["path"] for f in ho.get("staged_files") or [])
            assert staged == sorted([FIRST, SECOND]), f"staged after the rest: {staged}"
            d.shot("02_rest_linked")
            accept = next((lbl for lbl in card.labels() if lbl.startswith("Accept")), None)
            assert accept, f"no Accept after the rest: {card.title_var.get()!r} {card.labels()}"
            d.step(card, accept)
            root = Path(app.workspace)
            assert (root / FIRST).read_text(encoding="utf-8") == "class Todo:\n    pass\n", "the first file is on disk"
            assert "def load(path)" in (root / SECOND).read_text(encoding="utf-8"), "the second file is on disk"
            assert not card.title_var.get().startswith("The last answer was cut off"), card.title_var.get()
            d.shot("03_both_on_disk")
            assert app.shell.current == "home", f"the path left Home for {app.shell.current!r}"
            d.finish()
        finally:
            d.destroy()
    d.say(f"S4 cut-off answer -> continue prompt -> the rest -> both files on disk; {len(d.clicks)} clicks + "
          f"{d.pastes} pastes: PASS")


if __name__ == "__main__":
    run(main)
