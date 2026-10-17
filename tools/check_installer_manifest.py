#!/usr/bin/env python3
"""Consistency gate between install.ps1, release_manifest.json and the source tree.

install.ps1 copies an explicit list of top-level files and aiwb/ modules into the
flat program folder. Fails when a payload file is never installed, when
install.ps1 references a file the payload lacks, when an application module in
apps/desktop/src or a unit-test module in apps/desktop/tests is not shipped,
or when APP_VERSION differs from the manifest.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_desktop_installer as builder  # noqa: E402

DESKTOP = builder.DESKTOP


def parse_install_lists(text: str) -> tuple[list[str], list[str]]:
    top = re.search(r"foreach \(\$fileName in @\(([^)]*)\)\)", text)
    mods = re.search(r"foreach \(\$moduleName in @\(([^)]*)\)\)", text)
    if not top or not mods:
        raise SystemExit("FAIL: could not locate file lists in install.ps1")
    q = re.compile(r"'([^']+)'")
    return q.findall(top.group(1)), ["aiwb/" + m for m in q.findall(mods.group(1))]


def main() -> int:
    try:
        manifest = builder.load_manifest()
        builder.check_app_version(manifest["version"])
    except builder.BuildError as exc:
        print(f"FAIL: {exc}")
        return 1
    payload = dict(manifest["payload"])  # zip path -> repo source
    install = (builder.REPO / payload["install.ps1"]).read_text(encoding="utf-8-sig")
    top, mods = parse_install_lists(install)
    installed = set(top) | set(mods) | {"uninstall.bat"}
    problems: list[str] = []
    for f in sorted(installed - set(payload)):
        problems.append(f"install.ps1 copies {f} but the payload does not contain it")
    for f in sorted(set(payload) - installed - {"install.ps1"}):
        problems.append(f"payload contains {f} but install.ps1 never installs it")
    shipped = set(payload.values())
    for py in sorted((DESKTOP / "src").rglob("*.py")):
        rel = py.relative_to(builder.REPO).as_posix()
        if "__pycache__" not in rel and rel not in shipped:
            problems.append(f"{rel} exists but is not in release_manifest.json")
    for py in sorted((DESKTOP / "tests").glob("test_*.py")):
        rel = py.relative_to(builder.REPO).as_posix()
        if rel not in shipped:
            problems.append(f"{rel} exists but is not in release_manifest.json")
    if problems:
        print("FAIL: installer/manifest inconsistency")
        for p in problems:
            print("  - " + p)
        return 1
    print(f"PASS: install.ps1 installs all {len(payload) - 1} payload files; manifest v{manifest['version']} consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
