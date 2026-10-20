"""Roadmap 4.4.0 gate: status report to the project manager and the manager's decision (flowchart F18–F21, F25).

* the shared fixture ``packages/contracts/fixtures/report/pm-decision.v1.json`` (parsing + routing) passes;
* the status prompt carries integrated files, finished and stuck tasks, GitHub facts and the decision contract;
* all three branches on a real project: emergency → priority + paused dependants + dispatched first (F10);
  stage left → next wave (F10); nothing left → completion (F26).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2 import report, waves  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.guide import Guide  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[3] / "packages/contracts/fixtures/report/pm-decision.v1.json"


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.fx = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_remaining(self):
        for c in self.fx["remaining"]:
            with self.subTest(c=c):
                self.assertEqual(report.parse_remaining(c["in"]), c["out"])

    def test_emergency(self):
        for c in self.fx["emergency"]:
            with self.subTest(c=c):
                self.assertEqual(report.parse_emergency(c["in"]), c["out"])

    def test_route(self):
        for c in self.fx["route"]:
            with self.subTest(c=c):
                self.assertEqual(report.route(["x"] * c["emergency"], c["remaining"], c["open"]), c["out"])
        self.assertEqual(set(c["out"] for c in self.fx["route"]), set(report.ROUTES))


def _block(rev, ops, **extra):
    return ("Analysis.\n<<<AIWB_MANAGER_PROPOSAL>>>\n"
            + json.dumps({"schema_version": "1.0", "base_state_revision": rev, "summary": "s", "operations": ops, **extra})
            + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>")


def _new(ref, title):
    return {"operation": "create_task", "temporary_ref": ref, "title": title, "objective": title,
            "owner_role": "implementer", "acceptance_criteria": ["works"], "scope": {"include": [f"src/{ref}/**"]}}


class BranchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        ts = self.c.project.tasks
        self.a = ts.create({"title": "Core", "objective": "core", "owner_agent_id": "agent-implementer",
                            "allowed_paths": ["src/a/"], "acceptance_criteria": ["works"]}, status="ready")["task_id"]
        self.b = ts.create({"title": "UI", "objective": "ui", "owner_agent_id": "agent-implementer",
                            "allowed_paths": ["src/b/"], "acceptance_criteria": ["works"]}, status="ready")["task_id"]
        with self.c.project.store.transaction("t") as s:
            s["settings"]["goal"] = "x"
            s["settings"].setdefault("team", {})["max_parallel_chats"] = 1

    def tearDown(self):
        self.tmp.cleanup()

    def _paste(self, text):
        r = self.c.route_answer(text)
        self.assertEqual(r.kind, "proposal", r.message)
        return r.reference_id

    def _accept(self, pid):
        return self.c.project.proposals.review(pid, [o["index"] for o in self.c.project.proposals.get(pid)["operations"]
                                                      if o["valid"]], confirm_stale=True)

    def test_status_prompt_has_sections_and_contract(self):
        with self.c.project.store.transaction("t") as s:
            s["tasks"][self.b]["status"] = "blocked"
            s["tasks"][self.b]["blocked_reason"] = "stuck after 3 troubleshooting prompts: cut off"
            s["handoffs"]["H-9"] = {"handoff_id": "H-9", "task_id": self.a, "status": "accepted",
                                    "integrated_at": "2099-01-01T00:00:00Z", "integrated_files": ["src/a/x.py"]}
            s["settings"].setdefault("flow", {})["repo"] = {"full_name": "me/app", "branch": "aiwb/app"}
        st = self.c.state()
        sec = report.status_sections(st)
        self.assertTrue(any("src/a/x.py" in x for x in sec["integrated"]))
        self.assertTrue(any(self.b in x and "stuck" in x for x in sec["stuck"]))
        self.assertIn("Repository: me/app (branch aiwb/app)", sec["github"])
        step = next(s for s in self.g.steps() if s["key"] == "manager_update") if any(
            s["key"] == "manager_update" for s in self.g.steps()) else None
        prompt = report.status_prompt(st, self.c.manager_update())
        for needle in ("roadmap_remaining", "emergency_tasks", "Stuck tasks", "src/a/x.py", "AIWB_MANAGER_PROPOSAL"):
            self.assertIn(needle, prompt)
        if step:
            self.assertIn("emergency_tasks", step["prompt"])

    def test_emergency_branch(self):
        with self.c.project.store.transaction("t") as s:
            s["tasks"][self.a]["status"] = "in_progress"
        rev = self.c.state()["state_revision"]
        pid = self._paste(_block(rev, [_new("fix", "Hotfix")], roadmap_remaining=True,
                                 emergency_tasks=[{"ref": "fix", "blocks": [self.a, self.b]}]))
        p = self.c.project.proposals.get(pid)
        self.assertEqual(p["emergency_tasks"], [{"ref": "fix", "blocks": [self.a, self.b]}])
        out = self._accept(pid)
        d = out["result"]["decision"]
        self.assertEqual(d["route"], "emergency")
        st = self.c.state()
        fix = d["emergency"][0]
        self.assertEqual(st["tasks"][fix]["priority"], "critical")
        self.assertIn("emergency", st["tasks"][fix]["flags"])
        for tid in (self.a, self.b):
            self.assertEqual(st["tasks"][tid]["status"], "blocked")
            self.assertTrue(st["tasks"][tid]["blocked_reason"].startswith("waiting for " + fix))
        self.assertEqual(sorted(d["paused"]), sorted([self.a, self.b]))
        self.assertEqual(waves.dispatch(st)["next"], [fix], "the emergency is dispatched first")
        self.assertEqual(self.g.flow()["node"], "F10")
        self.assertIn("pm_decision", [e["type"] for e in self.c.project.store.events.all()])

    def test_next_stage_branch(self):
        rev = self.c.state()["state_revision"]
        pid = self._paste(_block(rev, [_new("n1", "Stage 2")], roadmap_remaining=True, emergency_tasks=[]))
        d = self._accept(pid)["result"]["decision"]
        self.assertEqual(d["route"], "next_stage")
        self.assertEqual(self.g.flow()["node"], "F10")
        self.assertTrue(self.c.state()["settings"]["flow"]["roadmap_remaining"])

    def test_complete_branch(self):
        with self.c.project.store.transaction("t") as s:
            for tid in (self.a, self.b):
                s["tasks"][tid]["status"] = "done"
        rev = self.c.state()["state_revision"]
        pid = self._paste(_block(rev, [], roadmap_remaining=False, emergency_tasks=[]))
        out = self._accept(pid)
        self.assertEqual(out["status"], "accepted")
        self.assertEqual(out["result"]["decision"]["route"], "complete")
        self.assertEqual(self.g.flow()["node"], "F26")

    def test_empty_plan_without_decision_is_refused(self):
        rev = self.c.state()["state_revision"]
        r = self.c.route_answer(_block(rev, [], roadmap_remaining=True))
        self.assertNotEqual(r.kind, "proposal")


if __name__ == "__main__":
    unittest.main()
