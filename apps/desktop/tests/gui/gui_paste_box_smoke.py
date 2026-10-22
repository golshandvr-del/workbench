"""Roadmap 5.10.0 gate: the real paste box — live diagnosis, Load ZIP…, and answers in other formats to files on disk.

Only real widgets: the Workbench's primary button / More menu open the paste box; a poller types into its Text widget
(or clicks **Load ZIP…** with the file dialog answered), waits for the live diagnosis line to change, reads it, and
presses **Use this answer**.

Path: charter WITHOUT markers in a ```json fence and with model-style damage → the box says "Charter ✓ … auto-fix"
before anything is imported → accept → task 1 answered as a GPT ZIP (Load ZIP…) → accept → file on disk → task 2
answered as Markdown code blocks (no manifest) → accept → file on disk; a cut-off answer shows "Cut off ✗".
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import time
import tkinter as tk
import traceback
import zipfile
from pathlib import Path
from typing import Any, Callable

import AI_Workbench as wb
from gui_smoke_helpers import wait_for_project_ready

REPO = Path(__file__).resolve().parents[4]
CHARTER = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"


def walk(w: tk.Misc):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


class Paster:
    """Answers each paste box that opens with one scripted ``action(box_widgets) -> None``."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.jobs: list[Callable[[dict[str, Any]], None]] = []
        self.lines: list[str] = []
        self.errors: list[str] = []
        self._seen: set[str] = set()
        root.report_callback_exception = lambda *a: self.errors.append("".join(traceback.format_exception(*a)))
        root.after(60, self._poll)

    def pump(self, ms: int = 300) -> None:
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)

    def _poll(self) -> None:
        try:
            for t in [w for w in walk(self.root) if isinstance(w, tk.Toplevel)]:
                if str(t) in self._seen or not t.winfo_ismapped() or not self.jobs:
                    continue
                kids = list(walk(t))
                btn = {str(c.cget("text")): c for c in kids if c.winfo_class() == "TButton"}
                if "Use this answer" not in btn or "Load ZIP…" not in btn:
                    continue
                self._seen.add(str(t))
                labels = [c for c in kids if c.winfo_class() == "TLabel"]
                w = {"top": t, "text": next(c for c in kids if c.winfo_class() == "Text"), "buttons": btn,
                     "status": lambda: str(labels[-1].cget("text")) if labels else "",
                     "labels": labels}
                job = self.jobs.pop(0)
                self.root.after(10, lambda w=w, job=job: self._run(w, job))
        except tk.TclError:
            pass
        self.root.after(60, self._poll)

    def _run(self, w: dict[str, Any], job: Callable[[dict[str, Any]], None]) -> None:
        try:
            job(w)
        except Exception:  # noqa: BLE001 - reported by the smoke
            self.errors.append(traceback.format_exc())
            try:
                w["top"].destroy()
            except tk.TclError:
                pass

    def status_of(self, w: dict[str, Any]) -> str:
        """The live diagnosis line (the label just above the hint label)."""
        texts = [str(lbl.cget("text")) for lbl in w["labels"]]
        return next((x for x in texts if "✓" in x or "✗" in x or x.startswith(("Paste", "Nothing"))), "")

    def wait_line(self, w: dict[str, Any], needle: str, timeout: float = 4.0) -> str:
        end = time.monotonic() + timeout
        line = ""
        while time.monotonic() < end:
            self.root.update()
            line = self.status_of(w)
            if needle in line:
                self.lines.append(line)
                return line
            time.sleep(0.02)
        raise AssertionError(f"live diagnosis never showed {needle!r}; last line: {line!r}")


def menu_labels(menu: tk.Menu) -> list[str]:
    end = menu.index("end")
    return [] if end is None else [menu.entrycget(i, "label") for i in range(end + 1)]


def click(ws: Any, label: str) -> None:
    if ws.next_btn.cget("text").rstrip("…").startswith(label.rstrip("…")):
        ws.next_btn.invoke()
        return
    labels = menu_labels(ws.next_menu)
    hit = next((x for x in labels if x.rstrip("…").startswith(label.rstrip("…"))), None)
    assert hit, f"neither {ws.next_btn.cget('text')!r} nor More has {label!r}: {labels}"
    ws.next_menu.invoke(labels.index(hit))


