"""Unit tests for the 3.0.0 single shell: application-wide preferences and layout helpers."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from aiwb.ui.prefs import AppPrefs  # noqa: E402
from aiwb.ui import shell as ui_shell  # noqa: E402


class AppPrefsTests(unittest.TestCase):
    def test_defaults_and_invalid_values(self) -> None:
        p = AppPrefs({"ui_theme": "neon", "ui_lang": "xx", "ui_mode": "god"})
        self.assertEqual((p.theme, p.lang, p.mode), ("light", "en", "simple"))

    def test_loads_saved_values(self) -> None:
        p = AppPrefs({"ui_theme": "dark", "ui_lang": "fa", "ui_mode": "advanced"})
        self.assertTrue(p.rtl and p.advanced)
        self.assertEqual(p.tr(("Home", "خانه")), "خانه")

    def test_change_notifies_and_saves_once(self) -> None:
        saved, seen = [], []
        p = AppPrefs({}, save=saved.append)
        p.subscribe(seen.append)
        p.set_theme("dark")
        p.set_theme("dark")  # no-op
        p.set_lang("fa")
        p.set_mode("advanced")
        self.assertEqual(seen, ["theme", "lang", "mode"])
        self.assertEqual(saved[-1], {"ui_theme": "dark", "ui_lang": "fa", "ui_mode": "advanced"})

    def test_unsubscribe(self) -> None:
        seen = []
        p = AppPrefs({})
        off = p.subscribe(seen.append)
        off()
        p.set_theme("dark")
        self.assertEqual(seen, [])

    def test_rejects_unknown(self) -> None:
        p = AppPrefs({})
        for fn, v in ((p.set_theme, "blue"), (p.set_lang, "de"), (p.set_mode, "pro")):
            with self.assertRaises(ValueError):
                fn(v)


class ShellModelTests(unittest.TestCase):
    def test_every_nav_page_is_defined_and_settings_is_last(self) -> None:
        for key in ui_shell.NAV_ORDER:
            self.assertIn(key, ui_shell.PAGES)
        self.assertIn("settings", ui_shell.PAGES)
        self.assertNotIn("settings", ui_shell.NAV_ORDER)

    def test_simple_mode_keeps_the_guided_path(self) -> None:
        simple = [k for k, v in ui_shell.PAGES.items() if not v[3]]
        for key in ("home", "workbench", "prompt", "response", "settings"):
            self.assertIn(key, simple)
        for key in ("git", "run", "profile"):
            self.assertNotIn(key, simple)

    def test_no_raw_colours_in_ui_package(self) -> None:
        for name in ("shell.py", "prefs.py"):
            text = (SRC / "aiwb" / "ui" / name).read_text(encoding="utf-8")
            self.assertEqual(re.findall(r"#[0-9A-Fa-f]{6}", text), [], name)

    def test_vendored_theme_is_complete(self) -> None:
        base = SRC / "aiwb" / "ui" / "sv_theme"
        for rel in ("sv.tcl", "LICENSE", "theme/light.tcl", "theme/dark.tcl", "theme/sprites_light.tcl",
                    "theme/sprites_dark.tcl", "theme/spritesheet_light.png", "theme/spritesheet_dark.png"):
            self.assertTrue((base / rel).is_file(), rel)
        self.assertIn("MIT", (base / "LICENSE").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
