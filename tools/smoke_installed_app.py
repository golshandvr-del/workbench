#!/usr/bin/env python3
"""GUI startup smoke test for the AI Workbench desktop app.

Launches the real Tk application from a given directory (source tree or an
installed program folder) in an isolated LOCALAPPDATA, verifies the main
window builds its tabs without exceptions, then closes it.

Usage: python tools/smoke_installed_app.py [APP_DIR]   (default: apps/desktop/src)
Needs a display (Windows desktop session or Xvfb on Linux).
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import traceback
from pathlib import Path


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows console codepages cannot print Unicode paths
        try:
            stream.reconfigure(errors="backslashreplace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    app_dir = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parent.parent / "apps" / "desktop" / "src"
    entry = app_dir / "AI_Workbench.py"
    if not entry.is_file():
        print(f"FAIL: {entry} not found")
        return 1
    with tempfile.TemporaryDirectory(prefix="aiwb-smoke-") as tmp:
        os.environ["LOCALAPPDATA"] = tmp
        os.environ["APPDATA"] = tmp
        sys.path.insert(0, str(app_dir))
        spec = importlib.util.spec_from_file_location("aiwb_smoke_app", entry)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        errors: list[str] = []
        root = module.tk.Tk()
        root.report_callback_exception = lambda et, ev, tb: errors.append("".join(traceback.format_exception(et, ev, tb)))
        try:
            app = module.WorkbenchApp(root)
            root.update_idletasks()
            for _ in range(20):
                root.update()
            tabs = [app.notebook.tab(t, "text") for t in app.notebook.tabs()]
            title = root.title()
        finally:
            try:
                root.destroy()
            except Exception:
                pass
        if errors:
            print("FAIL: Tk callback exceptions:\n" + "\n".join(errors))
            return 1
        print(f"window title: {title}")
        print(f"tabs ({len(tabs)}): {', '.join(tabs)}")
        if module.APP_VERSION not in title and module.APP_VERSION not in " ".join(tabs):
            print(f"note: APP_VERSION {module.APP_VERSION} not shown in title")
        if len(tabs) < 3:
            print("FAIL: expected the main notebook to have tabs")
            return 1
        print(f"PASS: AI Workbench {module.APP_VERSION} GUI smoke from {app_dir}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
