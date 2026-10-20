"""Roadmap 5.0.0 gate: the splash launcher starts the app; images from the rasteriser load in Tk; start time.

Prints ``start <seconds>`` (launcher → built window) so the speed can be compared before/after.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

APP_DIR = Path(os.environ.get("AIWB_APP_DIR") or Path(__file__).resolve().parents[2] / "src")
sys.path.insert(0, str(APP_DIR))


def main() -> int:
    data = tempfile.mkdtemp()
    os.environ["LOCALAPPDATA"] = data
    os.environ["APPDATA"] = data
    t0 = time.perf_counter()
    from aiwb.ui.startup import Splash, enable_dpi_awareness, ui_scale

    assert enable_dpi_awareness() in ("", "per-monitor-v2", "per-monitor", "system")
    root = tk.Tk()
    root.withdraw()
    splash = Splash(root, title="AI Workbench", version="5")
    assert splash.top is not None and splash.top.winfo_exists()
    splash.progress(0.5)
    import AI_Workbench

    app = AI_Workbench.WorkbenchApp(root)
    splash.close()
    root.deiconify()
    root.update()
    t1 = time.perf_counter()
    assert splash.top is None
    assert 1.0 <= ui_scale(root) <= 3.0

    from aiwb.ui.assets import ICONS, Assets
    a = Assets(root, "midnight", ui_scale(root))
    img = a.sprite("task_active")
    assert img.width() > 10 and img.height() == img.width()
    for name in ICONS:
        assert a.icon(name, 20).width() >= 20
    n = len(a)
    a.sprite("task_active")
    assert len(a) == n, "sprites must be cached"
    a.set_theme("daylight")
    assert len(a) == 0
    _ = app
    root.destroy()
    print(f"start {t1 - t0:.2f}s")
    print("v5.0.0 startup smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
