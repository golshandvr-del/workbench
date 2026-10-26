"""Roadmap 5.13.0 (owner audit B5): every command by one id — ``aiwb/ui/commands.py`` and the audit built on it."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
ROOT = Path(__file__).resolve().parents[3]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aiwb.ui import commands, structure5, ui_map  # noqa: E402


class RegistryTests(unittest.TestCase):
    def test_ids_are_unique_and_dotted(self):
        ids = commands.ids()
        self.assertEqual(len(ids), len(set(ids)))
        for cid in ids:
            self.assertRegex(cid, r"^[a-z]+\.[a-z_]+$")

    def test_a_label_means_one_job_per_place(self):
        """Two commands may share a word only in places that do not overlap (History's Copy prompt ≠ Home's)."""
        seen: dict[str, list[commands.Command]] = {}
        for c in commands.COMMANDS:
            for lab in {commands.norm(x) for x in c.labels}:
                seen.setdefault(lab, []).append(c)
        for lab, cs in seen.items():
            for i, a in enumerate(cs):
                for b in cs[i + 1:]:
                    for wa in a.where or ("",):
                        for wb in b.where or ("",):
                            overlap = not wa or not wb or wa.startswith(wb) or wb.startswith(wa)
                            self.assertFalse(overlap, f"{lab!r}: {a.id} ({wa}) and {b.id} ({wb})")

    def test_synonyms_resolve_to_one_id(self):
        for lab in ("COPY PROMPT", "Copy prompt", "Prepare prompt for this task", "Prepare the prompt"):
            self.assertEqual(commands.command_of("Home", lab), "task.copy_prompt", lab)
        self.assertEqual(commands.command_of("History", "Copy prompt"), "history.copy_prompt")
        self.assertEqual(commands.command_of("Settings › Classic tools (1.x) › Prompt", "Copy prompt"),
                         "classic.copy_prompt")
        self.assertEqual(commands.command_of("Agents", "Something new…"), "label:something new")
        self.assertEqual(commands.label("task.sent"), "SEND PROMPT")
        with self.assertRaises(KeyError):
            commands.label("no.such")

    def test_task_menu_rows_are_registered(self):
        """The Mission Map task menu (structure5.TASK_MENU) uses the registered words of the task loop."""
        for _id, lab, _icon, _acts in structure5.TASK_MENU:
            self.assertTrue(commands.command_of("Home", lab).startswith("task."), lab)


class AuditTests(unittest.TestCase):
    def tree(self, home: list, other: list, more_items: int = 0) -> dict:
        n = ui_map.node
        bar = [n("More", "menu", [n(f"m{i}", "item") for i in range(more_items)])] if more_items else []
        return n("AI Workbench", "app", [n("Rail", "area", [n("Home", "page", home),
                                                            n("Agents", "page", other + bar)])])

    def test_two_words_for_one_job_are_two_homes(self):
        t = self.tree([ui_map.node("COPY PROMPT", "item")], [ui_map.node("Prepare prompt for this task", "button")])
        out = ui_map.two_homes(t)  # a synonym used only by task.copy_prompt is that job on Agents too
        self.assertEqual(len(out), 1)
        self.assertIn("task.copy_prompt", out[0])
        t = self.tree([ui_map.node("COPY PROMPT", "item")], [ui_map.node("Copy prompt", "button")])
        # "Copy prompt" means several jobs (History, Classic tools): outside their places it is its own command
        self.assertEqual(ui_map.two_homes(t), [])
        t = self.tree([ui_map.node("Edit team…", "button")], [ui_map.node("Edit team…", "button")])
        self.assertEqual(len(ui_map.two_homes(t)), 1)

    def test_more_rules(self):
        n = ui_map.node
        ok = self.tree([], [], more_items=3)
        self.assertFalse([x for x in ui_map.audit(ok) if "More of" in x])
        big = self.tree([], [], more_items=4)
        self.assertTrue([x for x in ui_map.audit(big) if "More of 4 items" in x])
        home = n("AI Workbench", "app", [n("Rail", "area", [n("Home", "page", [n("More", "menu", [n("x", "item")])])])])
        self.assertTrue([x for x in ui_map.audit(home) if "Home has no More" in x])

    def test_shipped_map_is_clean(self):
        tree = ui_map.parse_markdown((ROOT / "docs" / "UI_MAP.md").read_text(encoding="utf-8"))
        self.assertEqual(ui_map.two_homes(tree), [])
        self.assertFalse([x for x in ui_map.audit(tree) if "More" in x])


if __name__ == "__main__":
    unittest.main()
