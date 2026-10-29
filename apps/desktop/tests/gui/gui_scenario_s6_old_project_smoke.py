"""Roadmap 5.15.0 scenario S6: a project made by AI Workbench 5.7.0 opens in today's app and the work goes on.

The fixture ``tests/fixtures/projects/v5.7.0_todo.zip`` was written by the REAL 5.7.0 code (``build_v570_project.py``):
a charter accepted, 3 tasks, the first task's prompt copied (``HO-0001`` waits for the chat's answer), one file of the
user's. REAL widgets: the folder is opened like *Add existing folder* does → nothing in it changes by opening it (same
AIs, tasks, revision, the user's file) → Home shows the waiting step of 5.7.0 → paste the chat's answer → Accept →
the file is on disk and the user's own file is untouched.
"""
from __future__ import annotations

import json
import tkinter as tk
import zipfile
from pathlib import Path

from gui_smoke_helpers import wait_for_project_ready
from scenario_driver import REPO, Driver, digest, guided_answer, run, scenario_home

ZIP = REPO / "apps/desktop/tests/fixtures/projects/v5.7.0_todo.zip"
NAME = "Todo 570"


def main() -> None:
    with scenario_home("s6") as home:
        with zipfile.ZipFile(ZIP) as z:
            z.extractall(home / "Documents")
        folder = home / "Documents" / NAME
        state_file = folder / ".workbench/v2/state.json"
        old = json.loads(state_file.read_text(encoding="utf-8"))
        files_before = digest(folder)
        d = Driver(tk.Tk(), "s6")
        try:
            app = d.start()
            app.set_workspace(folder, focus_project=True)      # what Add existing folder… does after the folder dialog
            wait_for_project_ready(app, d.root, folder)
            d.pump(1000)
            ctl = app.workspace_window.wc.ctl
            st = ctl.state()
            assert sorted(st["agents"]) == sorted(old["agents"]), "opening changed the AIs"
            assert sorted(st["tasks"]) == sorted(old["tasks"]) == ["TASK-0001", "TASK-0002", "TASK-0003"]
            assert st["state_revision"] == old["state_revision"], (old["state_revision"], st["state_revision"])
            assert digest(folder) == files_before, "opening changed the user's files"
            h = st["handoffs"]["HO-0001"]
            assert h["status"] == "prompt_exported", h["status"]
            card = app.home_card
            card.refresh()
            d.pump(300)
            assert "TASK-0001" in card.title_var.get() or "Core" in card.title_var.get(), card.title_var.get()
            d.shot("01_opened")

            d.use_answer(card, guided_answer(h, {"src/core/todo.py": "TODOS: list[str] = []\n"}, "core done"), "✓")
            accept = next((lbl for lbl in card.labels() if lbl.startswith("Accept")), None)
            assert accept, f"no Accept after the answer: {card.title_var.get()!r} {card.labels()}"
            d.step(card, accept)
            assert (folder / "src/core/todo.py").read_text(encoding="utf-8") == "TODOS: list[str] = []\n"
            assert (folder / "src/todo/__init__.py").read_text(encoding="utf-8") == "# mine\n", "the user's file"
            assert ctl.state()["handoffs"]["HO-0001"]["status"] in ("accepted", "applied", "reconciled"), \
                ctl.state()["handoffs"]["HO-0001"]["status"]
            d.shot("02_answer_applied")
            d.finish()
        finally:
            d.destroy()
    d.say(f"S6 project made by 5.7.0 -> opened untouched (same AIs, tasks, revision, files) -> waiting step on Home -> "
          f"answer -> file on disk; {len(d.clicks)} clicks + {d.pastes} pastes: PASS")


if __name__ == "__main__":
    run(main)
