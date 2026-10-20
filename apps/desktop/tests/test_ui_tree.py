"""Roadmap 5.0.0: docs/UI_TREE.md must equal the UI structure in code (aiwb/ui/structure5.py).

Project rule: every tab, button, menu or section is recorded in docs/UI_TREE.md in the same PR.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aiwb.ui import structure5  # noqa: E402

TREE_MD = ROOT.parents[1] / "docs" / "UI_TREE.md"


def parse_tree(text: str) -> dict:
    body = text.split("<!-- ui-tree:start -->", 1)[1].split("<!-- ui-tree:end -->", 1)[0]
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw in body.splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if not line.startswith("- ") or indent % 2:
            raise ValueError(f"bad tree line: {raw!r}")
        level = indent // 2
        while stack[-1][0] >= level:
            stack.pop()
        if level != stack[-1][0] + 1:
            raise ValueError(f"tree skips a level: {raw!r}")
        label = line[2:].strip()
        parent = stack[-1][1]
        if label in parent:
            raise ValueError(f"duplicate sibling {label!r}")
        parent[label] = {}
        stack.append((level, parent[label]))
    return root


class UiTreeTests(unittest.TestCase):
    def test_doc_equals_code(self):
        doc = parse_tree(TREE_MD.read_text(encoding="utf-8"))
        self.assertEqual(doc, structure5.tree(),
                         "docs/UI_TREE.md and aiwb/ui/structure5.py differ — record every UI change in the tree")

    def test_miller_rule(self):
        self.assertEqual(structure5.violations(), [])
        self.assertTrue(structure5.violations({str(i): {} for i in range(9)}))

    def test_one_home_per_command(self):
        ids = [t[0] for t in structure5.TOOLBAR] + [c[0] for t in structure5.TOOLBAR for c in t[3]]
        ids += [t[0] for t in structure5.TASK_MENU] + [a[0] for a in structure5.ASSISTANT_MENU]
        self.assertEqual(len(ids), len(set(ids)), ids)
        rail = [r[0] for r in structure5.RAIL]
        tools = [t[0] for t in structure5.TOOLS]
        self.assertFalse(set(rail) & set(tools))

    def test_task_menu_maps_to_guide_actions(self):
        guide_src = (ROOT / "src" / "aiwb" / "v2" / "guide.py").read_text(encoding="utf-8")
        for _id, _label, _icon, actions in structure5.TASK_MENU:
            self.assertTrue(actions)
            for a in actions:
                self.assertIn(f'_a("{a}"', guide_src, a)

    def test_parser_rejects_bad_trees(self):
        wrap = "<!-- ui-tree:start -->\n{}\n<!-- ui-tree:end -->"
        with self.assertRaises(ValueError):
            parse_tree(wrap.format("- A\n    - skipped"))
        with self.assertRaises(ValueError):
            parse_tree(wrap.format("- A\n- A"))


if __name__ == "__main__":
    unittest.main()
