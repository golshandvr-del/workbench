"""Roadmap 4.6.0 gate: completion, expansion or archive (flowchart F26–F28).

* F26 is offered only after the manager's "complete" decision with no open task; the summary is built from state
  and lands on the timeline (``project_completed``);
* F27 yes → the next major cycle (history kept, expansion prompt with history + idea, back to the planning loop);
* F27 no → F28: the final ``aiwb-bundle.v1`` is written and the archived project refuses every write until reopened.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2 import ModelError, closeout  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.guide import Guide  # noqa: E402


class CloseoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = ProjectsController(self.root, make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        self.store = self.c.project.store
        t = self.c.project.tasks.create({"title": "Core", "objective": "core", "owner_agent_id": "agent-implementer",
                                         "acceptance_criteria": ["works"]}, status="ready")["task_id"]
        with self.store.transaction("t") as s:
            s["settings"]["goal"] = "A calculator"
            s["tasks"][t]["status"] = "done"
            s["handoffs"]["H-1"] = {"handoff_id": "H-1", "task_id": t, "status": "accepted", "to_agent_id": "agent-implementer",
                                    "integrated_at": "2026-01-01T00:00:00Z", "integrated_files": ["src/calc.py"]}
            s["versions"]["VER-1"] = {"version_id": "VER-1", "label": "1.0.0", "status": "released", "tag": "v1.0.0",
                                      "commit_sha": "a" * 40, "run_id": "run-7", "milestone_ids": []}
        self.t = t

    def tearDown(self):
        self.tmp.cleanup()

    def decide_complete(self):
        with self.store.transaction("decision") as s:
            s["settings"].setdefault("flow", {})["last_decision"] = {"route": "complete", "proposal_id": "P-1"}

    def test_not_offered_before_the_managers_decision(self):
        self.assertFalse(closeout.can_announce(self.c.state()))
        self.assertNotIn("closeout:announce", [s["key"] for s in self.g.steps()])
        with self.assertRaises(ModelError):
            closeout.announce(self.store)

    def test_announce_summary_and_timeline(self):
        self.decide_complete()
        self.assertEqual(self.g.flow()["node"], "F26")
        steps = self.g.steps()
        self.assertEqual([s["key"] for s in steps], ["closeout:announce"])
        self.assertIn("1.0.0 (v1.0.0; run-7)", steps[0]["explain"])
        self.g.perform("closeout:announce", "announce")
        st = self.c.state()
        self.assertEqual(st["settings"]["flow"]["completion"]["tasks_done"], 1)
        self.assertEqual(st["settings"]["flow"]["completion"]["files"], ["src/calc.py"])
        self.assertIn("project_completed", [e["type"] for e in st["events"]])
        self.assertEqual(self.g.flow()["node"], "F27")

    def test_expand_starts_next_cycle_with_history(self):
        self.decide_complete()
        self.g.perform("closeout:announce", "announce")
        out = self.g.perform("closeout:expand", "expand", idea="Add a scientific mode")
        for needle in ("next major cycle", "Add a scientific mode", "Cycle 1 is complete", "src/calc.py",
                       "AIWB_MANAGER_PROPOSAL", "roadmap_remaining"):
            self.assertIn(needle, out["prompt"])
        fs = self.c.state()["settings"]["flow"]
        self.assertEqual(fs["cycle"], 2)
        self.assertEqual(len(fs["history"]), 1)
        self.assertNotIn("completed_at", fs)
        keys = [s["key"] for s in self.g.steps()]
        self.assertNotIn("closeout:expand", keys)
        self.assertIn("manager_update", keys, "back to the planning loop with the project manager")

    def test_archive_read_only_and_reopen(self):
        self.decide_complete()
        with self.assertRaises(ModelError):
            closeout.archive(self.store, self.root)  # announce first
        self.g.perform("closeout:announce", "announce")
        out = self.g.perform("closeout:expand", "archive")
        path = closeout.archive_path(self.root, self.c.state())
        self.assertIn(str(path), out["message"])
        b = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(b["bundle_type"], "aiwb-bundle")
        self.assertEqual(self.g.flow()["node"], "F28")
        self.assertEqual([s["key"] for s in self.g.steps()], ["closeout:archived"])
        rev = self.c.state()["state_revision"]
        with self.assertRaises(ModelError):
            self.c.project.tasks.create({"title": "X", "objective": "x", "acceptance_criteria": ["y"]})
        with self.assertRaises(ModelError):
            with self.store.transaction("goal") as s:
                s["settings"]["goal"] = "changed"
        self.assertEqual(self.c.state()["state_revision"], rev, "nothing was written")
        self.g.perform("closeout:archived", "reopen")
        self.assertFalse(closeout.is_archived(self.c.state()))
        self.c.project.tasks.create({"title": "X", "objective": "x", "acceptance_criteria": ["y"]})


if __name__ == "__main__":
    unittest.main()
