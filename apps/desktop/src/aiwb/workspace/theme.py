"""Design tokens for the Project Workbench shell (GUI roadmap stage 4/5, Design System 1.0).

Single source for colours, type, spacing, control sizes and layout breakpoints
(``docs/specs/GUI_DESIGN_SYSTEM_FA.md``). Views never hard-code colours, fonts or
spacing; colour never carries meaning alone (every status has a symbol and words
from :mod:`aiwb.i18n`). Applying a theme only configures ttk styles — it never
touches project state.
"""
from __future__ import annotations

from typing import Any

THEMES = ("light", "dark")
DESIGN_SYSTEM_VERSION = "1.0"

PALETTES: dict[str, dict[str, str]] = {  # 3.0.0: aligned with the Fluent (Sun Valley) theme surfaces
    "light": {"bg": "#fafafa", "surface": "#ffffff", "surface_alt": "#f0f0f0", "sidebar": "#f0f0f0", "field": "#fdfdfd",
              "text": "#1c1c1c", "muted": "#5c5c5c", "border": "#e0e0e0", "border_strong": "#8a8a8a", "divider": "#e5e5e5",
              "selected": "#dde9f7", "selected_text": "#0f2a47", "focus": "#005fb8",
              "accent": "#005fb8", "accent_text": "#ffffff", "accent_hover": "#1a6fc2",
              "success": "#0e700e", "warning": "#8a5300", "danger": "#c42b1c", "info": "#005a9e",
              "banner_info": "#e6f0fa", "banner_warning": "#fff4ce", "banner_danger": "#fde7e9", "banner_success": "#dff6dd"},
    "dark": {"bg": "#1c1c1c", "surface": "#272727", "surface_alt": "#2b2b2b", "sidebar": "#202020", "field": "#292929",
             "text": "#f2f2f2", "muted": "#b0b0b0", "border": "#3d3d3d", "border_strong": "#8a8a8a", "divider": "#333333",
             "selected": "#203a55", "selected_text": "#eef6ff", "focus": "#57c8ff",
             "accent": "#57c8ff", "accent_text": "#00141f", "accent_hover": "#7dd5ff",
             "success": "#6ccb5f", "warning": "#fce100", "danger": "#ff99a4", "info": "#99ebff",
             "banner_info": "#1a2b3c", "banner_warning": "#3a3214", "banner_danger": "#442726", "banner_success": "#1f3320"},
}
# Legacy names (2.3.0–2.6.0) kept as aliases so older call sites keep working.
LEGACY_ALIASES = {"select": "selected", "blocking": "danger", "action": "warning", "ok": "success"}
for _p in PALETTES.values():
    for _old, _new in LEGACY_ALIASES.items():
        _p[_old] = _p[_new]

STATUS_LEVELS = ("success", "warning", "danger", "info")
TEXT_ROLES = ("text", "muted", "success", "warning", "danger", "info", "accent")
SURFACES = ("bg", "surface", "surface_alt", "sidebar", "field", "selected",
            "banner_info", "banner_warning", "banner_danger", "banner_success")

# Spacing scale: base unit 4px (space.N = N*4). Legacy names map onto the scale.
SPACE = {0: 0, 1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32}
SPACING = {"xs": 2, "s": SPACE[1], "m": SPACE[2], "l": SPACE[3], "xl": SPACE[4]}

FONT_FAMILY = "Segoe UI"
CODE_FAMILY = "Consolas"
TYPE = {  # role: (size in points, weight)
    "page_title": (15, "bold"), "section_title": (11, "bold"), "body": (10, "normal"),
    "secondary": (9, "normal"), "caption": (8, "normal"), "code": (9, "normal"),
}
FONT_SIZES = {"small": TYPE["secondary"][0], "body": TYPE["body"][0], "title": TYPE["section_title"][0],
              "headline": TYPE["page_title"][0]}

CONTROL = {"padding": (10, 4), "row_height": 26, "min_target": 24, "border_width": 1, "radius": 0}

