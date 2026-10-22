"""Roadmap 5.6.0: Agents hub cards (aiwb/ui/agents5.cards) and the controller's hub writes."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures_ten_agents as fx  # noqa: E402
from aiwb.ui import agents5, mission_model  # noqa: E402
from aiwb.v2 import agent_hub as hub  # noqa: E402
from aiwb.v2.models import ModelError  # noqa: E402


class Cards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fx.build(Path(self.tmp.name))
        self.ctl = self.d["ctl"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_numbers_match_mission_lanes(self):
        st = self.ctl.state()
        rows = agents5.cards(st)
        lanes = {ln["agent_id"]: ln["number"] for ln in mission_model.build(st)["lanes"]}
        self.assertEqual(len(rows), len(hub.agent_stats(st)))
        for r in rows:
            if r["agent_id"] in lanes:
                self.assertEqual(r["number"], lanes[r["agent_id"]])
        nums = [r["number"] for r in rows]
        self.assertEqual(nums, sorted(nums))
        self.assertEqual(len(set(nums)), len(nums), "every AI has its own number")

    def test_state_word_and_summary(self):
        rows = agents5.cards(self.ctl.state())
        for r in rows:
            self.assertIn(agents5.state_of(r), ("Stuck", "Overloaded", "Working", "Idle", "Free"))
            self.assertIn("done", agents5.stats_line(r))
        text = agents5.summary(rows)
        self.assertEqual(len(text.splitlines()), len(rows))
        self.assertEqual(agents5.cards(None), [])

    def test_state_word_priority(self):
        base = {"alerts": [], "current_task_id": ""}
        self.assertEqual(agents5.state_of(base), "Free")
        self.assertEqual(agents5.state_of({**base, "alerts": ["idle"]}), "Idle")
        self.assertEqual(agents5.state_of({**base, "current_task_id": "T"}), "Working")
        self.assertEqual(agents5.state_of({**base, "current_task_id": "T", "alerts": ["overloaded"]}), "Overloaded")
        self.assertEqual(agents5.state_of({**base, "alerts": ["overloaded", "stuck"]}), "Stuck")

    def test_note_roundtrip_and_prompt(self):
        st = self.ctl.state()
        aid = next(r["agent_id"] for r in hub.agent_stats(st) if r["role"] != "project_manager")
        rev = st["state_revision"]
        self.assertEqual(self.ctl.set_agent_note(aid, "  Prefer small commits.  \n"), "Prefer small commits.")
        st2 = self.ctl.state()
        self.assertEqual(st2["state_revision"], rev + 1)
        self.assertEqual(hub.note(st2, aid), "Prefer small commits.")
        self.assertTrue(any(e["type"] == "agent_note_changed" for e in st2["events"][-3:]))
        self.assertIn("Prefer small commits.", self.ctl.agent_briefing(aid))
        self.ctl.set_agent_note(aid, "Prefer small commits.")  # unchanged: no new revision
        self.assertEqual(self.ctl.state()["state_revision"], rev + 1)
        self.ctl.set_agent_note(aid, "")
        self.assertEqual(hub.note(self.ctl.state(), aid), "")

    def test_apply_rebalance_refuses_started_or_unknown(self):
        st = self.ctl.state()
        started = next((t for t in st["tasks"].values() if t.get("active_attempt_id")), None)
        to = next(r["agent_id"] for r in hub.agent_stats(st) if r["role"] != "project_manager")
        with self.assertRaises(ModelError):
            self.ctl.apply_rebalance("TASK-9999", to)
        if started is not None:
            with self.assertRaises(ModelError):
                self.ctl.apply_rebalance(started["task_id"], to)

    def test_apply_rebalance_moves_suggestions(self):
        for m in self.ctl.agent_hub()["moves"]:
            out = self.ctl.apply_rebalance(m["task_id"], m["to_agent_id"])
            self.assertEqual(out["owner_agent_id"], m["to_agent_id"])


if __name__ == "__main__":
    unittest.main()
