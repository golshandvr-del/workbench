"""Roadmap 5.13.0 (owner audit B3): milestones and versions are handled on the Mission Map's columns.

* Pure rows: a milestone column offers ACCEPT MILESTONE (only when the Guide offers it), NEW MILESTONE (open tasks
  of the column), PROPOSE VERSION (made of that milestone); a version column offers RECORD RELEASE instead.
* A real project: tasks → NEW MILESTONE groups them → done tasks → ACCEPT MILESTONE enabled → PROPOSE VERSION
  of it → RECORD RELEASE enabled — the same steps the Workbench's Timeline tab had, now on the map.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.ui import column_menu, mission_model  # noqa: E402
from aiwb.v2.guide import _a, _step  # noqa: E402


def model(kind: str, status: str = "planned", task_status: str = "ready") -> dict:
    return {"columns": [{"key": "MS-0001" if kind == "milestone" else "VER-0001", "label": "MVP", "kind": kind,
                         "status": status}],
            "lanes": [{"agent_id": "a", "nodes": [{"task_id": "T-2", "status": task_status, "column": 0},
                                                  {"task_id": "T-1", "status": "done", "column": 0}]}]}


def by_id(rows: list[dict]) -> dict:
    return {r["id"]: r for r in rows}


class PureRowsTests(unittest.TestCase):
    def test_milestone_column(self):
        rows = by_id(column_menu.items([], model("milestone"), 0))
        self.assertEqual(list(rows), ["accept_milestone", "new_milestone", "propose_version"])
        self.assertFalse(rows["accept_milestone"]["enabled"])
        self.assertTrue(rows["accept_milestone"]["hint"], "a disabled row explains itself")
        self.assertEqual(rows["new_milestone"]["task_ids"], ["T-2"], "only the open tasks of the column")
        self.assertEqual(rows["propose_version"]["milestone_ids"], ["MS-0001"])
        step = _step("milestone:MS-0001", "decision", "Accept milestone MVP", "x",
                     [_a("accept_milestone", "Accept the milestone")], ref="MS-0001")
        row = by_id(column_menu.items([step], model("milestone"), 0))["accept_milestone"]
        self.assertEqual((row["enabled"], row["step"], row["action"]), (True, "milestone:MS-0001", "accept_milestone"))

    def test_version_column(self):
        rows = by_id(column_menu.items([], model("version", task_status="done"), 0))
        self.assertEqual(list(rows), ["record_release", "new_milestone", "propose_version"])
        self.assertFalse(rows["record_release"]["enabled"])
        self.assertFalse(rows["new_milestone"]["enabled"], "no open task in the column")
        self.assertEqual(rows["propose_version"]["milestone_ids"], [])
        step = _step("version:VER-0001", "decision", "Release version 1.0.0", "x",
                     [_a("release", "Record the release…", "commit_sha", "tag", "run_id"), _a("withdraw", "Withdraw")],
                     ref="VER-0001")
        row = by_id(column_menu.items([step], model("version"), 0))["record_release"]
        self.assertEqual((row["enabled"], row["action"], row["needs"]), (True, "release", ["commit_sha", "tag", "run_id"]))

    def test_rows_draw_in_the_floating_menu(self):
        for r in column_menu.items([], model("milestone"), 0):
            self.assertTrue({"id", "label", "icon", "enabled", "step", "action", "needs", "hint"} <= set(r))


class RealProjectTests(unittest.TestCase):
    def setUp(self):
        import AI_Workbench as wb
        from aiwb.v2.controller import ProjectsController
        from aiwb.v2.guide import Guide
        from aiwb.v2.models import normalize_agent
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        p = self.c.project
        p.agents.create(normalize_agent({"agent_id": "agent-dev", "name": "Coder", "role": "implementer"}))
        self.tids = [p.tasks.create({"title": f"Part {i}", "objective": "o", "owner_agent_id": "agent-dev",
                                     "allowed_paths": [f"src/p{i}/**"]})["task_id"] for i in (1, 2)]

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, index: int = 0) -> dict:
        m = mission_model.build(self.c.state())
        return by_id(column_menu.items(self.g.steps(), m, index)), m

    def test_milestone_then_version_from_the_columns(self):
        rows, m = self.rows()
        self.assertEqual(m["columns"][0]["kind"], "next")
        self.assertEqual(rows["new_milestone"]["task_ids"], sorted(self.tids))
        tl = self.c.project.timeline
        ms = tl.create_milestone({"title": "MVP", "task_ids": rows["new_milestone"]["task_ids"]})
        rows, m = self.rows()
        self.assertEqual((m["columns"][0]["kind"], m["columns"][0]["label"]), ("milestone", "MVP"))
        self.assertFalse(rows["accept_milestone"]["enabled"], "tasks are not done yet")
        with self.c.project.store.transaction("test") as s:  # the tasks are finished (the delivery path is tested elsewhere)
            for t in self.tids:
                s["tasks"][t]["status"] = "done"
        rows, _ = self.rows()
        self.assertTrue(rows["accept_milestone"]["enabled"])
        self.g.perform(rows["accept_milestone"]["step"], rows["accept_milestone"]["action"])
        self.assertEqual(self.c.state()["milestones"][ms["milestone_id"]]["status"], "accepted")
        v = tl.propose_version({"label": "0.1.0", "milestone_ids": rows["propose_version"]["milestone_ids"]})
        rows, m = self.rows()
        self.assertEqual((m["columns"][0]["kind"], m["columns"][0]["key"]), ("version", v["version_id"]))
        self.assertTrue(rows["record_release"]["enabled"], "its milestone is accepted")
        out = self.g.perform(rows["record_release"]["step"], "release", commit_sha="abcdef1", tag="", run_id="42")
        self.assertIn("released", out["message"])


if __name__ == "__main__":
    unittest.main()
