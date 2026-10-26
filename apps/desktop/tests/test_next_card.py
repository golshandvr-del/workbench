"""Roadmap 5.11.0: the model of Home's Next-step card (aiwb/ui/next_card.card_model) — pure, no display."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aiwb.ui.next_card import card_model, humanize, names_of  # noqa: E402
from aiwb.v2.guide import _a, _step  # noqa: E402

NAMES = {"agent-project-manager": "Project manager", "agent-core-dev": "Core dev", "agent-core-dev-2": "Core dev 2",
         "agent-x": "agent-x"}


def charter() -> dict:
    return _step("charter", "prompt", "Get the Project Charter from your project-manager chat", "Goal: snake.",
                 [_a("copy", "Copy the charter prompt"), _a("sent", "I sent it"), _a("paste", "Paste the charter", "text"),
                  _a("design", "Change the project details…", "goal")], agent="agent-project-manager", rank=2)


def handoff(agent: str, rank: int = 22) -> dict:
    return _step(f"handoff:H-{agent}", "prompt", f"Copy the prompt for T-1 Core into {agent}'s chat", f"for {agent}",
                 [_a("copy", "Copy prompt"), _a("sent", "I sent it"), _a("paste", "Paste the answer", "text"),
                  _a("abandon", "Drop this prompt…", "reason")], agent=agent, rank=rank)


class CardModelTests(unittest.TestCase):
    def test_empty(self):
        m = card_model([], NAMES)
        self.assertTrue(m["empty"])
        self.assertIsNone(m["primary"])
        self.assertIsNone(m["paste"])

    def test_paste_action_goes_to_the_panel_not_to_more(self):
        m = card_model([charter()], NAMES)
        self.assertEqual(m["primary"]["text"], "Copy the charter prompt")
        self.assertEqual(m["paste"]["id"], "paste")
        self.assertEqual([a["text"] for a in m["more"]], ["I sent it", "Change the project details…"])
        self.assertEqual(m["who"], "Project manager")

    def test_ids_become_names_longest_first(self):
        m = card_model([handoff("agent-core-dev-2")], NAMES)
        self.assertIn("Core dev 2's chat", m["title"])
        self.assertNotIn("agent-", m["title"] + m["explain"])
        self.assertEqual(humanize("agent-core-dev and agent-x", NAMES), "Core dev and agent-x")

    def test_more_open_count(self):
        m = card_model([charter(), handoff("agent-core-dev")], NAMES)
        self.assertIn("(1 more open)", m["explain"])

    def test_focus_on_one_ai(self):
        steps = [charter(), handoff("agent-core-dev", 30)]
        m = card_model(steps, NAMES, focus="agent-core-dev")
        self.assertEqual(m["key"], "handoff:H-agent-core-dev")
        self.assertEqual(m["focus"], "agent-core-dev")
        self.assertNotIn("more open", m["explain"])
        idle = card_model(steps, NAMES, focus="agent-core-dev-2")
        self.assertTrue(idle["empty"])
        self.assertIn("Core dev 2 has nothing to do", idle["title"])
        self.assertIn("Get the Project Charter", idle["explain"])

    def test_focus_on_one_step(self):
        steps = [charter(), handoff("agent-core-dev", 30), {**handoff("agent-core-dev", 31), "key": "handoff:H-2"}]
        m = card_model(steps, NAMES, focus="agent-core-dev", step_key="handoff:H-2")
        self.assertEqual(m["key"], "handoff:H-2")
        gone = card_model(steps, NAMES, focus="agent-core-dev", step_key="handoff:closed")
        self.assertEqual(gone["key"], "handoff:H-agent-core-dev")   # a closed step falls back to the AI's queue

    def test_open_steps_list_names_the_ai(self):
        """5.13.0: "All open steps (N)" lists every open step with the AI's name (never its id)."""
        m = card_model([charter(), handoff("agent-core-dev", 30)], NAMES)
        self.assertEqual([s["key"] for s in m["open"]], ["charter", "handoff:H-agent-core-dev"])
        self.assertTrue(m["open"][1]["title"].endswith(" · Core dev"), m["open"][1]["title"])
        self.assertNotIn("agent-", " ".join(s["title"] for s in m["open"]))
        self.assertEqual(card_model([], NAMES)["open"], [])

    def test_no_guide_step_needs_more_than_three_other_buttons(self):
        """5.13.0 (B5): Home has no More, so a step shows its other actions as buttons — at most MAX_OTHERS. Every
        literal action list in the guide is checked (the paste action goes to the panel, the primary is the button)."""
        import ast
        from aiwb.ui.next_card import MAX_OTHERS
        tree = ast.parse((SRC / "aiwb" / "v2" / "guide.py").read_text(encoding="utf-8"))
        appended = set()  # lists assigned to "acts" get one more action appended later (Drop this prompt…)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
                if any(isinstance(t, ast.Name) and t.id == "acts" for t in node.targets):
                    appended.add(id(node.value))
                if any(isinstance(t, ast.Tuple) and any(isinstance(e, ast.Name) and e.id == "acts" for e in t.elts)
                       for t in node.targets):
                    appended.add(id(node.value))
        checked = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.List) or not node.elts:
                continue
            calls = [e for e in node.elts if isinstance(e, ast.Call) and getattr(e.func, "id", "") == "_a"]
            if len(calls) != len(node.elts):
                continue
            buttons = [c for c in calls if not any(isinstance(a, ast.Constant) and a.value == "text" for a in c.args[2:])]
            others = len(buttons) - 1 + (1 if id(node) in appended else 0)
            self.assertLessEqual(others, MAX_OTHERS, f"guide.py line {node.lineno}: {others} other buttons")
            checked += 1
        self.assertGreater(checked, 20)

    def test_paste_only_step_has_no_primary_button(self):
        st = _step("continue", "paste", "Paste", "", [_a("paste", "Paste the rest", "text")])
        m = card_model([st], NAMES)
        self.assertIsNone(m["primary"])
        self.assertEqual(m["paste"]["id"], "paste")

    def test_needs_get_an_ellipsis(self):
        st = _step("decision:D-1", "decision", "Decide", "", [_a("decide", "Decide", "choice"), _a("x", "Other")])
        self.assertEqual(card_model([st], NAMES)["primary"]["text"], "Decide…")

    def test_names_of_state(self):
        st = {"agents": {"agent-a": {"name": "Alice"}, "agent-b": {"name": ""}}}
        self.assertEqual(names_of(st), {"agent-a": "Alice", "agent-b": "agent-b"})
        self.assertEqual(names_of(None), {})



