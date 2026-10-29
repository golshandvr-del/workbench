"""Roadmap 5.15.0 scenario S5: close the app in the middle of the work and open it again — nothing is lost.

Home only, REAL widgets. Guided project → charter → Accept → Prepare (the task prompt is copied, the chat is
working) → the user closes the window (``on_close``, the window's X: settings are saved) → the app starts again in a
new Tk with the same user profile → the same project is open by itself, Home shows the same open step (the answer
for the same handoff and attempt), nothing was asked twice → paste the chat's answer → Accept → the file is on disk.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

from gui_smoke_helpers import wait_for_project_ready
from scenario_driver import Driver, charter_to_first_prompt, guided_answer, new_guided_project, run, scenario_home


def main() -> None:
    with scenario_home("s5"):
        d = Driver(tk.Tk(), "s5")
        try:
            app = d.start()
            card = new_guided_project(d, app, "Notes", "A small notes app", ["Core dev", "UI dev", "QA"])
            h = charter_to_first_prompt(d, app, card)
            folder = Path(app.workspace)
            before = (card.title_var.get(), card.key if hasattr(card, "key") else None)
            tasks_before = sorted(app.workspace_window.wc.ctl.state()["tasks"])
            d.shot("01_before_close")

            # the user closes the window while the chat works, then starts the app again
            app = d.restart(app)
            assert app.workspace is not None and Path(app.workspace) == folder, f"reopened {app.workspace!r}"
            wait_for_project_ready(app, d.root, folder)
            d.pump(800)
            card = app.home_card
            card.refresh()
            d.pump(300)
            ctl = app.workspace_window.wc.ctl
            st = ctl.state()
            assert sorted(st["tasks"]) == tasks_before, "the tasks changed across the restart"
            ho = st["handoffs"][h["handoff_id"]]
            assert ho["attempt_id"] == h["attempt_id"] and ho["status"] == h["status"], (ho["status"], h["status"])
            assert card.title_var.get() == before[0], f"Home after reopening: {card.title_var.get()!r} != {before[0]!r}"
            assert app.shell.toolbar.project_var.get() == "Notes", app.shell.toolbar.project_var.get()
            d.shot("02_reopened")

            # the chat's answer arrives after the restart → linked to the same handoff → Accept → on disk
            d.use_answer(card, guided_answer(h, {"src/core/notes.py": "NOTES: list[str] = []\n"}, "core done"), "✓")
            accept = next((lbl for lbl in card.labels() if lbl.startswith("Accept")), None)
            assert accept, f"no Accept after the answer: {card.title_var.get()!r} {card.labels()}"
            d.step(card, accept)
            assert (folder / "src/core/notes.py").read_text(encoding="utf-8") == "NOTES: list[str] = []\n"
            d.shot("03_file_written")
            assert app.shell.current == "home", f"the path left Home for {app.shell.current!r}"
            d.finish()
        finally:
            d.destroy()
    d.say(f"S5 close mid-work -> reopen -> same project, same step, same attempt -> answer -> file on disk; "
          f"{len(d.clicks)} clicks + {d.pastes} pastes: PASS")


if __name__ == "__main__":
    run(main)
