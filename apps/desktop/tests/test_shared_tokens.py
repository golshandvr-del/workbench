"""Roadmap 6.0.0: packages/design/tokens5.json is the desktop tokens5 written out for the mobile app (parity gate)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent))  # installed copy: tests sit next to aiwb/

from aiwb.ui import structure5, tokens5  # noqa: E402

JSON = next((p / "packages" / "design" / "tokens5.json" for p in HERE.parents
             if (p / "packages" / "design" / "tokens5.json").is_file()), None)


@unittest.skipIf(JSON is None, "packages/design/tokens5.json is only in the repository (not in an installed copy)")
class SharedTokensTest(unittest.TestCase):
    def setUp(self) -> None:
        assert JSON is not None
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
        """The shared tokens feed the phone: its bottom bar is structure5.MOBILE_BAR (5.13.0: the desktop rail is four)."""
        self.assertEqual([(r["key"], r["label"], r["icon"]) for r in self.d["rail"]], list(structure5.MOBILE_BAR))
        desktop = {k for k, _l, _i, _s in structure5.RAIL}
        self.assertTrue(desktop <= {k for k, _l, _i in structure5.MOBILE_BAR})


if __name__ == "__main__":
    unittest.main()
