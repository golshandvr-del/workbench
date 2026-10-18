"""Tk window for an AIWB_CONTEXT_REQUEST (roadmap 1.16.3).

Shows what the model asked for, the status of each item, and prepares an inline
listing (copied to the clipboard) or a ZIP context pack. Workbench never sends
anything itself: the user pastes/attaches the result in the same chat.
Sensitive files are refused unless the user explicitly allows that one file.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from aiwb import context_request as cr

STATUS_TEXT = {
    "ready": "ready",
    "stale": "ready (changed since model saw it)",
    "missing": "missing",
    "refused_unsafe": "refused: unsafe path",
    "refused_sensitive": "refused: sensitive",
    "invalid_range": "invalid range",
    "symbol_not_found": "symbol not found",
    "too_large": "too large",
}


class ContextRequestWindow:
    def __init__(self, parent: tk.Misc, request: cr.ContextRequest, project_root: Path, *,
                 path_problem: Callable[[str], str], is_sensitive: Callable[[str], bool],
                 attempt_line: Callable[[], str], clipboard: Callable[[str], None],
                 on_prepared: Callable[[str, list], None] | None = None) -> None:
        self.request = request
        self.root_dir = project_root
        self.path_problem = path_problem
        self.is_sensitive = is_sensitive
        self.attempt_line = attempt_line
        self.clipboard = clipboard
        self.on_prepared = on_prepared
        self.allow_sensitive: set[str] = set()
        self.items: list[cr.ResolvedItem] = []
        self.last_inline = ""

        self.win = tk.Toplevel(parent)
        self.win.title("Context request — AI Workbench")
        self.win.geometry("1000x640")
        ttk.Label(self.win, wraplength=960, text=(
            "The model asked for more context. Review each item. Workbench only PREPARES the context; "
            "you paste or attach it in the same chat. Sensitive files are never included unless you allow them one by one."
        )).pack(anchor="w", padx=12, pady=(12, 4))
        if request.reason:
            ttk.Label(self.win, wraplength=960, text="Reason: " + request.reason).pack(anchor="w", padx=12)
        cols = ("path", "mode", "status", "lines", "required", "reason")
        self.tree = ttk.Treeview(self.win, columns=cols, show="headings", height=12)
        for c, w in zip(cols, (300, 80, 220, 90, 70, 220)):
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=12, pady=6)
        if request.questions:
            ttk.Label(self.win, text="Questions from the model:").pack(anchor="w", padx=12)
            self.questions = tk.Text(self.win, height=4, wrap="word")
            self.questions.insert("1.0", "\n".join("- " + q for q in request.questions))
            self.questions.configure(state="disabled")
            self.questions.pack(fill="x", padx=12)
        self.summary = tk.StringVar()
        ttk.Label(self.win, textvariable=self.summary).pack(anchor="w", padx=12, pady=4)
        bar = ttk.Frame(self.win, padding=10)
        bar.pack(fill="x")
        ttk.Button(bar, text="Copy inline context", style="Primary.TButton", command=self.do_inline).pack(side="left")
        ttk.Button(bar, text="Save ZIP context pack…", command=self.do_zip).pack(side="left", padx=6)
        ttk.Button(bar, text="Allow selected sensitive file…", command=self.do_allow_sensitive).pack(side="left", padx=6)
        ttk.Button(bar, text="Close", command=self.close).pack(side="right")
        self.refresh()

    def refresh(self) -> None:
        self.items = cr.resolve(self.request, self.root_dir, path_problem=self.path_problem,
                                is_sensitive=self.is_sensitive, allow_sensitive=self.allow_sensitive)
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.items):
            self.tree.insert("", "end", iid=str(i), values=(
                r.path, r.mode, STATUS_TEXT.get(r.status, r.status) + (f" — {r.detail}" if r.detail and r.status != "ready" else ""),
                r.lines, "yes" if r.required else "no", r.reason))
        ready = sum(1 for r in self.items if r.deliverable)
        missing_req = [r.path for r in self.items if r.required and not r.deliverable]
        self.summary.set(f"{ready}/{len(self.items)} item(s) ready · suggested delivery: {cr.suggest_delivery(self.items)}"
                         + (f" · required but unavailable: {', '.join(missing_req)}" if missing_req else ""))

    def selected(self) -> cr.ResolvedItem | None:
        sel = self.tree.selection()
        return self.items[int(sel[0])] if sel else None

    def do_allow_sensitive(self) -> None:
        item = self.selected()
        if item is None or item.status != "refused_sensitive":
            messagebox.showinfo("Allow sensitive file", "Select an item marked 'refused: sensitive' first.", parent=self.win)
            return
        if messagebox.askyesno("Include sensitive file?", (
                f"'{item.path}' looks like it may contain secrets (keys, tokens, passwords).\n\n"
                "Include it in the prepared context anyway? Only do this if you are sure it contains no secrets."),
                parent=self.win):
            self.allow_sensitive.add(item.path)
            self.refresh()

    def build_inline(self) -> str:
        self.last_inline = cr.pack_inline(self.request, self.items, attempt_line=self.attempt_line())
        return self.last_inline

    def do_inline(self) -> str:
        text = self.build_inline()
        self.clipboard(text)
        if self.on_prepared:
            self.on_prepared("inline:clipboard", self.items)
        return text

    def do_zip(self, path: str | None = None) -> Path | None:
        if path is None:
            path = filedialog.asksaveasfilename(parent=self.win, title="Save context pack", defaultextension=".zip",
                                                initialfile="aiwb-context-pack.zip", filetypes=[("ZIP", "*.zip")])
        if not path:
            return None
        target = Path(path)
        target.write_bytes(cr.pack_zip(self.request, self.items, self.root_dir))
        if self.on_prepared:
            self.on_prepared("zip:" + target.name, self.items)
        return target

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
