"""Image cache of the 5.x look (roadmap 5.0.0): sprites and line icons drawn by :mod:`raster`, per theme and scale.

Every image is made once per (name, theme, scale, args) and kept for the life of the Tk interpreter, so redraws
and animations only move canvas items. :func:`sprite_png` is pure (no Tk) and unit-tested; :class:`Assets` turns
the PNG into a ``tk.PhotoImage``.

Icons are designed on a 24-unit grid with 1.75-unit round strokes (the outline style of the reference images).
"""
from __future__ import annotations

import math
import tkinter as tk
from typing import Any, Callable

from .raster import Raster, arc, bezier, hexagon
from .tokens5 import GEOMETRY, palette5, theme5

Strokes = list[list[tuple[float, float]]]


# -- icons (24×24 design grid) ----------------------------------------------------------------------
def _rect(x0: float, y0: float, x1: float, y1: float, r: float) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    pts += arc(x1 - r, y0 + r, r, 90, 0, 6)
    pts += arc(x1 - r, y1 - r, r, 0, -90, 6)
    pts += arc(x0 + r, y1 - r, r, -90, -180, 6)
    pts += arc(x0 + r, y0 + r, r, 180, 90, 6)
    return pts + [pts[0]]


ICONS: dict[str, Callable[[], Strokes]] = {
    "home": lambda: [[(3.5, 11), (12, 3.8), (20.5, 11)], [(5.5, 9.5), (5.5, 20), (18.5, 20), (18.5, 9.5)],
                     [(10, 20), (10, 14.5), (14, 14.5), (14, 20)]],
    "projects": lambda: [[(3, 7), (3, 19), (21, 19), (21, 9), (11.5, 9), (9.5, 6), (3, 6), (3, 7)],
                         [(3, 11), (21, 11)]],
    "agents": lambda: [_rect(5, 8, 19, 19, 3), [(12, 8), (12, 4.5)], arc(12, 4, 0.9, 0, 360, 10),
                       [(9.3, 12.5), (9.3, 13.8)], [(14.7, 12.5), (14.7, 13.8)], [(9.5, 16.3), (14.5, 16.3)],
                       [(3, 12), (3, 15)], [(21, 12), (21, 15)]],
    "history": lambda: [arc(12, 12, 8.5, 140, -220, 40), [(12, 7.5), (12, 12), (15.2, 14)],
                        [(3.2, 7.6), (4.6, 10.9), (7.9, 9.6)]],
    "settings": lambda: [arc(12, 12, 3, 0, 360, 24)] + [
        [(12 + 6.2 * math.cos(math.radians(a)), 12 + 6.2 * math.sin(math.radians(a))),
         (12 + 8.8 * math.cos(math.radians(a)), 12 + 8.8 * math.sin(math.radians(a)))] for a in range(0, 360, 45)]
        + [arc(12, 12, 6.2, 0, 360, 32)],
    "plus_circle": lambda: [arc(12, 12, 8.5, 0, 360, 40), [(12, 8), (12, 16)], [(8, 12), (16, 12)]],
    "open": lambda: [[(3, 19), (3, 5.5), (9.5, 5.5), (11.5, 8), (19, 8), (19, 10.5)],
                     [(3, 19), (6.3, 11.2), (21.5, 11.2), (18.2, 19), (3, 19)]],
    "save": lambda: [_rect(4, 4, 20, 20, 2.2), [(8, 4), (8, 9), (15, 9), (15, 4)], [(7.5, 20), (7.5, 14), (16.5, 14), (16.5, 20)]],
    "run": lambda: [[(7, 4.5), (19, 12), (7, 19.5), (7, 4.5)]],
    "copy": lambda: [_rect(8, 7, 19, 21, 2), [(16, 7), (16, 4.8), (14.8, 3.5), (6.2, 3.5), (5, 4.8), (5, 16.8), (6.2, 18), (8, 18)]],
    "send": lambda: [[(21, 3), (3, 10.5), (10.2, 13.8), (13.5, 21), (21, 3)], [(21, 3), (10.2, 13.8)]],
    "sparkle": lambda: [[(10, 3.5), (11.6, 8.4), (16.5, 10), (11.6, 11.6), (10, 16.5), (8.4, 11.6), (3.5, 10),
                         (8.4, 8.4), (10, 3.5)], [(18, 14), (18.8, 16.2), (21, 17), (18.8, 17.8), (18, 20), (17.2, 17.8),
                                                  (15, 17), (17.2, 16.2), (18, 14)]],
    "check": lambda: [[(4.5, 12.5), (9.5, 17.5), (19.5, 6.5)]],
    "chevron_right": lambda: [[(9, 5.5), (15.5, 12), (9, 18.5)]],
    "chevron_down": lambda: [[(6.5, 9.5), (12, 15), (17.5, 9.5)]],
    "dots": lambda: [arc(6, 12, 0.6, 0, 360, 8), arc(12, 12, 0.6, 0, 360, 8), arc(18, 12, 0.6, 0, 360, 8)],
    "tools": lambda: [[(14.5, 6.5), (17.5, 3.5), (20.5, 6.5), (17.5, 9.5)], [(17.5, 6.5), (5, 19)],
                      [(4, 4), (9, 9)], [(15, 15), (20, 20)], [(3.5, 7), (7, 3.5)]],
    "bell": lambda: [[(6, 17), (6, 11), (7.5, 7), (12, 5), (16.5, 7), (18, 11), (18, 17), (19.5, 18.5), (4.5, 18.5), (6, 17)],
                     [(10, 21), (14, 21)]],
}


