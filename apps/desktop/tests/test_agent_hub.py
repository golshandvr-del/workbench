"""Roadmap 5.6.0: the Agents hub model (aiwb/v2/agent_hub.py) — stats, alerts, rebalance, queue, briefing, notes."""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures_ten_agents as fx  # noqa: E402
from aiwb.v2 import agent_hub as hub  # noqa: E402
from aiwb.v2.models import ModelError  # noqa: E402


class HubOnTenAgents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = fx.build(Path(cls.tmp.name))
        cls.st = cls.d["ctl"].state()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_stats_cover_every_enabled_agent(self):
        rows = hub.agent_stats(self.st)
        enabled = [a for a in self.st["agents"].values() if a.get("enabled", True)]
        self.assertEqual(len(rows), len(enabled))
        self.assertEqual(rows[0]["role"], "project_manager")
        for r in rows:
            self.assertGreaterEqual(r["open"], 0)
            self.assertTrue(0.0 <= r["rework_rate"] <= 1.0)
            self.assertTrue(0.0 <= r["load_share"] <= 1.0)
        self.assertAlmostEqual(sum(r["load_share"] for r in rows), 1.0 if any(r["open"] for r in rows) else 0.0,
                               delta=0.06)

    def test_alerts_sorted_and_typed(self):
        out = hub.alerts(self.st, now=datetime.now(timezone.utc) + timedelta(days=3))
        self.assertTrue(all(a["kind"] in ("idle", "stuck", "overloaded", "overlap") for a in out))
        self.assertEqual([a["rank"] for a in out], sorted(a["rank"] for a in out))

    def test_rebalance_only_moves_unstarted_ready_tasks(self):
        for m in hub.rebalance(self.st):
            t = self.st["tasks"][m["task_id"]]
            self.assertEqual(t["status"], "ready")
            self.assertFalse(t.get("active_attempt_id"))
            self.assertNotEqual(m["from_agent_id"], m["to_agent_id"])

    def test_queue_and_briefing(self):
        aid = next(r["agent_id"] for r in hub.agent_stats(self.st) if r["open"])
        q = hub.queue(self.st, aid)
        self.assertEqual([r["rank"] for r in q], sorted(r["rank"] for r in q))
        text = hub.briefing(self.st, aid, project_name="Ten")
        self.assertIn(f"({aid}, role", text)
        self.assertIn("## Your queue", text)
        self.assertIn("READY", text)
        with self.assertRaises(ModelError):
            hub.briefing(self.st, "agent-nobody")


class NoteTests(unittest.TestCase):
    def test_set_note_trims_and_clears(self):
        st = {"agents": {"agent-a": {}}, "settings": {}}
        self.assertEqual(hub.set_note(st, "agent-a", "  use tabs  \nno emojis \n"), "use tabs\nno emojis")
        self.assertEqual(hub.note_lines(st, "agent-a"),
                         ["- Note from the project owner: use tabs", "- Note from the project owner: no emojis"])
        hub.set_note(st, "agent-a", "")
        self.assertEqual(hub.note(st, "agent-a"), "")
        with self.assertRaises(ModelError):
            hub.set_note(st, "agent-x", "x")
        self.assertEqual(len(hub.set_note(st, "agent-a", "y" * 5000)), hub.NOTE_MAX)


if __name__ == "__main__":
    unittest.main()
