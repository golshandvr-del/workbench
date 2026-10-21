"""Roadmap 5.5.0: balance rules of the App Map (aiwb/ui/ui_map.audit) — on fixtures and on docs/UI_MAP.md."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aiwb.ui import ui_map  # noqa: E402

DOC = Path(__file__).resolve().parents[3] / "docs" / "UI_MAP.md"
n = ui_map.node


def rail(*pages: dict) -> dict:
    return n("AI Workbench", "app", [n("Rail", "area", list(pages))])


def page(label: str, k: int) -> dict:
    return n(label, "page", [n("S", "section", [n(f"{label} c{i}", "button") for i in range(k)])])


class RuleTests(unittest.TestCase):
    def test_balanced_fixture_passes(self):
        self.assertEqual(ui_map.audit(rail(page("A", 4), page("B", 6))), [])

    def test_almost_empty_page(self):
        out = ui_map.audit(rail(page("A", 2), page("B", 3)))
        self.assertTrue(any("A: only 2 command" in x for x in out), out)

    def test_overloaded_section(self):
        out = ui_map.audit(rail(page("A", 8), page("B", 7)))
        self.assertTrue(any("A › S: 8 direct controls" in x for x in out), out)

    def test_too_many_visible(self):
        big = n("A", "page", [n(f"S{j}", "section", [n(f"b{j}{i}", "button") for i in range(4)]) for j in range(3)])
        out = ui_map.audit(rail(big, n("B", "page", [n(f"x{i}", "button") for i in range(6)])))
        self.assertTrue(any("A: 12 controls at once" in x for x in out), out)

    def test_long_menu(self):
        m = n("A", "page", [n("More", "menu", [n(f"i{i}", "item") for i in range(13)])])
        out = ui_map.audit(rail(m, n("B", "page", [n(f"x{i}", "button") for i in range(4)])))
        self.assertTrue(any("menu of 13 items" in x for x in out), out)

    def test_two_homes_and_generic_verbs(self):
        a = n("A", "page", [n("Export…", "button"), n("Refresh", "button"), n("a1", "button")])
        b = n("B", "page", [n("Export...", "button"), n("Refresh", "button"), n("b1", "button")])
        out = ui_map.audit(rail(a, b))
        self.assertIn("command with two homes: export (A, B)", out)
        self.assertFalse(any("refresh" in x for x in out), out)

    def test_duplicate_siblings(self):
        a = n("A", "page", [n("Go", "button"), n("Go", "button"), n("x", "button")])
        self.assertTrue(any("duplicate sibling labels ['Go']" in x for x in ui_map.audit(rail(a, page("B", 3)))))

    def test_unbalanced_destinations(self):
        out = ui_map.audit(rail(page("A", 3), n("B", "page", [n(f"S{j}", "section", [n(f"b{j}{i}", "button")
                                                                                    for i in range(7)])
                                                           for j in range(2)])))
        self.assertTrue(any("rail destinations unbalanced" in x for x in out), out)

    def test_rules_can_be_tightened(self):
        self.assertTrue(ui_map.audit(rail(page("A", 4), page("B", 4)), {"page_min_commands": 5}))


class ShippedMapTests(unittest.TestCase):
    """The map shipped in docs/UI_MAP.md (= the live app, see test_ui_map / gui_v5_map_smoke) is balanced."""

    def test_docs_map_is_balanced(self):
        tree = ui_map.parse_markdown(DOC.read_text(encoding="utf-8"))
        self.assertEqual(ui_map.audit(tree), [])

    def test_every_page_has_sections(self):
        tree = ui_map.parse_markdown(DOC.read_text(encoding="utf-8"))
        for row in ui_map.stats(tree):
            if " › " not in row["page"]:  # rail destinations: at least 2 meaningful groups
                self.assertGreaterEqual(row["sections"] + row["tabs"], 2, row)


if __name__ == "__main__":
    unittest.main()
