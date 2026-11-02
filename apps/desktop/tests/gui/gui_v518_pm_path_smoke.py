"""Roadmap 5.18.0 gate (R1 + R6): the short project-manager path, on Home with real widgets.

1. The first task prompt (copied by the card) asks for ONE answer format: files + AIWB_HANDOFF — never "only as an
   AIWB_MANAGER_PROPOSAL block".
2. A proposal nothing can be read from (``operations: []`` + an assessment) is no dead end: the message says so, a
   SHORT correction prompt is on the clipboard, and the card still has its paste box.
3. A half-right proposal (``operations: []`` + ``decisions`` + ``file_change_proposals``, as in the friend's log) is
   imported: the card shows "Review the plan … (1 change)" and the message says what was read and what was not used.
"""
from __future__ import annotations

import json
import tkinter as tk
from typing import Any

from scenario_driver import Driver, charter_to_first_prompt, new_guided_project, run, scenario_home


def blk(data: dict[str, Any]) -> str:
    return "My analysis of the project…\n<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps(data) + \
        "\n<<<AIWB_END_MANAGER_PROPOSAL>>>\n"


def main() -> None:
    with scenario_home("v518"):
        d = Driver(tk.Tk(), "v518")
        app = d.start()
        card = new_guided_project(d, app, "Calc", "A small HTML calculator", ["Developer 1", "Developer 2"])
        h = charter_to_first_prompt(d, app, card)
        ctl = app.workspace_window.wc.ctl
        prompt = d.clipboard()
        assert h["attempt_id"] in prompt and "<<<AIWB_HANDOFF>>>" in prompt, prompt[:300]
        assert "Return changes only as an AIWB_MANAGER_PROPOSAL" not in prompt, "task prompt asks for two formats"
        rev = ctl.state()["state_revision"]

        # 2) nothing usable -> short fix prompt, same card, paste box still there
        before = card.title_var.get()
        d.use_answer(card, blk({"schema_version": "1.0", "base_state_revision": rev, "operations": [],
                                "task_assessment": {h["task_id"]: "on track"}}), "")
        msg = card.message_var.get()
        assert "Nothing to apply" in msg and "correction prompt" in msg, msg
        fix = d.clipboard()
        assert fix.startswith("# AI Workbench — please correct your last answer"), fix[:200]
        assert len(fix.splitlines()) < 20, f"fix prompt is not short: {len(fix.splitlines())} lines"
        assert card.title_var.get() == before and card.paste.winfo_manager(), card.title_var.get()

        # 3) half-right proposal -> imported, reviewable
        d.use_answer(card, blk({"schema_version": "1.0", "base_state_revision": rev, "operations": [],
                                "decisions": [{"title": "Number formatting", "options": ["Intl", "toFixed"],
                                               "recommendation": "Intl"}],
                                "file_change_proposals": [{"path": "README.md", "content": "…"}]}), "")
        title, msg = card.title_var.get(), card.message_var.get()
        assert title.startswith("Review the plan") and "(1 change)" in title, title
        assert "Read from the answer" in msg and "not used" in msg and "has no operations" not in msg, msg
        p = sorted(ctl.state()["proposals"].values(), key=lambda x: x["proposal_id"])[-1]
        assert [o["operation"] for o in p["operations"]] == ["propose_decision"], p["operations"]
        d.finish()
        d.say("v5.18.0 PM path smoke passed: task prompt has one format · useless proposal -> short fix prompt "
              f"({len(fix.splitlines())} lines), card unchanged · half-right proposal -> '{title}' with what was "
              "read / not used: PASS")
        d.destroy()


if __name__ == "__main__":
    run(main)
