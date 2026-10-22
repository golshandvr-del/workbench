"""Roadmap 5.5.0: the App Map (aiwb/ui/ui_map.py) and docs/UI_MAP.md.

The live comparison (map extracted from the running app == docs/UI_MAP.md) runs in the GUI smoke
``gui_v5_map_smoke.py`` (needs a display); these tests are pure and check the document against the design tree.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aiwb.ui import map_view, structure5, ui_map  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DOC = REPO / "docs" / "UI_MAP.md"


def sample() -> dict:
    n = ui_map.node
    return n("AI Workbench", "app", [
        n("Toolbar", "area", [n("New Project", "menu", [n("Guided", "item"), n("Add folder", "item")]),
                              n("Run", "button")]),
        n("Rail", "area", [
            n("Home", "page", [n("Map", "section", [n("Open", "button"), n("Copy", "button"), n("Mark", "button")])]),
            n("Agents", "page", [n("Team", "section", [n("Plan", "button"), n("Brief", "button")]),
                                 n("Desk", "section", [n("Prepare", "button")])]),
        ]),
    ])


class MarkdownTests(unittest.TestCase):
    def test_round_trip(self):
        t = sample()
        md = ui_map.to_markdown(t)
        self.assertEqual(ui_map.parse_markdown(md), t)
        self.assertIn("  - New Project [menu]\n    - Guided [item]", md)

    def test_markers_and_bad_lines(self):
        md = "intro\n<!-- ui-map:start -->\n" + ui_map.to_markdown(sample()) + "<!-- ui-map:end -->\nafter\n"
        self.assertEqual(ui_map.parse_markdown(md), sample())
        with self.assertRaises(ValueError):
            ui_map.parse_markdown("- A [page]\n    - skipped [button]\n")
        with self.assertRaises(ValueError):
            ui_map.parse_markdown("- A [nonsense]\n")
        with self.assertRaises(ValueError):
            ui_map.parse_markdown("* not a map line\n")


class CountTests(unittest.TestCase):
    def test_commands_and_visible(self):
        t = sample()
        home = t["children"][1]["children"][0]
        self.assertEqual(ui_map.commands(home), 3)
        self.assertEqual(ui_map.visible_controls(home), 3)
        rows = {r["page"]: r for r in ui_map.stats(t)}
        self.assertEqual(rows["Agents"]["sections"], 2)
        self.assertEqual(rows["Agents"]["commands"], 3)

    def test_menu_items_do_not_count_as_visible(self):
        n = ui_map.node
        pg = n("P", "page", [n("More", "menu", [n(f"i{k}", "item") for k in range(9)])])
        self.assertEqual(ui_map.visible_controls(pg), 1)
        self.assertEqual(ui_map.commands(pg), 9)

    def test_tabs_count_one_at_a_time(self):
        n = ui_map.node
        pg = n("P", "page", [n("A", "tab", [n("x", "button")] * 3), n("B", "tab", [n("y", "button")] * 5)])
        self.assertEqual(ui_map.visible_controls(pg), 5)


class DrawingTests(unittest.TestCase):
    def test_layout_parents_centred_and_one_row_per_leaf(self):
        g = ui_map.layout(sample())
        leaves = [b for i, b in enumerate(g["boxes"]) if not any(a == i for a, _b in g["edges"])]
        self.assertEqual(len({b["y"] for b in leaves}), len(leaves))
        self.assertEqual(len(g["edges"]), len(g["boxes"]) - 1)
        for a, _b in g["edges"]:
            kids = [g["boxes"][c]["y"] for p, c in g["edges"] if p == a]
            self.assertAlmostEqual(g["boxes"][a]["y"], (min(kids) + max(kids)) / 2)

    def test_svg_is_well_formed(self):
        import xml.etree.ElementTree as ET
        svg = ui_map.to_svg(sample())
        root = ET.fromstring(svg)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertIn("Add folder", svg)
        self.assertIn("<path", svg)

    def test_filter_keeps_ancestors(self):
        f = map_view.filtered(sample(), "prep")
        self.assertEqual(ui_map.to_markdown(f), "- Rail [area]\n  - Agents [page]\n    - Desk [section]\n"
                                                "      - Prepare [button]\n")
        t = sample()
        self.assertIs(map_view.filtered(t, "  "), t)  # empty filter = the whole map
        self.assertEqual(map_view.filtered(sample(), "zzz")["children"], [])
        self.assertIn("balanced", map_view.summary(sample()))


class DocumentTests(unittest.TestCase):
    """docs/UI_MAP.md is valid, generated, and agrees with the design tree (structure5 / docs/UI_TREE.md)."""

    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")
        cls.tree = ui_map.parse_markdown(cls.text)

    def test_generated_header_and_picture(self):
        self.assertIn("tools/ui_map.py", self.text)
        for name in ("ui_map.png", "ui_map.svg"):
            self.assertTrue((REPO / "docs" / "design" / name).is_file(), name)

    def test_areas_and_rail_match_design_tree(self):
        areas = [c["label"] for c in self.tree["children"]]
        self.assertEqual(areas, ["Toolbar", "Rail", "Status bar"])
        rail = self.tree["children"][1]
        self.assertEqual([c["label"] for c in rail["children"]], [r[1] for r in structure5.RAIL])
        toolbar = self.tree["children"][0]
        self.assertEqual([c["label"] for c in toolbar["children"]], [t[1] for t in structure5.TOOLBAR])
        status = self.tree["children"][2]
        self.assertEqual([c["label"] for c in status["children"]], list(structure5.STATUS_BAR))

    def test_every_expert_tool_under_its_home(self):
        rail = {c["label"]: c for c in self.tree["children"][1]["children"]}
        dest_label = {r[0]: r[1] for r in structure5.RAIL}
        for key, label in structure5.TOOLS:
            home = rail[dest_label[structure5.TOOL_HOME[key]]]
            tools = next(c for c in home["children"] if c["label"] == "Tools")
            self.assertIn(label, [c["label"] for c in tools["children"] if c["kind"] == "page"], key)

    def test_task_menu_matches_design(self):
        home = self.tree["children"][1]["children"][0]
        menu = next(n for _p, n in ui_map.iter_nodes(home) if n["kind"] == "menu" and n["label"] == "Task menu")
        self.assertEqual([c["label"] for c in menu["children"]], [m[1] for m in structure5.TASK_MENU])

    def test_mobile_section_matches_design(self):
        """Roadmap 6.1.0: the phone's bottom bar is the rail and its long-press menu is the task menu."""
        part = self.text.split("<!-- ui-map-mobile:start -->", 1)[1].split("<!-- ui-map-mobile:end -->", 1)[0]
        mobile = ui_map.parse_markdown(part, "AI Workbench Mobile")
        bar = mobile["children"][0]
        self.assertEqual(bar["label"], "Bottom bar")
        self.assertEqual([c["label"] for c in bar["children"]], [r[1] for r in structure5.RAIL])
        menu = next(n for _p, n in ui_map.iter_nodes(mobile) if n["kind"] == "menu")
        self.assertEqual([c["label"] for c in menu["children"]], [m[1] for m in structure5.TASK_MENU])

    def test_counts_table_matches_tree(self):
        for r in ui_map.stats(self.tree):
            self.assertIn(f"| {r['page']} | {r['sections']} | {r['tabs']} | {r['commands']} |", self.text, r)


if __name__ == "__main__":
    unittest.main()
