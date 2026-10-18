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


if __name__ == "__main__":
    unittest.main()
