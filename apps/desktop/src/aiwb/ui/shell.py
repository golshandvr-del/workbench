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
from .layout import no_flow, refresh_styles, row_style, set_direction
from .prefs import AppPrefs

# key -> (EN label, FA label, glyph, advanced_only)
PAGES: dict[str, tuple[str, str, str, bool]] = {
    "home": ("Home", "خانه", "⌂", False),
    "workbench": ("Project Workbench", "میز کار پروژه", "◈", False),
    "agents": ("Agents", "عامل‌ها", "◎", False),
    "prompt": ("Prompt", "پرامپت", "✎", False),
    "response": ("AI Response", "پاسخ AI", "⇩", False),
    "profile": ("Project Profile", "پروفایل پروژه", "☰", True),
    "history": ("History", "تاریخچه", "↺", False),  # 5.x: a main rail destination
    "run": ("Run & Report", "اجرا و گزارش", "▶", True),
    "git": ("Git / GitHub", "گیت / گیت‌هاب", "⑂", True),
    "settings": ("Settings", "تنظیمات", "⚙", False),
}
NAV_ORDER = ("home", "workbench", "agents", "prompt", "response", "profile", "history", "run", "git")


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


# Page -> rail destination of the 5.x shell (roadmap 5.1.0, docs/UI_TREE.md): expert pages live under Agents › Tools.
RAIL_OF: dict[str, str] = {"home": "home", "workbench": "projects", "agents": "agents", "prompt": "agents",
                           "response": "agents", "profile": "agents", "run": "agents", "git": "agents",
                           "history": "history", "settings": "settings"}
# Rail destination -> page shown when it is clicked
RAIL_PAGE: dict[str, str] = {"home": "home", "projects": "workbench", "agents": "agents", "history": "history",
                             "settings": "settings"}
STATUS_POLL_MS = 2500


class AppShell:
    """Owns the chrome (5.x: toolbar · icon rail · page stack · live status bar); pages are plain frames.

    ``commands`` maps toolbar ids of :data:`structure5.TOOLBAR` to callables; ``message`` is the application's
    status sentence; ``facts`` returns the open project's V2 state (or ``None``) for the status bar.
    """

    def __init__(self, root: tk.Tk, prefs: AppPrefs, *, title: str, version: str,
                 commands: dict[str, Callable[[], Any]] | None = None, message: tk.StringVar | None = None,
                 facts: Callable[[], dict[str, Any] | None] | None = None) -> None:
        from . import chrome5, status5
        from .assets import Assets
        from .startup import ui_scale

        self.root = root
        self.prefs = prefs
        self.version = version
        self.pages: dict[str, ttk.Frame] = {}
        self.page_hooks: dict[str, Callable[[], None]] = {}
        self.pref_listeners: list[Callable[[str], None]] = []
        self.status_listeners: list[Callable[[dict[str, Any] | None], None]] = []
        self.current = "home"
        self.facts_fn = facts
        self._status5 = status5
        self._last_rev: tuple[str, int] | None = None
        self.palette = appearance.apply(root, prefs.theme)
        fit_to_screen(root)
        self.assets = Assets(root, chrome5.chrome_theme(prefs.theme), ui_scale(root))
        self.message_var = message if message is not None else tk.StringVar(value="")
        self.outer = ttk.Frame(root)
        self.outer.pack(fill="both", expand=True)
        self.toolbar = chrome5.Toolbar(self.outer, self.assets, dict(commands or {}))
        self.toolbar.pack(side="top", fill="x")
        self.topline = tk.Frame(self.outer, height=1, bd=0)
        self.topline._aiwb_keep_colours = True  # type: ignore[attr-defined]
        self.topline.pack(side="top", fill="x")
        self.statusbar = chrome5.StatusBar(self.outer, self.assets, message=self.message_var, version=version)
        self.statusbar.pack(side="bottom", fill="x")
        self.body = ttk.Frame(self.outer)
        self.body.pack(side="top", fill="both", expand=True)
        self.rail = chrome5.IconRail(self.body, self.assets, self.select_rail)
        self.nav = self.rail.items
        self.nav_var = tk.StringVar(value="home")
        self.main = ttk.Frame(self.body)
        self.main.rowconfigure(0, weight=1)
        self.main.columnconfigure(0, weight=1)
        self.page_title = tk.StringVar()
        self.project_var = self.toolbar.project_var
        self.project_label = self.toolbar.project_lbl
        self.notebook = ttk.Notebook(self.main, style="Shell.TNotebook")
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=(14, 14), pady=(10, 6))
        self._layout_rail()
        self._relabel()
        self._recolor_chrome()
        prefs.subscribe(self._on_pref)
        self.root.after(STATUS_POLL_MS, self._poll_status)

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

    def select_rail(self, dest: str) -> None:
        self.show(RAIL_PAGE.get(dest, dest))

    def show(self, key: str) -> None:
        if key not in self.pages:
            return
        if not self.page_visible(key):
            self.prefs.set_mode("advanced")  # explicit navigation to an expert page reveals it
        self.current = key
        self.notebook.select(self.pages[key])
        self._mark(key)
        hook = self.page_hooks.get(key)
        if hook is not None:
            hook()

    def _mark(self, key: str) -> None:
        dest = RAIL_OF.get(key, key)
        self.nav_var.set(dest)
        self.page_title.set(self.prefs.tr(PAGES[key][:2]))
        self.rail.select(dest)

    def sync_from_notebook(self) -> None:
        """Keep rail + title in step when code calls ``notebook.select(frame)`` directly."""
        key = self.key_for(self.notebook.select())
        if key and key != self.current:
            self.current = key
            self._mark(key)
            hook = self.page_hooks.get(key)
            if hook is not None:
                hook()

    def page_visible(self, key: str) -> bool:
        return self.prefs.advanced or not PAGES[key][3]

    def visible_pages(self) -> list[str]:
        return [k for k in NAV_ORDER + ("settings",) if k in self.pages and self.page_visible(k)]

    # -- status bar
    def refresh_status(self) -> dict[str, Any]:
        state = None
        if self.facts_fn is not None:
            try:
                state = self.facts_fn()
            except Exception:  # noqa: BLE001 - a broken project state must not break the status bar
                state = None
        facts = self._status5.summary(state)
        self.statusbar.show_facts(facts)
        for fn in list(self.status_listeners):  # e.g. the Mission Map redraws when the state revision changes
            try:
                fn(state)
            except Exception:  # noqa: BLE001 - a listener must not break the status bar
                pass
        if state is not None:
            rev = (str(state.get("project_id", "")), int(state.get("state_revision", 0) or 0))
            if self._last_rev is None or rev[0] != self._last_rev[0]:
                self.statusbar.show_saved("Saved")
            elif rev[1] != self._last_rev[1]:
                self.statusbar.show_saved("Autosaved")
            self._last_rev = rev
        else:
            self._last_rev = None
            self.statusbar.show_saved("")
        return facts

    def _poll_status(self) -> None:
        try:
            if not self.root.winfo_exists():
                return
            self.refresh_status()
            self.root.after(STATUS_POLL_MS, self._poll_status)
        except tk.TclError:
            pass

    # -- chrome
    def _layout_rail(self) -> None:
        self.rail.pack_forget()
        self.main.pack_forget()
        side = "right" if self.prefs.rtl else "left"
        self.rail.pack(side=side, fill="y")
        self.main.pack(side=side, fill="both", expand=True)

    def _relabel(self) -> None:
        if self.current in PAGES:
            self.page_title.set(self.prefs.tr(PAGES[self.current][:2]))

    def _recolor_chrome(self) -> None:
        from .tokens5 import palette5
        p = palette5(self.assets.theme)
        self.topline.configure(background=p["line_soft"])
        self.toolbar.recolor()
        self.rail.recolor()
        self.statusbar.recolor()

    def _on_pref(self, key: str) -> None:
        if key == "theme":
            from .chrome5 import chrome_theme
            self.palette = appearance.apply(self.root, self.prefs.theme)
            refresh_styles(self.root)
            self.assets.set_theme(chrome_theme(self.prefs.theme))
            self._recolor_chrome()
        if key == "lang":
            set_direction(self.prefs.rtl)
        if key in ("lang", "mode"):
            self._layout_rail()
            self._relabel()
        if key == "mode" and not self.page_visible(self.current):
            self.show("home")
        for fn in list(self.pref_listeners):
            fn(key)

    def on_pref(self, fn: Callable[[str], None]) -> None:
        self.pref_listeners.append(fn)


