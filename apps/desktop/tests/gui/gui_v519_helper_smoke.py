"""Roadmap 5.19.0 gate: the optional helper AI, on the real app with a local fake OpenAI-compatible server.

1. Not set up: Home shows no helper button; Settings has the "Helper AI (optional)" card (Test disabled).
2. Settings › Helper AI: address + model (no key — like a local Ollama) → Save → Test answers "OK" (background thread,
   the window stays responsive). Home now shows "Explain this step"; clicking it puts the helper's sentence in the
   card message.
3. An answer Workbench cannot use (prose, no blocks) → "Fix with helper AI" appears → the rewritten answer lands in
   the paste box (never applied by itself) → "Use this answer" accepts it (✓).
4. Settings › Remove → the helper buttons disappear from Home again. No dialogs, no callback errors.
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/ (FakeServer lives in test_helper_ai.py)

from scenario_driver import Driver, charter_to_first_prompt, guided_answer, new_guided_project, run, scenario_home  # noqa: E402
from test_helper_ai import FakeServer  # noqa: E402

from aiwb.ui.next_card import EXPLAIN_LABEL, FIX_LABEL  # noqa: E402


def wait_helper(d: Driver, card, seconds: float = 10) -> None:
    end = time.monotonic() + seconds
    d.pump(100)
    while card.helper_busy and time.monotonic() < end:
        d.pump(50)
    assert not card.helper_busy, "the helper AI call never finished"


def main() -> None:
    srv = FakeServer()
    try:
        with scenario_home("v519"):
            d = Driver(tk.Tk(), "v519")
            app = d.start()
            card = new_guided_project(d, app, "Calc", "A small HTML calculator", ["Developer 1", "Developer 2"])
            w = app.helper_widgets
            # 1) not set up
            assert card.helper_labels() == [], card.helper_labels()
            assert "Not set up" in w["status_var"].get() and w["test"].instate(["disabled"]), w["status_var"].get()
            assert not w["body"].winfo_manager(), "the helper card should start collapsed"
            h = charter_to_first_prompt(d, app, card)

            # 2) set up (no key) → Show settings → Save helper → Test
            app.shell.show("settings")
            d.pump(200)
            d.click(w["toggle"], "Show settings")
            assert w["body"].winfo_manager() and w["save"].winfo_ismapped(), "Show settings did not open the form"
            w["url_var"].set(srv.url)
            w["model_var"].set("small-model")
            d.click(w["save"], "Save helper")
            assert w["status_var"].get().startswith("Saved."), w["status_var"].get()
            assert app.settings_data.get("helper_ai", {}).get("model") == "small-model", app.settings_data
            srv.reply = "OK"
            d.click(w["test"], "Test")
            end = time.monotonic() + 10
            while "answered" not in w["status_var"].get() and time.monotonic() < end:
                d.pump(50)
            assert w["status_var"].get().startswith("✓"), w["status_var"].get()
            assert card.helper_labels() == [EXPLAIN_LABEL], card.helper_labels()

            srv.reply = "Send the copied prompt to the Core developer chat, then paste its whole answer here."
            d.click(card.explain_btn, EXPLAIN_LABEL)
            wait_helper(d, card)
            assert card.message_var.get().startswith("Helper AI: Send the copied prompt"), card.message_var.get()
            assert "Step:" in srv.seen[-1]["body"]["messages"][-1]["content"], srv.seen[-1]

            # 3) unusable answer → Fix with helper AI → rewritten answer in the paste box → Use this answer
            prose = "Here is the calculator. I wrote calc.py with an add function: def add(a, b): return a + b"
            d.use_answer(card, prose, "")
            assert card.failed and FIX_LABEL in card.helper_labels(), (card.message_var.get(), card.helper_labels())
            srv.reply = "```\n" + guided_answer(h, {"src/core/calc.py": "def add(a, b):\n    return a + b\n"},
                                                "core done") + "```"
            d.click(card.fix_btn, FIX_LABEL)
            wait_helper(d, card)
            sent = srv.seen[-1]["body"]["messages"][-1]["content"]
            assert prose in sent and "AIWB_HANDOFF" in sent, sent[:300]
            got = card.paste.text()
            assert got.startswith("AIWB_ATTEMPT_ID:") and "<<<AIWB_HANDOFF>>>" in got, got[:200]
            assert "rewrote the answer" in card.message_var.get(), card.message_var.get()
            assert app.workspace_window.wc.ctl.state()["handoffs"][h["handoff_id"]]["status"] != "accepted"
            d.wait_line(card.paste, "✓")
            d.click(card.paste.ok_btn)
            d.pump(500)
            assert card.failed is None, card.failed
            assert card.model.get("key") != h["handoff_id"] or "✓" in card.message_var.get(), card.title_var.get()

            # 4) remove → buttons gone
            app.shell.show("settings")
            d.pump(200)
            d.click(w["remove"], "Remove")
            d.pump(200)
            app.shell.show("home")
            d.pump(200)
            assert card.helper_labels() == [], card.helper_labels()
            assert "helper_ai" not in app.settings_data, app.settings_data
            d.finish()
            d.say(f"v5.19.0 helper AI smoke passed: hidden when not set up · Save/Test ({len(srv.seen)} calls to the "
                  "local server) · Explain this step · unusable answer -> Fix with helper AI -> fixed text in the box "
                  "-> accepted · Remove hides the buttons: PASS")
            d.destroy()
    finally:
        srv.close()


if __name__ == "__main__":
    run(main)
