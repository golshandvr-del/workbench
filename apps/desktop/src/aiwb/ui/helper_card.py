"""Settings › Helper AI (optional) — roadmap 5.19.0.

One card: address (with presets), model, API key (hidden; kept in Windows Credential Manager), time limit, and
Save · Test · Remove. Nothing here is needed: without settings Workbench works exactly as before.

:class:`MainThreadQueue` hands results of background calls back to the Tk thread (Tk must never be touched from a
worker thread; ``after`` from a thread is not safe in every Tcl build). It polls only while a call is running.
"""
from __future__ import annotations

import queue
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from .. import helper_ai

CARD_TITLE = "Helper AI (optional)"
CARD_HINT = ("A small AI behind any OpenAI-compatible API (OpenRouter, Groq, Google AI Studio, a local Ollama …). "
             "When set up, Home shows \"Explain this step\" and, when an answer cannot be used, \"Fix with helper AI\". "
             "Nothing is sent unless you click one of them. Not set up: Workbench works exactly as before.")
POLL_MS = 80
SHOW_LABEL = "Show settings"
HIDE_LABEL = "Hide settings"
SAVE_LABEL = "Save helper"   # not "Save": that word is the Toolbar's project save


class MainThreadQueue:
    """``schedule(fn)`` may be called from any thread; ``fn`` runs later on the Tk thread of ``widget``."""

    def __init__(self, widget: tk.Misc) -> None:
        self.widget = widget
        self._q: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._pending = 0
        self._after: Any = None

    def schedule(self, fn: Callable[[], None]) -> None:
        self._q.put(fn)

    def started(self) -> None:
        """A background call started (Tk thread): keep polling until its result arrived."""
        self._pending += 1
        if self._after is None:
            self._after = self.widget.after(POLL_MS, self._poll)

    def _poll(self) -> None:
        self._after = None
        while True:
            try:
                fn = self._q.get_nowait()
            except queue.Empty:
                break
            self._pending = max(0, self._pending - 1)
            try:
                fn()
            except tk.TclError:
                pass   # the window closed while the call ran
        if self._pending:
            try:
                self._after = self.widget.after(POLL_MS, self._poll)
            except tk.TclError:
                self._after = None

    def run(self, fn: Callable[[], Any], done: Callable[[Any, str], None]) -> None:
        self.started()
        helper_ai.run_async(fn, done, self.schedule)