def icon_png(name: str, size: int, color: str, stroke: float = 1.75) -> bytes:
    """A line icon as PNG, ``size`` pixels square, drawn from the 24-unit design grid."""
    if name not in ICONS:
        raise KeyError(f"unknown icon {name!r}")
    k = size / 24.0
    r = Raster(size, size)
    width = max(1.2, stroke * k)
    for path in ICONS[name]():
        r.stroke([(x * k, y * k) for x, y in path], width, color)
    return r.to_png()


# -- sprites -----------------------------------------------------------------------------------------
def sprite_png(name: str, theme: str = "midnight", scale: float = 1.0, **kw: Any) -> tuple[bytes, int, int]:
    """Draw one sprite. Returns (png, width, height). Sizes follow :data:`GEOMETRY` × ``scale``."""
    p = palette5(theme)
    s = scale
    g = GEOMETRY
    if name.startswith("task_"):
        state = name[5:]
        r_ = g["task_r"] * s
        pad = 14 * s if state in ("active", "selected", "hover") else 4 * s
        size = int(math.ceil(2 * (r_ + pad)))
        c = size / 2.0
        im = Raster(size, size)
        if state in ("active", "selected", "hover"):
            im.glow(c, c, r_ * 0.6, r_ + pad, p["active_glow"], 0.55 if state != "hover" else 0.4)
            im.disc(c, c, r_, p["active"])
            im.ring(c, c, r_ - 0.6 * s, 1.6 * s, p["active_hi"], 0.9)
            if state == "selected":
                im.ring(c, c, r_ + 4.5 * s, 1.5 * s, p["active_hi"], 0.9)
        elif state == "done":
            im.disc(c, c, r_, p["go_deep"])
            im.ring(c, c, r_ - 0.8 * s, 1.6 * s, p["done"])
            k = r_ / 9.0
            im.stroke([(c - 4 * k, c + 0.2 * k), (c - 1.2 * k, c + 3 * k), (c + 4.4 * k, c - 3 * k)], 1.8 * s, p["done"])
        elif state == "blocked":
            im.disc(c, c, r_, p["idle"])
            im.ring(c, c, r_ - 0.8 * s, 1.6 * s, p["danger"])
            im.stroke([(c - 4 * s, c), (c + 4 * s, c)], 1.8 * s, p["danger"])
        elif state == "attention":
            im.disc(c, c, r_, p["idle"])
            im.ring(c, c, r_ - 0.8 * s, 1.6 * s, p["warn"])
            im.disc(c, c, 2.4 * s, p["warn"])
        else:  # idle / future
            im.disc(c, c, r_, p["idle"])
            im.ring(c, c, r_ - 0.8 * s, 1.6 * s, p["idle_ring"])
        return im.to_png(), size, size
    if name == "hex":
        r_ = g["hex_r"] * s
        size = int(math.ceil(2 * r_ + 6 * s))
        c = size / 2.0
        im = Raster(size, size)
        im.glow(c, c, r_ * 0.7, r_ + 3 * s, p["go"], 0.18)
        im.polygon(hexagon(c, c, r_), p["go"])
        im.polygon(hexagon(c, c, r_ - 1.6 * s), p["go_deep"])
        return im.to_png(), size, size
    if name == "source":
        r_ = g["source_r"] * s
        pad = 12 * s
        size = int(math.ceil(2 * (r_ + pad)))
        c = size / 2.0
        im = Raster(size, size)
        im.glow(c, c, r_ * 0.5, r_ + pad, p["source_glow"], 0.5)
        im.disc(c, c, r_, p["source"])
        im.disc(c - r_ * 0.3, c - r_ * 0.3, r_ * 0.35, "#fff6d5", 0.65)
        return im.to_png(), size, size
    if name == "capsule":
        w, h = int(kw.get("w", 92) * s), int(26 * s)
        im = Raster(w + int(8 * s), h + int(8 * s))
        o = 4 * s
        im.round_rect(o - 2 * s, o - 2 * s, w + o + 2 * s, h + o + 2 * s, h, p["go"], 0.12)
        im.round_rect(o, o, w + o, h + o, h / 2, p["go_deep"])
        im.round_rect_outline(o, o, w + o, h + o, h / 2, 1.6 * s, p["go"])
        return im.to_png(), im.w, im.h
    if name == "particle":
        size = int(math.ceil(12 * s))
        im = Raster(size, size)
        im.glow(size / 2, size / 2, 0.5 * s, size / 2, p[kw.get("role", "active_hi")], 0.9)
        im.disc(size / 2, size / 2, 1.3 * s, "#ffffff", 0.85)
        return im.to_png(), size, size
    if name == "panel":  # rounded surface used for bubbles, menus, buttons
        w, h = int(kw["w"]), int(kw["h"])
        rad = float(kw.get("r", g["radius_bubble"])) * s
        role, border = kw.get("role", "raised"), kw.get("border", "")
        shadow = int(kw.get("shadow", 0) * s)
        im = Raster(w + 2 * shadow, h + 2 * shadow)
        if shadow:
            for i in range(shadow, 0, -1):
                im.round_rect(shadow - i, shadow - i + i * 0.5, w + shadow + i, h + shadow + i, rad + i, p["shadow"],
                              0.05)
        im.round_rect(shadow, shadow, w + shadow, h + shadow, rad, p[role])
        if border:
            im.round_rect_outline(shadow, shadow, w + shadow, h + shadow, rad, max(1.0, s), p[border])
        return im.to_png(), im.w, im.h
    if name == "branch":  # curved connector from (0, y0) to (w, y1), drawn inside a w×h box
        w, h = int(kw["w"]), int(kw["h"])
        y0, y1 = float(kw["y0"]), float(kw["y1"])
        im = Raster(max(1, w), max(1, h))
        pts = bezier((0, y0), (w * 0.45, y0), (w * 0.35, y1), (w, y1))
        if kw.get("lit"):
            im.soft_stroke(pts, 1.4 * s, 3.5 * s, p["active_glow"], 0.35)
        im.stroke(pts, 1.4 * s, p[kw.get("role", "text_faint")], float(kw.get("alpha", 1.0)))
        return im.to_png(), im.w, im.h
    if name == "dot":
        size = int(math.ceil(10 * s))
        im = Raster(size, size)
        im.glow(size / 2, size / 2, 2 * s, size / 2, p[kw.get("role", "go")], 0.35)
        im.disc(size / 2, size / 2, 3.2 * s, p[kw.get("role", "go")])
        return im.to_png(), size, size
    if name == "avatar":
        size = int(math.ceil(30 * s))
        im = Raster(size, size)
        c = size / 2
        im.disc(c, c, c - 0.5, p["raised_hi"])
        im.disc(c, c * 0.8, c * 0.36, p["text_dim"])
        im.fill_sdf(lambda x, y: max(math.hypot(x - c, y - c * 1.9) - c * 0.78, math.hypot(x - c, y - c) - (c - 0.5)),
                    p["text_dim"])
        im.ring(c, c, c - 1, 1.2 * s, p["line"])
        return im.to_png(), size, size
    raise KeyError(f"unknown sprite {name!r}")


