"""Quick — one AI chat (roadmap 5.14.0): the window.

One window replaces the classic 1.x Prompt and AI Response pages:

1. **The job** — describe what the AI should make or change, pick the answer format and (optionally) the files it
   must see → *Copy the prompt*.
2. **The answer** — the same paste panel as Home (live diagnosis, *Load ZIP…*) → *Check the answer*.
3. **The files** — each file new / changed / unchanged with its diff → *Apply* (one backup) · *Restore last apply*.
   A cut-off answer offers *Copy the continue prompt*.

*Make it a multi-AI project…* turns the folder into a Guided project later (files untouched).
The engine is :mod:`aiwb.v2.quick`; this module only draws and calls it. Every action returns a value for tests.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

from aiwb.v2 import quick

from . import layout as ui_layout

TITLE = "Quick — one AI chat"
STATUS_TEXT = {"new": "New", "changed": "Changed", "same": "Unchanged"}


def diagnose(text: str, state: Any = None) -> Any:
    """The paste panel's live check in Quick mode: the shared preview without the multi-AI parts.

    A Quick answer has no handoff, so the "no AIWB_HANDOFF manifest" warning is dropped, and an answer without files
    says what Quick expects (charters and context requests belong to Guided projects).
    """
    from ..intake.preview import preview
    p = preview(text, None)
    p.warnings = [w for w in p.warnings if "AIWB_HANDOFF" not in w]
    if p.kind in ("charter", "proposal", "context_request"):
        p.ok = False
        p.line = "Not a Quick answer ✗ · this is for a multi-AI project — Quick reads file answers only."
    elif p.kind == "unknown":
        p.line = "No file found yet ✗ · paste the chat's whole answer (its files), or load its ZIP."
    return p


class QuickWindow:
    """``QuickWindow(parent, root_folder, clipboard=, status=, on_convert=)``; ``win`` is the Toplevel."""

    def __init__(self, parent: tk.Misc, root: Path, *, clipboard: Callable[[str], None] | None = None,
                 status: Callable[[str], None] | None = None,
                 on_convert: Callable[[Path], Any] | None = None) -> None:
        self.root = Path(root)
        self._clip = clipboard or (lambda _t: None)
        self._status = status or (lambda _m: None)
        self.on_convert = on_convert
        self.answer: dict[str, Any] | None = None
        self.items: list[dict[str, Any]] = []
        self.last_prompt = ""
        self.win = tk.Toplevel(parent)
        self.win.title(f"{TITLE} — {self.root.name}")
        try:
            self.win.transient(parent.winfo_toplevel())
        except tk.TclError:
            pass
        page = ui_layout.ScrollPage(self.win)
        page.pack(fill="both", expand=True)
        body = page.body
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text=TITLE, style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 0))
        ttk.Label(body, text=f"Folder: {self.root}  ·  one chat, no team. Files are written only after you apply, "
                             "with a backup you can restore.", style="Hint.TLabel", wraplength=860,
                  justify="left").grid(row=1, column=0, sticky="w", padx=14, pady=(2, 8))
        self._make_job(body)
        self._make_answer(body)
        self._make_files(body)
        foot = ttk.Frame(body)
        foot.grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 12))
        self.convert_btn = ttk.Button(foot, text="Make it a multi-AI project…", command=self.ask_convert)
        self.convert_btn.pack(side="left")
        ttk.Button(foot, text="Close", command=self.win.destroy).pack(side="right")
        self.message_var = tk.StringVar(value="")
        ttk.Label(foot, textvariable=self.message_var, style="Hint.TLabel", wraplength=600,
                  justify="left").pack(side="left", padx=(12, 0))
        self._refresh_restore()
        ui_layout.place_dialog(self.win, 940, 820, parent)

    # ------------------------------------------------------------------ layout
    def _make_job(self, body: ttk.Frame) -> None:
        card = ttk.Frame(body, style="Card.TFrame", padding=(14, 10))
        card.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 9))
        ttk.Label(card, text="1  The job", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(card, text="What should the AI make or change? One or two sentences are enough.",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(2, 4))
        self.task_box = tk.Text(card, height=3, wrap="word", undo=True)
        self.task_box.pack(fill="x")
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Answer format", style="Card.TLabel").pack(side="left")
        labels = [label for _k, label in quick.FORMATS]
        self.format_var = tk.StringVar(value=labels[0])
        ttk.Combobox(row, textvariable=self.format_var, values=labels, state="readonly", width=30).pack(
            side="left", padx=(6, 12))
        ttk.Label(row, text="Files it must see (optional)", style="Card.TLabel").pack(side="left")
        self.include_var = tk.StringVar(value="")
        self.include_btn = ttk.Menubutton(row, text="Choose… (0)")
        self.include_menu = tk.Menu(self.include_btn, tearoff=False, postcommand=self._fill_include_menu)
        self.include_btn.configure(menu=self.include_menu)
        self.include_btn.pack(side="left", padx=(6, 0))
        self.included: list[str] = []
        self.prompt_btn = ttk.Button(row, text="Copy the prompt", style="Primary.TButton", command=self.copy_prompt)
        self.prompt_btn.pack(side="right")

    def _make_answer(self, body: ttk.Frame) -> None:
        from .paste_box import PastePanel
        card = ttk.Frame(body, style="Card.TFrame", padding=(14, 10))
        card.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 9))
        ttk.Label(card, text="2  The answer", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(card, text="Paste the chat's whole answer (use the Copy button of its code block), or load the ZIP "
                             "it gave you.", style="CardMuted.TLabel", wraplength=860).pack(anchor="w", pady=(2, 4))
        self.paste = PastePanel(card, on_use=self.use_answer, primary_text="Check the answer", height=6,
                                wraplength=860, style="Card.TFrame", diagnose=diagnose)
        self.paste.pack(fill="x")

    def _make_files(self, body: ttk.Frame) -> None:
        card = ttk.Frame(body, style="Card.TFrame", padding=(14, 10))
        card.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 9))
        ttk.Label(card, text="3  The files", style="CardTitle.TLabel").pack(anchor="w")
        self.files_var = tk.StringVar(value="Check an answer to see its files here.")
        ttk.Label(card, textvariable=self.files_var, style="CardMuted.TLabel", wraplength=860,
                  justify="left").pack(anchor="w", pady=(2, 4))
        pair = ttk.Frame(card, style="Card.TFrame")
        pair.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(pair, columns=("status", "lines"), height=5, selectmode="browse")
        self.tree.heading("#0", text="File")
        self.tree.heading("status", text="State")
        self.tree.heading("lines", text="Lines")
        self.tree.column("#0", width=300)
        self.tree.column("status", width=90, anchor="w")
        self.tree.column("lines", width=60, anchor="e")
        self.tree.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.show_diff())
        self.diff = tk.Text(pair, height=8, wrap="none", font=("Consolas", 9))
        self.diff.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.diff.tag_configure("add", foreground="#2e7d32")
        self.diff.tag_configure("del", foreground="#c62828")
        self.diff.configure(state="disabled")
        bar = ttk.Frame(card, style="Card.TFrame")
        bar.pack(fill="x", pady=(8, 0))
        self.apply_btn = ttk.Button(bar, text="Apply", style="Primary.TButton", command=self.apply_now,
                                    state="disabled")
        self.apply_btn.pack(side="left")
        self.restore_btn = ttk.Button(bar, text="Restore last apply", command=self.restore_now)
        self.restore_btn.pack(side="left", padx=(6, 0))
        self.continue_btn = ttk.Button(bar, text="Copy the continue prompt", command=self.copy_continue)

    # ------------------------------------------------------------------ helpers
    def fmt(self) -> str:
        label = self.format_var.get()
        return next((k for k, lab in quick.FORMATS if lab == label), "aiwb")

    def set_format(self, key: str) -> None:
        self.format_var.set(dict(quick.FORMATS).get(key, quick.FORMATS[0][1]))

    def task(self) -> str:
        return self.task_box.get("1.0", "end-1c").strip()

    def set_task(self, text: str) -> None:
        self.task_box.delete("1.0", "end")
        self.task_box.insert("1.0", text)

    def _say(self, message: str) -> str:
        self.message_var.set(message)
        self._status(message)
        return message

    def _fill_include_menu(self) -> None:
        self.include_menu.delete(0, "end")
        files = quick.inventory(self.root)
        if not files:
            self.include_menu.add_command(label="(the folder is empty)", state="disabled")
            return
        for rel, _size in files[:60]:
            v = tk.BooleanVar(value=rel in self.included)
            self.include_menu.add_checkbutton(label=rel, variable=v, command=lambda r=rel: self.toggle_include(r))
        if len(files) > 60:
            self.include_menu.add_command(label=f"… {len(files) - 60} more (type their paths in the job)",
                                          state="disabled")

    def toggle_include(self, rel: str) -> list[str]:
        if rel in self.included:
            self.included.remove(rel)
        else:
            self.included.append(rel)
        self.include_btn.configure(text=f"Choose… ({len(self.included)})")
        return self.included

    def _refresh_restore(self) -> None:
        last = quick.last_apply(self.root)
        self.restore_btn.configure(state="normal" if last else "disabled")

    # ------------------------------------------------------------------ actions
    def copy_prompt(self) -> str:
        """Build the prompt for the job and put it on the clipboard. Returns it ('' when refused)."""
        try:
            prompt = quick.build_prompt(self.root, self.task(), self.fmt(), self.included)
        except quick.QuickError as exc:
            self._say(str(exc))
            return ""
        self.last_prompt = prompt
        self._clip(prompt)
        self._say("Prompt copied. Paste it into a new chat, send it, then paste the whole answer in step 2.")
        return prompt

    def use_answer(self, text: str = "") -> dict[str, Any]:
        """Read the pasted answer (PastePanel's primary button) and list its files."""
        text = text if text else self.paste.text()
        self.answer = a = quick.read_answer(text)
        zip_name = getattr(self.paste, "zip_name", "")
        if zip_name and a["files"]:  # the ZIP was turned into file blocks by the paste panel: name its real source
            a["label"] = f"GPT ZIP · {zip_name}"
        self.items = quick.plan(self.root, a["files"]) if a["files"] else []
        self.tree.delete(*self.tree.get_children())
        for i in self.items:
            self.tree.insert("", "end", iid=i["path"], text=i["path"],
                             values=(STATUS_TEXT[i["status"]], i["lines"]))
        lines = []
        if self.items:
            lines.append(f"{len(self.items)} file{'s' if len(self.items) != 1 else ''} ({a['label']}): "
                         f"{quick.summary(self.items)}.")
        if a["fixes"]:
            lines.append("Fixed automatically: " + "; ".join(a["fixes"][:4]) + ".")
        if a["problems"]:
            lines.append("Problems: " + "; ".join(a["problems"][:4]) + ".")
        if a["truncated"]:
            lines.append("The answer was cut off — copy the continue prompt into the same chat; the files that "
                         "arrived complete can be applied now.")
        self.files_var.set("\n".join(lines))
        todo = [i for i in self.items if i["status"] != "same"]
        self.apply_btn.configure(state="normal" if todo else "disabled",
                                 text=f"Apply {len(todo)} file{'s' if len(todo) != 1 else ''}" if todo else "Apply")
        if a["truncated"] and a["continue_prompt"]:
            if not self.continue_btn.winfo_manager():
                self.continue_btn.pack(side="left", padx=(6, 0))
        else:
            self.continue_btn.pack_forget()
        if self.items:
            self.tree.selection_set(self.items[0]["path"])
            self.show_diff(self.items[0]["path"])
        self._say("Check the files, then apply." if todo else (lines[-1] if lines else "No file found."))
        return a

    def show_diff(self, path: str = "") -> str:
        sel = path or (self.tree.selection()[0] if self.tree.selection() else "")
        item = next((i for i in self.items if i["path"] == sel), None)
        text = "" if item is None else (item["diff"] or "(the file is already exactly like this)")
        self.diff.configure(state="normal")
        self.diff.delete("1.0", "end")
        for line in text.splitlines(True):
            tag = "add" if line.startswith("+") and not line.startswith("+++") else (
                "del" if line.startswith("-") and not line.startswith("---") else "")
            self.diff.insert("end", line, tag)
        self.diff.configure(state="disabled")
        return text

    def apply_now(self) -> dict[str, Any] | None:
        """Write the new and changed files (after one backup)."""
        try:
            rec = quick.apply(self.root, self.items, task=self.task())
        except quick.QuickError as exc:
            self._say(str(exc))
            return None
        self.items = quick.plan(self.root, [{"path": i["path"], "content": i["content"]} for i in self.items])
        for i in self.items:
            if self.tree.exists(i["path"]):
                self.tree.item(i["path"], values=(STATUS_TEXT[i["status"]], i["lines"]))
        self.apply_btn.configure(state="disabled", text="Apply")
        self._refresh_restore()
        self._say(f"Applied {len(rec['written'])} file(s) — backup {rec['apply_id']}. Restore last apply undoes it.")
        return rec

    def restore_now(self) -> dict[str, Any] | None:
        try:
            out = quick.restore(self.root)
        except quick.QuickError as exc:
            self._say(str(exc))
            return None
        self._refresh_restore()
        msg = f"Restored {len(out['restored'])} file(s)."
        if out["kept"]:
            msg += " Kept because you edited them after the apply: " + ", ".join(out["kept"]) + "."
        if self.items:
            self.use_answer(self.paste.text())
        self._say(msg)
        return out

    def copy_continue(self) -> str:
        text = (self.answer or {}).get("continue_prompt", "")
        if text:
            self._clip(text)
            self._say("Continue prompt copied: paste it into the same chat, then paste the rest of the answer.")
        return text

    def ask_convert(self) -> dict[str, Any] | None:
        """*Make it a multi-AI project…*: the team table, then :func:`aiwb.v2.quick.to_guided`."""
        from aiwb.v2 import team_setup

        from .team_table import TeamTable
        dlg = tk.Toplevel(self.win)
        dlg.title("Make it a multi-AI project")
        outer = ttk.Frame(dlg, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="The goal of the project", style="SectionTitle.TLabel").pack(anchor="w")
        goal = tk.Text(outer, height=3, wrap="word")
        goal.pack(fill="x", pady=(4, 8))
        goal.insert("1.0", self.task() or (quick.state(self.root)["rounds"][-1]["task"]
                                           if quick.state(self.root)["rounds"] else ""))
        ttk.Label(outer, text="Your AI team (your files stay as they are)", style="CardTitle.TLabel").pack(anchor="w")
        table = TeamTable(outer, team_setup.default_rows(2), show_note=False)
        table.pack(fill="x")
        err = tk.StringVar()
        ttk.Label(outer, textvariable=err, style="Danger.TLabel", wraplength=640).pack(anchor="w", pady=(6, 0))
        result: dict[str, Any] = {}

        def ok() -> dict[str, Any] | None:
            out = self.convert(goal.get("1.0", "end-1c"), table.rows(), err=err)
            if out is not None:
                result.update(out)
                dlg.destroy()
            return out
        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="Cancel", command=dlg.destroy).pack(side="right")
        ttk.Button(bar, text="Make the project", style="Primary.TButton", command=ok).pack(side="right", padx=(0, 7))
        ui_layout.place_dialog(dlg, 720, 480, self.win)
        self.convert_dialog = {"win": dlg, "goal": goal, "table": table, "ok": ok, "error": err}
        return self.convert_dialog

    def convert(self, goal: str, rows: list[dict[str, Any]], *, err: tk.StringVar | None = None) -> dict[str, Any] | None:
        try:
            out = quick.to_guided(self.root, goal, rows)
        except Exception as exc:  # noqa: BLE001 — shown inline, never a traceback
            (err.set if err is not None else self._say)(str(exc))
            return None
        self._say(f"{self.root.name} is now a multi-AI project with {out['workers']} AI(s). Its next step is on Home.")
        if self.on_convert is not None:
            self.on_convert(self.root)
        return out
