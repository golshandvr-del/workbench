"""Anti-aliased shape rasteriser for the 5.x look (roadmap 5.0.0, docs/design/DESIGN_LANGUAGE.md §8).

Tk on Windows draws canvas ovals, polygons and lines without anti-aliasing, which is the main reason the old UI
looked rough. This module draws soft shapes in pure Python — signed-distance fields with analytic edge coverage
for filled shapes and capsule-distance stamping for strokes — into an RGBA buffer and encodes it as a PNG with
real alpha (``zlib`` + ``struct`` only). ``tk.PhotoImage(data=…)`` loads the PNG natively (Tk 8.6), so the
canvas only *places* images: crisp at every DPI, fast to redraw, no Pillow needed at run time.

Coordinates are pixels of the final image; callers multiply design units by the DPI scale. Colours are
``"#rrggbb"``; ``alpha`` is 0…1. Buffers are premultiplied floats.
"""
from __future__ import annotations

import base64
import math
import struct
import zlib
from typing import Callable, Iterable, Sequence

Point = tuple[float, float]


def rgb(color: str) -> tuple[float, float, float]:
    c = color.lstrip("#")
    if len(c) != 6:
        raise ValueError(f"colour must be #rrggbb, not {color!r}")
    return int(c[0:2], 16) / 255.0, int(c[2:4], 16) / 255.0, int(c[4:6], 16) / 255.0


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def _seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else _clamp(((px - ax) * dx + (py - ay) * dy) / ll)
    qx, qy = ax + t * dx - px, ay + t * dy - py
    return math.sqrt(qx * qx + qy * qy)


def bezier(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 0) -> list[Point]:
    """Points of a cubic Bézier curve (enough steps for a smooth stroke)."""
    if steps <= 0:
        approx = sum(math.dist(a, b) for a, b in ((p0, p1), (p1, p2), (p2, p3)))
        steps = max(8, int(approx / 3))
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]))
    return out


def arc(cx: float, cy: float, r: float, a0: float, a1: float, steps: int = 0) -> list[Point]:
    """Points of a circular arc; angles in degrees, 0 = east, counter-clockwise on screen (y down → negated)."""
    if steps <= 0:
        steps = max(6, int(abs(a1 - a0) / 6))
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
             cy - r * math.sin(math.radians(a0 + (a1 - a0) * i / steps))) for i in range(steps + 1)]


