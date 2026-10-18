"""Roadmap 2.6.0 (stages 7, 8; Gate C): needs-attention queue, team dashboard, change routes, context requests."""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures_ten_agents as fx  # noqa: E402
from aiwb.v2.changes import suggest_route  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.dashboard import RANKS, attention_queue, filter_agents, summarize, team_overview  # noqa: E402
from aiwb.v2.models import ModelError  # noqa: E402
from aiwb.workspace.controller import WorkspaceController  # noqa: E402


class GateCTenAgents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = fx.build(Path(cls.tmp.name))
        cls.st = cls.d["ctl"].state()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_failures_are_separated_and_ranked(self):
        q = attention_queue(self.st)
        sp = self.d["special"]
        by_ref = {i["ref"]: i for i in q}
        self.assertEqual(q[0]["ref"], sp["decision"])
        self.assertEqual(by_ref[sp["stale"]]["rank"], 2)
        self.assertEqual(by_ref[sp["partial"]]["rank"], 3)
        self.assertEqual(by_ref[sp["parse_failed"]]["rank"], 3)
        self.assertNotIn(sp["waiting"], by_ref)  # waiting for the user's paste is info, not an alarm
        ranks = [i["rank"] for i in q]
        self.assertEqual(ranks, sorted(ranks))

    def test_every_item_explains_why_and_what(self):
        for i in attention_queue(self.st):
            self.assertTrue(i["why"] and i["ask"] and i["rank_text"] in [v[0] for v in RANKS.values()], i)
            if i["kind"] == "task" and i["rank"] <= 3:
                self.assertTrue(i["trace"]["attempt_id"], i)

    def test_deterministic(self):
        self.assertEqual(attention_queue(self.st), attention_queue(self.st))

    def test_info_only_when_asked(self):
        refs = {i["ref"] for i in attention_queue(self.st, include_info=True)}
        self.assertIn(self.d["special"]["waiting"], refs)

    def test_compact_density_and_summary(self):
        ov = team_overview(self.st)
        self.assertEqual(ov["density"], "compact")
        s = summarize(attention_queue(self.st), max_per_rank=3)
        more = [i for i in s if i["kind"] == "more"]
        self.assertTrue(more and more[0]["hidden"])
        self.assertLess(len(s), len(attention_queue(self.st)))

    def test_agent_attention_counts_and_filters(self):
        ov = team_overview(self.st)
        by = {a["agent_id"]: a for a in ov["agents"]}
        self.assertGreaterEqual(by["agent-fx-03"]["attention"], 1)
        self.assertEqual(by["agent-fx-04"]["stage"], "ready_to_prepare")  # its other task is ready; waiting is lower
        only = filter_agents(ov["agents"], attention_only=True)
        self.assertTrue(all(a["attention"] for a in only))
        self.assertEqual([a["agent_id"] for a in filter_agents(ov["agents"], text="chat 3")], ["agent-fx-03"])

    def test_only_two_items_when_only_two_need_action(self):
        with tempfile.TemporaryDirectory() as t:
            ctl = ProjectsController(Path(t))
            p = ctl.project
            for i in range(10):
                p.tasks.create({"title": f"draft {i}", "objective": "o"})
            p.decisions.propose("A", "a")
            p.decisions.propose("B", "b")
            q = attention_queue(ctl.state())
            self.assertEqual([i["kind"] for i in q], ["decision", "decision"])

    def test_queue_speed_with_ten_agents(self):
        t0 = time.perf_counter()
        for _ in range(20):
            attention_queue(self.st)
            team_overview(self.st)
        self.assertLess((time.perf_counter() - t0) / 20, 0.25)


class WorkspaceDashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fx.build(Path(self.tmp.name), n_agents=6)
        self.wc = WorkspaceController(self.d["ctl"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_mark_seen_hides_but_keeps_history(self):
        items = self.wc.attention(collapse=False)
        events = self.d["ctl"].project.store.ledger.count()
        rev = self.d["ctl"].state()["state_revision"]
        self.wc.mark_seen([items[0]["key"]])
        left = self.wc.attention(collapse=False, hide_seen=True)
        self.assertNotIn(items[0]["key"], [i["key"] for i in left])
        self.assertEqual(self.d["ctl"].project.store.ledger.count(), events)
        self.assertEqual(self.d["ctl"].state()["state_revision"], rev)
        self.wc.clear_seen()
        self.assertEqual(len(self.wc.attention(collapse=False, hide_seen=True)), len(items))

    def test_open_attention_selects_task(self):
        item = next(i for i in self.wc.attention(collapse=False) if i["kind"] == "task")
        section, ref = self.wc.open_attention(item)
        self.assertEqual((section, self.wc.selection), ("tasks", ("task", ref)))

    def test_dashboard_fa_labels(self):
        self.wc.set_language("fa")
        q = self.wc.attention(collapse=False)
        self.assertTrue(any("پاسخ" in i["rank_text"] or "تصمیم" in i["rank_text"] for i in q))
        self.wc.set_language("en")


class ChangeRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctl = ProjectsController(Path(self.tmp.name))
        self.p = self.ctl.project
        t = self.p.tasks.create({"title": "Login form", "objective": "o", "owner_agent_id": "agent-implementer",
                                 "scope": {"include": ["src/login/**"]}, "acceptance_criteria": ["login works"]})
        self.p.tasks.transition(t["task_id"], "ready")
        self.tid = t["task_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_suggestions(self):
        st = self.ctl.state()
        self.assertEqual(suggest_route(st, self.tid, "fix the login button colour")["route"], "revise")
        self.assertEqual(suggest_route(st, self.tid, "add a new feature: export to PDF")["route"], "new_task")
        self.assertEqual(suggest_route(st, self.tid, "migrate the whole app to another framework")["route"], "replan")
        self.assertTrue(suggest_route(st, self.tid, "hmm")["ambiguous"])
        with self.assertRaises(ModelError):
            suggest_route(st, self.tid, " ")

    def test_revise_creates_revision_and_old_attempt_goes_stale(self):
        h = self.ctl.start_task(self.tid)
        out = self.ctl.apply_change_route(self.tid, "revise", "fix the login error message")
        self.assertEqual(out["revision"], 2)
        self.assertIn("stale", out["message"])
        self.assertTrue(self.ctl.state()["handoffs"][h["handoff_id"]])

    def test_new_task_depends_on_open_task(self):
        out = self.ctl.apply_change_route(self.tid, "new_task", "add password reset")
        t = self.ctl.state()["tasks"][out["task_id"]]
        self.assertEqual((t["status"], t["depends_on"]), ("draft", [self.tid]))

    def test_replan_changes_nothing(self):
        rev = self.ctl.state()["state_revision"]
        out = self.ctl.apply_change_route(self.tid, "replan", "switch database")
        self.assertIn("AIWB_MANAGER_PROPOSAL", out["prompt"])
        self.assertEqual(self.ctl.state()["state_revision"], rev)

    def test_bad_route(self):
        with self.assertRaises(ModelError):
            self.ctl.apply_change_route(self.tid, "guess", "x")

    def test_context_request_answer_is_routed(self):
        h = self.ctl.start_task(self.tid)
        body = {"schema_version": "1.0", "type": "AIWB_CONTEXT_REQUEST", "attempt_id": h["attempt_id"],
                "task_id": self.tid, "reason": "need the form", "files": [{"path": "src/login/form.py"}]}
        r = self.ctl.route_answer("I need more.\n<<<AIWB_CONTEXT_REQUEST>>>\n" + json.dumps(body)
                                  + "\n<<<AIWB_END_CONTEXT_REQUEST>>>")
        self.assertEqual(r.kind, "context_request")
        self.assertIn("src/login/form.py", r.message)
        from aiwb.v2.workflow import task_stage
        self.assertEqual(task_stage(self.ctl.state(), self.tid)["stage"], "context_request_pending")
        q = attention_queue(self.ctl.state())
        self.assertEqual(next(i for i in q if i["ref"] == self.tid)["action"], "open_context")

    def test_broken_context_request_changes_nothing(self):
        rev = self.ctl.state()["state_revision"]
        r = self.ctl.route_answer("<<<AIWB_CONTEXT_REQUEST>>>\n{bad\n<<<AIWB_END_CONTEXT_REQUEST>>>")
        self.assertEqual(r.kind, "rejected")
        self.assertEqual(self.ctl.state()["state_revision"], rev)


if __name__ == "__main__":
    unittest.main()
