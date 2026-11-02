"""Roadmap 5.17.0 gate (R5): a decision is asked in ONE clear window — the question, the options, the recommendation.

Real path on Home: charter → first task prompt → the AI answers "needs a decision" with the question
"Should the calculator use vanilla JS or React?" → Accept the delivery → the card says the task waits for a decision →
**Decide and continue…** opens one window (never ``askstring``) that shows the full question and the options as radio
buttons plus "Other answer…". Checked: Esc cancels and nothing changes; OK with nothing chosen names the missing answer
and keeps the window; choosing "React" records the decision with that text and the task continues.
"""
from __future__ import annotations

import json
import tkinter as tk
from typing import Any

import AI_Workbench as wb
from aiwb.ui import action_form
from aiwb.workspace import shell as ws_shell
from scenario_driver import Driver, charter_to_first_prompt, handoff_manifest, new_guided_project, run, scenario_home

QUESTION = "Should the calculator use vanilla JS or React?"


def no_askstring(*_a: Any, **_k: Any) -> None:
    raise AssertionError("a step input was asked with simpledialog.askstring (5.17.0: one ActionForm only)")


def main() -> None:
    forms: list[action_form.ActionForm] = []
    real = action_form.ActionForm

    class Recorded(real):  # type: ignore[misc, valid-type]
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            forms.append(self)

    action_form.ActionForm = Recorded  # ask_form looks the class up at call time
    wb.simpledialog.askstring = no_askstring
    ws_shell.simpledialog.askstring = no_askstring
    with scenario_home("v517"):
        d = Driver(tk.Tk(), "v517", allow_windows=Driver.WORK_WINDOWS + (action_form.FORM_TITLE_PREFIX,))
        app = d.start()
        card = new_guided_project(d, app, "Calc", "A small HTML calculator", ["Developer 1", "Developer 2"])
        h = charter_to_first_prompt(d, app, card)
        man = handoff_manifest(h, "need a decision", outcome="needs_decision")
        man["decision_requests"] = [QUESTION]
        d.use_answer(card, f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n<<<AIWB_HANDOFF>>>\n" + json.dumps(man)
                     + "\n<<<AIWB_END_HANDOFF>>>\n", "")
        d.step(card, "Accept the delivery")
        assert "waits for a decision" in card.title_var.get(), card.title_var.get()
        ctl = app.workspace_window.wc.ctl
        tid = h["task_id"]

        seen: dict[str, Any] = {}

        def drive(script: Any) -> None:
            def tick(n: int = 0) -> None:
                if len(forms) > seen.get("n", 0) and not forms[-1].closed:
                    seen["n"] = len(forms)
                    script(forms[-1])
                elif n < 100:
                    d.root.after(50, tick, n + 1)
            d.root.after(50, tick)

        # 1) Esc = cancel: nothing changes
        def esc(f: action_form.ActionForm) -> None:
            seen["title"] = f.top.title()
            seen["question"] = str(f.question_label.cget("text"))
            seen["options"] = f.option_texts("choice")
            f.top.event_generate("<Escape>")
        drive(esc)
        d.step(card, "Decide and continue…")
        assert seen.get("title", "").startswith(action_form.FORM_TITLE_PREFIX), seen
        assert QUESTION in seen["question"], f"the form does not show the AI's question: {seen['question']!r}"
        assert seen["options"] == ["vanilla JS", "React", action_form.OTHER_LABEL], seen["options"]
        assert ctl.state()["tasks"][tid]["status"] == "needs_decision", "Esc changed the task"

        # 2) OK with nothing chosen keeps the window and names the answer; then React + a reason
        def decide(f: action_form.ActionForm) -> None:
            assert f.values()["choice"] == "", "an option was chosen for the user (no recommendation)"
            assert f.ok() is None and not f.closed and "Your decision" in f.error_var.get(), f.error_var.get()
            f.choose("choice", "React")
            f.write("rationale", "the team knows React")
            f.ok_btn.invoke()
        drive(decide)
        d.step(card, "Decide and continue…")
        st = ctl.state()
        dec = [x for x in st["decisions"].values() if x["status"] == "accepted"]
        assert dec and dec[-1]["decision"] == "React" and dec[-1]["rationale"] == "the team knows React", dec
        assert st["tasks"][tid]["status"] != "needs_decision", st["tasks"][tid]["status"]
        assert "waits for a decision" not in card.title_var.get(), card.title_var.get()
        d.finish()
        d.say(f"v5.17.0 forms smoke passed: one window '{seen['title']}' · full question · options "
              f"{seen['options'][:2]} + Other answer · Esc = nothing changed · empty OK keeps the window · "
              "React recorded with its reason · no askstring: PASS")
        d.destroy()


if __name__ == "__main__":
    run(main)
