"""Roadmap 5.4.0: the Mission Map right-click menu — every row maps to a real Guide action for that task's state.

* Synthetic Guide steps: each task state enables exactly the rows the Guide allows, in the preferred action order.
* A real project driven through the Guide: ready task → COPY PROMPT (prepare) → SEND PROMPT → GET AI RESPONSE
  enabled, and the rows of other tasks are unaffected.
* Keyboard helpers skip disabled rows and wrap.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.ui import structure5, task_menu  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.guide import Guide, _a, _step  # noqa: E402
from aiwb.v2.models import normalize_agent  # noqa: E402


def enabled(rows):
    return {r["id"]: r["action"] for r in rows if r["enabled"]}


class PureMenuTests(unittest.TestCase):
    def test_rows_follow_structure5(self):
        rows = task_menu.items([], "T-1")
        self.assertEqual([r["label"] for r in rows], [m[1] for m in structure5.TASK_MENU])
        self.assertFalse(any(r["enabled"] for r in rows))
        self.assertTrue(all(r["hint"] for r in rows), "a disabled row explains itself")

    def test_ready_task_offers_copy_only(self):
        st = [_step("task:T-1", "prompt", "Start", "", [_a("prepare", "Prepare the prompt")], task_id="T-1")]
        self.assertEqual(enabled(task_menu.items(st, "T-1")), {"copy_prompt": "prepare"})

    def test_open_handoff_states(self):
        def h(acts):
            return [_step("handoff:H-1", "prompt", "x", "", acts, task_id="T-1")]
        not_copied = h([_a("copy", "Copy prompt"), _a("sent", "I sent it"), _a("paste", "Paste", "text"),
                        _a("abandon", "Drop…", "reason")])
        self.assertEqual(enabled(task_menu.items(not_copied, "T-1")),
                         {"copy_prompt": "copy", "send_prompt": "sent", "get_response": "paste"})
        sent = h([_a("paste", "Paste the answer", "text"), _a("copy", "Copy the prompt again")])
        rows = task_menu.items(sent, "T-1")
        self.assertEqual(enabled(rows), {"copy_prompt": "copy", "get_response": "paste"})
        self.assertEqual(next(r for r in rows if r["id"] == "get_response")["needs"], ["text"])

    def test_mark_done_prefers_accept_then_review_then_validation(self):
        st = [_step("handoff:H-2", "decision", "Check", "", [_a("accept_handoff", "Accept the delivery"),
                                                            _a("reject_handoff", "Reject…", "reason")], task_id="T-2"),
              _step("task:T-3", "decision", "Review", "", [_a("approve", "Approve"),
                                                          _a("reject_review", "Needs changes…", "note")]),
              _step("task:T-4", "decision", "Verify", "", [_a("validation_passed", "Tests passed…", "run_id"),
                                                          _a("waive_validation", "Accept on review…", "reason")])]
        self.assertEqual(enabled(task_menu.items(st, "T-2")), {"mark_done": "accept_handoff"})
        self.assertEqual(enabled(task_menu.items(st, "T-3")), {"mark_done": "approve"})
        r4 = task_menu.items(st, "T-4")
        self.assertEqual(enabled(r4), {"mark_done": "validation_passed"})
        self.assertEqual(r4[3]["step"], "task:T-4")

    def test_other_tasks_do_not_leak(self):
        st = [_step("task:T-1", "prompt", "Start", "", [_a("prepare", "Prepare")], task_id="T-1")]
        self.assertEqual(enabled(task_menu.items(st, "T-9")), {})

    def test_step_task(self):
        self.assertEqual(task_menu.step_task({"key": "task:T-7"}), "T-7")
        self.assertEqual(task_menu.step_task({"key": "handoff:H-1", "task_id": "T-8"}), "T-8")
        self.assertEqual(task_menu.step_task({"key": "dispatch"}), "")

    def test_keyboard_moves_skip_disabled_and_wrap(self):
        rows = [{"enabled": True}, {"enabled": False}, {"enabled": True}, {"enabled": False}]
        self.assertEqual(task_menu.first_enabled(rows), 0)
        self.assertEqual(task_menu.move(rows, 0, 1), 2)
        self.assertEqual(task_menu.move(rows, 2, 1), 0)
        self.assertEqual(task_menu.move(rows, 0, -1), 2)
        none = [{"enabled": False}] * 3
        self.assertEqual(task_menu.first_enabled(none), -1)
        self.assertEqual(task_menu.move(none, -1, 1), -1)

    def test_every_menu_action_exists_in_guide(self):
        src = (Path(__file__).resolve().parents[1] / "src/aiwb/v2/guide.py").read_text(encoding="utf-8")
        for item_id, _l, _i, allowed in structure5.TASK_MENU:
            self.assertEqual(set(task_menu.PREFERENCE[item_id]), set(allowed), item_id)
            for a in allowed:
                self.assertIn(f'_a("{a}"', src)


class RealGuideMenuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        p = self.c.project
        with p.store.transaction("agents") as s:
            for i in (1, 2):
                aid = f"agent-ai-{i}"
                s["agents"][aid] = normalize_agent({"agent_id": aid, "role": "implementer", "name": f"Builder {i}",
                                                    "template_id": ""})
        self.t1 = p.tasks.create({"title": "One", "objective": "o", "owner_agent_id": "agent-ai-1",
                                  "scope": {"include": ["a/**"]}, "acceptance_criteria": ["ok"]})["task_id"]
        self.t2 = p.tasks.create({"title": "Two", "objective": "o", "owner_agent_id": "agent-ai-2",
                                  "scope": {"include": ["b/**"]}, "acceptance_criteria": ["ok"]})["task_id"]
        p.tasks.transition(self.t1, "ready")

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, tid):
        return task_menu.items(Guide(self.c).steps(), tid)

    def run_row(self, tid, item):
        row = next(r for r in self.rows(tid) if r["id"] == item)
        self.assertTrue(row["enabled"], row)
        return Guide(self.c).perform(row["step"], row["action"])

    def test_copy_send_then_response(self):
        self.assertEqual(enabled(self.rows(self.t1)), {"copy_prompt": "prepare"})
        self.assertEqual(enabled(self.rows(self.t2)), {})
        out = self.run_row(self.t1, "copy_prompt")
        self.assertTrue(out.get("prompt") and out.get("handoff_id"))
        Guide(self.c).perform(f"handoff:{out['handoff_id']}", "copy")
        self.assertIn("send_prompt", enabled(self.rows(self.t1)))
        self.run_row(self.t1, "send_prompt")
        after = enabled(self.rows(self.t1))
        self.assertEqual(after.get("get_response"), "paste")
        self.assertNotIn("send_prompt", after)
        self.assertEqual(enabled(self.rows(self.t2)), {})


if __name__ == "__main__":
    unittest.main()