class CardWidgetTests(unittest.TestCase):
    """5.13.0 (owner audit C2): the card never shows a blank blue button (primary without words)."""

    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def card(self, steps):
        from aiwb.ui.next_card import NextStepCard
        return NextStepCard(self.root, steps=lambda: steps, state=lambda: {}, perform=lambda *a: {},
                            clipboard=lambda t: None, status=lambda m: None)

    def test_no_blank_button_before_refresh(self):
        c = self.card([])
        self.assertFalse(c.next_btn.winfo_manager(), "the empty primary button is not shown before refresh()")

    def test_paste_only_step_shows_no_primary(self):
        c = self.card([_step("continue", "paste", "Paste", "", [_a("paste", "Paste the rest", "text")])])
        c.refresh()
        self.assertFalse(c.next_btn.winfo_manager())

    def test_blank_label_is_never_shown(self):
        c = self.card([_step("x", "prompt", "X", "", [_a("go", "   ")])])
        c.refresh()
        self.assertFalse(c.next_btn.winfo_manager())

    def test_primary_with_words_is_shown(self):
        c = self.card([charter()])
        c.refresh()
        self.assertTrue(c.next_btn.winfo_manager())
        self.assertEqual(c.next_btn.cget("text"), "Copy the charter prompt")


if __name__ == "__main__":
    unittest.main()
