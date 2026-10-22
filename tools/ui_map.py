#!/usr/bin/env python3
"""Regenerate the App Map (roadmap 5.5.0) from the running application.

    xvfb-run -a python tools/ui_map.py            # write docs/UI_MAP.md + docs/design/ui_map.svg/.png
    xvfb-run -a python tools/ui_map.py --check    # exit 1 if docs/UI_MAP.md differs from the live map

The map is taken in Advanced mode with one fixed sample project open (so the Project Workbench is mapped too).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "apps" / "desktop" / "src"
GUI = ROOT / "apps" / "desktop" / "tests" / "gui"
DOC = ROOT / "docs" / "UI_MAP.md"
SVG = ROOT / "docs" / "design" / "ui_map.svg"
PNG = ROOT / "docs" / "design" / "ui_map.png"

HEAD = """# App Map — every place and every command (roadmap 5.5.0)

Generated from the running application by `tools/ui_map.py` (Advanced mode, one sample project open).
**Do not edit the tree by hand:** change the UI, then run `xvfb-run -a python tools/ui_map.py`.
`test_ui_map.py` fails when this file and the live application differ; `test_ui_balance.py` applies the balance rules.

Kinds: `area` (Toolbar, Rail, Status bar) · `page` · `section` · `tab` · `button` · `menu` → `item` ·
`option` (choice control) · `link` (opens another page; the command lives there).

Picture: [`design/ui_map.png`](design/ui_map.png) (also in the app: Settings › App Map).
"""


def live_tree() -> dict:
    sys.path[:0] = [str(SRC), str(GUI)]
    import tkinter as tk

    import AI_Workbench as wb
    from aiwb.ui import ui_map
    from gui_smoke_helpers import wait_for_project_ready
    temp = tempfile.mkdtemp(prefix="aiwb-ui-map-")
    os.environ["LOCALAPPDATA"] = str(Path(temp) / "appdata")
    project = Path(temp) / "Sample project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    root = tk.Tk()
    root.geometry("1440x900+0+0")
    try:
        app = wb.WorkbenchApp(root)
        app.shell.prefs.set_mode("advanced")
        app.set_workspace(project, focus_project=True)
        wait_for_project_ready(app, root, project)
        app.shell.show("workbench")
        for _ in range(10):
            root.update()
            time.sleep(0.02)
        return ui_map.extract(app)
    finally:
        root.destroy()


def table(tree: dict) -> str:
    from aiwb.ui import ui_map
    rows = ["| Page | Sections | Tabs | Commands | Visible at once | Links |", "|---|---:|---:|---:|---:|---:|"]
    for r in ui_map.stats(tree):
        rows.append(f"| {r['page']} | {r['sections']} | {r['tabs']} | {r['commands']} | {r['visible']} | {r['links']} |")
    return "\n".join(rows) + "\n"


def document(tree: dict) -> str:
    from aiwb.ui import ui_map
    problems = ui_map.audit(tree)
    rules = "\n".join(f"- `{k}` = {v}" for k, v in ui_map.RULES.items())
    audit = "\n".join(f"- {p}" for p in problems) if problems else "- none: the map is balanced."
    return (HEAD + "\n## Counts\n\n" + table(tree) + "\n## Balance rules\n\n" + rules + "\n\nAudit:\n\n" + audit
            + "\n\n## Tree\n\n<!-- ui-map:start -->\n" + ui_map.to_markdown(tree) + "<!-- ui-map:end -->\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    tree = live_tree()
    from aiwb.ui import ui_map
    if args.check:
        doc = ui_map.parse_markdown(DOC.read_text(encoding="utf-8"))
        if ui_map.to_markdown(doc) != ui_map.to_markdown(tree):
            print("docs/UI_MAP.md is out of date — run: xvfb-run -a python tools/ui_map.py")
            return 1
        print("docs/UI_MAP.md matches the live application")
        return 0
    DOC.write_text(document(tree), encoding="utf-8")
    SVG.write_text(ui_map.to_svg(tree), encoding="utf-8")
    import shutil
    import subprocess
    tool = shutil.which("magick") or shutil.which("convert")
    if tool:  # the PNG is for people reading the docs; the in-app viewer draws the same layout on a Canvas
        subprocess.run([tool, "-density", "110", str(SVG), str(PNG)], check=True, timeout=300)
    else:
        print("ImageMagick not found: docs/design/ui_map.png not refreshed")
    print(f"wrote {DOC.relative_to(ROOT)}, {SVG.relative_to(ROOT)}, {PNG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
