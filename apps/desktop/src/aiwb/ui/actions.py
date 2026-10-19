"""Calm action bars (roadmap 3.3.0 — UI information architecture).

Rule: a view shows at most :data:`MAX_PRIMARY` real buttons for the things a user
does every time; everything else lives in one grouped ``More ▾`` menu. Commands
that moved into the menu keep a button-like handle (:class:`MenuAction`) so code
that enables/disables them (``.configure(state=...)``) keeps working unchanged.

:func:`describe` renders the page → section → button → menu-item tree used by the
``gui_ia_smoke`` Gate and by ``docs/specs/UI_TREE.md``.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Iterable, Sequence

MAX_PRIMARY = 4
MAX_VISIBLE_PER_VIEW = 10
MORE_LABEL = "More ▾"
BUTTON_CLASSES = ("TButton", "Button", "TMenubutton", "Menubutton")

# (label, command) or (label, command, style) ; None = separator
Item = Any


class MenuAction:
    """Button-compatible handle for a command that lives in a ``More ▾`` menu."""

    def __init__(self, menu: tk.Menu, index: int, label: str) -> None:
        self.menu = menu
        self.index = index
        self.label = label

    def configure(self, cnf: dict[str, Any] | None = None, **kw: Any) -> None:
        kw = {**(cnf or {}), **kw}
        opts: dict[str, Any] = {}
        if "state" in kw:
            opts["state"] = "disabled" if str(kw["state"]) == "disabled" else "normal"
        if "text" in kw:
            self.label = str(kw["text"])
            opts["label"] = self.label
        if "command" in kw:
            opts["command"] = kw["command"]
        if opts:
            self.menu.entryconfigure(self.index, **opts)

    config = configure

    def cget(self, key: str) -> Any:
        if key == "text":
            return self.menu.entrycget(self.index, "label")
        return self.menu.entrycget(self.index, key)

    def invoke(self) -> Any:
        return self.menu.invoke(self.index)

    def winfo_exists(self) -> bool:
        try:
            return bool(self.menu.winfo_exists())
        except tk.TclError:
            return False

    def pack(self, *a: Any, **k: Any) -> None:  # tolerated no-ops for legacy layout code
        return None

    grid = pack
    pack_forget = pack


class ActionBar(ttk.Frame):
    """A row of up to MAX_PRIMARY buttons plus one grouped ``More ▾`` menu."""

    def __init__(self, master: tk.Misc, primary: Sequence[Item] = (), more: Sequence[tuple[str, Sequence[Item]]] = (),
                 *, more_label: str = MORE_LABEL, side: str = "left", **kw: Any) -> None:
        super().__init__(master, **kw)
        if len(primary) > MAX_PRIMARY:
            raise ValueError(f"ActionBar allows at most {MAX_PRIMARY} primary buttons, got {len(primary)}")
        self.side = side
        self.buttons: dict[str, ttk.Button] = {}
        self.actions: dict[str, MenuAction] = {}
        for item in primary:
            label, command = item[0], item[1]
            style = item[2] if len(item) > 2 and item[2] else None
            b = ttk.Button(self, text=label, command=command, **({"style": style} if style else {}))
            b.pack(side=side, padx=(0, 6) if side == "left" else (6, 0))
            self.buttons[label] = b
        self.more_button: ttk.Menubutton | None = None
        self.menu: tk.Menu | None = None
        if any(items for _g, items in more):
            self.menu = tk.Menu(self, tearoff=False)
            self.more_button = ttk.Menubutton(self, text=more_label, menu=self.menu)
            self.more_button.pack(side=side, padx=(0, 6) if side == "left" else (6, 0))
            first = True
            for group, items in more:
                if not items:
                    continue
                if not first:
                    self.menu.add_separator()
                first = False
                if group:
                    self.menu.add_command(label=group.upper(), state="disabled")
                for item in items:
                    if item is None:
                        self.menu.add_separator()
                        continue
                    label, command = item[0], item[1]
                    self.menu.add_command(label=label, command=command)
                    self.actions[label] = MenuAction(self.menu, int(self.menu.index("end")), label)

    def handle(self, label: str) -> Any:
        """The button or menu handle for *label* (same API either way)."""
        return self.buttons.get(label) or self.actions[label]

    def labels(self) -> list[str]:
        return list(self.buttons) + list(self.actions)


def _menu_labels(menu: tk.Menu) -> list[str]:
    out: list[str] = []
    end = menu.index("end")
    if end is None:
        return out
    for i in range(int(end) + 1):
        if menu.type(i) == "command" and str(menu.entrycget(i, "state")) != "disabled" or (
                menu.type(i) == "command" and not menu.entrycget(i, "label").isupper()):
            out.append(str(menu.entrycget(i, "label")))
    return out


def _mapped(w: tk.Misc) -> bool:
    try:
        return bool(w.winfo_manager())
    except tk.TclError:
        return False


def visible_buttons(view: tk.Misc) -> list[str]:
    """Labels of real buttons laid out in *view* (nested notebooks: only the selected tab)."""
    out: list[str] = []

    def walk(w: tk.Misc) -> None:
        if isinstance(w, tk.Toplevel):
            return
        cls = w.winfo_class()
        if cls in BUTTON_CLASSES and _mapped(w):
            try:
                out.append(str(w.cget("text")))
            except tk.TclError:
                pass
            return
        if cls == "TNotebook":
            sel = w.select()
            if sel:
                walk(w.nametowidget(sel))
            return
        for ch in w.winfo_children():
            if _mapped(ch) or ch.winfo_class() == "Menu":
                walk(ch)

    for ch in view.winfo_children():
        walk(ch)
    return out


def describe(view: tk.Misc, depth: int = 0) -> list[str]:
    """Indented tree: sections (labelled frames, sub-tabs), buttons, and More-menu items."""
    lines: list[str] = []
    pad = "  " * depth

    def walk(w: tk.Misc, d: int) -> None:
        if isinstance(w, tk.Toplevel) or not (_mapped(w) or w.winfo_class() == "Menu"):
            return
        cls = w.winfo_class()
        p = "  " * d
        if cls in ("TButton", "Button"):
            lines.append(f"{p}- [{w.cget('text')}]")
            return
        if cls in ("TMenubutton", "Menubutton"):
            lines.append(f"{p}- [{w.cget('text')}]")
            try:
                menu = w.nametowidget(w.cget("menu"))
                for lab in _menu_labels(menu):
                    lines.append(f"{p}    · {lab}")
            except (tk.TclError, KeyError):
                pass
            return
        if cls in ("TCheckbutton", "TRadiobutton") and str(w.cget("text")):
            lines.append(f"{p}- ( ) {w.cget('text')}")
            return
        if cls in ("TLabelframe", "Labelframe") and str(w.cget("text")):
            lines.append(f"{p}- **{w.cget('text')}**")
            d += 1
        if cls == "TNotebook":
            for tab in w.tabs():
                lines.append(f"{p}- tab: **{w.tab(tab, 'text')}**")
                for ch in w.nametowidget(tab).winfo_children():
                    walk(ch, d + 1)
            return
        for ch in w.winfo_children():
            walk(ch, d)

    for ch in view.winfo_children():
        walk(ch, depth)
    return [pad + ln if pad else ln for ln in lines]


def all_commands(views: Iterable[tk.Misc]) -> set[str]:
    """Every command label reachable from *views* (buttons + More-menu items, all sub-tabs)."""
    found: set[str] = set()
    for v in views:
        for ln in describe(v):
            s = ln.strip()
            if s.startswith("- [") and s.endswith("]"):
                found.add(s[3:-1])
            elif s.startswith("· "):
                found.add(s[2:])
    return found


def bar(master: tk.Misc, primary: Sequence[Item] = (), more: Sequence[tuple[str, Sequence[Item]]] = (),
        **pack: Any) -> ActionBar:
    """Create and pack an :class:`ActionBar` (``fill="x"`` by default)."""
    ab = ActionBar(master, primary, more)
    ab.pack(**({"fill": "x"} | pack))
    return ab


Callback = Callable[[], Any]
