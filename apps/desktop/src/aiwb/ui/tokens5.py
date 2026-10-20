"""Design tokens of the 5.x look "Mission Map" (roadmap 5.0.0, docs/design/DESIGN_LANGUAGE.md).

The only place where 5.x colours, type and geometry are written down. Views read tokens; they never hard-code a
colour. Midnight (dark, from the owner's reference images) is the default; Daylight mirrors every token.
"""
from __future__ import annotations

import sys
from typing import Any

THEMES5 = ("midnight", "daylight")
DEFAULT_THEME5 = "midnight"
# The 3.x/4.x preference values map onto the 5.x themes (settings.json keeps working).
LEGACY_THEME = {"dark": "midnight", "light": "daylight", "midnight": "midnight", "daylight": "daylight"}

PALETTES5: dict[str, dict[str, str]] = {
    "midnight": {
        "window": "#0f131a", "field": "#10151c", "panel": "#151a23", "raised": "#1b2130", "raised_hi": "#232a3b",
        "line": "#2a3142", "line_soft": "#1d2331", "text": "#e6eaf2", "text_dim": "#9aa3b5", "text_faint": "#5f687b",
        "active": "#2f7bff", "active_hi": "#5b97ff", "active_glow": "#1d5fe0", "active_text": "#ffffff",
        "version": "#5aa9ff", "go": "#22c55e", "go_hi": "#4ade80", "go_deep": "#0f3d26", "source": "#f5c542",
        "source_glow": "#f59e0b", "idle": "#2c313d", "idle_ring": "#4a5263", "done": "#22c55e",
        "warn": "#f59e0b", "danger": "#f43f5e", "bubble_user": "#1f2738", "bubble_ai": "#181e2b",
        "menu": "#1a202d", "menu_border": "#2e3647", "shadow": "#05070b", "selection": "#1e3a6b",
    },
    "daylight": {
        "window": "#f3f5f9", "field": "#fbfcfe", "panel": "#eef1f6", "raised": "#ffffff", "raised_hi": "#e7ecf4",
        "line": "#d5dbe6", "line_soft": "#e6eaf1", "text": "#151a23", "text_dim": "#4f5869", "text_faint": "#8a93a5",
        "active": "#1f66e5", "active_hi": "#3b7bf0", "active_glow": "#7aa7f7", "active_text": "#ffffff",
        "version": "#2563eb", "go": "#16a34a", "go_hi": "#22c55e", "go_deep": "#dcfce7", "source": "#e0a800",
        "source_glow": "#f5c542", "idle": "#e3e7ee", "idle_ring": "#a8b0bf", "done": "#16a34a",
        "warn": "#b45309", "danger": "#e11d48", "bubble_user": "#e6eefc", "bubble_ai": "#ffffff",
        "menu": "#ffffff", "menu_border": "#d5dbe6", "shadow": "#9aa3b5", "selection": "#dbe7fd",
    },
}
ROLES5 = tuple(PALETTES5["midnight"])

UI_FONT = "Segoe UI Variable Text" if sys.platform == "win32" else "Segoe UI"
UI_FONT_FALLBACK = ("Segoe UI", "Helvetica", "Arial")
MONO_FONT = "Cascadia Mono" if sys.platform == "win32" else "DejaVu Sans Mono"
MONO_FALLBACK = ("Consolas", "Courier New")
TYPE5 = {  # role: (family-kind, points, weight)
    "title": ("ui", 11, "bold"), "body": ("ui", 10, "normal"), "small": ("ui", 9, "normal"),
    "caption": ("ui", 8, "normal"), "label_caps": ("ui", 8, "bold"), "capsule": ("ui", 9, "bold"),
    "mono": ("mono", 9, "normal"), "mono_small": ("mono", 8, "normal"), "brand": ("ui", 11, "bold"),
}

GEOMETRY = {
    "rail_w": 64, "toolbar_h": 44, "status_h": 30, "assistant_w": 340, "assistant_hide_below": 1100,
    "lane_gap": 68, "col_gap": 66, "task_r": 11, "task_ring": 2, "hex_r": 12, "source_r": 8,
    "radius_ctl": 6, "radius_bubble": 10, "radius_menu": 10, "grid": 4,
}

MOTION = {"hover_ms": 120, "menu_ms": 180, "page_ms": 240, "grow_ms": 600, "pulse_ms": 1600, "fps": 60}


def theme5(name: str) -> str:
    """5.x theme for a stored preference (old ``light``/``dark`` values keep working)."""
    return LEGACY_THEME.get(str(name), DEFAULT_THEME5)


def palette5(name: str) -> dict[str, str]:
    return dict(PALETTES5[theme5(name)])


def font5(role: str, scale: float = 1.0) -> tuple[Any, ...]:
    kind, size, weight = TYPE5[role]
    family = MONO_FONT if kind == "mono" else UI_FONT
    return (family, max(6, round(size * scale)), weight)


def mix(a: str, b: str, t: float) -> str:
    """Linear blend of two ``#rrggbb`` colours (t = 0 → a, 1 → b); used for hover and fades."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def contrast(fg: str, bg: str) -> float:
    """WCAG contrast ratio of two colours (tests keep text readable in both themes)."""
    def lum(c: str) -> float:
        out = []
        for i in (1, 3, 5):
            v = int(c[i:i + 2], 16) / 255.0
            out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    la, lb = sorted((lum(fg), lum(bg)), reverse=True)
    return (la + 0.05) / (lb + 0.05)
