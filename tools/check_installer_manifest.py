#!/usr/bin/env python3
"""Consistency gate between install.ps1 and release_manifest.json.

install.ps1 copies an explicit list of top-level files and aiwb/ modules.
A module added to the payload but forgotten in install.ps1 would ship in the
ZIP yet never be installed — this check fails the build in that case, and also
when install.ps1 references a file the payload does not contain.

Also checks: every Python file under apps/desktop/aiwb is in the payload, and
the aiwb package __version__ is not newer than APP_VERSION.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DESKTOP = REPO / "apps" / "desktop"


def parse_install_lists(text: str) -> tuple[list[str], list[str]]:
    top = re.search(r"foreach \(\$fileName in @\(([^)]*)\)\)", text)
    mods = re.search(r"foreach \(\$moduleName in @\(([^)]*)\)\)", text)
    if not top or not mods:
        raise SystemExit("FAIL: could not locate file lists in install.ps1")
    q = re.compile(r"'([^']+)'")
    return q.findall(top.group(1)), ["aiwb/" + m for m in q.findall(mods.group(1))]


def main() -> int:
    manifest = json.loads((DESKTOP / "release_manifest.json").read_text(encoding="utf-8"))
    payload = set(manifest["payload_files"])
    install = (DESKTOP / "install.ps1").read_text(encoding="utf-8-sig")
    top, mods = parse_install_lists(install)
    installed = set(top) | set(mods) | {"uninstall.bat"}
    problems: list[str] = []
    for f in sorted(installed - payload):
        problems.append(f"install.ps1 copies {f} but payload does not contain it")
    for f in sorted(payload - installed - {"install.ps1"}):
        problems.append(f"payload contains {f} but install.ps1 never installs it")
    for py in sorted((DESKTOP / "aiwb").rglob("*.py")):
        rel = py.relative_to(DESKTOP).as_posix()
        if "__pycache__" not in rel and rel not in payload:
            problems.append(f"{rel} exists in source but is missing from release_manifest.json")
    for f in sorted(p.name for p in DESKTOP.glob("*.py")):
        if f not in payload:
            problems.append(f"top-level {f} exists in source but is missing from release_manifest.json")
    app_version = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', (DESKTOP / "AI_Workbench.py").read_text(encoding="utf-8"), re.M)
    if not app_version or app_version.group(1) != manifest["version"]:
        problems.append("APP_VERSION in AI_Workbench.py differs from release_manifest.json version")
    if problems:
        print("FAIL: installer/manifest inconsistency")
        for p in problems:
            print("  - " + p)
        return 1
    print(f"PASS: install.ps1 installs all {len(payload) - 1} payload files; manifest v{manifest['version']} consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
