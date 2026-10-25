"""Home › Next step — the cockpit card (roadmap 5.11.0, audit A7).

Before 5.11.0 Home only *named* the next step and sent the user to the Workbench, whose strip had the buttons and a
popup paste box. The card now does the step itself, on Home:

* the step's title and explanation, with each AI's **name** (not its id);
* the primary action as a button, the other actions in **More**;
* whenever the step accepts an answer, the **paste panel inside the page** (:class:`aiwb.ui.paste_box.PastePanel`,
  live diagnosis + Load ZIP…) — no popup window;
* "Prepare the prompt" also copies it (one click less), and every prompt an action yields (fix prompt, continue
  prompt, change request) is copied and said so;
* clicking an AI on the Mission Map *focuses* the card on that AI's own queue; More › "Back to the next step" returns.

:func:`card_model` is pure (``test_next_card.py``); :class:`NextStepCard` draws it and runs the actions through the
``perform(key, action, inputs)`` callback — the embedded Workbench's ``guide_action``, the same code path as before.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

USER = "you"
BACK_LABEL = "Back to the next step"
# actions whose result prompt is copied at once (the user's next move is to paste it into a chat)
COPY_RESULT = ("paste", "request_changes", "troubleshoot", "repair", "review_prompt", "manager_prompt", "escalate")


def names_of(state: dict[str, Any] | None) -> dict[str, str]:
    """``agent_id`` → the name the user gave the AI (the id itself when it has no name)."""
    out: dict[str, str] = {}
    for aid, a in ((state or {}).get("agents") or {}).items():
        name = str((a or {}).get("name") or "").strip()
        out[aid] = name or aid
    return out


def humanize(text: str, names: dict[str, str]) -> str:
    """Replace agent ids in a guide text with the AIs' names (longest id first, so ``agent-dev-2`` wins)."""
    for aid in sorted(names, key=len, reverse=True):
        if names[aid] != aid and aid in text:
            text = text.replace(aid, names[aid])
    return text


def _label(a: dict[str, Any]) -> str:
    lab = str(a["label"])
    return lab + ("…" if a["needs"] and not lab.endswith("…") else "")


def card_model(steps: list[dict[str, Any]], names: dict[str, str], focus: str = "", step_key: str = "") -> dict[str, Any]:
    """What the card shows for the guide's ``steps`` (most urgent first); ``focus`` = one AI's queue only,
    ``step_key`` = that very step when it is still open (Mission Map › GET AI RESPONSE on a task).

    Keys: ``key``, ``title``, ``explain``, ``who``, ``primary`` (action or None), ``more`` (actions), ``paste``
    (the action that takes the answer text, or None), ``focus``, ``empty``.
    """
    base = {"key": "", "title": "", "explain": "", "who": "", "primary": None, "more": [], "paste": None,
            "focus": focus, "empty": False, "agent_id": ""}
    if not steps:
        return {**base, "empty": True, "title": "Open or create a project to see its next step."}
    pick = steps[0]
    if focus:
        mine = [s for s in steps if s["agent_id"] == focus]
        if not mine:
            who = names.get(focus, focus)
            return {**base, "empty": True, "title": f"{who} has nothing to do right now",
                    "explain": f"No prompt or answer of {who} is waiting. The project's next step: "
                               f"{humanize(steps[0]['title'], names)}.", "who": who, "agent_id": focus}
        pick = mine[0]
    if step_key:
        pick = next((s for s in steps if s["key"] == step_key), pick)
    acts = list(pick["actions"])
    paste = next((a for a in acts if "text" in a["needs"]), None)
    buttons = [a for a in acts if a is not paste]
    primary = next((a for a in buttons if a["primary"]), None)
    if primary is None and paste is None and buttons:
        primary = buttons[0]
    more = [a for a in buttons if a is not primary]
    others = len([s for s in steps if not focus or s["agent_id"] == focus]) - 1
    explain = humanize(pick["explain"], names) + (f"  ({others} more open)" if others > 0 else "")
    who = "" if pick["agent_id"] == USER else names.get(pick["agent_id"], pick["agent_id"])
    return {**base, "key": pick["key"], "title": humanize(pick["title"], names), "explain": explain, "who": who,
            "agent_id": pick["agent_id"],
            "primary": None if primary is None else {**primary, "text": _label(primary)},
            "more": [{**a, "text": _label(a)} for a in more], "paste": paste}


