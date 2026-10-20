"""Roadmap 5.0.0: the design foundation of the 5.x look — rasteriser, tokens and image assets (pure, no Tk)."""
from __future__ import annotations

import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.ui import raster, tokens5  # noqa: E402
from aiwb.ui.assets import ICONS, icon_png, sprite_png  # noqa: E402


def decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Tiny PNG reader for the tests (RGBA, filter 0 only — what :mod:`raster` writes)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(data):
        ln = int.from_bytes(data[pos:pos + 4], "big")
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            w, h = int.from_bytes(body[:4], "big"), int.from_bytes(body[4:8], "big")
            assert body[8] == 8 and body[9] == 6, "8-bit RGBA expected"
        elif tag == b"IDAT":
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    assert len(raw) == h * (1 + 4 * w)
    return w, h, raw


class RasterTests(unittest.TestCase):
    def test_disc_edge_is_anti_aliased(self):
        r = raster.Raster(40, 40).disc(20, 20, 10.3, "#2f7bff")
        row = raster.coverage_profile(r, 20, range(8, 13))
        self.assertEqual(row[0], 0.0)
        self.assertEqual(row[-1], 1.0)
        self.assertTrue(any(0.0 < a < 1.0 for a in row), row)  # a soft edge, not a staircase

    def test_polygon_fills_inside_for_either_winding(self):
        for pts in (raster.hexagon(20, 20, 14), list(reversed(raster.hexagon(20, 20, 14)))):
            r = raster.Raster(40, 40).polygon(pts, "#22c55e")
            self.assertEqual(r.alpha_at(20, 20), 1.0)
            self.assertEqual(r.alpha_at(1, 1), 0.0)

    def test_png_is_valid_with_real_alpha(self):
        r = raster.Raster(16, 12).disc(8, 6, 4, "#ffffff", 0.5)
        data = r.to_png()
        self.assertEqual(raster.png_size(data), (16, 12))
        w, h, raw = decode_png(data)
        alphas = {raw[y * (1 + 4 * w) + 1 + 4 * x + 3] for y in range(h) for x in range(w)}
        self.assertIn(0, alphas)
        self.assertTrue(any(0 < a < 255 for a in alphas))

    def test_stroke_joints_do_not_darken(self):
        r = raster.Raster(30, 30).stroke([(5, 15), (15, 15), (25, 15)], 3, "#ffffff", 0.5)
        self.assertAlmostEqual(r.alpha_at(15, 15), 0.5, places=3)

    def test_glow_falls_off(self):
        r = raster.Raster(40, 40).glow(20, 20, 2, 18, "#1d5fe0", 0.6)
        self.assertGreater(r.alpha_at(20, 20), r.alpha_at(28, 20))
        self.assertGreater(r.alpha_at(28, 20), r.alpha_at(37, 20))

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            raster.Raster(0, 5)
        with self.assertRaises(ValueError):
            raster.rgb("blue")
        with self.assertRaises(ValueError):
            raster.Raster(5, 5).polygon([(0, 0), (1, 1)], "#000000")


class TokenTests(unittest.TestCase):
    def test_palettes_share_roles(self):
        self.assertEqual(set(tokens5.PALETTES5["midnight"]), set(tokens5.PALETTES5["daylight"]))
        for p in tokens5.PALETTES5.values():
            for v in p.values():
                raster.rgb(v)

    def test_text_is_readable(self):
        for name, p in tokens5.PALETTES5.items():
            for surface in ("window", "panel", "raised", "bubble_ai", "bubble_user", "menu"):
                self.assertGreaterEqual(tokens5.contrast(p["text"], p[surface]), 7.0, (name, surface))
                self.assertGreaterEqual(tokens5.contrast(p["text_dim"], p[surface]), 4.5, (name, surface))

    def test_legacy_theme_values(self):
        self.assertEqual(tokens5.theme5("dark"), "midnight")
        self.assertEqual(tokens5.theme5("light"), "daylight")
        self.assertEqual(tokens5.theme5("nonsense"), tokens5.DEFAULT_THEME5)

    def test_mix_and_fonts(self):
        self.assertEqual(tokens5.mix("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(tokens5.mix("#000000", "#ffffff", 5), "#ffffff")
        self.assertEqual(tokens5.font5("body", 2.0)[1], 20)
        self.assertEqual(tokens5.font5("mono")[0], tokens5.MONO_FONT)

    def test_grid(self):
        for k in ("rail_w", "toolbar_h", "lane_gap"):
            self.assertEqual(tokens5.GEOMETRY[k] % tokens5.GEOMETRY["grid"], 0, k)


class AssetTests(unittest.TestCase):
    SPRITES = ("task_active", "task_idle", "task_done", "task_selected", "task_blocked", "task_attention",
               "task_hover", "hex", "source", "capsule", "particle", "dot", "avatar")

    def test_every_sprite_in_both_themes_and_scales(self):
        for theme in tokens5.THEMES5:
            for scale in (1.0, 1.5, 2.0):
                for name in self.SPRITES:
                    data, w, h = sprite_png(name, theme, scale)
                    self.assertEqual(raster.png_size(data), (w, h), name)
        a1, a2 = sprite_png("task_idle", scale=1.0), sprite_png("task_idle", scale=2.0)
        self.assertAlmostEqual(a2[1] / a1[1], 2.0, delta=0.15)

    def test_parametric_sprites(self):
        data, w, h = sprite_png("panel", w=120, h=40, r=10, role="menu", border="menu_border", shadow=6)
        self.assertEqual((w, h), (132, 52))
        data, w, h = sprite_png("branch", w=60, h=200, y0=4, y1=190, lit=True)
        self.assertEqual((w, h), (60, 200))

    def test_icons(self):
        self.assertGreaterEqual(len(ICONS), 15)
        for name in ICONS:
            self.assertEqual(raster.png_size(icon_png(name, 20, "#e6eaf2")), (20, 20), name)
        with self.assertRaises(KeyError):
            icon_png("nope", 20, "#ffffff")
        with self.assertRaises(KeyError):
            sprite_png("nope")


if __name__ == "__main__":
    unittest.main()
