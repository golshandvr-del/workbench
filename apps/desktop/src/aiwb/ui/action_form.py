"""One clear window for all inputs of a step (roadmap 5.17.0, R5).

Before 5.17 each input was its own tiny ``askstring`` box ("Your decision", then "Why?"): the user never saw the
question the AI asked, the options, nor the project manager's recommendation. :class:`ActionForm` draws the form spec
of :func:`aiwb.v2.choices.form_spec` in **one** window:

* the step title and the **full question** at the top;
* a decision as **radio buttons** — the recommended option pre-selected and labelled "(recommended)" — plus
  "Other answer…" with its own text box; without known options a plain text box;
* passed/failed as two radio buttons; an optional reason pre-filled with its default;
* Enter = OK, Esc = Cancel; a missing answer is named in the window, which stays open.

``ask_form(parent, spec)`` is the modal API (returns the inputs dict or ``None``). ``TEST_HOOK`` — when set, a
callable ``(spec) -> dict | None`` — answers instead of the window (unit tests of the call sites).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from ..v2.choices import OTHER, initial_values, validate
from . import layout as ui_layout

FORM_TITLE_PREFIX = "AI Workbench · "
RECOMMENDED = " (recommended)"
OTHER_LABEL = "Other answer…"
WIDTH = 640
TEST_HOOK: Callable[[dict[str, Any]], dict[str, str] | None] | None = None


class ActionForm:
    """The form window. ``result`` is the inputs dict after OK, ``None`` after Cancel / close."""

    def __init__(self, parent: tk.Misc, spec: dict[str, Any], *, modal: bool = True,
                 on_done: Callable[[dict[str, str] | None], Any] | None = None) -> None:
        self.spec = spec
        self.result: dict[str, str] | None = None
        self.on_done = on_done
        self.closed = False
        self.vars: dict[str, tk.StringVar] = {}
        self.other_vars: dict[str, tk.StringVar] = {}
        self.other_entries: dict[str, ttk.Entry] = {}
        self.radios: dict[str, list[ttk.Radiobutton]] = {}
        self.entries: dict[str, ttk.Entry] = {}
        self.top = tk.Toplevel(parent)
        self.top.withdraw()
        self.top.title(FORM_TITLE_PREFIX + (spec.get("title") or "Your answer"))
        self.top.transient(parent.winfo_toplevel())
        body = ttk.Frame(self.top, padding=14)
        body.pack(fill="both", expand=True)
        wrap = WIDTH - 40
        if spec.get("step_title"):
            ttk.Label(body, text=spec["step_title"], style="SectionTitle.TLabel", wraplength=wrap,
                      justify="left").pack(anchor="w")
        self.question_label = ttk.Label(body, text=spec.get("question") or "", wraplength=wrap, justify="left")
        if spec.get("question"):
            self.question_label.pack(anchor="w", pady=(6, 10), fill="x")
        start = initial_values(spec)
        for f in spec["fields"]:
            self._field(body, f, start.get(f["need"], ""), wrap)
        self.error_var = tk.StringVar(value="")
        self.error_label = ttk.Label(body, textvariable=self.error_var, style="Error.TLabel", wraplength=wrap,
                                     justify="left")
        self.error_label.pack(anchor="w", pady=(6, 0))
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(10, 0))
        self.cancel_btn = ttk.Button(bar, text="Cancel", command=self.cancel)
        self.cancel_btn.pack(side="right")
        self.ok_btn = ttk.Button(bar, text="OK", style="Accent.TButton", command=self.ok)
        self.ok_btn.pack(side="right", padx=(0, 8))
        self.top.bind("<Return>", lambda _e: self.ok())
        self.top.bind("<KP_Enter>", lambda _e: self.ok())
        self.top.bind("<Escape>", lambda _e: self.cancel())
        self.top.protocol("WM_DELETE_WINDOW", self.cancel)
        self.top.update_idletasks()
        ui_layout.place_dialog(self.top, WIDTH, max(220, body.winfo_reqheight() + 8), parent)
        self.top.deiconify()
        self._focus_first()
        if modal:
            try:
                self.top.grab_set()
            except tk.TclError:
                pass

    # -- building ------------------------------------------------------------------------------------------
    def _field(self, body: ttk.Frame, f: dict[str, Any], value: str, wrap: int) -> None:
        need = f["need"]
        box = ttk.Frame(body)
        box.pack(fill="x", pady=(4, 4))
        ttk.Label(box, text=f["label"], style="Strong.TLabel").pack(anchor="w")
        var = tk.StringVar(value=value)
        self.vars[need] = var
        if f["kind"] in ("choice", "yesno") and f.get("options"):
            labels = f.get("option_labels") or {}
            self.radios[need] = []
            for opt in f["options"]:
                text = labels.get(opt, opt) + (RECOMMENDED if opt == f.get("recommended") else "")
                rb = ttk.Radiobutton(box, text=text, value=opt, variable=var, command=lambda n=need: self._sync(n))
                rb.pack(anchor="w", padx=(10, 0), pady=1)
                self.radios[need].append(rb)
            if f["kind"] == "choice":
                rb = ttk.Radiobutton(box, text=OTHER_LABEL, value=OTHER, variable=var,
                                     command=lambda n=need: self._sync(n, focus=True))
                rb.pack(anchor="w", padx=(10, 0), pady=1)
                self.radios[need].append(rb)
                ov = tk.StringVar(value="")
                self.other_vars[need] = ov
                e = ttk.Entry(box, textvariable=ov)
                e.pack(fill="x", padx=(30, 0), pady=(0, 2))
                e.bind("<FocusIn>", lambda _e, n=need: (self.vars[n].set(OTHER), self._sync(n)))
                self.other_entries[need] = e
                self._sync(need)
        else:
            e = ttk.Entry(box, textvariable=var)
            e.pack(fill="x", pady=(2, 0))
            self.entries[need] = e

    def _sync(self, need: str, focus: bool = False) -> None:
        e = self.other_entries.get(need)
        if e is None:
            return
        other = self.vars[need].get() == OTHER
        e.state(["!disabled"] if other else ["disabled"])
        if other and focus:
            e.focus_set()

    def _focus_first(self) -> None:
        for f in self.spec["fields"]:
            w = (self.radios.get(f["need"]) or [None])[0] or self.entries.get(f["need"])
            if w is not None:
                for rb in self.radios.get(f["need"], []):  # the selected radio gets the focus
                    if str(rb.cget("value")) == self.vars[f["need"]].get():
                        w = rb
                        break
                w.focus_set()
                return
        self.ok_btn.focus_set()

    # -- reading / acting (also the test API) -----------------------------------------------------------------
    def values(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for need, var in self.vars.items():
            v = var.get()
            out[need] = self.other_vars[need].get() if v == OTHER and need in self.other_vars else v
        return out

    def choose(self, need: str, option: str) -> None:
        """Select an option (or ``OTHER``) like a click on its radio button."""
        for rb in self.radios.get(need, []):
            if str(rb.cget("value")) == option:
                rb.invoke()
                return
        raise KeyError(f"{need}: no option {option!r}")

    def write(self, need: str, text: str) -> None:
        """Type into a field; for a choice this is the "Other answer…" box (which it selects)."""
        if need in self.other_vars:
            self.choose(need, OTHER)
            self.other_vars[need].set(text)
        else:
            self.vars[need].set(text)

    def option_texts(self, need: str) -> list[str]:
        return [str(rb.cget("text")) for rb in self.radios.get(need, [])]

    def ok(self) -> dict[str, str] | None:
        inputs, err = validate(self.spec, self.values())
        if err:
            self.error_var.set(err)
            return None
        self.result = inputs
        self._close()
        return inputs

    def cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.top.grab_release()
            self.top.destroy()
        except tk.TclError:
            pass
        if self.on_done is not None:
            self.on_done(self.result)


def ask_form(parent: tk.Misc, spec: dict[str, Any]) -> dict[str, str] | None:
    """Open the form, wait for it, return the inputs (``None`` when cancelled). A spec without fields is ``{}``."""
    if not spec.get("fields"):
        return {}
    if TEST_HOOK is not None:
        return TEST_HOOK(spec)
    form = ActionForm(parent, spec)
    try:
        form.top.wait_window()
    except tk.TclError:
        pass
    return form.result
