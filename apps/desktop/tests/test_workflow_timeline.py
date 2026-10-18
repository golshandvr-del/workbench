"""Roadmap 2.5.0 (stages 5, 6; Gate B, D): manual workflow projection, user facts, milestones, versions, progress, lanes."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.models import ModelError  # noqa: E402
from aiwb.v2.timeline import lanes, planned_items, progress, set_task_weights  # noqa: E402
from aiwb.v2.workflow import STAGES, stage_label, task_stage  # noqa: E402
from aiwb.workspace.controller import WorkspaceController  # noqa: E402


def _task(p, title="A", owner="agent-implementer", ready=True):
    t = p.tasks.create({"title": title, "objective": "o", "owner_agent_id": owner, "scope": {"include": [f"{title}/**"]},
                        "acceptance_criteria": ["x"]})
    if ready:
        p.tasks.transition(t["task_id"], "ready")
    return t["task_id"]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctl = ProjectsController(Path(self.tmp.name))
        self.p = self.ctl.project

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self, tid):
        return task_stage(self.p.store.load(), tid)["stage"]

    def test_gate_b_prepare_copy_send_are_distinct(self):
        tid = _task(self.p)
        self.assertEqual(self.stage(tid), "ready_to_prepare")
        h = self.ctl.start_task(tid)
        self.assertEqual(self.stage(tid), "prompt_prepared")
        self.ctl.mark_copied(h["handoff_id"])
        self.assertEqual(self.stage(tid), "prompt_copied")
        self.ctl.confirm_sent(h["handoff_id"])
        s = task_stage(self.p.store.load(), tid)
        self.assertEqual(s["stage"], "waiting_for_response")
        self.assertTrue(s["sent_confirmed_at"])
        types = [r["event_type"] for r in self.p.store.ledger.all()]
        self.assertLess(types.index("prompt_copied"), types.index("user_confirmed_sent"))
        rec = [r for r in self.p.store.ledger.all() if r["event_type"] == "user_confirmed_sent"][0]
        self.assertEqual(rec["time_source"], "user_confirmed")
        self.assertEqual(rec["source"], "user")

    def test_copy_twice_counts_and_never_means_sent(self):
        tid = _task(self.p)
        h = self.ctl.start_task(tid)
        self.ctl.mark_copied(h["handoff_id"])
        self.ctl.mark_copied(h["handoff_id"])
        att = self.p.store.load()["attempts"][h["attempt_id"]]
        self.assertEqual(att["workflow"]["copy_count"], 2)
        self.assertNotIn("sent_confirmed_at", att["workflow"])
        self.assertEqual(self.stage(tid), "prompt_copied")

    def test_duplicate_start_warning(self):
        tid = _task(self.p)
        self.assertEqual(self.ctl.start_warning(tid), "")
        h = self.ctl.start_task(tid)
        self.ctl.confirm_sent(h["handoff_id"])
        w = self.ctl.start_warning(tid)
        self.assertIn(h["attempt_id"], w)
        self.assertIn("stale", w)

    def test_confirm_sent_only_for_active_attempt(self):
        tid = _task(self.p)
        h1 = self.ctl.start_task(tid)
        self.ctl.start_task(tid)
        with self.assertRaises(ModelError):
            self.ctl.confirm_sent(h1["handoff_id"])

    def test_attempt_binds_account_and_chat_and_keeps_it(self):
        acc = self.p.resources.add_account({"display_name": "GPT paid", "provider": "GPT"})
        acc2 = self.p.resources.add_account({"display_name": "Claude", "provider": "Claude"})
        self.p.resources.bind_chat("agent-implementer", acc["account_profile_id"], chat_name="c1")
        tid = _task(self.p)
        h = self.ctl.start_task(tid)
        self.ctl.mark_copied(h["handoff_id"])
        self.p.resources.bind_chat("agent-implementer", acc2["account_profile_id"], chat_name="c2")
        wf = self.p.store.load()["attempts"][h["attempt_id"]]["workflow"]
        self.assertEqual(wf["account_profile_id"], acc["account_profile_id"])  # history not rewritten

    def test_confirm_sent_with_foreign_binding_refused(self):
        acc = self.p.resources.add_account({"display_name": "GPT", "provider": "GPT"})
        b = self.p.resources.bind_chat("agent-reviewer", acc["account_profile_id"], chat_name="r")
        tid = _task(self.p)
        h = self.ctl.start_task(tid)
        with self.assertRaises(ModelError):
            self.ctl.confirm_sent(h["handoff_id"], b["chat_binding_id"])

    def test_context_flow_stages(self):
        tid = _task(self.p)
        h = self.ctl.start_task(tid)
        wf = self.p.workflow
        wf.note_context_request(h["attempt_id"])
        self.assertEqual(self.stage(tid), "context_request_pending")
        with self.assertRaises(ModelError):
            wf.mark_context_sent(h["attempt_id"])
        wf.mark_context_prepared(h["attempt_id"], kind="zip")
        self.assertEqual(self.stage(tid), "context_prepared")
        wf.mark_context_sent(h["attempt_id"])
        self.assertNotIn(self.stage(tid), ("context_prepared", "context_request_pending"))

    def test_stage_labels_never_claim_model_activity(self):
        for key, (en, fa) in STAGES.items():
            self.assertNotIn("working", en.lower(), key)
            self.assertEqual(stage_label(key, "fa"), fa)

    def test_draft_and_done_and_cancelled(self):
        tid = _task(self.p, ready=False)
        self.assertEqual(self.stage(tid), "planned")
        self.p.tasks.transition(tid, "cancelled")
        self.assertEqual(self.stage(tid), "abandoned")


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctl = ProjectsController(Path(self.tmp.name))
        self.p = self.ctl.project
        self.ids = [_task(self.p, f"T{i}", ready=False) for i in range(3)]

    def tearDown(self):
        self.tmp.cleanup()

    def test_milestone_accept_requires_done_or_force(self):
        m = self.p.timeline.create_milestone({"title": "MVP", "task_ids": self.ids[:2]})
        with self.assertRaises(ModelError):
            self.p.timeline.accept_milestone(m["milestone_id"])
        out = self.p.timeline.accept_milestone(m["milestone_id"], force=True)
        self.assertEqual(out["status"], "accepted")
        self.assertEqual(out["accepted_with_open"], self.ids[:2])
        with self.assertRaises(ModelError):
            self.p.timeline.update_milestone(m["milestone_id"], {"title": "x"})

    def test_milestone_unknown_task_refused(self):
        with self.assertRaises(ModelError):
            self.p.timeline.create_milestone({"title": "M", "task_ids": ["TASK-9999"]})

    def test_version_flow_needs_real_facts(self):
        v = self.p.timeline.propose_version({"label": "1.0.0", "task_ids": self.ids})
        with self.assertRaises(ModelError):
            self.p.timeline.advance_version(v["version_id"], "released", run_id="1")
        with self.assertRaises(ModelError):
            self.p.timeline.advance_version(v["version_id"], "local")
        with self.assertRaises(ModelError):
            self.p.timeline.advance_version(v["version_id"], "local", commit_sha="not-a-sha!")
        self.p.timeline.advance_version(v["version_id"], "local", commit_sha="abcdef1")
        with self.assertRaises(ModelError):
            self.p.timeline.advance_version(v["version_id"], "tagged")
        self.p.timeline.advance_version(v["version_id"], "tagged", tag="v1.0.0")
        with self.assertRaises(ModelError):
            self.p.timeline.advance_version(v["version_id"], "released")
        out = self.p.timeline.advance_version(v["version_id"], "released", run_id="39160611807")
        self.assertEqual(out["status"], "released")
        self.assertEqual([h["to"] for h in out["history"]], ["local", "tagged", "released"])
        self.assertIn("release_published", [r["event_type"] for r in self.p.store.ledger.all()])

    def test_version_label_policy_and_duplicates(self):
        with self.assertRaises(ModelError):
            self.p.timeline.propose_version({"label": "spring"})
        self.p.timeline.propose_version({"label": "spring", "policy": "free"})
        with self.assertRaises(ModelError):
            self.p.timeline.propose_version({"label": "spring", "policy": "free"})

    def test_adding_task_does_not_create_version(self):
        _task(self.p, "Z")
        self.assertEqual(self.p.timeline.versions(), [])

    def test_progress_counts_and_excludes_cancelled(self):
        self.p.tasks.transition(self.ids[2], "cancelled")
        pr = progress(self.p.store.load())
        self.assertEqual((pr["done"], pr["total"], pr["excluded"]), (0, 2, 1))
        self.assertIsNone(pr["weighted"])

    def test_weighted_progress_only_with_weights_and_estimated(self):
        set_task_weights(self.p.store, {t: 1 for t in self.ids})
        pr = progress(self.p.store.load())
        self.assertTrue(pr["weighted"]["estimated"])
        with self.assertRaises(ModelError):
            set_task_weights(self.p.store, {self.ids[0]: -1})

    def test_lanes_and_planned_items(self):
        self.p.timeline.create_milestone({"title": "M", "task_ids": self.ids, "target_date": "2026-12-01"})
        lz = lanes(self.p.store.ledger.all(), self.p.store.load())
        self.assertIn("agent-implementer", lz)
        self.assertIn("project", lz)
        pl = planned_items(self.p.store.load())
        self.assertTrue(all(x["planned"] for x in pl))

    def test_workspace_read_models_do_not_write(self):
        wc = WorkspaceController(self.ctl)
        rev = self.p.store.load()["state_revision"]
        wc.timeline_lanes()
        wc.milestone_rows()
        wc.version_rows()
        wc.planned()
        wc.task_rows()
        wc.progress_details(wc.overview()["progress"])
        for lang in ("en", "fa"):
            wc.set_language(lang)
            wc.task_rows()
        self.assertEqual(self.p.store.load()["state_revision"], rev)

    def test_progress_text_shows_numerator_and_denominator(self):
        wc = WorkspaceController(self.ctl)
        txt = wc.progress_text(wc.overview()["progress"])
        self.assertIn("0", txt)
        self.assertIn("3", txt)


if __name__ == "__main__":
    unittest.main()
