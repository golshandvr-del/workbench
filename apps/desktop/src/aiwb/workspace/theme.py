"""Design tokens for the Project Workbench shell (roadmap 2.3.0 stage 1, ADR-007).

Single source for colours, spacing, fonts and status/severity symbols. Views never
hard-code colours; colour never carries meaning alone (every status has a symbol
and words from :mod:`aiwb.i18n`).
"""
from __future__ import annotations

from typing import Any

THEMES = ("light", "dark")

PALETTES: dict[str, dict[str, str]] = {
    "light": {"bg": "#f6f7f9", "surface": "#ffffff", "sidebar": "#eef1f5", "text": "#1d2430", "muted": "#5b6577",
              "accent": "#2457c5", "accent_text": "#ffffff", "border": "#d5dbe4", "select": "#dce7ff",
              "blocking": "#a3161b", "action": "#8a5a00", "info": "#285a8f", "ok": "#1d6b35"},
    "dark": {"bg": "#16191f", "surface": "#1f232b", "sidebar": "#1a1e25", "text": "#e6e9ef", "muted": "#9aa4b5",
             "accent": "#7aa2ff", "accent_text": "#0d1220", "border": "#343a46", "select": "#2c3a5c",
             "blocking": "#ff8a8f", "action": "#f0c060", "info": "#8fbfff", "ok": "#7fd69a"},
}

SPACING = {"xs": 2, "s": 4, "m": 8, "l": 12, "xl": 16}
FONT_FAMILY = "Segoe UI"
FONT_SIZES = {"small": 9, "body": 10, "title": 12, "headline": 14}

# Responsive breakpoints (ADR-007 §3)
MIN_SIZE = (960, 600)
INSPECTOR_STACK_BELOW = 1100
SIDEBAR_COMPACT_BELOW = 900
DEFAULT_SIZE = (1280, 760)

# Minimum WCAG-style contrast for text on its surface (checked by tests)
MIN_CONTRAST = 4.5


def palette(theme: str) -> dict[str, str]:
    return PALETTES.get(theme, PALETTES["light"])


def _lum(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def contrast_problems() -> list[str]:
    out = []
    for name, p in PALETTES.items():
        for fg in ("text", "muted", "blocking", "action", "info", "ok", "accent"):
            for bg in ("bg", "surface", "sidebar"):
                c = contrast(p[fg], p[bg])
                if c < MIN_CONTRAST:
                    out.append(f"{name}: {fg} on {bg} contrast {c:.2f} < {MIN_CONTRAST}")
        if contrast(p["accent_text"], p["accent"]) < MIN_CONTRAST:
            out.append(f"{name}: accent_text on accent")
    return out


def layout_for(width: int) -> dict[str, Any]:
    """Pure responsive decision used by the shell and by tests."""
    return {"inspector": "stacked" if width < INSPECTOR_STACK_BELOW else "side",
            "sidebar": "compact" if width < SIDEBAR_COMPACT_BELOW else "full"}


def clamp_to_work_area(x: int, y: int, w: int, h: int, area: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Keep a window fully inside the work area (ax, ay, aw, ah); shrink if it cannot fit (§14.1)."""
    ax, ay, aw, ah = area
    w, h = min(w, aw), min(h, ah)
    x = min(max(x, ax), ax + aw - w)
    y = min(max(y, ay), ay + ah - h)
    return x, y, w, h


def apply(style: Any, theme: str) -> dict[str, str]:
    """Configure ttk styles used by the workspace. Returns the palette."""
    p = palette(theme)
    f = (FONT_FAMILY, FONT_SIZES["body"])
    style.configure("WS.TFrame", background=p["bg"])
    style.configure("WS.Surface.TFrame", background=p["surface"])
    style.configure("WS.Sidebar.TFrame", background=p["sidebar"])
    style.configure("WS.TLabel", background=p["bg"], foreground=p["text"], font=f)
    style.configure("WS.Surface.TLabel", background=p["surface"], foreground=p["text"], font=f)
    style.configure("WS.Muted.TLabel", background=p["bg"], foreground=p["muted"], font=(FONT_FAMILY, FONT_SIZES["small"]))
    style.configure("WS.Title.TLabel", background=p["bg"], foreground=p["text"], font=(FONT_FAMILY, FONT_SIZES["title"], "bold"))
    style.configure("WS.Next.TLabel", background=p["surface"], foreground=p["text"],
                    font=(FONT_FAMILY, FONT_SIZES["title"], "bold"))
    for sev in ("blocking", "action", "info", "ok"):
        style.configure(f"WS.{sev}.TLabel", background=p["surface"], foreground=p[sev], font=f)
    style.configure("WS.Nav.TButton", font=f, anchor="w", padding=(SPACING["m"], SPACING["s"]))
    style.configure("WS.NavActive.TButton", font=(FONT_FAMILY, FONT_SIZES["body"], "bold"), anchor="w",
                    padding=(SPACING["m"], SPACING["s"]))
    style.configure("WS.Primary.TButton", font=(FONT_FAMILY, FONT_SIZES["body"], "bold"))
    style.configure("WS.Treeview", font=f, rowheight=22)
    return p
