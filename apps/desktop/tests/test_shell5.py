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
        self.assertEqual(status5.summary(state())["text"], "No agents running")

    def test_running_from_tasks_and_handoffs(self):
        s = state(tasks={"t1": {"status": "in_progress", "owner_agent_id": "a1"},
                         "t2": {"status": "ready", "owner_agent_id": "a2"},
                         "t3": {"status": "todo", "owner_agent_id": "a3"}},
                  handoffs={"h1": {"status": "prompt_exported", "task_id": "t3"},
                            "h2": {"status": "accepted", "task_id": "t2"}})
        self.assertEqual(status5.running_agents(s), ["a1", "a3"])
        self.assertEqual(status5.summary(s)["text"], "2 agents running")
        self.assertTrue(status5.summary(s)["live"])

    def test_one_agent_singular_and_unknown_agents_ignored(self):
        s = state(tasks={"t1": {"status": "in_review", "owner_agent_id": "a1"},
                         "t2": {"status": "in_progress", "owner_agent_id": "ghost"}})
        self.assertEqual(status5.summary(s)["text"], "1 agent running")

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

    def test_tools_live_under_agents(self):
        for key, _label in structure5.TOOLS:
            self.assertEqual(ui_shell.RAIL_OF[key], "agents", key)

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
