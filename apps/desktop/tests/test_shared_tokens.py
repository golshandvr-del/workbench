"""Roadmap 6.0.0: packages/design/tokens5.json is the desktop tokens5 written out for the mobile app (parity gate)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "desktop" / "src"))

from aiwb.ui import structure5, tokens5  # noqa: E402

JSON = ROOT / "packages" / "design" / "tokens5.json"


class SharedTokensTest(unittest.TestCase):
    def setUp(self) -> None:
        self.d = json.loads(JSON.read_text(encoding="utf-8"))

    def test_palettes_equal_desktop(self) -> None:
        self.assertEqual(self.d["palettes"], tokens5.PALETTES5)
        self.assertEqual(self.d["default_theme"], tokens5.DEFAULT_THEME5)
        self.assertEqual(self.d["themes"], list(tokens5.THEMES5))

    def test_type_geometry_motion_equal_desktop(self) -> None:
        self.assertEqual({k: (v["kind"], v["pt"], v["weight"]) for k, v in self.d["type"].items()}, tokens5.TYPE5)
        self.assertEqual(self.d["geometry"], tokens5.GEOMETRY)
        self.assertEqual(self.d["motion"], tokens5.MOTION)

    def test_rail_equal_desktop(self) -> None:
        self.assertEqual([(r["key"], r["label"], r["icon"]) for r in self.d["rail"]],
                         [(k, label, i) for k, label, i, _s in structure5.RAIL])


if __name__ == "__main__":
    unittest.main()
