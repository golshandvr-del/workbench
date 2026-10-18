"""Tk window for the Response Inbox (roadmap 1.16.0/1.16.1).

Lists every captured raw response (newest first) with its status, attempt and
last parse result. Actions never write project files:

* *Reparse*                — run the pipeline again on the stored raw bytes
* *Load into response box* — hand the raw text back to the normal preview flow
* *Copy repair prompt*     — focused prompt for a partial/failed response
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from .errors import explain
from .pipeline import ImportPipeline, PipelineOutcome
from .salvage import SalvageResult, repair_prompt


class InboxWindow:
    def __init__(self, parent: tk.Misc, pipeline: ImportPipeline, *,
                 load_text: Callable[[str], None], task_text: Callable[[], str] = lambda: "",
                 clipboard: Callable[[str], None] | None = None) -> None:
        self.pipe = pipeline
        self.load_text = load_text
        self.task_text = task_text
        self.clipboard = clipboard
        self.last: dict[str, PipelineOutcome] = {}
        self.win = tk.Toplevel(parent)
        self.win.title("Response Inbox — AI Workbench")
        self.win.geometry("1000x620")
        ttk.Label(self.win, wraplength=960, text=(
            "Every pasted/loaded response is stored here byte-for-byte BEFORE parsing (in .workbench/inbox, "
            "never committed). A parser failure never loses the answer: reparse it later, or ask the model only "
            "for the missing files. Nothing here writes project files.")).pack(anchor="w", padx=8, pady=6)
        cols = ("captured", "status", "source", "attempt", "size")
        self.tree = ttk.Treeview(self.win, columns=cols, show="tree headings", height=10)
        self.tree.heading("#0", text="Response ID")
        for c, w in zip(cols, (150, 80, 90, 230, 80)):
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w, anchor="w")
        self.tree.column("#0", width=260)
        self.tree.pack(fill="x", padx=8)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())
        bar = ttk.Frame(self.win)
        bar.pack(fill="x", padx=8, pady=6)
        self.btn_reparse = ttk.Button(bar, text="Reparse", command=self.do_reparse)
        self.btn_reparse.pack(side="left")
        self.btn_load = ttk.Button(bar, text="Load into response box", command=self.do_load)
        self.btn_load.pack(side="left", padx=6)
        self.btn_repair = ttk.Button(bar, text="Copy repair prompt", command=self.do_repair)
        self.btn_repair.pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left", padx=6)
        ttk.Button(bar, text="Close", command=self.close).pack(side="right")
        self.detail = tk.Text(self.win, wrap="word", height=16)
        self.detail.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.refresh()

    # -- helpers
    def selected_id(self) -> str:
        sel = self.tree.selection()
        return sel[0] if sel else ""

    def refresh(self) -> None:
        keep = self.selected_id()
        self.tree.delete(*self.tree.get_children())
        for r in self.pipe.store.list():
            self.tree.insert("", "end", iid=r.response_id, text=r.response_id,
                             values=(r.captured_at.replace("T", " ")[:19], r.status, r.source,
                                     r.declared_attempt_id or r.attempt_id or "—", f"{r.size:,}"))
        if keep and self.tree.exists(keep):
            self.tree.selection_set(keep)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])
        self._show_selected()

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def _show_selected(self) -> None:
        rid = self.selected_id()
        rec = self.pipe.store.get(rid) if rid else None
        if rec is None:
            self._set_detail("No responses captured yet.")
            return
        lines = [f"Response {rec.response_id}", f"SHA-256 {rec.sha256}", f"Status: {rec.status}",
                 f"Attempt: {rec.declared_attempt_id or rec.attempt_id or 'none'}", ""]
        last = rec.parse_results[-1] if rec.parse_results else None
        if last:
            lines.append("Last parse (" + str(last.get("at", "")) + "): " + str(last.get("status")))
            lines.append("Stages: " + ", ".join(f"{k}={v}" for k, v in (last.get("stages") or {}).items()))
            if last.get("format"):
                lines.append("Format: " + str(last["format"]))
            if last.get("salvaged"):
                lines.append("Recovered files: " + ", ".join(last["salvaged"]))
            for issue in last.get("issues", []):
                lines += ["", explain(issue)]
        else:
            lines.append("Not parsed yet — press Reparse.")
        self._set_detail("\n".join(lines))

    # -- actions
    def do_reparse(self) -> PipelineOutcome | None:
        rid = self.selected_id()
        if not rid:
            return None
        out = self.pipe.reparse(rid)
        self.last[rid] = out
        self.refresh()
        return out

    def do_load(self) -> None:
        rid = self.selected_id()
        if rid:
            self.load_text(self.pipe.store.read_text(rid))
            self.close()

    def repair_text(self) -> str:
        rid = self.selected_id()
        if not rid:
            return ""
        out = self.last.get(rid) or self.pipe.reparse(rid)
        self.last[rid] = out
        res = out.salvage or SalvageResult()
        if not (res.broken or res.missing or res.duplicates or res.complete):
            issue = out.issues[0] if out.issues else None
            reason = explain(issue) if issue else "The response could not be imported."
            aid = out.response.declared_attempt_id or out.response.attempt_id
            head = f"AIWB_ATTEMPT_ID: {aid}\n" if aid else ""
            return (head + "AI Workbench could not import your previous answer.\n\n" + reason +
                    "\n\nResend the COMPLETE answer in the exact format required by the original prompt. "
                    "Do not claim that anything was run or tested.")
        return repair_prompt(res, attempt_id=out.response.declared_attempt_id or out.response.attempt_id,
                             task=self.task_text())

    def do_repair(self) -> None:
        text = self.repair_text()
        if not text:
            return
        if self.clipboard:
            self.clipboard(text)
        else:
            self.win.clipboard_clear()
            self.win.clipboard_append(text)
        try:
            messagebox.showinfo("Repair prompt copied", "Paste it into the same chat as the original prompt.", parent=self.win)
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
