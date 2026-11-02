"""Roadmap 5.16.0 gate (R2 R3 R4): the app is light when nobody touches it, and menus never linger.

* After the Mission Map's short live period, the motion clock draws **zero** frames while idle.
* The status poll does nothing (no redraw, no listener) while ``state.json`` is unchanged; a real change refreshes.
* A right-click menu opens fast (panel 9-sliced) and closes on: page switch, a click elsewhere, the main window being
  moved or minimised. Nothing is written by any of it.
"""
from __future__ import annotations

import time
import tkinter as tk

from aiwb.ui import menu5
from scenario_driver import Driver, charter_to_first_prompt, new_guided_project, run, scenario_home


def open_menu(d: Driver, app, tid: str) -> menu5.FloatingMenu:
    t0 = time.perf_counter()
    m = app.mission_menu(tid, 300, 300)
    d.root.update()
    took = (time.perf_counter() - t0) * 1000
    assert m is not None and not m.closed and m.top.winfo_exists(), "the menu did not open"
    assert menu5.open_menus() == [m], menu5.open_menus()
    return m, took


def main() -> None:
    with scenario_home("v516"):
        d = Driver(tk.Tk(), "v516")
        app = d.start()
        card = new_guided_project(d, app, "Calc", "A small HTML calculator", ["Developer 1", "Developer 2"])
        h = charter_to_first_prompt(d, app, card)
        tid = h["task_id"]
        app.shell.show("home")
        d.pump(400)
        state_file = app.workspace / ".workbench" / "v2" / "state.json"
        before = state_file.stat().st_mtime_ns

        # R3: the live loops settle, then an idle app draws nothing
        from aiwb.ui.mission_canvas import LIVE_MS
        mo = app.shell.motion
        d.pump(LIVE_MS + 1200)
        f0, t0 = mo.frames, time.monotonic()
        d.pump(3000)
        fps = (mo.frames - f0) / (time.monotonic() - t0)
        assert fps == 0.0 and not mo.anims, f"idle app still animates: {fps:.1f} frames/s {list(mo.anims)}"

        # R2: unchanged state.json -> the poll skips everything; a change refreshes
        sh = app.shell
        calls: list[int] = []
        sh.status_listeners.append(lambda st: calls.append(1))
        sh._poll_once()
        skipped0 = getattr(sh, "polls_skipped", 0)
        assert sh._poll_once() is False and sh._poll_once() is False, "an unchanged state was refreshed"
        assert sh.polls_skipped == skipped0 + 2 and not calls[1:], (sh.polls_skipped, calls)
        assert app.status_state() is app.status_state(), "status_state re-read an unchanged file"

        # R4: the menu opens fast and closes on every app-wide event
        m, took = open_menu(d, app, tid)
        assert took < 600, f"menu open took {took:.0f} ms"
        sh.show("workbench"); d.pump(200)
        assert m.closed and not menu5.open_menus(), "page switch left the menu open"
        sh.show("home"); d.pump(300)

        m, took2 = open_menu(d, app, tid)
        app.mission.event_generate("<Button-1>", x=5, y=5); d.pump(200)
        assert m.closed, "a click elsewhere left the menu open"

        m, _ = open_menu(d, app, tid)
        x, y = d.root.winfo_rootx(), d.root.winfo_rooty()
        d.root.geometry(f"+{x + 40}+{y + 30}"); d.pump(500)
        assert m.closed, "moving the main window left the menu open"

        m, _ = open_menu(d, app, tid)
        d.root.iconify(); d.pump(500)
        assert m.closed, "minimising the main window left the menu open"
        d.root.deiconify(); d.pump(400)

        m, _ = open_menu(d, app, tid)
        m.close(); m.close()  # closing twice is safe
        assert not menu5.open_menus()

        assert state_file.stat().st_mtime_ns == before, "the light checks wrote the project state"
        d.finish()
        d.say(f"v5.16.0 light smoke passed: idle 0 frames/s after {LIVE_MS} ms · poll skipped while state.json "
              f"unchanged · menu {took:.0f}/{took2:.0f} ms · closes on page switch, click elsewhere, move, minimise "
              "· nothing written: PASS")
        d.destroy()


if __name__ == "__main__":
    run(main)
