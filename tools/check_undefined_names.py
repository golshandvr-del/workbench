#!/usr/bin/env python3
"""Fail on undefined names (pyflakes) in desktop sources and tools.

Only *undefined name* findings fail the gate; style warnings are ignored so the
legacy single-file app does not need a rewrite.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGETS = [REPO / "apps/desktop/src", REPO / "apps/desktop/tests", REPO / "tools"]


def main() -> int:
    try:
        import pyflakes  # noqa: F401
    except ImportError:
        print("FAIL: pyflakes is not installed (pip install pyflakes)")
        return 2
    proc = subprocess.run([sys.executable, "-m", "pyflakes", *map(str, TARGETS)], capture_output=True, text=True)
    bad = [line for line in proc.stdout.splitlines() if "undefined name" in line]
    for line in bad:
        print(line)
    print(f"{'FAIL' if bad else 'PASS'}: {len(bad)} undefined name(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