class NextStepCard(ttk.Frame):
    """The card. Callbacks: ``steps()`` → guide steps, ``state()`` → project state (names, diagnosis),
    ``perform(key, action, inputs)`` → result dict (``{"error": message}`` when refused or cancelled),
    ``clipboard(text)`` and ``status(message)``."""

    def __init__(self, master: tk.Misc, *, steps: Callable[[], list[dict[str, Any]]],
                 state: Callable[[], dict[str, Any] | None], perform: Callable[[str, str, dict[str, Any] | None], Any],
                 clipboard: Callable[[str], None], status: Callable[[str], None], wraplength: int = 820,
                 **kw: Any) -> None:
        super().__init__(master, style="Card.TFrame", padding=(12, 8), **kw)
        self._steps, self._state, self._perform = steps, state, perform
        self._clipboard, self._status = clipboard, status
        self.focus_agent = ""
        self.focus_key = ""
        self.model: dict[str, Any] = card_model([], {})
        head = ttk.Frame(self, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Next step", style="CardAccent.TLabel").pack(side="left", padx=(0, 10))
        self.title_var = tk.StringVar(value=self.model["title"])
        self.title_label = ttk.Label(head, textvariable=self.title_var, style="Card.TLabel", wraplength=wraplength - 120,
                                     justify="left")
        self.title_label.pack(side="left", fill="x", expand=True)
        self.explain_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.explain_var, style="CardMuted.TLabel", wraplength=wraplength,
                  justify="left").pack(anchor="w", pady=(4, 0))
        self.message_var = tk.StringVar(value="")
        self.message_label = ttk.Label(self, textvariable=self.message_var, style="CardMuted.TLabel",
                                       wraplength=wraplength, justify="left")
        self.message_label.pack(anchor="w", pady=(2, 0))
        bar = ttk.Frame(self, style="Card.TFrame")
        bar.pack(fill="x", pady=(6, 0))
        self.next_btn = ttk.Button(bar, text="", style="Primary.TButton", command=self.do_next)
        self.next_btn.pack(side="left")
        self.next_menu = tk.Menu(bar, tearoff=False)
        self.next_more = ttk.Menubutton(bar, text="More", menu=self.next_menu)
        self.next_more.pack(side="left", padx=(6, 0))
        self._bar = bar
        from .paste_box import PastePanel
        self.paste = PastePanel(self, state=self._state, on_use=self.use_answer, height=6, wraplength=wraplength,
                                style="Card.TFrame")
        self.paste_hint = "Paste the whole answer of the chat below (or load the ZIP it gave you)."

    # ------------------------------------------------------------------ drawing
    def refresh(self) -> dict[str, Any]:
        """Read the guide again and redraw (reading never writes)."""
        try:
            steps = self._steps()
        except Exception as exc:  # noqa: BLE001 - a broken project state must not break Home
            steps = []
            self.message_var.set(str(exc)[:300])
        try:
            names = names_of(self._state())
        except Exception:  # noqa: BLE001
            names = {}
        old_key = self.model.get("key")
        self.model = m = card_model(steps, names, self.focus_agent, self.focus_key)
        who = f"  ·  {m['who']}" if m["who"] and not m["empty"] else ""
        self.title_var.set(m["title"] + who)
        self.explain_var.set(m["explain"])
        if m["primary"] is not None:
            self.next_btn.configure(text=m["primary"]["text"])
            self.next_btn.pack(side="left", before=self.next_more)
        else:
            self.next_btn.pack_forget()
        self.next_menu.delete(0, "end")
        for a in m["more"]:
            self.next_menu.add_command(label=a["text"], command=lambda i=a["id"]: self.action(i))
        if self.focus_agent:
            self.next_menu.add_command(label=BACK_LABEL, command=lambda: self.set_focus(""))
        if self.next_menu.index("end") is None:
            self.next_more.pack_forget()
        else:
            self.next_more.pack(side="left", padx=(6 if m["primary"] is not None else 0, 0))
        if m["paste"] is not None:
            self.paste.ok_btn.configure(text="Use this answer")
            if not self.paste.winfo_manager():
                self.paste.pack(fill="x", pady=(8, 0))
            if old_key != m["key"]:
                self.paste.clear()
        else:
            self.paste.pack_forget()
        return m

    def set_focus(self, agent_id: str, step_key: str = "") -> dict[str, Any]:
        """Show one AI's queue (Mission Map click on its name) — ``""`` = the project's next step; ``step_key`` picks
        one open step of that queue (a task's own prompt/answer)."""
        self.focus_agent, self.focus_key = agent_id, step_key
        self.message_var.set("")
        return self.refresh()

    # ------------------------------------------------------------------ actions
    def labels(self) -> list[str]:
        """Every action label on the card: the primary button, then More (for tests and the click counter)."""
        out = [self.next_btn.cget("text")] if self.next_btn.winfo_manager() else []
        end = self.next_menu.index("end")
        return out + ([] if end is None else [self.next_menu.entrycget(i, "label") for i in range(end + 1)])

    def do_next(self) -> Any:
        m = self.model
        return self.action(m["primary"]["id"]) if m["primary"] is not None else None

    def action(self, action_id: str, inputs: dict[str, Any] | None = None) -> Any:
        m = self.model
        if not m["key"]:
            return None
        out = self._perform(m["key"], action_id, inputs)
        if isinstance(out, dict) and not out.get("error") and action_id == "prepare" and out.get("handoff_id"):
            copied = self._perform(f"handoff:{out['handoff_id']}", "copy", {})  # the prompt is ready: copy it too
            if isinstance(copied, dict) and not copied.get("error"):
                out = {**copied, "handoff_id": out["handoff_id"],
                       "message": "Prompt ready and copied. Paste it into the AI's chat, then paste its answer here."}
        return self._done(out, action_id)

    def use_answer(self, text: str) -> Any:
        """The paste panel's "Use this answer": perform the step's paste action with the text."""
        m = self.model
        if m["paste"] is None:
            return None
        if not text.strip():
            self.message_var.set("Paste the whole answer first.")
            return None
        out = self._perform(m["key"], m["paste"]["id"], {"text": text})
        if isinstance(out, dict) and not out.get("error"):
            self.paste.clear()
        return self._done(out, m["paste"]["id"])

    def _done(self, out: Any, action_id: str) -> Any:
        if not isinstance(out, dict):
            self.refresh()
            return out
        msg = str(out.get("error") or out.get("message") or "")
        if not out.get("error") and out.get("prompt") and action_id in COPY_RESULT:
            self._clipboard(out["prompt"])
            msg += " The prompt for the chat is copied to the clipboard."
        self.message_var.set(msg)
        if msg:
            self._status(msg)
        self.refresh()
        return None if out.get("error") else out
