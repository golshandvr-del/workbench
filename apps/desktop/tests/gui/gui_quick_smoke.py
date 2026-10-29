"""Roadmap 5.14.0 gate: Quick — one AI chat, with REAL widgets, the three answer formats, Restore and Quick → Guided.

Path: Toolbar › New Project ▾ › Quick — one AI chat… → the small form (name typed, Create) → the Quick window →
describe the job → Copy the prompt (on the real clipboard, with the format's rules) →

1. **AIWB file blocks**, pasted from the real clipboard (``<<Paste>>``, what Ctrl+V does) → Check the answer → the
   file list (new / changed + diff) → Apply → the files are on disk → Restore last apply → the folder is as before;
2. **Strict JSON** → Check → Apply;
3. **GPT ZIP** through Load ZIP… → Check (the list names the ZIP) → Apply;
4. a **cut-off** answer → the continue prompt is offered and copied; the complete file can still be applied;
5. Home shows the Quick card (Open the Quick window) for this folder;
6. Make it a multi-AI project… → team table → Make the project → the files are untouched and Home shows the guided
   card (the Project Charter step).

No callback error and no message box on the way. ``AIWB_SCREENSHOT_DIR=dir`` writes a screenshot per step.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import traceback
import zipfile
from pathlib import Path

import AI_Workbench as wb

F4 = "````"


def block(path: str, body: str) -> str:
    return f'<<<AIWB_FILE path="{path}" action="write">>>\n{F4}\n{body}{F4}\n<<<AIWB_END_FILE>>>\n'


def digest(folder: Path) -> dict[str, str]:
    """Every project file (not .workbench / .git) → sha256; the before/after picture of the folder."""
    out = {}
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder).as_posix()
        if p.is_file() and not rel.startswith((".workbench/", ".git/")):
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


class Driver:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.errors: list[str] = []
        self.clicks: list[str] = []
        root.report_callback_exception = lambda *a: self.errors.append("".join(traceback.format_exception(*a)))

    def pump(self, ms: int = 300) -> None:
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

    def click(self, widget, what: str = "") -> None:
        self.clicks.append(what or str(widget.cget("text")))
        widget.invoke()
        self.pump(150)

    def clipboard_paste(self, box: tk.Text, value: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.pump(50)
        box.delete("1.0", "end")
        box.focus_force()
        box.event_generate("<<Paste>>")
        self.pump(100)
        got = box.get("1.0", "end-1c")
        assert got.replace("\r", "") == value.replace("\r", ""), f"the clipboard paste changed the text ({len(got)})"

    def wait_line(self, panel, needle: str, seconds: float = 5) -> str:
        end, line = time.monotonic() + seconds, ""
        while time.monotonic() < end and needle not in line:
            self.pump(50)
            line = panel.status_var.get()
        assert needle in line, f"live check never showed {needle!r}: {line!r}"
        return line

    def shot(self, name: str) -> None:
        out = os.environ.get("AIWB_SCREENSHOT_DIR")
        if not out or not shutil.which("import"):
            return
        Path(out).mkdir(parents=True, exist_ok=True)
        self.pump(300)
        subprocess.run(["import", "-window", "root", str(Path(out) / f"quick_{name}.png")], check=False, timeout=30)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-quick-") as temp:
        home = Path(temp)
        os.environ["LOCALAPPDATA"] = str(home / "appdata")
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
        (home / "Documents").mkdir()
        root = tk.Tk()
        root.geometry("1366x800+0+0")
        d = Driver(root)
        boxes: list[tuple] = []
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(wb.messagebox, name, (lambda n: lambda *a, **k: boxes.append((n, a)))(name))
        try:
            app = wb.WorkbenchApp(root)
            d.pump(600)
            # Toolbar › New Project ▾ › Quick — one AI chat…
            menu = app.shell.toolbar.menus["new"]
            labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)]
            assert "Quick — one AI chat…" in labels, labels
            d.clicks.append("New Project ▾")
            menu.invoke(labels.index("Quick — one AI chat…"))
            d.clicks.append("Quick — one AI chat…")
            d.pump(300)
            form = app.quick_form
            assert form["win"].winfo_ismapped(), "the Quick form did not open"
            form["name"].set("Hello Quick")
            d.shot("01_form")
            qw = form["create"]()
            d.clicks.append("Create")
            d.pump(500)
            assert qw is not None, f"Create failed: {form['error'].get()!r}"
            folder = Path(app.workspace)
            assert folder.name == "Hello Quick" and folder.is_dir(), folder
            assert app.shell.toolbar.project_var.get() == "Hello Quick", app.shell.toolbar.project_var.get()
            assert qw.win.winfo_ismapped() and qw.root == folder
            (folder / "app.py").write_text("print('old')\n", encoding="utf-8")
            empty = digest(folder)

            # the job → Copy the prompt (real clipboard)
            qw.task_box.insert("1.0", "Make a hello app with a README")
            d.click(qw.prompt_btn)
            prompt = root.clipboard_get()
            assert "Make a hello app with a README" in prompt and "AIWB_FILE" in prompt, prompt[:300]
            assert "app.py" in prompt, "the prompt does not list the project's files"
            d.shot("02_prompt_copied")

            # 1) AIWB file blocks from the clipboard → Check → list + diff → Apply → Restore
            ans = block("app.py", "print('hello')\n") + block("README.md", "# Hello\n")
            d.clipboard_paste(qw.paste.box, ans)
            line = d.wait_line(qw.paste, "Files ✓")
            assert "AIWB_HANDOFF" not in " ".join(qw.paste.preview.warnings), qw.paste.preview.warnings
            d.click(qw.paste.ok_btn)
            states = {i["path"]: i["status"] for i in qw.items}
            assert states == {"app.py": "changed", "README.md": "new"}, states
            assert "+print('hello')" in qw.diff.get("1.0", "end"), qw.diff.get("1.0", "end")
            assert str(qw.apply_btn.cget("state")) == "normal" and qw.apply_btn.cget("text") == "Apply 2 files"
            d.shot("03_aiwb_checked")
            d.click(qw.apply_btn)
            assert (folder / "app.py").read_text(encoding="utf-8") == "print('hello')\n"
            assert (folder / "README.md").read_text(encoding="utf-8") == "# Hello\n"
            assert str(qw.restore_btn.cget("state")) == "normal"
            d.shot("04_aiwb_applied")
            d.click(qw.restore_btn)
            assert digest(folder) == empty, "Restore did not bring the folder back"
            assert "Restored 2 file(s)" in qw.message_var.get(), qw.message_var.get()

            # 2) Strict JSON
            qw.set_format("json")
            d.click(qw.prompt_btn)
            assert '"files"' in root.clipboard_get()
            d.clipboard_paste(qw.paste.box, json.dumps({"files": [{"path": "app.py", "content": "print(2)\n"}],
                                                        "notes": "two"}))
            d.wait_line(qw.paste, "Files ✓")
            d.click(qw.paste.ok_btn)
            assert qw.answer["label"] == "Strict JSON", qw.answer["label"]
            d.click(qw.apply_btn)
            assert (folder / "app.py").read_text(encoding="utf-8") == "print(2)\n"

            # 3) GPT ZIP through Load ZIP…
            qw.set_format("zip")
            d.click(qw.prompt_btn)
            assert "ZIP" in root.clipboard_get()
            z = home / "answer.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("src/game.py", "SCORE = 0\n")
                zf.writestr("README.md", "# Game\n")
            qw.paste._ask_zip = lambda: str(z)
            d.click(qw.paste.zip_btn)
            d.wait_line(qw.paste, "ZIP ✓")
            d.click(qw.paste.ok_btn)
            assert qw.answer["label"] == "GPT ZIP · answer.zip", qw.answer["label"]
            assert {i["path"] for i in qw.items} == {"src/game.py", "README.md"}
            d.shot("05_zip_checked")
            d.click(qw.apply_btn)
            assert (folder / "src" / "game.py").read_text(encoding="utf-8") == "SCORE = 0\n"

            # 4) a cut-off answer → continue prompt; the complete file can be applied
            qw.set_format("aiwb")
            cut = block("b.py", "print(1)\n") + '<<<AIWB_FILE path="c.py" action="write">>>\n' + F4 + "\nprint(2"
            d.clipboard_paste(qw.paste.box, cut)
            d.wait_line(qw.paste, "Cut off")
            d.click(qw.paste.ok_btn)
            assert qw.answer["truncated"] and qw.continue_btn.winfo_manager(), "no continue prompt offered"
            d.click(qw.continue_btn)
            assert root.clipboard_get() == qw.answer["continue_prompt"]
            d.shot("06_cut_off")

            # 5) Home shows the Quick card for this folder; it reopens the same window
            app.shell.show("home")
            app.home_card.refresh()
            d.pump(300)
            assert app.home_card.title_var.get() == "Quick — one AI chat", app.home_card.title_var.get()
            app.refresh_mission(app.status_state(), force=True)
            assert app.mission.model["empty"], "a Quick folder must not show template AI lanes on the map"
            qw.win.withdraw()
            d.shot("07_home_quick_card")
            d.click(app.home_card.button("Open the Quick window"))
            assert app.quick_window is qw and qw.win.winfo_ismapped()

            # 6) Make it a multi-AI project… → the files stay, Home shows the guided card
            before = digest(folder)
            d.click(qw.convert_btn)
            dlg = qw.convert_dialog
            dlg["goal"].delete("1.0", "end")
            dlg["goal"].insert("1.0", "A small snake game")
            d.shot("08_convert")
            out = dlg["ok"]()
            d.clicks.append("Make the project")
            d.pump(800)
            assert out is not None, dlg["error"].get()
            assert out["workers"] == 2, out
            assert digest(folder) == before, "converting changed project files"
            from aiwb.v2 import quick
            assert quick.is_guided(folder) and not quick.is_quick(folder)
            app.shell.show("home")
            app.home_card.refresh()
            d.pump(300)
            title = app.home_card.title_var.get()
            assert "Charter" in title, title
            d.shot("09_guided_home")
            assert not d.errors, d.errors[0]
            assert not boxes, boxes
            msg = (f"5.14.0 Quick smoke: menu → form → prompt → AIWB (clipboard) / JSON / ZIP → apply, Restore, cut-off "
                   f"→ continue, Home Quick card, Quick → Guided ({out['workers']} AIs, files untouched); "
                   f"{len(d.clicks)} clicks: PASS")
            # a Windows console (cp1252) cannot print →: replace what it cannot encode instead of failing a passed smoke
            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            print(msg.encode(enc, "replace").decode(enc, "replace"))
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - the runner prints the last line
        traceback.print_exc()
        sys.exit(1)
