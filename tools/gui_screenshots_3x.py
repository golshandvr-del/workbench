#!/usr/bin/env python3
"""Release Gate 3.9.0: "after" screenshots of the 3.x single-window shell.

    xvfb-run -a -s "-screen 0 1920x1080x24" python tools/gui_screenshots_3x.py --out docs/audit/screens/v3.9.0

The "before" set is ``docs/audit/screens/v2.6.0`` (taken with ``tools/gui_screenshots.py`` on the 2.6
Workspace). This tool opens the main window (Advanced mode, so every rail page is visible), loads the
synthetic ten-agent dataset into the project, and saves ``<page>[_<view>]_<theme>_<WxH>.png`` for every
rail page and every Workbench view, in light and dark, plus ``manifest.json``. English only (roadmap
language policy). Linux/Xvfb capture, not physical Windows. Never changes project state.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import tempfile
import tkinter as tk
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in ("apps/desktop/src", "apps/desktop", "apps/desktop/tests", "apps/desktop/tests/gui"):
    sys.path.insert(0, str(REPO / p))

from gui_screenshots import capture  # noqa: E402

WB_VIEWS = ("overview", "timeline", "tasks", "team", "files", "versions")
SIZES = ("1280x720", "1024x640")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--sizes", default=",".join(SIZES))
    args = ap.parse_args()
    if not shutil.which("import"):
        print("ImageMagick 'import' is required", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    import AI_Workbench as wb
    import fixtures_ten_agents as fx
    from aiwb.ui.shell import PAGES
    from gui_smoke_helpers import wait_for_project_ready

    shots = []
    with tempfile.TemporaryDirectory(prefix="aiwb-shots3-") as temp:
        os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
        project = Path(temp) / "Sample project"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        root = tk.Tk()
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(wb.messagebox, name, lambda *a, **k: None)
        app = wb.WorkbenchApp(root)
        app.prefs.set_lang("en")
        app.prefs.set_mode("advanced")
        app.set_workspace(project, focus_project=True)
        wait_for_project_ready(app, root, project)
        app.shell.show("workbench")
        root.update()
        w = app.workspace_window
        fx.build_into(w.wc.ctl)
        w.wc.ctl.project.store.reload() if hasattr(w.wc.ctl.project.store, "reload") else None
        rev = w.wc.ctl.state()["state_revision"]
        events = w.wc.ctl.project.store.ledger.count()
        for th in args.themes.split(","):
            app.prefs.set_theme(th)
            for size in args.sizes.split(","):
                root.geometry(f"{size}+0+0")
                root.update()
                for page in PAGES:
                    views = WB_VIEWS if page == "workbench" else ("",)
                    for view in views:
                        app.shell.show(page)
                        if view:
                            w.wc.select("", "")
                            w.show(view)
                        for _ in range(3):
                            root.update()
                        name = f"{page}{'_' + view if view else ''}_{th}_{size}.png"
                        capture(root, root, out / name)
                        shots.append({"file": name, "page": page, "view": view, "theme": th, "size": size,
                                      "actual": f"{root.winfo_width()}x{root.winfo_height()}"})
        assert w.wc.ctl.state()["state_revision"] == rev, "screenshots must not change project state"
        assert w.wc.ctl.project.store.ledger.count() == events, "screenshots must not add events"
        scaling = float(root.tk.call("tk", "scaling"))
        root.destroy()
    manifest = {"label": "3.9.0 after (single window, Fluent theme)", "before": "docs/audit/screens/v2.6.0",
                "dataset": "tests/fixtures_ten_agents.py (10 agents, 2 tasks each)", "tk_scaling": scaling,
                "mode": "advanced", "language": "en",
                "capture": "Xvfb + ImageMagick import (Linux, not physical Windows)",
                "machine": f"{platform.system()} {platform.release()} Python {platform.python_version()}",
                "shots": shots}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(shots)} screenshots -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
