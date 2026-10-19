#!/usr/bin/env python3
"""Reproducible Workspace screenshots (GUI roadmap stage 0 / §11.1).

    xvfb-run -a -s "-screen 0 1920x1080x24" python tools/gui_screenshots.py --out docs/audit/screens/v2.6.0

For every view × theme × language × size it opens the Project Workbench on the
synthetic ten-agent dataset (``tests/fixtures_ten_agents.py``), optionally
selects an item and saves ``<view>_<theme>_<lang>_<WxH>[_sel].png`` plus a
``manifest.json`` with the exact conditions (size, theme, language, DPI scaling,
dataset, selection, machine). Screenshots are taken from the X display with
ImageMagick ``import``; this is a Linux/Xvfb capture, not a physical-Windows one.
Only the UI preferences file (ui.json) is touched — never project state.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps/desktop/src"))
sys.path.insert(0, str(REPO / "apps/desktop"))
sys.path.insert(0, str(REPO / "apps/desktop/tests"))
sys.path.insert(0, str(REPO / "apps/desktop/tests/gui"))

VIEWS = ("overview", "timeline", "tasks", "team", "files", "versions", "settings")
SIZES = ("1280x720", "1024x640")


def capture(root: tk.Misc, win: tk.Misc, path: Path) -> None:
    root.update()
    win.update_idletasks()
    win.lift()
    root.update()
    wid = win.winfo_id()
    frame = win.wm_frame() if hasattr(win, "wm_frame") else hex(wid)
    for target in (frame, hex(wid)):
        r = subprocess.run(["import", "-window", str(target), str(path)], capture_output=True)
        if r.returncode == 0 and path.exists():
            return
    raise RuntimeError(f"screenshot failed for {path}: {r.stderr.decode()[:200]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--views", default=",".join(VIEWS))
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--langs", default="en,fa")
    ap.add_argument("--sizes", default=",".join(SIZES))
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    if not shutil.which("import"):
        print("ImageMagick 'import' is required", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    import AI_Workbench as wb
    import fixtures_ten_agents as fx
    from gui_smoke_helpers import wait_for_project_ready

    shots = []
    with tempfile.TemporaryDirectory(prefix="aiwb-shots-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Sample project"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(wb.messagebox, name, lambda *a, **k: None)
        app = wb.WorkbenchApp(root)
        app.set_workspace(project, focus_project=True)
        wait_for_project_ready(app, root, project)
        app.open_project_workbench()
        w = app.workspace_window
        data = fx.build_into(w.wc.ctl)
        sel_task = data["special"]["stale"]
        scaling = float(root.tk.call("tk", "scaling"))
        rev = w.wc.ctl.state()["state_revision"]
        events = w.wc.ctl.project.store.ledger.count()
        for lang in args.langs.split(","):
            w.lang_var.set(lang)
            w._set_lang()
            for th in args.themes.split(","):
                w.theme_var.set(th)
                w._set_theme()
                for size in args.sizes.split(","):
                    w.win.geometry(f"{size}+0+0")
                    root.update()
                    for view in args.views.split(","):
                        for selected in (False, True):
                            if selected and view not in ("tasks", "team"):
                                continue
                            if selected:
                                w.wc.select("task" if view == "tasks" else "agent",
                                            sel_task if view == "tasks" else "agent-fx-03")
                            else:
                                w.wc.select("", "")
                            w.show(view)
                            root.update()
                            name = f"{view}_{th}_{lang}_{size}{'_sel' if selected else ''}.png"
                            capture(root, w.win, out / name)
                            shots.append({"file": name, "view": view, "theme": th, "language": lang, "size": size,
                                          "selection": selected, "actual": f"{w.win.winfo_width()}x{w.win.winfo_height()}"})
        assert w.wc.ctl.state()["state_revision"] == rev, "screenshots must not change project state"
        assert w.wc.ctl.project.store.ledger.count() == events, "screenshots must not add events"
        root.destroy()
    manifest = {"label": args.label, "dataset": "tests/fixtures_ten_agents.py (10 agents, 2 tasks each)",
                "tk_scaling": scaling, "capture": "Xvfb + ImageMagick import (Linux, not physical Windows)",
                "machine": f"{platform.system()} {platform.release()} Python {platform.python_version()}",
                "shots": shots}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(shots)} screenshots -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
