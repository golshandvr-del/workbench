"""Roadmap 5.2.0 gate: Home › Mission Map with a real five-AI project.

* A project with 5 AIs and 3 versions (built through the public V2 services) draws one lane and one numbered
  hexagon per AI, one dashed column per version, and one circle per task at its version's column.
* Hover shows a halo + tooltip; a click selects the task and fills the details row; ``Open task in Workbench``
  selects it in the Workbench Inspector.
* Midnight and Daylight both draw; the map follows state changes (status-bar poll) by revision.
* Looking at the map never writes project state.
* ``AIWB_SCREENSHOT_DIR=dir`` writes ``mission_midnight.png`` / ``mission_daylight.png``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from aiwb.v2.models import normalize_agent
from gui_smoke_helpers import wait_for_project_ready


def settle(root: tk.Tk, n: int = 6) -> None:
    for _ in range(n):
        root.update()
        time.sleep(0.01)


def shot(root: tk.Tk, name: str) -> None:
    out = os.environ.get("AIWB_SCREENSHOT_DIR")
    if not out or not shutil.which("import"):
        return
    Path(out).mkdir(parents=True, exist_ok=True)
    settle(root, 10)
    subprocess.run(["import", "-window", str(root.winfo_id()), str(Path(out) / name)], check=False, timeout=30)


def plan_five(ctl) -> list[str]:
    """5 implementers, 3 tasks each, 3 versions; a few tasks moved on so every node state appears."""
    p = ctl.project
    with p.store.transaction("smoke agents") as s:
        for i in range(1, 6):
            aid = f"ai-{i}"
            s["agents"][aid] = normalize_agent({"agent_id": aid, "role": "implementer", "name": f"Builder {i}",
                                                "template_id": ""})
    per_version: list[list[str]] = [[], [], []]
    for i in range(1, 6):
        for k in range(3):
            t = p.tasks.create({"title": f"Builder {i} step {k + 1}", "objective": "o", "owner_agent_id": f"ai-{i}",
                                "scope": {"include": [f"m{i}/{k}/**"]}, "acceptance_criteria": ["ok"]})
            per_version[k].append(t["task_id"])
    for k, label in enumerate(("0.1.0", "0.2.0", "1.0.0")):
        p.timeline.propose_version({"label": label, "task_ids": per_version[k]})
    for tid in per_version[0]:
        p.tasks.transition(tid, "ready")
    return [tid for col in per_version for tid in col]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-v5-mission-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Mission five"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        root.geometry("1280x800+0+0")
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            sh = app.shell
            # no project: friendly empty map
            assert app.mission.model["empty"] and app.mission.find_withtag("empty")
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            sh.show("workbench")
            settle(root, 10)
            ctl = app.workspace_window.wc.ctl
            tids = plan_five(ctl)
            sh.refresh_status()  # the status-bar poll feeds the map
            sh.show("home")
            settle(root, 8)
            m = app.mission.model
            assert not m["empty"]
            assert [ln["agent_id"] for ln in m["lanes"]] == [f"ai-{i}" for i in range(1, 6)], m["lanes"]
            assert [c["label"] for c in m["columns"]] == ["0.1.0", "0.2.0", "1.0.0"], m["columns"]
            c = app.mission
            assert len(c.find_withtag("hex")) == 10  # sprite + number per AI
            assert len(c.find_withtag("lane")) == 5 and len(c.find_withtag("chevron")) == 5
            assert len(c.find_withtag("column")) == 3 and len(c.find_withtag("branch")) == 5
            assert len(c.find_withtag("node")) == 15 and set(c.node_ids) == set(tids)
            assert m["counts"]["active"] == 5 and m["counts"]["idle"] == 10, m["counts"]
            assert "5 AI lanes" in app.mission_summary_var.get(), app.mission_summary_var.get()
            rev, n = ctl.project.store.revision, ctl.project.store.ledger.count()
            # hover → halo + tooltip, at the circle's on-screen position
            tid = tids[6]
            x, y = c.geo["nodes"][tid]
            wx, wy = int(x - c.canvasx(0)), int(y - c.canvasy(0))
            assert c.task_at(wx, wy) == tid
            c.event_generate("<Motion>", x=wx, y=wy)
            settle(root, 3)
            assert c.hovered == tid and c.find_withtag("halo") and c.find_withtag("tip")
            c.event_generate("<ButtonPress-1>", x=wx, y=wy)
            c.event_generate("<ButtonRelease-1>", x=wx, y=wy)
            settle(root, 3)
            assert c.selected == tid
            assert tid in app.mission_detail_var.get() and "0.2.0" in app.mission_detail_var.get()
            assert "disabled" not in app.mission_open_btn.state()
            shot_at = {}
            for theme in ("dark", "light"):
                app.prefs.set_theme(theme)
                settle(root, 6)
                want = "midnight" if theme == "dark" else "daylight"
                assert c.assets.theme == want and len(c.find_withtag("node")) == 15
                shot_at[want] = str(c.cget("background")).lower()
                shot(root, f"mission_{want}.png")
            assert shot_at["midnight"] != shot_at["daylight"], shot_at
            app.prefs.set_theme("dark")
            assert (ctl.project.store.revision, ctl.project.store.ledger.count()) == (rev, n), "looking wrote state"
            # the map follows the state by revision
            ctl.project.tasks.transition(tids[0], "in_progress")
            sh.refresh_status()
            settle(root, 3)
            assert app.mission.node(tids[0])["status"] == "in_progress"
            # open in Workbench → Inspector shows the task
            app.mission_open_task()
            settle(root, 6)
            assert sh.current == "workbench"
            assert tuple(app.workspace_window.wc.selection) == ("task", tid), app.workspace_window.wc.selection
            print("v5.2.0 Mission Map smoke passed: 5 AI lanes · 3 version columns · 15 task circles · hover halo + "
                  "tooltip · click -> details -> Workbench Inspector · Midnight/Daylight · follows revisions · "
                  "looking writes nothing")
        finally:
            root.destroy()


if __name__ == "__main__":
    main()
