"""The single application shell (roadmap 3.0.0, ADR-009).

One window: a navigation rail on the start side, a title bar, a page stack (a
``ttk.Notebook`` whose tabs are hidden, so existing ``notebook.select(tab)``
calls keep working) and a status bar. Every feature is a *page* of this
window — the Project Workbench included. Theme, language and Simple/Advanced
mode are application-wide (:class:`aiwb.ui.prefs.AppPrefs`) and are changed in
one place: the Settings page.

Simple mode shows the guided pages only (Home, Workbench, Prompt, Response,
Settings); Advanced adds every expert tool. Switching never changes data.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from . import appearance
from .prefs import AppPrefs

# key -> (EN label, FA label, glyph, advanced_only)
PAGES: dict[str, tuple[str, str, str, bool]] = {
    "home": ("Home", "خانه", "⌂", False),
    "workbench": ("Project Workbench", "میز کار پروژه", "◈", False),
    "prompt": ("Prompt", "پرامپت", "✎", False),
    "response": ("AI Response", "پاسخ AI", "⇩", False),
    "profile": ("Project Profile", "پروفایل پروژه", "☰", True),
    "history": ("History", "تاریخچه", "↺", True),
    "run": ("Run & Report", "اجرا و گزارش", "▶", True),
    "git": ("Git / GitHub", "گیت / گیت‌هاب", "⑂", True),
    "settings": ("Settings", "تنظیمات", "⚙", False),
}
NAV_ORDER = ("home", "workbench", "prompt", "response", "profile", "history", "run", "git")
RAIL_WIDTH = 210


def work_area(root: tk.Misc) -> tuple[int, int, int, int]:
    """Usable screen area (x, y, w, h); leaves room for the Windows taskbar."""
    try:
        return 0, 0, root.winfo_screenwidth(), max(480, root.winfo_screenheight() - 48)
    except tk.TclError:
        return 0, 0, 1280, 720


def fit_to_screen(root: tk.Tk, want: tuple[int, int] = (1280, 820), minimum: tuple[int, int] = (900, 560)) -> str:
    """Size and centre the main window inside the work area; the minimum never exceeds the screen."""
    ax, ay, aw, ah = work_area(root)
    w, h = min(want[0], aw), min(want[1], ah)
    root.minsize(min(minimum[0], aw), min(minimum[1], ah))
    geo = f"{w}x{h}+{ax + (aw - w) // 2}+{ay + max(0, (ah - h) // 2)}"
    root.geometry(geo)
    return geo


class AppShell:
    """Owns the chrome; pages are plain frames created by the application."""

    def __init__(self, root: tk.Tk, prefs: AppPrefs, *, title: str, version: str) -> None:
        self.root = root
        self.prefs = prefs
        self.version = version
        self.pages: dict[str, ttk.Frame] = {}
        self.page_hooks: dict[str, Callable[[], None]] = {}
        self.pref_listeners: list[Callable[[str], None]] = []
        self.current = "home"
        self.palette = appearance.apply(root, prefs.theme)
        fit_to_screen(root)
        self.outer = ttk.Frame(root)
        self.outer.pack(fill="both", expand=True)
        self.outer.rowconfigure(0, weight=1)
        # rail
        self.rail = ttk.Frame(self.outer, style="Rail.TFrame", padding=(8, 10), width=RAIL_WIDTH)
        self.rail.grid_propagate(False)
        self.rail.pack_propagate(False)
        self.brand = ttk.Label(self.rail, text="◆ AI Workbench", style="RailBrand.TLabel", padding=(8, 2, 8, 14))
        self.brand.pack(fill="x")
        self.nav_var = tk.StringVar(value="home")
        self.nav: dict[str, ttk.Radiobutton] = {}
        for key in NAV_ORDER + ("settings",):
            b = ttk.Radiobutton(self.rail, variable=self.nav_var, value=key, style="Rail.Toolbutton",
                                command=lambda k=key: self.show(k))
            self.nav[key] = b
        self.rail_version = ttk.Label(self.rail, text=f"v{version}", style="RailHead.TLabel", padding=(10, 4))
        # main column
        self.main = ttk.Frame(self.outer)
        self.main.rowconfigure(1, weight=1)
        self.main.columnconfigure(0, weight=1)
        self.titlebar = ttk.Frame(self.main, style="TitleBar.TFrame", padding=(20, 12, 20, 6))
        self.titlebar.grid(row=0, column=0, sticky="ew")
        self.titlebar.columnconfigure(0, weight=1)
        self.page_title = tk.StringVar()
        self.title_label = ttk.Label(self.titlebar, textvariable=self.page_title, style="PageTitle.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.project_var = tk.StringVar(value="")
        self.project_label = ttk.Label(self.titlebar, textvariable=self.project_var, style="Crumb.TLabel")
        self.project_label.grid(row=1, column=0, sticky="w")
        self.actions = ttk.Frame(self.titlebar, style="TitleBar.TFrame")
        self.actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self.notebook = ttk.Notebook(self.main, style="Shell.TNotebook")
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=(14, 14), pady=(0, 6))
        self.statusbar = ttk.Frame(self.main, style="StatusBar.TFrame", padding=(14, 5))
        self.statusbar.grid(row=2, column=0, sticky="ew")
        self.statusbar.columnconfigure(0, weight=1)
        self._layout_rail()
        self._relabel()
        prefs.subscribe(self._on_pref)

    # -- pages
    def add_page(self, key: str, *, padding: Any = 12, on_show: Callable[[], None] | None = None) -> ttk.Frame:
        frame = ttk.Frame(self.notebook, padding=padding)
        self.notebook.add(frame, text=PAGES[key][0])
        self.pages[key] = frame
        if on_show is not None:
            self.page_hooks[key] = on_show
        return frame

    def key_for(self, frame: Any) -> str:
        for k, f in self.pages.items():
            if str(f) == str(frame):
                return k
        return ""

    def show(self, key: str) -> None:
        if key not in self.pages:
            return
        if not self.page_visible(key):
            self.prefs.set_mode("advanced")  # explicit navigation to an expert page reveals it
        self.current = key
        self.nav_var.set(key)
        self.notebook.select(self.pages[key])
        self.page_title.set(self.prefs.tr(PAGES[key][:2]))
        hook = self.page_hooks.get(key)
        if hook is not None:
            hook()

    def sync_from_notebook(self) -> None:
        """Keep rail + title in step when code calls ``notebook.select(frame)`` directly."""
        key = self.key_for(self.notebook.select())
        if key and key != self.current:
            self.current = key
            self.nav_var.set(key)
            self.page_title.set(self.prefs.tr(PAGES[key][:2]))
            hook = self.page_hooks.get(key)
            if hook is not None:
                hook()

    def page_visible(self, key: str) -> bool:
        return self.prefs.advanced or not PAGES[key][3]

    def visible_pages(self) -> list[str]:
        return [k for k in NAV_ORDER + ("settings",) if self.page_visible(k)]

    # -- chrome
    def _layout_rail(self) -> None:
        self.rail.pack_forget()
        self.main.pack_forget()
        side, other = ("right", "left") if self.prefs.rtl else ("left", "right")
        self.rail.pack(side=side, fill="y")
        self.main.pack(side=side, fill="both", expand=True)
        for b in self.nav.values():
            b.pack_forget()
        self.rail_version.pack_forget()
        for key in NAV_ORDER:
            if self.page_visible(key):
                self.nav[key].pack(fill="x", pady=1)
        self.rail_version.pack(side="bottom", fill="x")
        self.nav["settings"].pack(side="bottom", fill="x", pady=(1, 4))
        rtl = self.prefs.rtl
        anchor = "e" if rtl else "w"
        title_col, action_col = (1, 0) if rtl else (0, 1)
        self.titlebar.columnconfigure(title_col, weight=1)
        self.titlebar.columnconfigure(action_col, weight=0)
        self.title_label.grid_configure(column=title_col, sticky=anchor)
        self.project_label.grid_configure(column=title_col, sticky=anchor)
        self.actions.grid_configure(column=action_col, sticky="w" if rtl else "e")
        _ = other

    def _relabel(self) -> None:
        for key, b in self.nav.items():
            en, fa, glyph, _adv = PAGES[key]
            label = fa if self.prefs.rtl else en
            b.configure(text=(f"{label}  {glyph}" if self.prefs.rtl else f"{glyph}  {label}"))
        if self.current in PAGES:
            self.page_title.set(self.prefs.tr(PAGES[self.current][:2]))

    def _on_pref(self, key: str) -> None:
        if key == "theme":
            self.palette = appearance.apply(self.root, self.prefs.theme)
        if key in ("lang", "mode"):
            self._layout_rail()
            self._relabel()
        if key == "mode" and not self.page_visible(self.current):
            self.show("home")
        for fn in list(self.pref_listeners):
            fn(key)

    def on_pref(self, fn: Callable[[str], None]) -> None:
        self.pref_listeners.append(fn)


def build_settings_page(shell: AppShell, frame: ttk.Frame, *, extra: Callable[[ttk.Frame], None] | None = None) -> dict[str, Any]:
    """The one Settings page: appearance, language, experience mode (+ optional app section)."""
    prefs = shell.prefs
    frame.columnconfigure(0, weight=1)
    widgets: dict[str, Any] = {}

    def card(row: int, title: tuple[str, str], hint: tuple[str, str]) -> ttk.Frame:
        c = ttk.Frame(frame, style="Card.TFrame", padding=(18, 14))
        c.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        c.columnconfigure(0, weight=1)
        t = ttk.Label(c, style="CardTitle.TLabel")
        t.grid(row=0, column=0, sticky="w")
        h = ttk.Label(c, style="CardHint.TLabel", wraplength=640)
        h.grid(row=1, column=0, sticky="w", pady=(2, 8))
        widgets.setdefault("_titles", []).append((t, title, h, hint))
        return c

    theme_var = tk.StringVar(value=prefs.theme)
    lang_var = tk.StringVar(value=prefs.lang)
    mode_var = tk.StringVar(value=prefs.mode)
    c1 = card(0, ("Appearance", "ظاهر"), ("Light or dark — applies to every page immediately.",
                                         "روشن یا تیره — بلافاصله روی همهٔ صفحات اعمال می‌شود."))
    row1 = ttk.Frame(c1, style="Card.TFrame")
    row1.grid(row=2, column=0, sticky="w")
    widgets["theme"] = [ttk.Radiobutton(row1, variable=theme_var, value=v, style="Card.TRadiobutton",
                                        command=lambda: prefs.set_theme(theme_var.get())) for v in ("light", "dark")]
    c2 = card(1, ("Language", "زبان"), ("Interface language; Persian uses a right-to-left layout.",
                                       "زبان رابط؛ فارسی چیدمان راست‌به‌چپ دارد."))
    row2 = ttk.Frame(c2, style="Card.TFrame")
    row2.grid(row=2, column=0, sticky="w")
    widgets["lang"] = [ttk.Radiobutton(row2, variable=lang_var, value=v, style="Card.TRadiobutton",
                                       command=lambda: prefs.set_lang(lang_var.get())) for v in ("en", "fa")]
    c3 = card(2, ("Experience", "سطح تجربه"),
              ("Simple: a guided path — Home, Project Workbench, Prompt, AI Response. "
               "Advanced: adds Project Profile, History, Run & Report and Git / GitHub.",
               "ساده: مسیر هدایت‌شده — خانه، میز کار پروژه، پرامپت، پاسخ AI. "
               "پیشرفته: پروفایل پروژه، تاریخچه، اجرا و گزارش و گیت/گیت‌هاب هم اضافه می‌شوند."))
    row3 = ttk.Frame(c3, style="Card.TFrame")
    row3.grid(row=2, column=0, sticky="w")
    widgets["mode"] = [ttk.Radiobutton(row3, variable=mode_var, value=v, style="Card.TRadiobutton",
                                       command=lambda: prefs.set_mode(mode_var.get())) for v in ("simple", "advanced")]
    if extra is not None:
        c4 = card(3, ("Application", "برنامه"), ("Tools and data that belong to the whole application.",
                                                 "ابزارها و داده‌های مربوط به کل برنامه."))
        extra(c4)
    labels = {"light": ("Light", "روشن"), "dark": ("Dark", "تیره"), "en": ("English", "English"),
              "fa": ("فارسی", "فارسی"), "simple": ("Simple", "ساده"), "advanced": ("Advanced", "پیشرفته")}

    def relabel(_key: str = "") -> None:
        theme_var.set(prefs.theme)
        lang_var.set(prefs.lang)
        mode_var.set(prefs.mode)
        side = "right" if prefs.rtl else "left"
        for group, values in (("theme", ("light", "dark")), ("lang", ("en", "fa")), ("mode", ("simple", "advanced"))):
            for rb, v in zip(widgets[group], values):
                rb.configure(text=prefs.tr(labels[v]))
                rb.pack_forget()
                rb.pack(side=side, padx=(0, 18) if side == "left" else (18, 0))
        anchor = "e" if prefs.rtl else "w"
        for t, title, h, hint in widgets["_titles"]:
            t.configure(text=prefs.tr(title))
            h.configure(text=prefs.tr(hint), justify="right" if prefs.rtl else "left")
            t.grid_configure(sticky=anchor)
            h.grid_configure(sticky=anchor)
        for r in (row1, row2, row3):
            r.grid_configure(sticky=anchor)

    relabel()
    shell.on_pref(relabel)
    widgets.update(theme_var=theme_var, lang_var=lang_var, mode_var=mode_var, relabel=relabel)
    return widgets