def type_into(text: tk.Text, value: str) -> None:
    text.delete("1.0", "end")
    text.insert("1.0", value)
    text.edit_modified(True)          # what a real keystroke/paste does
    text.event_generate("<<Modified>>")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwb-paste-box-") as temp:
        home = Path(temp)
        os.environ["LOCALAPPDATA"] = str(home / "appdata")
        project = home / "Paste Box"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n", encoding="utf-8")
        zpath = home / "chatgpt_answer.zip"
        root = tk.Tk()
        root.geometry("1366x800+0+0")
        o = Paster(root)
        boxes: list[tuple] = []
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(wb.messagebox, name, (lambda n: lambda *a, **k: boxes.append((n, a)))(name))
        try:
            app = wb.WorkbenchApp(root)
            app.set_workspace(project, focus_project=True)
            wait_for_project_ready(app, root, project)
            app.open_project_workbench()
            ws = app.workspace_window
            ctl = ws.wc.ctl
            ws.guide_action("design", "design", {"goal": "Offline todo app for desktop and mobile"})
            o.pump(200)
            click(ws, "Copy the charter prompt")
            o.pump(200)

            # 1) charter with model damage: no markers, ```json fence, schema_version 1, no coordination section
            data = json.loads(CHARTER.read_text(encoding="utf-8"))
            data["base_state_revision"] = ctl.state()["state_revision"]
            data["schema_version"] = 1
            del data["coordination"]
            charter_text = "Here is the project charter you asked for:\n\n```json\n" + json.dumps(data, indent=2) + "\n```\n"

            def charter_job(w: dict[str, Any]) -> None:
                o.wait_line(w, "Paste the whole answer")
                type_into(w["text"], charter_text[: len(charter_text) // 2])
                o.wait_line(w, "✗")                        # half a charter: not accepted yet
                type_into(w["text"], charter_text)
                line = o.wait_line(w, "Charter ✓")
                assert "4 AIs · 3 tasks · 2 milestones" in line and "auto-fix" in line, line
                assert not ctl.state()["proposals"], "the live diagnosis imports nothing"
                w["buttons"]["Use this answer"].invoke()
            o.jobs.append(charter_job)
            click(ws, "Paste the charter")
            o.pump(500)
            assert not o.errors, "\n".join(o.errors)
            assert "Imported as PROP-" in ws.status_var.get(), ws.status_var.get()
            click(ws, "Accept")
            o.pump(400)
            st = ctl.state()
            assert len(st["tasks"]) == 3, st["tasks"].keys()

            # 2) task 1 answered as a ZIP (Load ZIP… with the real button; the file dialog is answered)
            click(ws, "Prepare")
            o.pump(200)
            click(ws, "Copy prompt")
            o.pump(200)
            click(ws, "I sent it")
            o.pump(200)
            b = io.BytesIO()
            with zipfile.ZipFile(b, "w") as z:
                z.writestr("todo/src/core/model.py", "TODOS: list[str] = []\n")
                z.writestr("todo/__MACOSX/._model.py", "x")
                z.writestr("todo/AIWB_HANDOFF.json", json.dumps({"summary": "core model", "outcome": "complete"}))
            zpath.write_bytes(b.getvalue())
            import aiwb.ui.paste_box as pb
            pb.filedialog.askopenfilename = lambda **k: str(zpath)

            def zip_job(w: dict[str, Any]) -> None:
                w["buttons"]["Load ZIP…"].invoke()
                line = o.wait_line(w, "ZIP ✓")
                assert "1 file from chatgpt_answer.zip" in line, line
                assert 'path="src/core/model.py"' in w["text"].get("1.0", "end"), "the ZIP's files are shown in the box"
                w["buttons"]["Use this answer"].invoke()
            o.jobs.append(zip_job)
            click(ws, "Paste the answer")
            o.pump(500)
            assert not o.errors, "\n".join(o.errors)
            assert "1 file(s) read" in ws.status_var.get() or "linked" in ws.status_var.get(), ws.status_var.get()
            click(ws, "Accept")
            o.pump(500)
            f1 = project / "src/core/model.py"
            assert f1.is_file() and "TODOS" in f1.read_text(encoding="utf-8"), "ZIP file on disk"

            # 3) the next task answered as Markdown code blocks without any manifest; first a cut-off version
            rev = next(s for s in ws.wc.guide_steps() if s["key"].startswith("task:"))
            assert any(a["id"] == "approve" for a in rev["actions"]), rev     # task 1 waits for the user's review
            ws.guide_action(rev["key"], "approve", {"note": ""})
            o.pump(200)
            ws.guide_action(rev["key"], "validation_passed", {"run_id": ""})
            o.pump(200)
            while any(s["key"] == rev["key"] for s in ws.wc.guide_steps()):    # e.g. close / done steps, if any
                st_ = next(s for s in ws.wc.guide_steps() if s["key"] == rev["key"])
                prim = next(a for a in st_["actions"] if a["primary"])
                assert prim["id"] not in ("approve", "validation_passed"), st_
                ws.guide_action(rev["key"], prim["id"], {n: "" for n in prim["needs"]})
                o.pump(200)
            nxt = next(s for s in ws.wc.guide_steps() if s["key"].startswith("task:")
                       and any(a["id"] == "prepare" for a in s["actions"]))
            ws.guide_action(nxt["key"], "prepare", {})
            o.pump(200)
            h = next(h for h in ctl.state()["handoffs"].values() if h["status"] in ("prepared", "prompt_exported"))
            task = ctl.state()["tasks"][h["task_id"]]
            base = task["scope"]["include"][0].rstrip("*").rstrip("/")
            click(ws, "Copy prompt")
            o.pump(200)
            click(ws, "I sent it")
            o.pump(200)
            md = f"Done! Here are the files.\n\n**{base}/app.py**\n```python\nprint('todo')\n```\n"

            def md_job(w: dict[str, Any]) -> None:
                type_into(w["text"], md[:-5])
                o.wait_line(w, "Cut off ✗")
                type_into(w["text"], md)
                line = o.wait_line(w, "Files ✓")
                assert "1 file · Markdown code blocks" in line, line
                w["buttons"]["Use this answer"].invoke()
            o.jobs.append(md_job)
            click(ws, "Paste the answer")
            o.pump(500)
            assert not o.errors, "\n".join(o.errors)
            click(ws, "Accept")
            o.pump(500)
            f2 = project / base / "app.py"
            assert f2.is_file() and "todo" in f2.read_text(encoding="utf-8"), f"Markdown file on disk: {f2}"
            assert not o.errors, "UI callback errors:\n" + "\n".join(o.errors)
            assert not [x for x in boxes if x[0] == "showerror"], boxes
        finally:
            root.destroy()
    print("Paste box (5.10.0): live diagnosis (" + " | ".join(o.lines[:4]) + ") · Load ZIP… · Markdown without manifest "
          "→ files on disk: PASS")


if __name__ == "__main__":
    main()