class Assets:
    """Per-interpreter cache of PhotoImages for the current theme and scale."""

    def __init__(self, widget: tk.Misc, theme: str = "midnight", scale: float = 1.0) -> None:
        self.widget = widget
        self.theme = theme5(theme)
        self.scale = scale
        self._cache: dict[tuple[Any, ...], tk.PhotoImage] = {}

    def set_theme(self, theme: str) -> None:
        theme = theme5(theme)
        if theme != self.theme:
            self.theme = theme
            self._cache.clear()

    def _photo(self, key: tuple[Any, ...], make: Callable[[], bytes]) -> tk.PhotoImage:
        img = self._cache.get(key)
        if img is None:
            import base64
            img = tk.PhotoImage(master=self.widget, data=base64.b64encode(make()).decode("ascii"), format="png")
            self._cache[key] = img
        return img

    def sprite(self, name: str, **kw: Any) -> tk.PhotoImage:
        key = ("s", name, self.theme, self.scale, tuple(sorted(kw.items())))
        return self._photo(key, lambda: sprite_png(name, self.theme, self.scale, **kw)[0])

    def icon(self, name: str, size: int = 20, role: str = "text_dim", color: str = "") -> tk.PhotoImage:
        px = max(8, round(size * self.scale))
        col = color or palette5(self.theme)[role]
        return self._photo(("i", name, px, col), lambda: icon_png(name, px, col))

    def __len__(self) -> int:
        return len(self._cache)
