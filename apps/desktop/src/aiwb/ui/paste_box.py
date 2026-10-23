"""The one paste box for a whole model answer (roadmap 5.10.0).

Before 5.10.0 two copies of a bare ``Text`` + "Use this answer" window existed (the Workbench shell and the Mission
Map menu) and neither said what the pasted text was until it had been imported. This one:

* shows a **live diagnosis** below the text while the user pastes or types (debounced; read-only —
  :func:`aiwb.intake.preview.preview`): kind of answer, counts, automatic fixes, problems;
* has **Load ZIP…** for a GPT ZIP: the archive is read with the safe limits of :mod:`aiwb.intake.answer_files` and
  turned into AIWB file blocks in the box, so the user sees what will be staged;
* keeps the old contract: modal, returns the text (``""`` when closed), the primary button is "Use this answer".

``ask_answer(parent, title, state=...)`` is the whole API; ``PasteBox`` is exposed for tests.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable

from . import layout as ui_layout

DEBOUNCE_MS = 250


class PasteBox:
    def __init__(self, parent: tk.Misc, title: str, *, state: dict[str, Any] | None = None,
                 primary_style: str = "Accent.TButton", modal: bool = True,
                 ask_zip: Callable[[], str] | None = None) -> None:
        self.state = state
        self.result: str = ""
        self.preview: Any = None
        self.zip_name = ""
        self._after: str | None = None
        self._ask_zip = ask_zip
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.transient(parent)
        bar = ttk.Frame(self.top)
        bar.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        self.ok_btn = ttk.Button(bar, text="Use this answer", style=primary_style, command=self.ok)
        self.ok_btn.pack(side="right")
        self.zip_btn = ttk.Button(bar, text="Load ZIP…", command=self.load_zip)
        self.zip_btn.pack(side="left")
        self.clear_btn = ttk.Button(bar, text="Clear", command=self.clear)
        self.clear_btn.pack(side="left", padx=(6, 0))
        self.details_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.details = ttk.Label(self.top, textvariable=self.details_var, style="Hint.TLabel", justify="left",
                                 wraplength=780)
        self.details.pack(side="bottom", fill="x", padx=10, pady=(0, 4))
        self.status = ttk.Label(self.top, textvariable=self.status_var, justify="left", wraplength=780)
        self.status.pack(side="bottom", fill="x", padx=10, pady=(0, 2))
        self.box = tk.Text(self.top, width=90, height=20, wrap="word", undo=True)
        self.box.pack(fill="both", expand=True, padx=8, pady=8)
        self.box.bind("<<Modified>>", self._modified)
        self.top.protocol("WM_DELETE_WINDOW", self.cancel)
        self.top.bind("<Control-Return>", lambda _e: self.ok())
        ui_layout.place_dialog(self.top, 820, 560, parent)
        self.refresh()
        self.box.focus_set()
        if modal:
            try:
                self.top.grab_set()
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ live diagnosis
    def _modified(self, _event: Any = None) -> None:
        if not self.box.edit_modified():
            return
        self.box.edit_modified(False)
        if self._after is not None:
            try:
                self.top.after_cancel(self._after)
            except tk.TclError:
                pass
        self._after = self.top.after(DEBOUNCE_MS, self.refresh)

    def text(self) -> str:
        return self.box.get("1.0", "end-1c")

    def refresh(self) -> Any:
        """Diagnose the current text now (also called by the debounce timer)."""
        from ..intake.preview import preview
        self._after = None
        self.preview = preview(self.text(), self.state)
        self._show(self.preview)
        return self.preview

    def _show(self, p: Any) -> None:
        self.status_var.set(p.line)
        self.details_var.set(p.details())
        try:
            colour = "#2e7d32" if p.ok else ("#b26a00" if p.kind in ("empty", "unknown", "truncated") else "#c62828")
            self.status.configure(foreground=colour)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ actions
    def load_zip(self, path: str | None = None) -> Any:
        """Read a ZIP answer (``path`` for tests; else a file dialog) and put its files into the box."""
        from ..intake.preview import preview_zip
        if path is None:
            path = self._ask_zip() if self._ask_zip else filedialog.askopenfilename(
                parent=self.top, title="Load the ZIP the chat gave you",
                filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")])
        if not path:
            return None
        p = Path(path)
        try:
            from ..intake.answer_files import MAX_ZIP
            if p.stat().st_size > MAX_ZIP:
                raise ValueError(f"the ZIP is larger than {MAX_ZIP // (1024 * 1024)} MB")
            data = p.read_bytes()
        except (OSError, ValueError) as exc:
            from ..intake.preview import Preview
            self.preview = Preview("unknown", False, f"ZIP ✗ · {exc}", problems=[str(exc)])
            self._show(self.preview)
            return self.preview
        text, pv = preview_zip(data, p.name)
        if text:
            self.zip_name = p.name
            self.box.delete("1.0", "end")
            self.box.insert("1.0", text)
            self.box.edit_modified(False)
        self.preview = pv
        self._show(pv)
        return pv

    def clear(self) -> None:
        self.box.delete("1.0", "end")
        self.zip_name = ""
        self.refresh()

    def ok(self) -> None:
        self.result = self.text()
        self.top.destroy()

    def cancel(self) -> None:
        self.result = ""
        self.top.destroy()


def ask_answer(parent: tk.Misc, title: str, *, state: dict[str, Any] | None = None,
               primary_style: str = "Accent.TButton") -> str:
    """Open the paste box, wait for it, return the answer text (``""`` when the user closed it)."""
    box = PasteBox(parent, title, state=state, primary_style=primary_style)
    box.top.wait_window()
    return box.result
