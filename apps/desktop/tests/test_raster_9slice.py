"""Roadmap 5.16.0 (R4): panel sprites are drawn small and 9-sliced — same pixels, size-independent cost."""
from __future__ import annotations

import struct
import sys
import time
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.ui.assets import sprite_png  # noqa: E402
from aiwb.ui.raster import Raster, png_size  # noqa: E402
from aiwb.ui.tokens5 import GEOMETRY, palette5  # noqa: E402


def _pixels(png: bytes) -> tuple[int, int, bytes]:
    i, idat, w, h = 8, b"", 0, 0
    while i < len(png):
        n = struct.unpack(">I", png[i:i + 4])[0]
        tag, data = png[i + 4:i + 8], png[i + 8:i + 8 + n]
        if tag == b"IHDR":
            w, h = struct.unpack(">II", data[:8])
        elif tag == b"IDAT":
            idat += data
        i += 12 + n
    return w, h, zlib.decompress(idat)


def _full_panel(w: int, h: int, r: float, role: str, border: str, shadow_u: float, s: float) -> bytes:
    """The pre-5.16 drawing: every pixel of the full-size image through the SDF rasteriser."""
    p = palette5("midnight")
    rad, shadow = float(r) * s, int(shadow_u * s)
    im = Raster(w + 2 * shadow, h + 2 * shadow)
    for i in range(shadow, 0, -1):
        im.round_rect(shadow - i, shadow - i + i * 0.5, w + shadow + i, h + shadow + i, rad + i, p["shadow"], 0.05)
    im.round_rect(shadow, shadow, w + shadow, h + shadow, rad, p[role])
    if border:
        im.round_rect_outline(shadow, shadow, w + shadow, h + shadow, rad, max(1.0, s), p[border])
    return im.to_png()


CASES = [
    (220, 180, GEOMETRY["radius_menu"], "menu", "menu_border", 10, 1.0),
    (220, 180, GEOMETRY["radius_menu"], "menu", "menu_border", 10, 1.5),
    (120, 40, 8, "raised", "", 0, 1.0),
    (30, 20, 12, "raised", "line", 4, 2.0),
    (300, 36, GEOMETRY["radius_bubble"], "raised", "", 6, 1.25),
]


class NineSliceTest(unittest.TestCase):
    def test_same_pixels_as_full_drawing(self) -> None:
        for w, h, r, role, border, sh, s in CASES:
            with self.subTest(w=w, h=h, s=s, shadow=sh):
                png, W, H = sprite_png("panel", "midnight", s, w=w, h=h, r=r, role=role, border=border, shadow=sh)
                self.assertEqual(png_size(png), (W, H))
                self.assertEqual(_pixels(png), _pixels(_full_panel(w, h, r, role, border, sh, s)))

    def test_cost_does_not_grow_with_size(self) -> None:
        r = GEOMETRY["radius_menu"]
        t0 = time.perf_counter()
        sprite_png("panel", "midnight", 1.0, w=260, h=420, r=r, role="menu", border="menu_border", shadow=10)
        big = time.perf_counter() - t0
        self.assertLess(big, 0.25, f"menu panel took {big * 1000:.0f} ms (budget 250 ms; was ~700 ms before 5.16)")

    def test_to_png_9slice_rejects_bad_targets(self) -> None:
        im = Raster(9, 9).round_rect(0, 0, 9, 9, 3, "#ffffff")
        with self.assertRaises(ValueError):
            im.to_png_9slice(8, 20, 4, 4)
        with self.assertRaises(ValueError):
            im.to_png_9slice(20, 20, 9, 4)
        self.assertEqual(png_size(im.to_png_9slice(40, 30, 4, 4)), (40, 30))
        self.assertEqual(im.to_png_9slice(9, 9, 4, 4), im.to_png())


if __name__ == "__main__":
    unittest.main()
