"""Roadmap 5.15.0 scenario S1: Quick — one AI chat makes a small app of three files, with REAL widgets.

New Project ▾ › Quick — one AI chat… → name → Create → the job → Copy the prompt → the chat's answer (three AIWB
file blocks, one file changed, two new) pasted with Ctrl+V → Check → Apply 3 files → the three files are on disk,
byte for byte → a second round edits one file → Apply → Restore last apply brings back the first round.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

from scenario_driver import Driver, block, digest, menu_labels, run, scenario_home

FILES = {
    "app.py": "from util import greet\n\nprint(greet('world'))\n",
    "util.py": "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n",
    "README.md": "# Hello\n\nRun `python app.py`.\n",
}


def main() -> None:
    with scenario_home("s1"):
        d = Driver(tk.Tk(), "s1")
        try:
            app = d.start()
            menu = app.shell.toolbar.menus["new"]
            assert "Quick — one AI chat…" in menu_labels(menu), menu_labels(menu)
            d.clicks.append("New Project ▾")
            d.click_menu(menu, "Quick — one AI chat…")
            form = app.quick_form
            form["name"].set("Hello three files")
            d.shot("01_form")
            qw = form["create"]()
            d.clicks.append("Create")
            d.pump(500)
            assert qw is not None, form["error"].get()
            folder = Path(app.workspace)
            (folder / "app.py").write_text("print('old')\n", encoding="utf-8")

            qw.task_box.insert("1.0", "A hello app: app.py uses util.greet; a README says how to run it")
            d.click(qw.prompt_btn)
            prompt = d.clipboard()
            assert "util.greet" in prompt and "AIWB_FILE" in prompt and "app.py" in prompt, prompt[:300]
            d.shot("02_prompt")

            d.paste(qw.paste.box, "Here are the files.\n\n" + "".join(block(p, c) for p, c in FILES.items()))
            d.wait_line(qw.paste, "Files ✓")
            d.click(qw.paste.ok_btn)
            states = {i["path"]: i["status"] for i in qw.items}
            assert states == {"app.py": "changed", "util.py": "new", "README.md": "new"}, states
            assert qw.apply_btn.cget("text") == "Apply 3 files", qw.apply_btn.cget("text")
            d.shot("03_checked")
            d.click(qw.apply_btn)
            for p, c in FILES.items():
                assert (folder / p).read_bytes() == c.encode("utf-8"), p
            first = digest(folder)
            d.shot("04_applied")

            # round 2: the chat changes one file; Restore takes the folder back to round 1
            d.paste(qw.paste.box, block("util.py", "def greet(name: str) -> str:\n    return f'Hi, {name}!'\n"))
            d.wait_line(qw.paste, "Files ✓")
            d.click(qw.paste.ok_btn)
            assert {i["path"]: i["status"] for i in qw.items} == {"util.py": "changed"}
            d.click(qw.apply_btn)
            assert "Hi," in (folder / "util.py").read_text(encoding="utf-8")
            d.click(qw.restore_btn)
            assert digest(folder) == first, "Restore did not bring round 1 back"
            d.shot("05_restored")
            d.finish()
        finally:
            d.destroy()
    d.say(f"S1 Quick, one AI, 3 files: prompt -> paste -> Apply 3 files -> round 2 -> Restore; "
          f"{len(d.clicks)} clicks + {d.pastes} pastes: PASS")


if __name__ == "__main__":
    run(main)
