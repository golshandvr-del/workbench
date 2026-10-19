"""One look for the whole application (roadmap 3.0.0, ADR-009).

* Loads the vendored Fluent theme (Sun Valley, MIT) once per Tk interpreter and
  switches between ``sun-valley-light`` / ``sun-valley-dark``.
* Maps every style name used anywhere in the app (classic ``Primary.TButton``,
  ``Hint.TLabel``, ``Card.TFrame`` … and the workspace ``WS.*`` styles) onto the
  semantic tokens in :mod:`aiwb.workspace.theme` — there is no second palette.
* Classic Tk widgets (``Text``, ``Listbox``, ``Canvas``) that ttk cannot reach are
  recoloured by walking the widget tree, so dark mode is complete.
* Falls back to ``clam`` + tokens when Tcl cannot load the theme (never fails start-up).

Changing the appearance never touches project data.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from ..workspace import theme as tokens

THEME_DIR = Path(__file__).resolve().parent / "sv_theme"
FLUENT = {"light": "sun-valley-light", "dark": "sun-valley-dark"}


def _interp_flag(widget: tk.Misc) -> bool:
    try:
        return bool(int(widget.tk.eval("info exists ::aiwb_sv_loaded")))
    except tk.TclError:
        return False


def load_fluent(widget: tk.Misc) -> bool:
    """Source sv.tcl once per interpreter. Returns False when the theme cannot be loaded."""
    if _interp_flag(widget):
        return True
    tcl = THEME_DIR / "sv.tcl"
    if not tcl.is_file():
        return False
    try:
        widget.tk.call("source", str(tcl))
        widget.tk.eval("set ::aiwb_sv_loaded 1")
        return True
    except tk.TclError:
        return False


def fluent_available(widget: tk.Misc) -> bool:
    try:
        return FLUENT["light"] in ttk.Style(widget).theme_names()
    except tk.TclError:
        return False


def apply(root: tk.Misc, theme_name: str) -> dict[str, str]:
    """Apply the theme to the whole application and return the token palette."""
    name = theme_name if theme_name in tokens.THEMES else "light"
    style = ttk.Style(root)
    if load_fluent(root) and fluent_available(root):
        try:
            style.theme_use(FLUENT[name])
        except tk.TclError:
            style.theme_use("clam")
    elif "clam" in style.theme_names():
        style.theme_use("clam")
    p = tokens.palette(name)
    _configure_shared(style, p)
    tokens.apply(style, name)  # WS.* styles (keeps the active element theme)
    try:
        root.winfo_toplevel().configure(background=p["bg"])
    except tk.TclError:
        pass
    recolor_tree(root.winfo_toplevel(), name)
    return p


def _configure_shared(style: ttk.Style, p: dict[str, str]) -> None:
    f = tokens.font
    style.configure(".", font=f("body"))
    style.configure("TFrame", background=p["bg"])
    style.configure("TLabel", background=p["bg"], foreground=p["text"], font=f("body"))
    style.configure("TCheckbutton", background=p["bg"], foreground=p["text"])
    style.configure("TRadiobutton", background=p["bg"], foreground=p["text"])
    style.configure("TLabelframe", background=p["bg"])
    style.configure("TLabelframe.Label", background=p["bg"], foreground=p["text"], font=f("section_title"))
    # Card surfaces (classic pages) — flat surface with the same tokens as the workspace
    style.configure("Card.TFrame", background=p["surface"])
    style.configure("Header.TFrame", background=p["bg"])
    style.configure("Surface.TLabel", background=p["surface"], foreground=p["text"], font=f("body"))
    style.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"], font=f("secondary"))
    style.configure("CardMuted.TLabel", background=p["surface"], foreground=p["muted"], font=f("secondary"))
    style.configure("Accent.TLabel", background=p["bg"], foreground=p["accent"], font=(*f("body")[:2], "bold"))
    style.configure("CardAccent.TLabel", background=p["surface"], foreground=p["accent"], font=(*f("body")[:2], "bold"))
    style.configure("Warning.TLabel", background=p["bg"], foreground=p["warning"], font=f("body"))
    style.configure("Danger.TLabel", background=p["bg"], foreground=p["danger"], font=f("body"))
    style.configure("Success.TLabel", background=p["bg"], foreground=p["success"], font=f("body"))
    style.configure("HeaderTitle.TLabel", background=p["bg"], foreground=p["text"], font=f("page_title"))
    style.configure("HeaderSub.TLabel", background=p["bg"], foreground=p["muted"], font=f("secondary"))
    style.configure("SectionTitle.TLabel", background=p["bg"], foreground=p["text"], font=f("section_title"))
    style.configure("Hint.TLabel", background=p["bg"], foreground=p["muted"], font=f("secondary"))
    style.configure("CardHint.TLabel", background=p["surface"], foreground=p["muted"], font=f("secondary"))
    style.configure("FieldTitle.TLabel", background=p["surface"], foreground=p["text"], font=(*f("body")[:2], "bold"))
    style.configure("Tooltip.TLabel", background=p["text"], foreground=p["bg"], font=f("secondary"), padding=(8, 4))
    # Primary = the Fluent accent button (one accent per page)
    try:
        if "Accent.TButton" in style.tk.splitlist(style.tk.call("ttk::style", "layout", "Accent.TButton") or ()) or \
                style.layout("Accent.TButton"):
            style.layout("Primary.TButton", style.layout("Accent.TButton"))
    except tk.TclError:
        pass
    style.configure("Primary.TButton", foreground=p["accent_text"], font=(*f("body")[:2], "bold"))
    # The page stack: a notebook whose tabs are hidden — navigation is the rail on the left.
    style.layout("Shell.TNotebook.Tab", [])
    style.configure("Shell.TNotebook", background=p["bg"], borderwidth=0, padding=0)
    try:
        style.layout("Shell.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
    except tk.TclError:
        pass
    # Shell chrome
    style.configure("Rail.TFrame", background=p["sidebar"])
    style.configure("TitleBar.TFrame", background=p["bg"])
    style.configure("StatusBar.TFrame", background=p["sidebar"])
    style.configure("StatusBar.TLabel", background=p["sidebar"], foreground=p["muted"], font=f("secondary"))
    style.configure("AppTitle.TLabel", background=p["bg"], foreground=p["text"], font=f("section_title"))
    style.configure("Crumb.TLabel", background=p["bg"], foreground=p["muted"], font=f("body"))
    style.configure("PageTitle.TLabel", background=p["bg"], foreground=p["text"], font=f("page_title"))
    style.configure("RailHead.TLabel", background=p["sidebar"], foreground=p["muted"], font=f("secondary"))
    style.configure("RailBrand.TLabel", background=p["sidebar"], foreground=p["accent"], font=f("section_title"))
    # Navigation rail entries: Fluent "Toolbutton" radios (selected = highlighted pill)
    style.configure("Rail.Toolbutton", anchor="w", padding=(12, 8), font=f("body"))
    style.configure("Pivot.Toolbutton", anchor="center", padding=(12, 6), font=f("body"))
    # Cards used by the Home / Settings pages
    style.configure("CardTitle.TLabel", background=p["surface"], foreground=p["text"], font=f("section_title"))
    style.configure("Card.TRadiobutton", background=p["surface"], foreground=p["text"])
    style.configure("Card.TCheckbutton", background=p["surface"], foreground=p["text"])


def classic_options(widget: tk.Misc, theme_name: str) -> dict[str, Any]:
    p = tokens.palette(theme_name)
    cls = widget.winfo_class()
    if cls in ("Text", "Listbox", "Entry", "Spinbox"):
        code = False
        try:
            fam = str(widget.cget("font"))
            code = "Consolas" in fam or "Courier" in fam or "monospace" in fam.lower()
        except tk.TclError:
            pass
        opts = tokens.classic_colours(theme_name, code=code)
        if cls == "Listbox":
            opts.pop("insertbackground", None)
        opts.pop("font", None)  # keep each widget's own font (code vs body)
        return opts
    if cls == "Canvas":
        return {"background": p["bg"], "highlightthickness": 0}
    if cls in ("Frame", "Toplevel", "Tk"):
        return {"background": p["bg"]}
    if cls == "Label":
        return {"background": p["bg"], "foreground": p["text"]}
    return {}


def recolor_tree(top: tk.Misc, theme_name: str) -> int:
    """Recolour classic Tk widgets below ``top``. Widgets marked ``_aiwb_keep_colours`` are skipped."""
    n = 0
    stack = [top]
    while stack:
        w = stack.pop()
        try:
            children = w.winfo_children()
        except tk.TclError:
            continue
        stack.extend(children)
        if getattr(w, "_aiwb_keep_colours", False):
            continue
        opts = classic_options(w, theme_name)
        if not opts:
            continue
        try:
            w.configure(**{k: v for k, v in opts.items() if k in w.keys()})
            n += 1
        except tk.TclError:
            pass
    return n
