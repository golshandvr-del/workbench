"""The one paste box for a whole model answer (roadmap 5.10.0).

Before 5.10.0 two copies of a bare ``Text`` + "Use this answer" window existed (the Workbench shell and the Mission
Map menu) and neither said what the pasted text was until it had been imported. This one:

* shows a **live diagnosis** below the text while the user pastes or types (debounced; read-only —
  :func:`aiwb.intake.preview.preview`): kind of answer, counts, automatic fixes, problems;
* has **Load ZIP…** for a GPT ZIP: the archive is read with the safe limits of :mod:`aiwb.intake.answer_files` and
  turned into AIWB file blocks in the box, so the user sees what will be staged;
* keeps the old contract: modal, returns the text (``""`` when closed), the primary button is "Use this answer".

``ask_answer(parent, title, state=...)`` is the popup API; ``PastePanel`` (5.11.0) is the same paste area as a frame
for Home's Next-step card; ``PasteBox`` is exposed for tests.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable

from . import layout as ui_layout

DEBOUNCE_MS = 250


class PastePanel(ttk.Frame):
    """The paste area as an embeddable frame (5.11.0): Text + live diagnosis + Load ZIP… / Clear / primary button.

    Home's Next-step card shows it inside the page (no popup); :class:`PasteBox` wraps one in a modal window.
    ``on_use(text)`` runs when the primary button is pressed (or Ctrl+Enter); ``state`` may be a callable so the
    diagnosis always checks against the current project revision.
    """

    def __init__(self, master: tk.Misc, *, state: Any = None, on_use: Callable[[str], Any] | None = None,
                 primary_text: str = "Use this answer", primary_style: str = "Accent.TButton",
                 ask_zip: Callable[[], str] | None = None, height: int = 20, width: int = 90,
                 wraplength: int = 780, diagnose: Callable[..., Any] | None = None, **kw: Any) -> None:
        super().__init__(master, **kw)
        self._state = state
        self._diagnose = diagnose  # 5.14.0: Quick mode passes its own (no handoff/manifest warnings)
        self.on_use = on_use
        self.preview: Any = None
        self.zip_name = ""
        self.zip_text = ""
        self._after: str | None = None
        self._ask_zip = ask_zip
        bar = ttk.Frame(self, style=kw.get("style", "TFrame"))
        bar.pack(side="bottom", fill="x", pady=(0, 0))
        self.ok_btn = ttk.Button(bar, text=primary_text, style=primary_style, command=self.use)
        self.ok_btn.pack(side="right")
        self.zip_btn = ttk.Button(bar, text="Load ZIP…", command=self.load_zip)
        self.zip_btn.pack(side="left")
        self.clear_btn = ttk.Button(bar, text="Clear", command=self.clear)
        self.clear_btn.pack(side="left", padx=(6, 0))
        self.details_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.details = ttk.Label(self, textvariable=self.details_var, style="Hint.TLabel", justify="left",
                                 wraplength=wraplength)
        self.details.pack(side="bottom", fill="x", padx=2, pady=(0, 4))
        self.status = ttk.Label(self, textvariable=self.status_var, justify="left", wraplength=wraplength)
        self.status.pack(side="bottom", fill="x", padx=2, pady=(0, 2))
        self.box = tk.Text(self, width=width, height=height, wrap="word", undo=True)
        self.box.pack(fill="both", expand=True, pady=(0, 6))
        self.box.bind("<<Modified>>", self._modified)
        self.box.bind("<Control-Return>", lambda _e: (self.use(), "break")[1])
        self.refresh()

    @property
    def state(self) -> dict[str, Any] | None:
        st = self._state
        if callable(st):
            try:
                return st()
            except Exception:  # noqa: BLE001 - the diagnosis works without a state (no revision checks)
                return None
        return st

    @state.setter
    def state(self, value: Any) -> None:
        self._state = value

    # ------------------------------------------------------------------ live diagnosis
    def _modified(self, _event: Any = None) -> None:
        if not self.box.edit_modified():
            return
        self.box.edit_modified(False)
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
        self._after = self.after(DEBOUNCE_MS, self.refresh)

    def text(self) -> str:
        return self.box.get("1.0", "end-1c")

    def refresh(self) -> Any:
        """Diagnose the current text now (also called by the debounce timer)."""
        from ..intake.preview import preview
        self._after = None
        self.preview = (self._diagnose or preview)(self.text(), self.state)
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
                parent=self.winfo_toplevel(), title="Load the ZIP the chat gave you",
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
            self.zip_text = text  # 5.14.0: the box text that came from the ZIP (a later paste is not the ZIP)
            self.box.delete("1.0", "end")
            self.box.insert("1.0", text)
            self.box.edit_modified(False)
        self.preview = pv
        self._show(pv)
        return pv

    def set_text(self, text: str) -> None:
        self.box.delete("1.0", "end")
        self.box.insert("1.0", text)
        self.box.edit_modified(False)
        self.refresh()

    def clear(self) -> None:
        self.box.delete("1.0", "end")
        self.zip_name = ""
        self.refresh()

    def use(self) -> Any:
        return self.on_use(self.text()) if self.on_use is not None else None


class PasteBox:
    """The modal popup form (Workbench strip, Mission Map menu): a :class:`PastePanel` in its own window."""

    def __init__(self, parent: tk.Misc, title: str, *, state: dict[str, Any] | None = None,
                 primary_style: str = "Accent.TButton", modal: bool = True,
                 ask_zip: Callable[[], str] | None = None) -> None:
        self.result: str = ""
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.transient(parent)
        self.panel = PastePanel(self.top, state=state, on_use=lambda _t: self.ok(), primary_style=primary_style,
                                ask_zip=ask_zip, padding=8)
        self.panel.pack(fill="both", expand=True)
        for name in ("ok_btn", "zip_btn", "clear_btn", "details_var", "status_var", "details", "status", "box"):
            setattr(self, name, getattr(self.panel, name))
        self.top.protocol("WM_DELETE_WINDOW", self.cancel)
        self.top.bind("<Control-Return>", lambda _e: self.ok())
        ui_layout.place_dialog(self.top, 820, 560, parent)
        self.box.focus_set()
        if modal:
            try:
                self.top.grab_set()
            except tk.TclError:
                pass

    # the panel's behaviour, under the names the 5.10.0 tests use
    @property
    def preview(self) -> Any:
        return self.panel.preview

    @property
    def state(self) -> dict[str, Any] | None:
        return self.panel.state

    @property
    def zip_name(self) -> str:
        return self.panel.zip_name

    def text(self) -> str:
        return self.panel.text()

    def refresh(self) -> Any:
        return self.panel.refresh()

    def load_zip(self, path: str | None = None) -> Any:
        return self.panel.load_zip(path)

    def clear(self) -> None:
        self.panel.clear()

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