# Layout (Wireframes §1)
MIN_SIZE = (960, 600)
DEFAULT_SIZE = (1280, 760)
INSPECTOR_STACK_BELOW = 1100
SIDEBAR_COMPACT_BELOW = 900
LAYOUT = {"sidebar_width": 176, "sidebar_compact_width": 72, "inspector_width": 300, "inspector_width_narrow": 260,
          "content_min_width": 560, "inspector_stacked_max": 0.30}

# Minimum WCAG contrast (checked by tests): text 4.5:1 (1.4.3); focus/control borders 3:1 (1.4.11, 2.4.11)
MIN_CONTRAST = 4.5
MIN_NON_TEXT_CONTRAST = 3.0


def palette(theme: str) -> dict[str, str]:
    return PALETTES.get(theme, PALETTES["light"])


def font(role: str) -> tuple[str, int] | tuple[str, int, str]:
    size, weight = TYPE[role]
    family = CODE_FAMILY if role == "code" else FONT_FAMILY
    return (family, size, weight) if weight != "normal" else (family, size)


def space(n: int) -> int:
    return SPACE[n]


def _lum(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def contrast_problems() -> list[str]:
    """Every text role on every surface, button text on accent, focus/control borders (Design System §2)."""
    out = []
    for name, p in PALETTES.items():
        for fg in TEXT_ROLES:
            for bg in SURFACES:
                c = contrast(p[fg], p[bg])
                if c < MIN_CONTRAST:
                    out.append(f"{name}: {fg} on {bg} contrast {c:.2f} < {MIN_CONTRAST}")
        for bg in ("accent", "accent_hover"):
            if contrast(p["accent_text"], p[bg]) < MIN_CONTRAST:
                out.append(f"{name}: accent_text on {bg}")
        if contrast(p["selected_text"], p["selected"]) < MIN_CONTRAST:
            out.append(f"{name}: selected_text on selected")
        for fg in ("focus", "border_strong"):
            for bg in ("bg", "surface", "field"):
                c = contrast(p[fg], p[bg])
                if c < MIN_NON_TEXT_CONTRAST:
                    out.append(f"{name}: {fg} on {bg} contrast {c:.2f} < {MIN_NON_TEXT_CONTRAST}")
    return out


def layout_for(width: int) -> dict[str, Any]:
    """Pure responsive decision used by the shell and by tests."""
    return {"inspector": "stacked" if width < INSPECTOR_STACK_BELOW else "side",
            "sidebar": "compact" if width < SIDEBAR_COMPACT_BELOW else "full"}


def inspector_width(width: int) -> int:
    return LAYOUT["inspector_width"] if width >= 1280 else LAYOUT["inspector_width_narrow"]


def clamp_to_work_area(x: int, y: int, w: int, h: int, area: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Keep a window fully inside the work area (ax, ay, aw, ah); shrink if it cannot fit (§14.1)."""
    ax, ay, aw, ah = area
    w, h = min(w, aw), min(h, ah)
    x = min(max(x, ax), ax + aw - w)
    y = min(max(y, ay), ay + ah - h)
    return x, y, w, h


def classic_colours(theme: str, *, code: bool = False) -> dict[str, Any]:
    """Options for classic Tk widgets (Text, Listbox, Spinbox) that ttk styles cannot reach (CC-1)."""
    p = palette(theme)
    return {"background": p["field"], "foreground": p["text"], "insertbackground": p["text"],
            "selectbackground": p["selected"], "selectforeground": p["selected_text"],
            "highlightthickness": 1, "highlightbackground": p["border_strong"], "highlightcolor": p["focus"],
            "relief": "flat", "borderwidth": 0, "font": font("code" if code else "body")}


def apply(style: Any, theme: str) -> dict[str, str]:
    """Configure the ttk styles used by the workspace. Returns the palette.

    Every style is scoped under ``WS.`` so the classic window keeps its own look.
    Uses the ``clam`` element theme (already used by the classic window) so colour
    tokens reach buttons, tables, entries and scrollbars (native Windows themes
    ignore background colours — CC-1/CC-2).
    """
    p = palette(theme)
    try:
        if style.theme_use() != "clam" and "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:  # pragma: no cover - theme not available
        pass
    body, small, code = font("body"), font("secondary"), font("code")
    bold = (*body[:2], "bold")
    pad = CONTROL["padding"]
    for name, bg in (("WS", "bg"), ("WS.Surface", "surface"), ("WS.Sidebar", "sidebar"), ("WS.Alt", "surface_alt")):
        style.configure(f"{name}.TFrame", background=p[bg])
        style.configure(f"{name}.TLabel", background=p[bg], foreground=p["text"], font=body)
        style.configure(f"{name}.Muted.TLabel", background=p[bg], foreground=p["muted"], font=small)
        style.configure(f"{name}.Code.TLabel", background=p[bg], foreground=p["text"], font=code)
        for lvl in STATUS_LEVELS:
            style.configure(f"{name}.{lvl}.TLabel", background=p[bg], foreground=p[lvl], font=body)
    style.configure("WS.Title.TLabel", background=p["bg"], foreground=p["text"], font=font("section_title"))
    style.configure("WS.PageTitle.TLabel", background=p["bg"], foreground=p["text"], font=font("page_title"))
    style.configure("WS.Section.TLabel", background=p["bg"], foreground=p["text"], font=font("section_title"))
    style.configure("WS.Next.TLabel", background=p["surface_alt"], foreground=p["text"], font=font("section_title"))
    style.configure("WS.InspTitle.TLabel", background=p["surface"], foreground=p["text"], font=font("section_title"))
    style.configure("WS.Inspector.TLabel", background=p["surface"], foreground=p["muted"], font=small)
    for lvl in STATUS_LEVELS:  # banners: status text on its tinted surface
        style.configure(f"WS.Banner.{lvl}.TFrame", background=p[f"banner_{lvl}"])
        style.configure(f"WS.Banner.{lvl}.TLabel", background=p[f"banner_{lvl}"], foreground=p[lvl], font=body)
    for old, new in (("blocking", "danger"), ("action", "warning"), ("ok", "success")):  # legacy severity labels
        style.configure(f"WS.{old}.TLabel", background=p["surface"], foreground=p[new], font=body)
    # buttons
    common = {"padding": pad, "font": body, "focuscolor": p["focus"], "relief": "flat", "borderwidth": 1}
    style.configure("WS.TButton", background=p["surface"], foreground=p["text"], bordercolor=p["border_strong"],
                    lightcolor=p["surface"], darkcolor=p["surface"], **common)
    style.map("WS.TButton", background=[("pressed", p["selected"]), ("active", p["surface_alt"]), ("disabled", p["bg"])],
              foreground=[("disabled", p["muted"])], bordercolor=[("focus", p["focus"])])
    style.configure("WS.Primary.TButton", background=p["accent"], foreground=p["accent_text"], bordercolor=p["accent"],
                    lightcolor=p["accent"], darkcolor=p["accent"], **{**common, "font": bold})
    style.map("WS.Primary.TButton", background=[("pressed", p["accent_hover"]), ("active", p["accent_hover"]),
                                                ("disabled", p["border"])],
              foreground=[("disabled", p["muted"])], bordercolor=[("focus", p["focus"])])
    for name, bg in (("WS.Quiet.TButton", "bg"), ("WS.QuietSurface.TButton", "surface")):
        style.configure(name, background=p[bg], foreground=p["accent"], bordercolor=p[bg], lightcolor=p[bg],
                        darkcolor=p[bg], **common)
        style.map(name, background=[("active", p["surface_alt"])], bordercolor=[("focus", p["focus"])],
                  foreground=[("disabled", p["muted"])])
    style.configure("WS.Danger.TButton", background=p["surface"], foreground=p["danger"], bordercolor=p["border_strong"],
                    lightcolor=p["surface"], darkcolor=p["surface"], **common)
    style.map("WS.Danger.TButton", background=[("active", p["banner_danger"])], bordercolor=[("focus", p["focus"])])
    for name, active in (("WS.Nav.TButton", False), ("WS.NavActive.TButton", True)):
        bg = p["selected"] if active else p["sidebar"]
        style.configure(name, anchor="w", padding=(SPACE[3], SPACE[2]), background=bg,
                        foreground=p["selected_text"] if active else p["text"], bordercolor=bg, lightcolor=bg,
                        darkcolor=bg, relief="flat", focuscolor=p["focus"], font=bold if active else body)
        style.map(name, background=[("active", p["selected"] if active else p["surface_alt"])],
                  bordercolor=[("focus", p["focus"])])
    # inputs
    for w in ("WS.TEntry", "WS.TCombobox", "WS.TSpinbox"):
        style.configure(w, fieldbackground=p["field"], foreground=p["text"], background=p["surface"],
                        bordercolor=p["border_strong"], lightcolor=p["field"], darkcolor=p["field"],
                        arrowcolor=p["text"], insertcolor=p["text"], padding=(SPACE[1], SPACE[1]), font=body)
        style.map(w, bordercolor=[("focus", p["focus"])], lightcolor=[("focus", p["focus"])],
                  fieldbackground=[("readonly", p["field"])], foreground=[("readonly", p["text"])],
                  selectbackground=[("readonly", p["field"])], selectforeground=[("readonly", p["text"])],
                  background=[("readonly", p["surface"]), ("active", p["surface_alt"])])
    for w, bg in (("WS.TCheckbutton", "bg"), ("WS.TRadiobutton", "bg"), ("WS.Surface.TRadiobutton", "surface")):
        style.configure(w, background=p[bg], foreground=p["text"], indicatorbackground=p["field"],
                        indicatorforeground=p["text"], focuscolor=p["focus"], font=body)
        style.map(w, background=[("active", p[bg])], indicatorbackground=[("selected", p["accent"])],
                  indicatorforeground=[("selected", p["accent_text"])])
    style.configure("WS.Vertical.TScrollbar", background=p["surface_alt"], troughcolor=p["bg"], bordercolor=p["bg"],
                    arrowcolor=p["muted"], lightcolor=p["surface_alt"], darkcolor=p["surface_alt"])
    style.configure("WS.Horizontal.TScrollbar", background=p["surface_alt"], troughcolor=p["bg"], bordercolor=p["bg"],
                    arrowcolor=p["muted"], lightcolor=p["surface_alt"], darkcolor=p["surface_alt"])
    style.configure("WS.Horizontal.TProgressbar", background=p["accent"], troughcolor=p["surface_alt"],
                    bordercolor=p["border"], lightcolor=p["accent"], darkcolor=p["accent"])
    style.configure("WS.TNotebook", background=p["bg"], bordercolor=p["border"], tabmargins=(0, 0, 0, 0))
    style.configure("WS.TNotebook.Tab", background=p["bg"], foreground=p["muted"], padding=(SPACE[3], SPACE[1]),
                    bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"], font=body, focuscolor=p["focus"])
    style.map("WS.TNotebook.Tab", background=[("selected", p["surface"])], foreground=[("selected", p["text"])],
              lightcolor=[("selected", p["accent"])])
    # tables
    style.configure("WS.Treeview", background=p["surface"], fieldbackground=p["surface"], foreground=p["text"],
                    font=body, rowheight=CONTROL["row_height"], bordercolor=p["border"], lightcolor=p["surface"],
                    darkcolor=p["surface"])
    style.map("WS.Treeview", background=[("selected", p["selected"])], foreground=[("selected", p["selected_text"])])
    style.configure("WS.Treeview.Heading", background=p["surface_alt"], foreground=p["muted"],
                    font=(*small[:2], "bold"), bordercolor=p["border"], lightcolor=p["surface_alt"],
                    darkcolor=p["surface_alt"], relief="flat", padding=(SPACE[2], SPACE[1]))
    style.map("WS.Treeview.Heading", background=[("active", p["divider"])])
    style.configure("WS.TSeparator", background=p["divider"])
    return p
