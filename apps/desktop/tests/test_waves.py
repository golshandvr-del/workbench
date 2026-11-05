"""Roadmap 4.1.0 gate: parallel paths and the dispatch desk (flowchart F9–F12, correction C3).

* waves follow dependencies; cycles and dead prerequisites are reported, not looped over;
* the dispatch desk never opens more chats than ``max_parallel_chats``, spreads the first prompts over the AI
  lanes, and queues the rest;
* "Prepare all prompts" makes one handoff per task of the wave, and the flow then sits at F11 → F12.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2 import waves  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.guide import Guide  # noqa: E402


def _t(tid, status="ready", deps=(), owner="agent-implementer"):
    return {"task_id": tid, "status": status, "depends_on": list(deps), "owner_agent_id": owner}


def _state(tasks, limit=2, handoffs=None):
    return {"tasks": {t["task_id"]: t for t in tasks}, "handoffs": handoffs or {},
            "agents": {"agent-implementer": {}, "agent-ui": {}, "agent-tester": {}},
            "settings": {"team": {"max_parallel_chats": limit}}}


class WaveTests(unittest.TestCase):
    def test_waves_follow_dependencies(self):
        st = _state([_t("T-1"), _t("T-2"), _t("T-3", "blocked", ["T-1"]), _t("T-4", "blocked", ["T-3", "T-2"]),
                     _t("T-5", "done")])
        self.assertEqual(waves.waves(st)["waves"], [["T-1", "T-2"], ["T-3"], ["T-4"]])

    def test_cycle_and_dead_prerequisites_are_reported(self):
        st = _state([_t("T-1", deps=["T-2"]), _t("T-2", deps=["T-1"]), _t("T-3", deps=["T-9"]),
                     _t("T-4", deps=["T-5"]), _t("T-5", "cancelled"), _t("T-6")])
        w = waves.waves(st)
        self.assertEqual(w["waves"], [["T-6"]])
        self.assertEqual(w["cycle"], ["T-1", "T-2"])
        self.assertEqual(w["dead"], ["T-3", "T-4"])

    def test_lanes_group_by_owner(self):
        st = _state([_t("T-1"), _t("T-2", owner="agent-ui"), _t("T-3", owner="agent-ui"), _t("T-4", owner="nobody")])
        self.assertEqual(waves.lanes(st), {"agent-implementer": ["T-1", "T-4"], "agent-ui": ["T-2", "T-3"]})


class DeskTests(unittest.TestCase):
    def test_chat_limit_and_lane_fairness(self):
        st = _state([_t("T-1"), _t("T-2"), _t("T-3", owner="agent-ui"), _t("T-4", owner="agent-tester")], limit=3)
        d = waves.dispatch(st)
        self.assertEqual(d["next"], ["T-1", "T-3", "T-4"])  # one per AI lane first
        self.assertEqual(d["queued"], ["T-2"])
        self.assertEqual(d["slots"], 3)

    def test_open_chats_use_slots(self):
        hs = {"H-1": {"handoff_id": "H-1", "task_id": "T-1", "status": "prompt_exported"}}
        st = _state([_t("T-1", "in_progress"), _t("T-2"), _t("T-3")], limit=2, handoffs=hs)
        d = waves.dispatch(st)
        self.assertEqual(d["active"], ["H-1"])
        self.assertEqual(d["slots"], 1)
        self.assertEqual(d["next"], ["T-2"])
        self.assertEqual(d["queued"], ["T-3"])
        st["settings"]["team"]["max_parallel_chats"] = 1
        self.assertEqual(waves.dispatch(st)["next"], [])

    def test_blocked_tasks_wait_for_their_wave(self):
        st = _state([_t("T-1"), _t("T-2", "blocked", ["T-1"])], limit=5)
        self.assertEqual(waves.dispatch(st)["next"], ["T-1"])


class GuideDeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        tasks = self.c.project.tasks
        for i, owner in enumerate(("agent-implementer", "agent-implementer", "agent-reviewer")):
            t = tasks.create({"title": f"Task {i}", "objective": f"Do part {i}", "owner_agent_id": owner,
                              "allowed_paths": [f"src/p{i}/"], "acceptance_criteria": ["works"]}, status="ready")
        with self.c.project.store.transaction("t") as s:
            s["settings"]["goal"] = "x"
            s["settings"].setdefault("team", {})["max_parallel_chats"] = 2
        self.tid = t["task_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_bf035_cancellation_retires_prompts_and_refuses_late_publication(self):
        import json
        from aiwb.v2 import files
        from aiwb.v2.models import ModelError
        for route in ("direct", "proposal", "supersede"):
            for received in (False, True):
                with self.subTest(route=route, received=received), tempfile.TemporaryDirectory() as tmp:
                    c = ProjectsController(Path(tmp), make_pipeline=wb.make_inbox_pipeline)
                    p = c.project
                    with p.store.transaction("one chat") as s:
                        s["settings"]["goal"] = "test cancellation"
                        s["settings"].setdefault("team", {})["max_parallel_chats"] = 1
                    ids = [p.tasks.create({"title": f"Part {i}", "objective": "test", "owner_agent_id": "agent-implementer",
                            "allowed_paths": [f"src/p{i}/"], "acceptance_criteria": ["works"]}, status="ready")["task_id"]
                           for i in range(2)]
                    h = c.start_task(ids[0])
                    hid = h["handoff_id"]
                    answer = (f'AIWB_ATTEMPT_ID: {h["attempt_id"]}\n'
                              '<<<AIWB_FILE path="src/p0/new.py" action="write">>>\n````\nVALUE = 1\n````\n<<<AIWB_END_FILE>>>\n'
                              '<<<AIWB_HANDOFF>>>\n' + json.dumps({"handoff_id": hid, "task_id": ids[0],
                              "attempt_id": h["attempt_id"], "outcome": "complete"}) + '\n<<<AIWB_END_HANDOFF>>>')
                    if received:
                        self.assertEqual(c.route_answer(answer).kind, "handoff")
                    if route == "proposal":
                        proposal = p.proposals.import_data({"base_state_revision": c.state()["state_revision"],
                            "operations": [{"operation": "close_or_cancel_task", "task_id": ids[0], "reason": "not wanted"}]})
                        p.proposals.review(proposal["proposal_id"], accept=[0])
                    else:
                        p.tasks.transition(ids[0], "superseded" if route == "supersede" else "cancelled", "not wanted")
                    st = c.state()
                    self.assertEqual(st["handoffs"][hid]["status"], "superseded")
                    self.assertEqual(st["attempts"][h["attempt_id"]]["status"], "abandoned")
                    self.assertFalse(st["tasks"][ids[0]].get("active_attempt_id"))
                    self.assertEqual(waves.dispatch(st)["next"], [ids[1]])
                    self.assertFalse(any(x["key"] == f"handoff:{hid}" for x in Guide(c).steps()))
                    # A reply arriving after cancellation is retained, but cannot revive or publish unwanted work.
                    p.handoffs.ingest(hid, "late-response", answer)
                    files.stage(p.store, hid, answer)
                    self.assertIn("late-response", c.state()["attempts"][h["attempt_id"]]["response_ids"])
                    for reason in (None, "accept anyway"):
                        before = c.state()
                        with self.assertRaises(ModelError):
                            files.integrate(p.store, p.store.root, hid, accept_reason=reason)
                        self.assertEqual(c.state(), before)
                    with self.assertRaises(ModelError):
                        p.handoffs.resolve(hid, True, "accept anyway")
                    self.assertFalse((p.store.root / "src/p0/new.py").exists())
                    self.assertEqual(waves.dispatch(c.state())["next"], [ids[1]])

    def test_bf035_cancellation_save_failure_keeps_entire_open_lifecycle(self):
        from unittest.mock import patch
        h = self.c.start_task(self.tid)
        before = self.c.state()
        with patch.object(self.c.project.store, "_write", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.c.project.tasks.transition(self.tid, "cancelled", "not wanted")
        self.assertEqual(self.c.state(), before)
        self.c.project.tasks.transition(self.tid, "cancelled", "retry")
        self.assertEqual(self.c.state()["handoffs"][h["handoff_id"]]["status"], "superseded")

    def test_bf035_all_open_states_retire_without_erasing_accepted_history(self):
        from aiwb.v2.models import MACHINES
        p = self.c.project
        h = self.c.start_task(self.tid)
        hid, aid = h["handoff_id"], h["attempt_id"]
        for status in ("prepared", "prompt_exported", "response_received", "parsed", "reconciled", "stale", "reconciliation_required"):
            for attempt_status in MACHINES["attempt"]:
                with self.subTest(handoff=status, attempt=attempt_status):
                    with p.store.transaction("old lifecycle fixture") as s:
                        s["tasks"][self.tid].update(status="in_progress", active_attempt_id=aid)
                        s["handoffs"][hid]["status"] = status
                        s["attempts"][aid]["status"] = attempt_status
                    p.tasks.transition(self.tid, "cancelled", "not wanted")
                    state = self.c.state()
                    self.assertEqual(state["handoffs"][hid]["status"], "superseded")
                    expected = attempt_status if attempt_status in ("accepted", "rejected", "abandoned") else "abandoned"
                    self.assertEqual(state["attempts"][aid]["status"], expected)
        with p.store.transaction("accepted historical delivery") as s:
            s["tasks"][self.tid]["status"] = "in_progress"
            s["handoffs"][hid]["status"] = "accepted"
            s["attempts"][aid]["status"] = "accepted"
        p.tasks.transition(self.tid, "cancelled", "not wanted")
        self.assertEqual(self.c.state()["handoffs"][hid]["status"], "accepted")
        self.assertEqual(self.c.state()["attempts"][aid]["status"], "accepted")

    def test_prepare_all_opens_one_chat_per_task_within_the_limit(self):
        steps = self.g.steps()
        desk = next(s for s in steps if s["key"] == "dispatch")
        self.assertEqual(len(desk["task_ids"]), 2)
        starts = [s for s in steps if s["key"].startswith("task:") and s["kind"] == "prompt"]
        self.assertEqual(len(starts), 2, "only the tasks of this wave get a start step")
        self.assertEqual(self.g.flow()["node"], "F10")
        out = self.g.perform("dispatch", "prepare_all")
        self.assertEqual(len(out["handoff_ids"]), 2)
        self.assertEqual(self.g.flow()["node"], "F11")
        self.assertFalse([s for s in self.g.steps() if s["key"] == "dispatch"], "no free chat left")
        for hid in out["handoff_ids"]:
            self.g.perform(f"handoff:{hid}", "sent")
        self.assertEqual(self.g.flow()["node"], "F12")


if __name__ == "__main__":
    unittest.main()
