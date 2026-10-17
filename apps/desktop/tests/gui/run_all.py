#!/usr/bin/env python3
"""Run every desktop GUI smoke script, each in its own interpreter.

Usage (needs a display — Windows desktop or ``xvfb-run`` on Linux):

    python apps/desktop/tests/gui/run_all.py [--app-dir DIR] [NAME_FILTER ...]

``--app-dir`` points the smokes at another copy of the application, e.g. the
installed folder ``%LOCALAPPDATA%\\Programs\\AIWorkbench``; default is ``src/``.
Each script runs with a timeout so one hung window cannot stall CI.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
TIMEOUT_SECONDS = 240


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app-dir", default=str(SRC))
    ap.add_argument("filters", nargs="*")
    args = ap.parse_args(argv)
    app_dir = Path(args.app_dir).resolve()
    if not (app_dir / "AI_Workbench.py").is_file():
        print(f"FAIL: {app_dir / 'AI_Workbench.py'} not found")
        return 2
    scripts = sorted(HERE.glob("gui_*smoke.py"))
    if args.filters:
        scripts = [p for p in scripts if any(f in p.name for f in args.filters)]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(app_dir), str(HERE), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    failed: list[str] = []
    for script in scripts:
        started = time.monotonic()
        try:
            proc = subprocess.run([sys.executable, str(script)], cwd=str(HERE), env=env,
                                  capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
            ok, out = proc.returncode == 0, (proc.stdout + proc.stderr).strip()
        except subprocess.TimeoutExpired:
            ok, out = False, f"timed out after {TIMEOUT_SECONDS}s"
        last = out.splitlines()[-1] if out else ""
        print(f"[{'PASS' if ok else 'FAIL'}] {script.name} ({time.monotonic() - started:.1f}s) {last[:160]}", flush=True)
        if not ok:
            failed.append(script.name)
            print("\n".join("    " + line for line in out.splitlines()[-40:]), flush=True)
    print(f"\n{len(scripts) - len(failed)}/{len(scripts)} GUI smoke scripts passed (app: {app_dir})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
