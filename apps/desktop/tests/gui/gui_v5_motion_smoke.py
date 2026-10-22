"""Roadmap 5.3.0 gate: motion on the real application.

* Opening a project with live tasks plays the branch growth (mask uncovered, then removed), starts the breathing
  pulse of active circles and light particles on live branches — all on the one shared clock.
* Page changes slide in; the rail marker slides; the clock frame cost stays inside a 60 fps frame budget.
* The clock sleeps when nothing moves (no live tasks → no timer scheduled).
* Settings › Motion › Reduce motion: every animation jumps to its end, loops stop, the clock sleeps, and the
  preference is saved. No Tk exception is raised at any point; animations never write project state.
"""
from __future__ import annotations

import os
import tempfile
import time
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from aiwb.v2.models import normalize_agent
from gui_smoke_helpers import wait_for_project_ready


def pump(root: tk.Tk, ms: float) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(0.004)


def main() -> None:
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="aiwb-v5-motion-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Motion three"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        root.report_callback_exception = lambda *a: errors.append(repr(a[1]))
        root.geometry("1280x800+0+0")
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            sh, mo = app.shell, app.shell.motion
            assert mo is app.mission.motion and sh.rail.motion is mo, "one shared clock"
            pump(root, 400)
            assert not mo.running, f"idle app must not tick: {list(mo.anims)}"
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            sh.show("workbench")
            pump(root, 300)
            ctl = app.workspace_window.wc.ctl
            p = ctl.project
            with p.store.transaction("smoke agents") as s:
                for i in range(1, 4):
                    s["agents"][f"agent-mo-{i}"] = normalize_agent({"agent_id": f"agent-mo-{i}", "role": "implementer",
                                                                    "name": f"Mover {i}", "template_id": ""})
            tids = []
            for i in range(1, 4):
                t = p.tasks.create({"title": f"Move {i}", "objective": "o", "owner_agent_id": f"agent-mo-{i}",
                                    "scope": {"include": [f"m{i}/**"]}, "acceptance_criteria": ["ok"]})
                tids.append(t["task_id"])
            p.timeline.propose_version({"label": "0.1.0", "task_ids": tids})
            grows: list[bool] = []
            real_grow = app.mission.grow

            def counted_grow() -> None:
                real_grow()
                grows.append(bool(mo.active("mission:grow") and app.mission.find_withtag("grow_mask")))
            app.mission.grow = counted_grow  # type: ignore[method-assign]
            sh.refresh_status()
            sh.show("home")
            # checked at the moment growth starts: a slow Windows runner may already have finished the 600 ms tween
            assert grows and grows[0], f"branch growth starts: {grows}"
            assert mo.active("shell:page"), "page slides in"
            pump(root, 800)
            assert not mo.active("mission:grow") and not app.mission.find_withtag("grow_mask"), "growth ends clean"
            # nothing live yet (all tasks draft) → the clock sleeps
            assert not mo.running, f"no live task: clock must sleep, got {list(mo.anims)}"
            p.tasks.transition(tids[0], "ready")
            p.tasks.transition(tids[1], "ready")
            sh.refresh_status()
            pump(root, 50)
            assert mo.active("mission:pulse") and mo.active("mission:particles"), list(mo.anims)
            assert len(app.mission.find_withtag("particle")) == 2
            c = app.mission
            cid = c.node_ids[tids[0]]
            images = set()
            frames0 = mo.frames
            for _ in range(60):
                pump(root, 30)
                images.add(str(c.itemcget(cid, "image")))
            assert len(images) >= 3, f"active circle breathes: {images}"
            assert mo.frames - frames0 >= 30, f"clock ticks: {mo.frames - frames0} frames in ~1.8 s"
            cost = sorted(mo.frame_cost_ms)
            p95 = cost[int(len(cost) * 0.95) - 1]
            assert p95 < 16.0, f"frame budget: p95 {p95:.2f} ms"
            # rail slide on the shared clock
            sh.nav["agents"].invoke()
            assert mo.active("rail:marker")
            pump(root, 400)
            assert not mo.active("rail:marker") and sh.rail.current == "agents"
            sh.show("home")
            pump(root, 300)
            rev, n = p.store.revision, p.store.ledger.count()
            # Reduce motion: jump to end, loops stop, clock sleeps, preference saved
            sh.show("settings")
            pump(root, 50)
            app.settings_widgets["motion"].invoke()
            assert app.prefs.reduce_motion and mo.reduced
            assert app.settings_data.get("ui_reduce_motion") is True
            pump(root, 100)
            assert not mo.running and not mo.anims, list(mo.anims)
            sh.show("home")
            assert not mo.running, "page change under Reduce motion is instant"
            assert not c.find_withtag("particle")
            c.select(tids[1])
            assert not mo.running
            app.settings_widgets["motion"].invoke()
            assert not app.prefs.reduce_motion
            pump(root, 50)
            assert mo.active("mission:pulse"), "loops resume when motion is allowed again"
            assert (p.store.revision, p.store.ledger.count()) == (rev, n), "animation wrote state"
            assert not errors, errors
            print(f"v5.3.0 motion smoke passed: one clock · branch growth · breathing ({len(images)} frames) · "
                  f"particles · page slide · rail slide · p95 frame {p95:.2f} ms · sleeps when idle · "
                  "Reduce motion (saved) · no Tk errors · no state written")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
