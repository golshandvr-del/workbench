"""Roadmap 5.15.0 scenario S2: a guided project with three named AIs, from New Project to the first accepted milestone.

Only Home and the wizard, REAL widgets: New Project ▾ › guided → wizard (name, goal, 3 AIs named by the user) →
Create (copies the charter prompt) → paste the charter → Accept → Prepare (copies the task prompt) → paste the
chat's answer (file + handoff) → Accept the delivery → the file is on disk → Tests/build passed → Accept the
milestone. The team on the map is the user's three names; no popup, no error, the path never leaves Home.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

from scenario_driver import Driver, charter_to_first_prompt, guided_answer, new_guided_project, run, scenario_home

NAMES = ["Core dev", "Desktop dev", "Mobile dev"]


def main() -> None:
    with scenario_home("s2"):
        d = Driver(tk.Tk(), "s2")
        try:
            app = d.start()
            card = new_guided_project(d, app, "Snake Game", "A small snake game for Windows", NAMES)
            assert app.shell.current == "home", app.shell.current
            st = app.workspace_window.wc.ctl.state()
            names = sorted(v.get("name", "") for k, v in st["agents"].items() if k != "agent-project-manager")
            assert names == sorted(NAMES), names
            assert card.next_btn.cget("text") == "Copy the charter prompt", card.labels()
            assert "Project Charter" in d.clipboard()
            d.shot("01_home_charter")

            h = charter_to_first_prompt(d, app, card)
            d.shot("02_prompt_copied")
            d.use_answer(card, guided_answer(h, {"src/core/snake.py": "SPEED = 5\n"}, "core done"), "✓")
            accept = next((lbl for lbl in card.labels() if lbl.startswith("Accept")), None)
            assert accept, f"no Accept after the answer: {card.labels()}"
            d.step(card, accept)
            target = Path(app.workspace) / "src/core/snake.py"
            assert target.read_text(encoding="utf-8") == "SPEED = 5\n", "the file is on disk"
            d.shot("03_file_written")

            tasks = app.workspace_window.wc.ctl.state()["tasks"]
            assert tasks[h["task_id"]]["status"] == "validation_pending", tasks[h["task_id"]]["status"]
            d.step(card, "Tests/build passed")
            assert card.title_var.get().startswith("Accept milestone"), (card.title_var.get(), card.labels())
            d.step(card, "Accept the milestone")
            ms = app.workspace_window.wc.ctl.state()["milestones"]
            assert any(m["status"] == "accepted" for m in ms.values()), {k: m["status"] for k, m in ms.items()}
            d.shot("04_milestone_accepted")
            assert app.shell.current == "home", f"the path left Home for {app.shell.current!r}"
            d.finish()
        finally:
            d.destroy()
    d.say(f"S2 Guided, 3 named AIs ({', '.join(NAMES)}): charter -> task -> file on disk -> tests -> first milestone "
          f"accepted; {len(d.clicks)} clicks + {d.pastes} pastes: PASS")


if __name__ == "__main__":
    run(main)
