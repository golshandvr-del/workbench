"""Shared workspace components (GUI roadmap stage 5; Design System 1.0 §6).

Every view builds its page from these helpers so spacing, type, colour and
direction are decided once. Helpers only build widgets — they never read or
write project state.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Iterable, Sequence

from . import theme

BANNER_SYMBOLS = {"info": "ℹ", "warning": "⚠", "danger": "✕", "success": "✓"}

# ttk class → workspace style (applied by theme_tree to widgets created without a WS style)
_CLASS_STYLE = {"TButton": "WS.TButton", "TEntry": "WS.TEntry", "TCombobox": "WS.TCombobox", "TSpinbox": "WS.TSpinbox",
                "TCheckbutton": "WS.TCheckbutton", "TRadiobutton": "WS.TRadiobutton", "Treeview": "WS.Treeview",
                "TProgressbar": "WS.Horizontal.TProgressbar", "TNotebook": "WS.TNotebook",
                "TLabelframe": "WS.TLabelframe", "TSeparator": "WS.TSeparator"}
_SURFACE_OF = {"WS.Surface.TFrame": "WS.Surface", "WS.Sidebar.TFrame": "WS.Sidebar", "WS.Alt.TFrame": "WS.Alt"}


def side(rtl: bool) -> str:
    """Pack side for the *start* of a row in the current direction."""
    return "right" if rtl else "left"


def end_side(rtl: bool) -> str:
    return "left" if rtl else "right"


def anchor(rtl: bool) -> str:
    return "e" if rtl else "w"


def justify(rtl: bool) -> str:
    return "right" if rtl else "left"


def _surface_prefix(widget: tk.Misc) -> str:
    parent = widget.master
    while parent is not None:
        try:
            st = str(parent.cget("style")) if isinstance(parent, ttk.Frame) else ""
        except tk.TclError:
            st = ""
        if st in _SURFACE_OF:
            return _SURFACE_OF[st]
        if st.startswith("WS.Banner."):
            return ""
        if st == "WS.TFrame" or isinstance(parent, (ttk.Labelframe, tk.Toplevel, tk.Tk)):
            return "WS"
        parent = parent.master
    return "WS"


def theme_tree(root: tk.Misc, theme_name: str) -> int:
    """Give every widget under *root* a workspace style / token colours. Returns the number of widgets styled.

    ttk widgets created without an explicit ``WS.`` style get the matching scoped
    style; classic Tk widgets (Text, Listbox, Canvas, Toplevel) get token colours.
    Keeps dialogs and views consistent in light and dark without per-view colours.
    """
    p = theme.palette(theme_name)
    n = 0
    stack = [root]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        cls = w.winfo_class()
        try:
            if isinstance(w, ttk.Widget):
                cur = str(w.cget("style"))
                if cur.startswith("WS."):
                    continue
                if cls == "TLabel":
                    w.configure(style=f"{_surface_prefix(w)}.TLabel" if _surface_prefix(w) else "WS.TLabel")
                elif cls == "TFrame":
                    w.configure(style="WS.TFrame")
                elif cls == "TScrollbar":
                    w.configure(style="WS.Vertical.TScrollbar" if str(w.cget("orient")) == "vertical"
                                else "WS.Horizontal.TScrollbar")
                elif cls in _CLASS_STYLE:
                    w.configure(style=_CLASS_STYLE[cls])
                else:
                    continue
                n += 1
            elif cls in ("Text", "Listbox"):
                opts = theme.classic_colours(theme_name, code=bool(getattr(w, "_ws_code", False)))
                if cls == "Listbox":
                    opts.pop("insertbackground", None)
                w.configure(**opts)
                n += 1
            elif cls in ("Toplevel", "Tk", "Canvas"):
                w.configure(background=p["bg"])
                n += 1
        except tk.TclError:
            continue
    return n


def style_text(widget: tk.Text | tk.Listbox, theme_name: str, *, code: bool = False) -> Any:
    widget._ws_code = code  # type: ignore[attr-defined]
    opts = theme.classic_colours(theme_name, code=code)
    if isinstance(widget, tk.Listbox):
        opts.pop("insertbackground", None)
    widget.configure(**opts)
    return widget


def page_header(parent: tk.Misc, title: str, purpose: str = "", *, rtl: bool = False,
                actions: Sequence[tuple[str, Callable[[], Any], str]] = (), row: int = 0) -> ttk.Frame:
    """Title + optional one-line purpose + action area. ``actions`` = (label, command, kind) with kind
    primary / secondary / quiet; the primary action sits at the far end in the reading direction."""
    box = ttk.Frame(parent, style="WS.TFrame")
    box.grid(row=row, column=0, sticky="ew", pady=(0, theme.space(3)))
    box.columnconfigure(0, weight=1)
    head = ttk.Frame(box, style="WS.TFrame")
    head.grid(row=0, column=0, sticky="ew")
    ttk.Label(head, text=title, style="WS.PageTitle.TLabel", anchor=anchor(rtl)).pack(side=side(rtl))
    acts = ttk.Frame(head, style="WS.TFrame")
    acts.pack(side=end_side(rtl))
    box.buttons = {}  # type: ignore[attr-defined]
    for label, cmd, kind in sorted(actions, key=lambda a: a[2] == "primary"):
        b = ttk.Button(acts, text=label, command=cmd, style=button_style(kind))
        b.pack(side=side(rtl), padx=(theme.space(2), 0) if not rtl else (0, theme.space(2)))
        box.buttons[label] = b  # type: ignore[attr-defined]
    if purpose:
        ttk.Label(box, text=purpose, style="WS.Muted.TLabel", anchor=anchor(rtl), justify=justify(rtl),
                  wraplength=760).grid(row=1, column=0, sticky="ew", pady=(theme.space(1), 0))
    return box


def button_style(kind: str) -> str:
    return {"primary": "WS.Primary.TButton", "quiet": "WS.Quiet.TButton", "danger": "WS.Danger.TButton"}.get(
        kind, "WS.TButton")


def section(parent: tk.Misc, title: str, *, rtl: bool = False, row: int | None = None, count: int | None = None,
            weight: int = 0) -> ttk.Frame:
    """Section title + body frame (no box). Replaces nested LabelFrames (anti-pattern 2). Returns the body."""
    outer = ttk.Frame(parent, style="WS.TFrame")
    if row is not None:
        outer.grid(row=row, column=0, sticky="nsew", pady=(theme.space(2), 0))
        if weight:
            parent.rowconfigure(row, weight=weight)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(1, weight=1)
    label = title + (f" ({count})" if count is not None else "")
    head = ttk.Frame(outer, style="WS.TFrame")
    head.grid(row=0, column=0, sticky="ew", pady=(0, theme.space(1)))
    ttk.Label(head, text=label, style="WS.Section.TLabel", anchor=anchor(rtl)).pack(side=side(rtl))
    body = ttk.Frame(outer, style="WS.TFrame")
    body.grid(row=1, column=0, sticky="nsew")
    body.columnconfigure(0, weight=1)
    body.head = head  # type: ignore[attr-defined]
    body.outer = outer  # type: ignore[attr-defined]
    return body


def banner(parent: tk.Misc, level: str, text: str, *, rtl: bool = False,
           on_close: Callable[[], Any] | None = None) -> ttk.Frame:
    """In-page feedback whose weight matches its importance (Design System §6; research principle 7)."""
    level = level if level in theme.STATUS_LEVELS else "info"
    box = ttk.Frame(parent, style=f"WS.Banner.{level}.TFrame", padding=(theme.space(3), theme.space(2)))
    lbl = ttk.Label(box, text=f"{BANNER_SYMBOLS[level]}  {text}", style=f"WS.Banner.{level}.TLabel",
                    anchor=anchor(rtl), justify=justify(rtl), wraplength=820)
    lbl.pack(side=side(rtl), fill="x", expand=True)
    if on_close:
        ttk.Button(box, text="×", width=2, style="WS.Quiet.TButton", command=on_close).pack(side=end_side(rtl))
    box.label = lbl  # type: ignore[attr-defined]
    box.level = level  # type: ignore[attr-defined]
    return box


def button_row(parent: tk.Misc, items: Iterable[tuple[str, Callable[[], Any], str]], *, rtl: bool = False) -> ttk.Frame:
    row = ttk.Frame(parent, style="WS.TFrame")
    row.buttons = {}  # type: ignore[attr-defined]
    for i, (label, cmd, kind) in enumerate(items):
        b = ttk.Button(row, text=label, command=cmd, style=button_style(kind))
        b.pack(side=side(rtl), padx=(0 if i == 0 else theme.space(2), 0) if not rtl else (0, 0 if i == 0 else theme.space(2)))
        row.buttons[label] = b  # type: ignore[attr-defined]
    return row


def table(parent: tk.Misc, columns: Sequence[tuple[str, str, int, bool]], *, height: int = 8, tree: bool = True,
          selectmode: str = "browse") -> ttk.Treeview:
    """Treeview + vertical scrollbar. ``columns`` = (id, heading, width, stretch); id "#0" is the tree column."""
    box = ttk.Frame(parent, style="WS.TFrame")
    box.columnconfigure(0, weight=1)
    box.rowconfigure(0, weight=1)
    ids = [c[0] for c in columns if c[0] != "#0"]
    tv = ttk.Treeview(box, columns=ids, show="tree headings" if tree else "headings", style="WS.Treeview",
                      height=height, selectmode=selectmode)
    for cid, head, width, stretch in columns:
        tv.heading(cid, text=head, anchor="w")
        tv.column(cid, width=width, minwidth=min(width, 60), stretch=stretch)
    sb = ttk.Scrollbar(box, orient="vertical", command=tv.yview, style="WS.Vertical.TScrollbar")
    tv.configure(yscrollcommand=sb.set)
    tv.grid(row=0, column=0, sticky="nsew")
    sb.grid(row=0, column=1, sticky="ns")
    tv.box = box  # type: ignore[attr-defined]
    return tv


def kv(parent: tk.Misc, rows: Sequence[tuple[str, str]], *, rtl: bool = False, surface: str = "WS.Surface") -> ttk.Frame:
    """Label: value rows (Inspector)."""
    box = ttk.Frame(parent, style=f"{surface}.TFrame")
    box.columnconfigure(1, weight=1)
    k_col, v_col = (1, 0) if rtl else (0, 1)
    for i, (k, v) in enumerate(rows):
        ttk.Label(box, text=k, style=f"{surface}.Muted.TLabel", anchor=anchor(rtl)).grid(
            row=i, column=k_col, sticky="nw", padx=(0, theme.space(2)) if not rtl else (theme.space(2), 0), pady=1)
        ttk.Label(box, text=v, style=f"{surface}.TLabel", anchor=anchor(rtl), justify=justify(rtl), wraplength=200).grid(
            row=i, column=v_col, sticky="ew", pady=1)
    return box


def empty_state(parent: tk.Misc, text: str, *, rtl: bool = False, surface: str = "WS") -> ttk.Label:
    return ttk.Label(parent, text=text, style=f"{surface}.Muted.TLabel", anchor=anchor(rtl), justify=justify(rtl),
                     wraplength=640)


def status_text(symbol: str, words: str) -> str:
    """Status is always symbol + words; colour is only a complement (WCAG 1.4.1)."""
    return f"{symbol} {words}".strip()