# Language policy (2026-10-19): the UI is English-only for now, so the Language card is
# not shown. The preference and translations stay in place for a later version.
SHOW_LANGUAGE_CARD = False


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
    row1 = no_flow(ttk.Frame(c1, style=row_style(c1)))
    row1.grid(row=2, column=0, sticky="w")
    widgets["theme"] = [ttk.Radiobutton(row1, variable=theme_var, value=v, style="Card.TRadiobutton",
                                        command=lambda: prefs.set_theme(theme_var.get())) for v in ("light", "dark")]
    c2 = card(1, ("Language", "زبان"), ("Interface language; Persian uses a right-to-left layout.",
                                       "زبان رابط؛ فارسی چیدمان راست‌به‌چپ دارد."))
    row2 = no_flow(ttk.Frame(c2, style=row_style(c2)))
    row2.grid(row=2, column=0, sticky="w")
    widgets["lang"] = [ttk.Radiobutton(row2, variable=lang_var, value=v, style="Card.TRadiobutton",
                                       command=lambda: prefs.set_lang(lang_var.get())) for v in ("en", "fa")]
    c3 = card(2, ("Experience", "سطح تجربه"),
              ("Simple: a guided path — Home, Projects, Agents, History. "
               "Advanced: adds the expert tools under Agents › Tools (Project Profile, Run & Report, Git / GitHub).",
               "ساده: مسیر هدایت‌شده — خانه، میز کار پروژه، پرامپت، پاسخ AI. "
               "پیشرفته: پروفایل پروژه، تاریخچه، اجرا و گزارش و گیت/گیت‌هاب هم اضافه می‌شوند."))
    row3 = no_flow(ttk.Frame(c3, style=row_style(c3)))
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

    if not SHOW_LANGUAGE_CARD:
        c2.grid_remove()
    relabel()
    shell.on_pref(relabel)
    widgets.update(theme_var=theme_var, lang_var=lang_var, mode_var=mode_var, relabel=relabel)
    return widgets
