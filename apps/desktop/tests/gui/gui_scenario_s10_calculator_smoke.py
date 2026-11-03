"""Roadmap 5.20.0 scenario S10 — "the friends' calculator" (the log that started roadmap 5.16 → 5.20).

A guided project "Calc" (an HTML calculator) with the project manager + two developers. As in the friend's log the
charter gives the project manager the first task (a short spec, docs/spec.md); the core developer builds the
calculator code after it. Before 5.18 the manager answered that task with manager proposals that had
``operations: []`` round after round (more than ten prompts, revision 27 → 63, not one code file).

Gate: at most **2 project-manager rounds** from the charter to the **first code file on disk**, only on Home:

1. Prepare → the manager's task prompt has ONE answer format (files + AIWB_HANDOFF), no "only a proposal" line.
2. Round 1: the manager answers like in the log — a proposal with ``operations: []`` and an assessment. No dead end:
   a short correction prompt (< 20 lines) is copied, the card keeps its paste box.
3. Round 2: the manager answers the correction with docs/spec.md + the handoff → Accept → the spec is on disk.
4. Tests/build passed → the core developer's step → Prepare → the developer's answer (src/core/calc.js) → Accept →
   the first code file is on disk. No popup, no error, the path never leaves Home.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from typing import Any

from scenario_driver import CHARTER, Driver, guided_answer, new_guided_project, open_handoff, run, scenario_home

SPEC = "# Calculator spec\n\n- Buttons 0-9, + - * /, =, C\n- Division by zero shows \"Error\"\n"
CALC = "export function calc(a, op, b) {\n  if (op === '/' && b === 0) return 'Error';\n  return eval(`${a}${op}${b}`);\n}\n"
MAX_PM_ROUNDS = 2


def calc_charter(rev: int) -> str:
    """The contract charter fixture reshaped into the friend's project: PM writes the spec, then core, then the UI."""
    d = json.loads(CHARTER.read_text(encoding="utf-8"))
    d["base_state_revision"] = rev
    d["project"] = {"name": "Calc", "goal": "A small HTML calculator", "summary": "One HTML page calculator."}
    d["team"]["agents"] = [a for a in d["team"]["agents"] if a["agent_id"] != "agent-mobile-dev"]
    d["team"]["total_agents"] = 3
    d["architecture"]["modules"] = d["architecture"]["modules"][:2]
    d["coordination"]["file_ownership"] = d["coordination"]["file_ownership"][:2]
    d["coordination"]["shared_contracts"][0]["consumers"] = ["agent-desktop-dev"]
    t1, t2, _t3 = d["tasks"]
    t0 = dict(t1, ref="t0", title="Calculator spec", objective="Write docs/spec.md (buttons, behaviour, errors)",
              owner_agent_id="agent-project-manager", scope={"include": ["docs/**"], "exclude": []},
              acceptance_criteria=["docs/spec.md written"], depends_on_refs=[])
    t1["depends_on_refs"] = ["t0"]
    d["tasks"] = [t0, t1, t2]
    d["roadmap"]["milestones"][0]["task_refs"] = ["t0", "t1"]
    d["roadmap"]["milestones"][1]["task_refs"] = ["t2"]
    d["start_prompts"] = d["start_prompts"][:2]
    return "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(d) + "\n<<<AIWB_END_PROJECT_CHARTER>>>"


def log_proposal(rev: int, task_id: str) -> str:
    """The shape the friend's manager kept sending: analysis + a proposal with no operations."""
    data = {"schema_version": "1.0", "base_state_revision": rev, "summary": "Spec review", "operations": [],
            "task_assessment": {task_id: "The spec should list the buttons and the error behaviour."}}
    return ("I reviewed the project. Here is my proposal.\n<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps(data)
            + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>\n")


def accept_label(card: Any) -> str:
    label = next((lbl for lbl in card.labels() if lbl.startswith("Accept")), None)
    assert label, f"no Accept after the answer: {card.title_var.get()!r} {card.labels()}"
    return label


def main() -> None:
    with scenario_home("s10"):
        d = Driver(tk.Tk(), "s10")
        try:
            app = d.start()
            card = new_guided_project(d, app, "Calc", "A small HTML calculator", ["Developer 1", "Developer 2"])
            ctl = app.workspace_window.wc.ctl
            d.use_answer(card, calc_charter(ctl.state()["state_revision"]), "Charter ✓")
            d.step(card, accept_label(card))
            assert "Project manager" in card.title_var.get(), card.title_var.get()
            d.step(card, "Prepare")
            h = open_handoff(app)
            prompt = d.clipboard()
            assert prompt.startswith("AIWB_ATTEMPT_ID:") and "<<<AIWB_HANDOFF>>>" in prompt, prompt[:200]
            assert "Return changes only as an AIWB_MANAGER_PROPOSAL" not in prompt, "the task prompt has two formats"
            d.shot("01_pm_prompt")

            # round 1 — the log's answer: a proposal with no operations → short correction prompt, same card
            pm_rounds = 1
            d.use_answer(card, log_proposal(ctl.state()["state_revision"], h["task_id"]), "")
            fix = d.clipboard()
            assert "Nothing to apply" in card.message_var.get(), card.message_var.get()
            assert fix.startswith("# AI Workbench — please correct your last answer"), fix[:200]
            assert len(fix.splitlines()) < 20, f"correction prompt has {len(fix.splitlines())} lines"
            assert card.paste.winfo_manager(), "the paste box disappeared after the correction prompt"

            # round 2 — the manager answers the correction: the spec + the handoff
            pm_rounds += 1
            d.use_answer(card, guided_answer(h, {"docs/spec.md": SPEC}, "spec written"), "✓")
            d.step(card, accept_label(card))
            root = Path(app.workspace)
            assert (root / "docs/spec.md").read_text(encoding="utf-8") == SPEC, "the spec is on disk"
            d.step(card, "Tests/build passed")
            d.shot("02_spec_accepted")

            # the core developer: Prepare → answer → Accept → first code file
            assert "Core developer" in card.title_var.get(), (card.title_var.get(), card.labels())
            d.step(card, "Prepare")
            h2 = open_handoff(app)
            assert h2["task_id"] != h["task_id"], h2
            d.use_answer(card, guided_answer(h2, {"src/core/calc.js": CALC}, "calculator core"), "✓")
            d.step(card, accept_label(card))
            assert (root / "src/core/calc.js").read_text(encoding="utf-8") == CALC, "the first code file is on disk"
            d.shot("03_first_code_file")
            assert pm_rounds <= MAX_PM_ROUNDS, f"{pm_rounds} project-manager rounds (max {MAX_PM_ROUNDS})"
            assert app.shell.current == "home", f"the path left Home for {app.shell.current!r}"
            d.finish()
        finally:
            d.destroy()
    d.say(f"S10 friends' calculator: charter -> PM task prompt (one format) -> log answer (no operations) -> short fix "
          f"prompt ({len(fix.splitlines())} lines) -> spec on disk -> core developer -> src/core/calc.js on disk in "
          f"{pm_rounds} PM rounds (max {MAX_PM_ROUNDS}); {len(d.clicks)} clicks + {d.pastes} pastes: PASS")


if __name__ == "__main__":
    run(main)
