"""Roadmap 3.6.0: visual timeline data mapping (pure, no Tk) — importance, lanes, version lines."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.ui.timeline_canvas import RADIUS, build_model, fit_label, importance, when_label  # noqa: E402


def rec(i, et, at="2026-10-19T10:00:00Z", **refs_after):
    refs = {k: v for k, v in refs_after.items() if k.endswith("_id")}
    after = {k: v for k, v in refs_after.items() if not k.endswith("_id")}
    return {"event_id": f"LE-{i:06d}-00", "event_type": et, "timestamp_utc": at, "refs": refs, "after": after,
            "payload": {}}


class ImportanceTests(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(importance(rec(1, "release_published")), "critical")
        self.assertEqual(importance(rec(1, "task_status", new="done")), "critical")
        self.assertEqual(importance(rec(1, "milestone_accepted")), "major")
        self.assertEqual(importance(rec(1, "task_status", new="blocked")), "major")
        self.assertEqual(importance(rec(1, "task_status", new="in_progress")), "normal")
        self.assertEqual(importance(rec(1, "project_settings_updated")), "minor")
        r = rec(1, "project_settings_updated")
        r["payload"]["importance"] = "critical"
        self.assertEqual(importance(r), "critical")

    def test_circle_size_grows_with_importance(self):
        self.assertTrue(RADIUS["minor"] < RADIUS["normal"] < RADIUS["major"] < RADIUS["critical"])


class ModelTests(unittest.TestCase):
    def state(self):
        return {"tasks": {"TASK-0001": {"owner_agent_id": "agent-core-dev"}},
                "versions": {
                    "VER-0001": {"version_id": "VER-0001", "label": "0.1.0", "status": "released",
                                 "created_at": "2026-10-19T09:00:00Z",
                                 "history": [{"from": "tagged", "to": "released", "at": "2026-10-19T12:00:00Z"}]},
                    "VER-0002": {"version_id": "VER-0002", "label": "0.2.0", "status": "proposed",
                                 "created_at": "2026-10-19T11:00:00Z", "history": []},
                    "VER-0003": {"version_id": "VER-0003", "label": "9.9.9", "status": "withdrawn",
                                 "created_at": "2026-10-19T11:00:00Z", "history": []}}}

    def test_lanes_versions_and_order(self):
        recs = [rec(1, "task_created", "2026-10-19T10:00:00Z", task_id="TASK-0001"),
                rec(2, "handoff_prepared", "2026-10-19T10:30:00Z", task_id="TASK-0001", to_agent_id="agent-ui-dev"),
                rec(3, "proposal_reviewed", "2026-10-19T11:00:00Z")]
        m = build_model(recs, self.state())
        lanes = {e["id"]: e["lane"] for e in m["events"]}
        self.assertEqual(lanes, {"LE-000001-00": "agent-core-dev", "LE-000002-00": "agent-ui-dev",
                                 "LE-000003-00": "project"})
        self.assertEqual(m["lanes"][0], "project")
        vs = {v["label"]: v for v in m["versions"]}
        self.assertEqual(set(vs), {"0.1.0", "0.2.0"}, "withdrawn versions are not drawn")
        self.assertTrue(vs["0.1.0"]["released"])
        self.assertFalse(vs["0.2.0"]["released"], "proposed version → dashed line")
        self.assertGreater(vs["0.1.0"]["t"], vs["0.2.0"]["t"], "released line sits at its release time")
        self.assertLess(m["t0"], m["t1"])

    def test_undated_legacy_events_keep_their_order(self):
        recs = [rec(1, "task_created", ""), rec(2, "task_created", "2026-10-19T10:00:00Z"), rec(3, "task_created", "")]
        m = build_model(recs, {"tasks": {}, "versions": {}})
        ts = [e["t"] for e in m["events"]]
        self.assertEqual(ts[0], ts[1])
        self.assertEqual(ts[1], ts[2])
        self.assertFalse(m["events"][0]["dated"])

    def test_lane_names_are_ai_names(self):
        """5.13.0 (owner audit C4): lanes are titled with the AI's name; "project" reads "Project"."""
        st = {**self.state(), "agents": {"agent-core-dev": {"name": "Core developer"}}}
        recs = [rec(1, "task_created", task_id="TASK-0001"), rec(2, "project_settings_updated")]
        m = build_model(recs, st)
        self.assertEqual(m["lane_names"], {"project": "Project", "agent-core-dev": "Core developer"})

    def test_labels_fit(self):
        self.assertEqual(fit_label("Core developer"), "Core developer")
        long = fit_label("CATIA COM Automation Engine developer")
        self.assertLessEqual(len(long), 18)
        self.assertTrue(long.endswith("…"))
        self.assertEqual(when_label(0.0), "")
        self.assertRegex(when_label(1792999999.0), r"^\d\d \w{3} \d\d:\d\d$")

    def test_empty(self):
        m = build_model([], {"tasks": {}, "versions": {}})
        self.assertEqual(m["events"], [])
        self.assertLess(m["t0"], m["t1"])


if __name__ == "__main__":
    unittest.main()