class Raster:
    """An RGBA image (premultiplied floats) with anti-aliased drawing operations."""

    def __init__(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("raster size must be positive")
        self.w, self.h = int(width), int(height)
        self.px = [0.0] * (self.w * self.h * 4)

    # -- low level ---------------------------------------------------------------------------------
    def blend(self, x: int, y: int, color: tuple[float, float, float], a: float) -> None:
        if a <= 0.0 or not (0 <= x < self.w and 0 <= y < self.h):
            return
        i = (y * self.w + x) * 4
        p = self.px
        k = 1.0 - a
        p[i] = color[0] * a + p[i] * k
        p[i + 1] = color[1] * a + p[i + 1] * k
        p[i + 2] = color[2] * a + p[i + 2] * k
        p[i + 3] = a + p[i + 3] * k

    def alpha_at(self, x: int, y: int) -> float:
        return self.px[(y * self.w + x) * 4 + 3]

    def color_at(self, x: int, y: int) -> tuple[int, int, int, int]:
        i = (y * self.w + x) * 4
        a = self.px[i + 3]
        if a <= 0:
            return 0, 0, 0, 0
        return (round(_clamp(self.px[i] / a) * 255), round(_clamp(self.px[i + 1] / a) * 255),
                round(_clamp(self.px[i + 2] / a) * 255), round(_clamp(a) * 255))

    def fill_sdf(self, sdf: Callable[[float, float], float], color: str, alpha: float = 1.0,
                 box: tuple[float, float, float, float] | None = None) -> None:
        """Fill where ``sdf(x, y) < 0`` with a one-pixel anti-aliased edge (coverage = 0.5 − distance)."""
        c = rgb(color)
        x0, y0, x1, y1 = box or (0, 0, self.w, self.h)
        for y in range(max(0, int(y0) - 1), min(self.h, int(math.ceil(y1)) + 1)):
            cy = y + 0.5
            for x in range(max(0, int(x0) - 1), min(self.w, int(math.ceil(x1)) + 1)):
                cov = 0.5 - sdf(x + 0.5, cy)
                if cov > 0.0:
                    self.blend(x, y, c, (1.0 if cov >= 1.0 else cov) * alpha)

    # -- shapes ------------------------------------------------------------------------------------
    def disc(self, cx: float, cy: float, r: float, color: str, alpha: float = 1.0) -> "Raster":
        self.fill_sdf(lambda x, y: math.hypot(x - cx, y - cy) - r, color, alpha, (cx - r, cy - r, cx + r, cy + r))
        return self

    def ring(self, cx: float, cy: float, r: float, width: float, color: str, alpha: float = 1.0) -> "Raster":
        half = width / 2.0
        self.fill_sdf(lambda x, y: abs(math.hypot(x - cx, y - cy) - r) - half, color, alpha,
                      (cx - r - half, cy - r - half, cx + r + half, cy + r + half))
        return self

    def glow(self, cx: float, cy: float, r0: float, r1: float, color: str, strength: float = 0.6) -> "Raster":
        """Soft light: full ``strength`` inside ``r0``, falling off smoothly (quadratic) to zero at ``r1``."""
        c = rgb(color)
        span = max(0.001, r1 - r0)
        for y in range(max(0, int(cy - r1) - 1), min(self.h, int(cy + r1) + 2)):
            for x in range(max(0, int(cx - r1) - 1), min(self.w, int(cx + r1) + 2)):
                d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                if d < r1:
                    t = 0.0 if d <= r0 else (d - r0) / span
                    self.blend(x, y, c, strength * (1.0 - t) * (1.0 - t))
        return self

    def round_rect(self, x0: float, y0: float, x1: float, y1: float, radius: float, color: str,
                   alpha: float = 1.0) -> "Raster":
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        hx, hy = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        r = min(radius, hx, hy)

        def sdf(x: float, y: float) -> float:
            qx, qy = abs(x - cx) - hx + r, abs(y - cy) - hy + r
            return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r
        self.fill_sdf(sdf, color, alpha, (x0, y0, x1, y1))
        return self

    def round_rect_outline(self, x0: float, y0: float, x1: float, y1: float, radius: float, width: float,
                           color: str, alpha: float = 1.0) -> "Raster":
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        hx, hy = (x1 - x0) / 2.0 - width / 2.0, (y1 - y0) / 2.0 - width / 2.0
        r = max(0.0, min(radius - width / 2.0, hx, hy))

        def sdf(x: float, y: float) -> float:
            qx, qy = abs(x - cx) - hx + r, abs(y - cy) - hy + r
            return abs(math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r) - width / 2.0
        self.fill_sdf(sdf, color, alpha, (x0, y0, x1, y1))
        return self

    def polygon(self, pts: Sequence[Point], color: str, alpha: float = 1.0) -> "Raster":
        """Fill a convex polygon (any winding)."""
        n = len(pts)
        if n < 3:
            raise ValueError("a polygon needs 3 points")
        area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
        sign = -1.0 if area > 0 else 1.0  # inward normals for either winding
        edges = []
        for i in range(n):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            ln = math.hypot(bx - ax, by - ay) or 1.0
            edges.append((ax, ay, (by - ay) / ln * sign, -(bx - ax) / ln * sign))

        def sdf(x: float, y: float) -> float:
            return max(-((x - ax) * nx + (y - ay) * ny) for ax, ay, nx, ny in edges)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.fill_sdf(sdf, color, alpha, (min(xs), min(ys), max(xs), max(ys)))
        return self

    def stroke(self, pts: Sequence[Point], width: float, color: str, alpha: float = 1.0) -> "Raster":
        """A round-capped polyline. Overlaps keep the maximum coverage, so joints never darken."""
        if len(pts) == 1:
            pts = [pts[0], pts[0]]
        half = width / 2.0
        cov: dict[int, float] = {}
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            for y in range(max(0, int(min(ay, by) - half) - 1), min(self.h, int(max(ay, by) + half) + 2)):
                for x in range(max(0, int(min(ax, bx) - half) - 1), min(self.w, int(max(ax, bx) + half) + 2)):
                    v = half + 0.5 - _seg_dist(x + 0.5, y + 0.5, ax, ay, bx, by)
                    if v > 0.0:
                        k = y * self.w + x
                        if v > cov.get(k, 0.0):
                            cov[k] = 1.0 if v > 1.0 else v
        c = rgb(color)
        for k, v in cov.items():
            self.blend(k % self.w, k // self.w, c, v * alpha)
        return self

    def soft_stroke(self, pts: Sequence[Point], width: float, spread: float, color: str, strength: float) -> "Raster":
        """A blurred stroke (light along a path): full inside ``width/2``, fading to zero at ``width/2 + spread``."""
        half = width / 2.0
        reach = half + spread
        cov: dict[int, float] = {}
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            for y in range(max(0, int(min(ay, by) - reach) - 1), min(self.h, int(max(ay, by) + reach) + 2)):
                for x in range(max(0, int(min(ax, bx) - reach) - 1), min(self.w, int(max(ax, bx) + reach) + 2)):
                    d = _seg_dist(x + 0.5, y + 0.5, ax, ay, bx, by)
                    if d < reach:
                        t = 0.0 if d <= half else (d - half) / spread
                        v = (1.0 - t) * (1.0 - t)
                        k = y * self.w + x
                        if v > cov.get(k, 0.0):
                            cov[k] = v
        c = rgb(color)
        for k, v in cov.items():
            self.blend(k % self.w, k // self.w, c, v * strength)
        return self

    # -- output ------------------------------------------------------------------------------------
    def to_png(self) -> bytes:
        rows = bytearray()
        p = self.px
        for y in range(self.h):
            rows.append(0)
            base = y * self.w * 4
            for x in range(self.w):
                i = base + x * 4
                a = p[i + 3]
                if a <= 0.0:
                    rows += b"\x00\x00\x00\x00"
                    continue
                inv = 1.0 / a
                rows.append(int(_clamp(p[i] * inv) * 255 + 0.5))
                rows.append(int(_clamp(p[i + 1] * inv) * 255 + 0.5))
                rows.append(int(_clamp(p[i + 2] * inv) * 255 + 0.5))
                rows.append(int(_clamp(a) * 255 + 0.5))

        def chunk(tag: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b""))

    def to_base64(self) -> str:
        return base64.b64encode(self.to_png()).decode("ascii")


def hexagon(cx: float, cy: float, r: float, pointy: bool = False) -> list[Point]:
    """Six corners of a regular hexagon (flat top by default, as in the reference images)."""
    start = 30 if pointy else 0
    return [(cx + r * math.cos(math.radians(start + 60 * i)), cy + r * math.sin(math.radians(start + 60 * i)))
            for i in range(6)]


def png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


def coverage_profile(r: Raster, y: int, xs: Iterable[int]) -> list[float]:
    """Alpha values along a row (test helper: proves edges are soft, not stair-stepped)."""
    return [round(r.alpha_at(x, y), 3) for x in xs]
