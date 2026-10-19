"""Unit tests for aiwb.ui.actions (roadmap 3.3.0 — UI information architecture)."""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.ui import actions  # noqa: E402


def _tk():
    try:
        root = tk.Tk()
        root.withdraw()
        return root
    except tk.TclError:
        return None


class ActionBarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _tk()
        if self.root is None:
            self.skipTest("no display")
        self.calls: list[str] = []

    def tearDown(self) -> None:
        if self.root is not None:
            self.root.destroy()

    def cmd(self, name):
        return lambda: self.calls.append(name)

    def test_primary_limit(self):
        with self.assertRaises(ValueError):
            actions.ActionBar(self.root, [(str(i), self.cmd(str(i))) for i in range(actions.MAX_PRIMARY + 1)])

    def test_menu_handles_behave_like_buttons(self):
        bar = actions.bar(self.root, primary=(("Go", self.cmd("go")),),
                          more=(("Group", (("Later", self.cmd("later")), ("Other", self.cmd("other")))),))
        h = bar.handle("Later")
        h.configure(state="disabled")
        self.assertEqual(str(h.cget("state")), "disabled")
        h.configure(state="normal")
        h.invoke()
        bar.handle("Go").invoke()
        self.assertEqual(self.calls, ["later", "go"])
        self.assertEqual(bar.labels(), ["Go", "Later", "Other"])

    def test_all_commands_includes_menu_items_but_not_group_headers(self):
        f = tk.Frame(self.root)
        f.pack()
        actions.bar(f, primary=(("A", self.cmd("a")),), more=(("Group", (("B", self.cmd("b")),)),))
        self.root.update()
        found = actions.all_commands([f])
        self.assertIn("A", found)
        self.assertIn("B", found)
        self.assertNotIn("GROUP", found)

    def test_no_more_button_without_secondary_items(self):
        bar = actions.ActionBar(self.root, (("Only", self.cmd("o")),))
        self.assertIsNone(bar.more_button)


if __name__ == "__main__":
    unittest.main()
