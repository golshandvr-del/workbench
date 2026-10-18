"""Projects controller: routing every answer via the Inbox, simple/advanced read models, warnings."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import AI_Workbench as wb  # noqa: E402
from aiwb import inbox  # noqa: E402
from aiwb.v2.controller import SIMPLE_STATUS, ProjectsController  # noqa: E402
from aiwb.v2.models import TASK_STATUSES, ModelError  # noqa: E402
from aiwb.v2.next_action import compute_next_actions  # noqa: E402
from test_v2_flow import manifest  # noqa: E402


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = ProjectsController(self.root, make_pipeline=wb.make_inbox_pipeline)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_status_has_a_word_and_a_symbol(self):
        self.assertEqual(set(SIMPLE_STATUS), set(TASK_STATUSES))
        for sym, word in SIMPLE_STATUS.values():
            self.assertTrue(sym and word)

    def test_every_next_action_type_has_simple_text(self):
        import inspect
        from aiwb.v2 import next_action
        from aiwb.v2.controller import SIMPLE_ACTION
        import re
        types = set(re.findall(r'_act\("([a-z_]+)"', inspect.getsource(next_action)))
        self.assertTrue(types)
        self.assertEqual(types - set(SIMPLE_ACTION), set())

    def test_route_and_modes(self):
        self.c.planning_prompt("Goal")
        self.assertEqual(self.c.state()["settings"]["goal"], "Goal")
        rev = self.c.project.store.revision
        r = self.c.route_answer("<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps({"schema_version": "1.0", "base_state_revision": rev,
                                "summary": "s", "operations": [{"operation": "create_task", "temporary_ref": "a",
                                "title": "T", "objective": "o", "owner_role": "implementer"}]}) + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>")
        self.assertEqual(r.kind, "proposal")
        self.assertEqual(len(inbox.InboxStore(self.root).list()), 1)
        self.c.accept_proposal(r.reference_id, [0])
        tid = self.c.project.tasks.list()[0]["task_id"]
        simple = self.c.task_rows()[0]
        self.assertNotIn("revision", simple)
        self.c.set_mode("advanced")
        adv = self.c.task_rows()[0]
        self.assertEqual((adv["task_id"], adv["status"]), (simple["task_id"], simple["status"]), "same data")
        self.assertIn("revision", adv)
        with self.assertRaises(ModelError):
            self.c.set_mode("expert")
        h = self.c.start_task(tid)
        r2 = self.c.route_answer(manifest(h))
        self.assertEqual((r2.kind, r2.reference_id), ("handoff", h["handoff_id"]))
        self.assertEqual(self.c.route_answer("hello").kind, "inbox_only")
        self.assertEqual(self.c.route_answer("  ").kind, "rejected")
        broken = self.c.route_answer("<<<AIWB_MANAGER_PROPOSAL>>>{bad<<<AIWB_END_MANAGER_PROPOSAL>>>")
        self.assertEqual(broken.kind, "rejected")
        self.assertIn("kept in the Inbox", broken.message)
        self.assertEqual(len(inbox.InboxStore(self.root).list()), 4, "every non-empty answer stored raw")

    def test_warnings_prioritise_decisions(self):
        t = self.c.project.tasks.create({"title": "A", "objective": "a"})
        self.c.project.tasks.transition(t["task_id"], "ready")
        d = self.c.project.decisions.propose("Pick DB", "?", affected_task_ids=[t["task_id"]])
        w = self.c.warnings()
        self.assertTrue(w[0].startswith("Decision needed") and d["decision_id"] in w[0])
        self.assertEqual(compute_next_actions(self.c.state())[0]["type"], "resolve_decision")
        self.assertIn("decision", self.c.next_action_text().lower())

    def test_mode_switch_changes_no_data_and_persists(self):
        t = self.c.project.tasks.create({"title": "A", "objective": "a"})
        rev = self.c.project.store.revision
        before = json.dumps(self.c.state(), sort_keys=True)
        self.c.set_mode("advanced")
        self.c.set_mode("simple")
        self.c.set_mode("advanced")
        self.assertEqual(self.c.project.store.revision, rev, "view switch never bumps state_revision")
        self.assertEqual(json.dumps(self.c.state(), sort_keys=True), before)
        again = ProjectsController(self.root, make_pipeline=wb.make_inbox_pipeline)
        self.assertEqual(again.mode, "advanced", "view preference persisted outside the state")
        (self.c.project.store.dir / "ui.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(ProjectsController(self.root).mode, "simple", "corrupt preference falls back")
        self.assertTrue(t["task_id"])

    def test_next_action_same_meaning_in_both_views(self):
        t = self.c.project.tasks.create({"title": "A", "objective": "a", "owner_agent_id": "agent-implementer"})
        self.c.project.tasks.transition(t["task_id"], "ready")
        self.c.project.tasks.create({"title": "B", "objective": "b"})
        self.c.set_mode("simple")
        simple = self.c.next_action_view()
        self.c.set_mode("advanced")
        adv = self.c.next_action_view()
        for k in ("type", "reference_id", "summary", "needs_approval"):
            self.assertEqual(simple[k], adv[k])
        self.assertNotIn("reason", simple)
        self.assertTrue(adv["reason"])
        self.assertIsInstance(adv["queue"], list)

    def test_advanced_panels_are_read_only_and_complete(self):
        t = self.c.project.tasks.create({"title": "A", "objective": "a", "owner_agent_id": "agent-implementer"})
        self.c.project.tasks.transition(t["task_id"], "ready")
        h = self.c.start_task(t["task_id"])
        d = self.c.project.decisions.propose("Pick", "?")
        self.c.project.evidence.record(type="manual_review", subject_type="task", subject_id=t["task_id"],
                                       source_kind="user", result="approved")
        rev = self.c.project.store.revision
        panels = self.c.advanced_panels()
        self.assertEqual(set(panels), {"Agents", "Decisions", "Evidence", "Attempts", "Proposals", "Publish"})
        self.assertIn("agent-architect", panels["Agents"])
        self.assertIn(d["decision_id"], panels["Decisions"])
        self.assertIn("VERIFIED", panels["Evidence"])
        self.assertIn(h["attempt_id"], panels["Attempts"])
        self.assertIn(h["handoff_id"], panels["Attempts"])
        self.assertIn("locally only", panels["Publish"])
        self.assertEqual(self.c.project.store.revision, rev)

    def test_simple_and_advanced_share_operations(self):
        """§28: the window only calls controller methods; no view-specific write path exists."""
        import inspect
        from aiwb.v2 import projects_window
        src = inspect.getsource(projects_window)
        for forbidden in ("store.transaction", ".tasks.transition(", ".tasks.update(", ".evidence.record(",
                          "handoffs.ingest(", "proposals.review("):
            self.assertNotIn(forbidden, src, forbidden)
        self.assertNotIn('mode == "simple"', src.split("def refresh")[0])


if __name__ == "__main__":
    unittest.main()
