"""Design System 1.0 rules (GUI roadmap stage 4/5; docs/specs/GUI_DESIGN_SYSTEM_FA.md).

* every palette has the same semantic tokens; legacy aliases still resolve;
* text roles on every surface ≥ 4.5:1, focus / control borders ≥ 3:1 (WCAG 1.4.3, 1.4.11);
* type roles and spacing scale are the only sizes; views contain no raw colours,
  font tuples or ad-hoc ``LabelFrame``/``tk.Text`` without the theme helper.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from aiwb.workspace import theme  # noqa: E402

VIEW_FILES = [SRC / "aiwb/workspace/shell.py"] + sorted((SRC / "aiwb/workspace").glob("view_*.py"))
REQUIRED = {"bg", "surface", "surface_alt", "sidebar", "field", "text", "muted", "border", "border_strong", "divider",
            "selected", "selected_text", "focus", "accent", "accent_text", "accent_hover", "success", "warning",
            "danger", "info", "banner_info", "banner_warning", "banner_danger", "banner_success"}


class DesignTokens(unittest.TestCase):
    def test_palettes_have_all_semantic_tokens(self) -> None:
        keys = [set(p) for p in theme.PALETTES.values()]
        self.assertTrue(all(k == keys[0] for k in keys), "light and dark must define the same tokens")
        self.assertLessEqual(REQUIRED, keys[0])
        for old, new in theme.LEGACY_ALIASES.items():
            for p in theme.PALETTES.values():
                self.assertEqual(p[old], p[new])
        for p in theme.PALETTES.values():
            for v in p.values():
                self.assertRegex(v, r"^#[0-9a-f]{6}$")

    def test_contrast(self) -> None:
        self.assertEqual(theme.contrast_problems(), [])
        self.assertGreaterEqual(theme.contrast("#000000", "#ffffff"), 20.9)

    def test_type_and_spacing_scales(self) -> None:
        self.assertEqual(set(theme.TYPE), {"page_title", "section_title", "body", "secondary", "caption", "code"})
        sizes = [s for s, _ in theme.TYPE.values()]
        self.assertTrue(all(8 <= s <= 16 for s in sizes))
        self.assertGreater(theme.TYPE["page_title"][0], theme.TYPE["section_title"][0])
        self.assertEqual(theme.font("code")[0], theme.CODE_FAMILY)
        self.assertEqual(sorted(theme.SPACE), [0, 1, 2, 3, 4, 6, 8])
        self.assertTrue(all(v == k * 4 for k, v in theme.SPACE.items()))
        self.assertGreaterEqual(theme.CONTROL["row_height"], theme.CONTROL["min_target"])

    def test_layout_tokens(self) -> None:
        self.assertEqual(theme.inspector_width(1366), theme.LAYOUT["inspector_width"])
        self.assertEqual(theme.inspector_width(1100), theme.LAYOUT["inspector_width_narrow"])
        self.assertLess(theme.LAYOUT["inspector_stacked_max"], 0.5)
        self.assertGreaterEqual(theme.MIN_SIZE[0], theme.LAYOUT["sidebar_width"] + theme.LAYOUT["content_min_width"])

    def test_classic_widget_colours_come_from_tokens(self) -> None:
        for name in theme.THEMES:
            c = theme.classic_colours(name)
            p = theme.palette(name)
            self.assertEqual((c["background"], c["foreground"]), (p["field"], p["text"]))
            self.assertEqual(c["highlightcolor"], p["focus"])

    def test_views_use_tokens_only(self) -> None:
        bad = []
        for f in VIEW_FILES:
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#", 1)[0] if not re.search(r"[\"']#[0-9a-fA-F]{3,6}[\"']", line) else line
                if re.search(r"[\"']#[0-9a-fA-F]{3,6}[\"']", code):
                    bad.append(f"{f.name}:{n} raw colour")
                if re.search(r"font=\(\s*[\"']", code):
                    bad.append(f"{f.name}:{n} raw font")
                if re.search(r"(foreground|background|fg|bg)=[\"'][a-z]+[\"']", code):
                    bad.append(f"{f.name}:{n} named colour")
        self.assertEqual(bad, [])

    def test_apply_is_scoped_to_workspace_styles(self) -> None:
        calls = []

        class FakeStyle:
            def theme_use(self, *a):
                return "clam"

            def theme_names(self):
                return ("clam",)

            def configure(self, name, **kw):
                calls.append(name)

            def map(self, name, **kw):
                calls.append(name)

        p = theme.apply(FakeStyle(), "dark")
        self.assertEqual(p["bg"], theme.PALETTES["dark"]["bg"])
        self.assertTrue(calls and all(c.startswith("WS.") for c in calls), [c for c in calls if not c.startswith("WS.")])


if __name__ == "__main__":
    unittest.main()