def build_helper_card(parent: tk.Misc, service: helper_ai.HelperService, *, on_change: Callable[[], None] | None = None,
                      runner: MainThreadQueue | None = None) -> dict[str, Any]:
    """Build the card into ``parent`` (a Card.TFrame); returns its widgets (tests drive them)."""
    runner = runner or MainThreadQueue(parent)
    w: dict[str, Any] = {"runner": runner}
    ttk.Label(parent, text=CARD_TITLE, style="CardTitle.TLabel").pack(anchor="w")
    ttk.Label(parent, text=CARD_HINT, style="CardHint.TLabel", wraplength=640, justify="left").pack(anchor="w",
                                                                                                   pady=(2, 8))
    # Collapsed by default (Settings shows at most 8 controls at once): one button opens the form.
    body = ttk.Frame(parent, style="Card.TFrame")
    w["body"] = body

    def toggle() -> bool:
        if body.winfo_manager():
            body.pack_forget()
            w["toggle"].configure(text=SHOW_LABEL)
            return False
        body.pack(fill="x", before=w["status_label"])
        w["toggle"].configure(text=HIDE_LABEL)
        return True

    w["do_toggle"] = toggle
    w["toggle"] = ttk.Button(parent, text=SHOW_LABEL, command=toggle)
    w["toggle"].pack(anchor="w")
    form = ttk.Frame(body, style="Card.TFrame")
    form.pack(fill="x", pady=(8, 0))
    form.columnconfigure(1, weight=1)
    c = service.config
    url_var = tk.StringVar(value=str(c.get("base_url", "")))
    model_var = tk.StringVar(value=str(c.get("model", "")))
    key_var = tk.StringVar(value="")
    timeout_var = tk.StringVar(value=str(service.timeout))
    preset_names = [n for n, _u in helper_ai.PRESETS]

    def pick_preset(_e: Any = None) -> None:
        name = w["preset"].get()
        url = dict(helper_ai.PRESETS).get(name)
        if url:
            url_var.set(url)

    ttk.Label(form, text="Provider", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=2)
    w["preset"] = ttk.Combobox(form, values=preset_names, state="readonly", width=28)
    w["preset"].grid(row=0, column=1, sticky="w", pady=2)
    w["preset"].bind("<<ComboboxSelected>>", pick_preset)
    rows = (("Address", url_var, {}), ("Model", model_var, {}),
            ("API key", key_var, {"show": "•"}), ("Time limit (s)", timeout_var, {"width": 8}))
    for r, (label, var, kw) in enumerate(rows, start=1):
        ttk.Label(form, text=label, style="Card.TLabel").grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)
        e = ttk.Entry(form, textvariable=var, **kw)
        e.grid(row=r, column=1, sticky="w" if "width" in kw else "ew", pady=2)
        w[label] = e
    w["key_hint"] = ttk.Label(form, style="CardHint.TLabel")
    w["key_hint"].grid(row=3, column=2, sticky="w", padx=(8, 0))
    status_var = tk.StringVar(value=service.summary())
    bar = ttk.Frame(body, style="Card.TFrame")
    bar.pack(anchor="w", pady=(8, 0))
    w["status_label"] = ttk.Label(parent, textvariable=status_var, style="CardHint.TLabel", wraplength=640,
                                  justify="left")
    w["status_label"].pack(anchor="w", pady=(6, 0))

    def key_hint() -> None:
        w["key_hint"].configure(text="saved — leave empty to keep it" if service.has_key else "optional for local servers")

    def changed() -> None:
        key_hint()
        w["remove"].state(["!disabled"] if service.configured else ["disabled"])
        w["test"].state(["!disabled"] if service.configured else ["disabled"])
        if on_change is not None:
            on_change()

    def save() -> bool:
        try:
            t = int(timeout_var.get().strip() or helper_ai.DEFAULT_TIMEOUT)
        except ValueError:
            status_var.set("The time limit must be a number of seconds.")
            return False
        key = key_var.get()
        try:
            service.configure(url_var.get(), model_var.get(), api_key=key if key.strip() else None, timeout=t)
        except helper_ai.HelperAIError as exc:
            status_var.set(str(exc))
            return False
        key_var.set("")
        url_var.set(service.config["base_url"])
        timeout_var.set(str(service.timeout))
        status_var.set("Saved. " + service.summary())
        changed()
        return True

    def test() -> None:
        if not service.configured:
            status_var.set("Save an address and a model first.")
            return
        status_var.set("Testing the helper AI…")
        w["test"].state(["disabled"])

        def done(result: Any, error: str) -> None:
            w["test"].state(["!disabled"])
            status_var.set(f"✗ {error}" if error else f"✓ The helper AI answered: {str(result)[:80]}")
        runner.run(service.test, done)

    def remove() -> None:
        try:
            service.clear()
        except helper_ai.HelperAIError as exc:
            status_var.set(str(exc))
            return
        url_var.set("")
        model_var.set("")
        key_var.set("")
        w["preset"].set("")
        status_var.set("Removed. " + service.summary())
        changed()

    w["save"] = ttk.Button(bar, text=SAVE_LABEL, style="Primary.TButton", command=save)
    w["save"].pack(side="left")
    w["test"] = ttk.Button(bar, text="Test", command=test)
    w["test"].pack(side="left", padx=(6, 0))
    w["remove"] = ttk.Button(bar, text="Remove", command=remove)
    w["remove"].pack(side="left", padx=(6, 0))
    w.update(url_var=url_var, model_var=model_var, key_var=key_var, timeout_var=timeout_var, status_var=status_var,
             do_save=save, do_test=test, do_remove=remove)
    key_hint()
    w["remove"].state(["!disabled"] if service.configured else ["disabled"])
    w["test"].state(["!disabled"] if service.configured else ["disabled"])
    return w
