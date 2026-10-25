"""GUI smoke for the visual timeline (roadmap 3.6.0 Gate).

* 2000 ledger events render in < 300 ms (median of 3 redraws).
* Circle size follows importance; released version → solid line, proposed → dashed.
* Dark theme palette is used; zoom/pan keep the canvas consistent.
* History › Timeline shows the canvas and a click opens the event in the Workbench Inspector (5.13.0).
"""
from __future__ import annotations

import os
import statistics
import tempfile
import time
import tkinter as tk
from pathlib import Path

import AI_Workbench as wb
from aiwb.ui.timeline_canvas import RADIUS, TimelineCanvas, build_model
from aiwb.workspace import theme
from gui_smoke_helpers import wait_for_project_ready

IMPS = ("project_settings_updated", "task_created", "milestone_accepted", "release_published")


def synthetic(n: int) -> tuple[list[dict], dict]:
    recs = []
    for i in range(n):
        h, m = divmod(i, 60)
        recs.append({"event_id": f"LE-{i:06d}-00", "event_type": IMPS[i % 4],
                     "timestamp_utc": f"2026-10-{1 + (h // 24) % 28:02d}T{h % 24:02d}:{m:02d}:00Z",
                     "refs": {"agent_id": f"agent-{i % 3}"}, "after": {}, "payload": {}})
    state = {"tasks": {}, "versions": {
        "VER-0001": {"version_id": "VER-0001", "label": "1.0.0", "status": "released", "created_at": "2026-10-01T05:00:00Z",
                     "history": [{"to": "released", "at": "2026-10-01T06:00:00Z"}]},
        "VER-0002": {"version_id": "VER-0002", "label": "1.1.0", "status": "proposed", "created_at": "2026-10-01T10:00:00Z",
                     "history": []}}}
    return recs, state


def check_canvas(root: tk.Tk) -> None:
    recs, state = synthetic(2000)
    model = build_model(recs, state)
    pal = theme.palette("dark")
    c = TimelineCanvas(root, palette=pal, height=200, width=1200)
    c.pack(fill="both", expand=True)
    root.update()
    c.set_model(model)
    times = []
    for _ in range(3):
        t = time.perf_counter()
        c.redraw()
        root.update_idletasks()
        times.append((time.perf_counter() - t) * 1000)
    med = statistics.median(times)
    assert med < 300, f"2000 events took {med:.0f} ms"
    assert c.cget("background") == pal["surface"], "dark palette is used"
    sizes = {}
    for cid, it in c.items.items():
        if it["kind"] == "event":
            x0, _y0, x1, _y1 = c.coords(cid)
            sizes.setdefault(it["importance"], round((x1 - x0) / 2))
    assert sizes == {k: RADIUS[k] for k in sizes} and len(sizes) == 4, sizes
    lines = {it["label"]: c.itemcget(cid, "dash") for cid, it in c.items.items() if it["kind"] == "version"}
    assert lines.get("1.0.0", "x") == "" and lines.get("1.1.0"), lines
    c.zoom_at(4.0, 600)
    c.pan(200)
    assert c.offset > 0 and c.zoom == 4.0
    c.destroy()
    print(f"  2000 events: median redraw {med:.0f} ms")


def main() -> None:
    root = tk.Tk()
    root.geometry("1280x720+0+0")
    try:
        check_canvas(root)
    finally:
        root.destroy()
    with tempfile.TemporaryDirectory(prefix="aiwb-timeline-smoke-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Timeline"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        root.geometry("1280x720+0+0")
        try:
            app = wb.WorkbenchApp(root)
            for name in ("showinfo", "showwarning", "showerror"):
                setattr(wb.messagebox, name, lambda *a, **k: None)
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.open_project_workbench()
            w = app.workspace_window
            w.wc.ctl.project.tasks.create({"title": "First task", "objective": "Do the first thing"})
            # 5.13.0 (B3): the Workbench has no Timeline section any more — the past lives in History
            app.shell.show("history")
            root.update()
            app.refresh_history_timeline()
            root.update()
            c = app.history_tl
            assert c.model["events"], "timeline canvas has the project's events"
            cid = next(k for k, v in c.items.items() if v["kind"] == "event")
            x0, y0, x1, y1 = c.coords(cid)
            got = c.click((x0 + x1) / 2, (y0 + y1) / 2)   # the topmost circle at that point wins
            assert got and got["kind"] == "event", got
            assert w.wc.selection == ("event", got["id"]), w.wc.selection
            assert c.selected == got["id"]
        finally:
            root.destroy()
    print("PASS: visual timeline GUI smoke - 2000 events < 300ms, importance circles, version lines, dark, click -> Inspector")


if __name__ == "__main__":
    main()
