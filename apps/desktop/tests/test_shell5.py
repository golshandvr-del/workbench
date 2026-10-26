"""Roadmap 5.1.0: the 5.x shell — status-bar facts (pure) and the page → rail-destination map."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from aiwb.ui import shell as ui_shell, status5, structure5  # noqa: E402
from aiwb.ui.chrome5 import chrome_theme, ease_out  # noqa: E402


def state(**kw):
    base = {"agents": {"a1": {"agent_id": "a1"}, "a2": {"agent_id": "a2"}, "a3": {"agent_id": "a3"}},
            "tasks": {}, "handoffs": {}, "milestones": {}, "versions": {}}
    base.update(kw)
    return base


class StatusFactsTests(unittest.TestCase):
    def test_no_project(self):
        self.assertEqual(status5.summary(None), {"running": 0, "milestone": "", "live": False,
                                                 "text": "No project open"})

    def test_idle_project(self):
        self.assertEqual(status5.summary(state())["text"], "Nothing waiting")

    def test_only_what_is_true_with_names(self):
        """5.13.0 (owner audit B4): a task in progress is not "an agent running"; a sent prompt is a wait."""
        s = state(agents={"a1": {"name": "Coder"}, "a2": {"name": "Tester"}, "a3": {}},
                  tasks={"t1": {"status": "in_progress", "owner_agent_id": "a1"},
                         "t2": {"status": "ready", "owner_agent_id": "a2"}, "t3": {"status": "todo",
                                                                               "owner_agent_id": "a3"}},
                  handoffs={"h1": {"handoff_id": "h1", "status": "prompt_exported", "task_id": "t3", "to_agent_id": "a3"},
                            "h2": {"handoff_id": "h2", "status": "accepted", "task_id": "t2", "to_agent_id": "a2"}})
        f = status5.summary(s)
        self.assertEqual(f["text"], "Waiting for an answer from a3")
        self.assertEqual((f["running"], f["live"]), (1, True))
        s["handoffs"]["h3"] = {"handoff_id": "h3", "status": "prepared", "task_id": "t1", "to_agent_id": "a1"}
        s["handoffs"]["h4"] = {"handoff_id": "h4", "status": "parsed", "task_id": "t2", "to_agent_id": "a2"}
        self.assertEqual(status5.summary(s)["text"],
                         "Waiting for an answer from a3  ·  Check the answer of Tester  ·  Prompt ready for Coder")

    def test_two_waiting_and_unknown_agents_ignored(self):
        s = state(agents={"a1": {"name": "Coder"}, "a2": {"name": "Tester"}},
                  handoffs={"h1": {"handoff_id": "h1", "status": "prompt_exported", "to_agent_id": "a1"},
                            "h2": {"handoff_id": "h2", "status": "prompt_exported", "to_agent_id": "a2"},
                            "h3": {"handoff_id": "h3", "status": "prompt_exported", "to_agent_id": "ghost"}})
        self.assertEqual(status5.summary(s)["text"], "Waiting for an answer from Coder and Tester")
        self.assertNotIn("running", status5.summary(s)["text"])

    def test_milestone_first_planned_then_open_version(self):
        s = state(milestones={"m2": {"milestone_id": "m2", "title": "V0.2.0", "status": "planned"},
                              "m1": {"milestone_id": "m1", "title": "V0.1.0", "status": "done"}})
        self.assertEqual(status5.current_milestone(s), "V0.2.0")
        s = state(versions={"v1": {"version_id": "v1", "label": "V0.1.0", "status": "released"},
                            "v2": {"version_id": "v2", "label": "V0.2.0", "status": "proposed"}})
        self.assertEqual(status5.current_milestone(s), "V0.2.0")
        self.assertIn("Milestone V0.2.0", status5.summary(s)["text"])
        s = state(versions={"v1": {"version_id": "v1", "label": "V1.0.0", "status": "released"}})
        self.assertEqual(status5.current_milestone(s), "V1.0.0")

    def test_reading_never_mutates(self):
        s = state(tasks={"t1": {"status": "in_progress", "owner_agent_id": "a1"}})
        before = repr(s)
        status5.summary(s)
        self.assertEqual(repr(s), before)


class ShellMapTests(unittest.TestCase):
    def test_every_page_has_a_rail_destination(self):
        rail = {r[0] for r in structure5.RAIL}
        for key in ui_shell.PAGES:
            self.assertIn(ui_shell.RAIL_OF[key], rail, key)
        self.assertEqual(set(ui_shell.RAIL_PAGE), rail)
        for dest, page in ui_shell.RAIL_PAGE.items():
            self.assertEqual(ui_shell.RAIL_OF[page], dest)

    def test_tools_live_under_their_home_destination(self):
        """5.5.0: each expert tool sits under the destination it belongs to (structure5.TOOL_HOME)."""
        for key, _label in structure5.TOOLS:
            self.assertEqual(ui_shell.RAIL_OF[key], structure5.TOOL_HOME[key], key)
        self.assertEqual({structure5.TOOL_HOME[k] for k, _l in structure5.TOOLS}, {"settings", "history"})

    def test_rail_destinations_are_never_advanced_only(self):
        for page in ui_shell.RAIL_PAGE.values():
            self.assertFalse(ui_shell.PAGES[page][3], page)

    def test_theme_mapping_and_easing(self):
        self.assertEqual(chrome_theme("dark"), "midnight")
        self.assertEqual(chrome_theme("light"), "daylight")
        self.assertEqual(ease_out(0), 0)
        self.assertEqual(ease_out(1), 1)
        self.assertEqual(ease_out(2), 1)
        self.assertGreater(ease_out(0.5), 0.5)


if __name__ == "__main__":
    unittest.main()
