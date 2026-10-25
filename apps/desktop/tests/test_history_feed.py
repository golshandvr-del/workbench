"""Roadmap 5.13.0 (owner audit B3): one History — prompts, answers, saved steps, events and versions, one filter.

* Steps: ``prompts``/``all`` keep every step, ``answers`` only steps with an answer, ``saved`` only checkpoints,
  ``events``/``versions`` show no steps.
* Events: ``versions`` = milestones/versions/releases only, ``events`` = everything else, ``all`` = both; plain words,
  the AI's name instead of its id; unknown event types still readable.
* Real ledger: a project with a task, a milestone and a version gives both groups; reading writes nothing.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.ui import history_feed as hf  # noqa: E402


STEPS = [
    {"id": "a", "response_status": "", "project_history_saved": False},
    {"id": "b", "response_status": "Validated", "project_history_saved": False},
    {"id": "c", "response_status": "Files Applied", "project_history_saved": True},
]


def rec(i: int, etype: str, fam: str, **refs: str) -> dict:
    return {"event_id": f"LE-{i:06d}-00", "event_type": etype, "family": fam, "refs": refs,
            "timestamp_utc": f"2026-10-25T10:{i:02d}:00Z", "after": {}, "before": {}}


class StepTests(unittest.TestCase):
    def test_filters(self):
        ids = lambda kind: [e["id"] for e in hf.filter_steps(STEPS, kind)]  # noqa: E731
        self.assertEqual(ids("all"), ["a", "b", "c"])
        self.assertEqual(ids("prompts"), ["a", "b", "c"])
        self.assertEqual(ids("answers"), ["b", "c"])
        self.assertEqual(ids("saved"), ["c"])
        self.assertEqual(ids("events"), [])
        self.assertEqual(ids("versions"), [])

    def test_kinds_and_labels(self):
        self.assertEqual([k for k, _ in hf.KINDS], ["all", "prompts", "answers", "saved", "events", "versions"])
        for k, label in hf.KINDS:
            self.assertEqual(hf.KEY_OF_LABEL[label], k)
        self.assertEqual(hf.event_families("versions"), ["version"])
        self.assertEqual(hf.event_families("all"), [])


class EventTests(unittest.TestCase):
    RECS = [rec(3, "version_proposed", "version", version_id="VER-0001"),
            rec(2, "task_status", "task", task_id="TASK-0001", agent_id="agent-dev"),
            rec(1, "brand_new_thing", "other")]

    def test_versions_events_all(self):
        self.assertEqual([r["title"] for r in hf.event_rows(self.RECS, "versions")], ["Version proposed"])
        self.assertEqual([r["title"] for r in hf.event_rows(self.RECS, "events")],
                         ["Task status changed", "Brand new thing"])
        self.assertEqual(len(hf.event_rows(self.RECS, "all")), 3)
        self.assertEqual(hf.event_rows(self.RECS, "prompts"), [])

    def test_names_not_ids(self):
        row = hf.event_rows(self.RECS, "events", {"agent-dev": "Coder"})[0]
        self.assertIn("Coder", row["detail"])
        self.assertNotIn("agent-dev", row["detail"])
        self.assertEqual(row["when"], "2026-10-25 10:02")

    def test_words_never_show_internal_names(self):
        for etype, words in hf.EVENT_WORDS.items():
            self.assertNotIn("_", words, etype)
            self.assertNotRegex(words.lower(), r"\bhandoff|\bwave|\bagent\b", etype)


class RealLedgerTests(unittest.TestCase):
    def test_project_events_and_versions(self):
        from aiwb.v2.controller import ProjectsController
        with tempfile.TemporaryDirectory() as tmp:
            ctl = ProjectsController(Path(tmp))
            p = ctl.project
            t = p.tasks.create({"title": "One", "objective": "o"})
            m = p.timeline.create_milestone({"title": "MVP", "task_ids": [t["task_id"]]})
            p.timeline.propose_version({"label": "1.0.0", "milestone_ids": [m["milestone_id"]]})
            rev = p.store.revision
            led = p.store.ledger
            vers = hf.event_rows(led.query(families=hf.event_families("versions"))["items"], "versions")
            self.assertEqual({r["title"] for r in vers}, {"Milestone created", "Version proposed"})
            evs = hf.event_rows(led.query()["items"], "events")
            self.assertIn("Task created", {r["title"] for r in evs})
            self.assertFalse({r["family"] for r in evs} & {"version"})
            self.assertEqual(p.store.revision, rev, "reading History wrote state")


if __name__ == "__main__":
    unittest.main()
