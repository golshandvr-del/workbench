"""Roadmap 5.2.0: the Mission Map model — lanes per AI, version columns, node states, layout (pure, no Tk)."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aiwb.ui import mission_model as mm  # noqa: E402


def five_ai_state() -> dict:
    agents = {f"a{i}": {"agent_id": f"a{i}", "name": f"Agent {i}", "role": "implementer"} for i in range(1, 6)}
    agents["pm"] = {"agent_id": "pm", "name": "PM", "role": "project_manager"}
    tasks, versions = {}, {}
    labels = ["1.0.0", "0.2.0", "0.10.0", "0.1.0"]  # deliberately unsorted; 0.10.0 > 0.2.0
    for vi, lab in enumerate(labels):
        ids = []
        for a in range(1, 6):
            tid = f"t-{lab}-{a}"
            ids.append(tid)
            tasks[tid] = {"task_id": tid, "title": f"{lab} #{a}", "status": "draft", "owner_agent_id": f"a{a}"}
        versions[f"v{vi}"] = {"version_id": f"v{vi}", "label": lab, "status": "planned", "task_ids": ids}
    return {"project_id": "p", "agents": agents, "tasks": tasks, "versions": versions, "milestones": {},
            "handoffs": {}, "state_revision": 3}


class NodeStateTests(unittest.TestCase):
    def test_states(self) -> None:
        self.assertEqual(mm.node_state({"status": "done"}), "done")
        self.assertEqual(mm.node_state({"status": "blocked"}), "blocked")
        self.assertEqual(mm.node_state({"status": "needs_decision"}), "attention")
        for st in ("ready", "in_progress", "in_review", "validation_pending"):
            self.assertEqual(mm.node_state({"status": st}), "active", st)
        self.assertEqual(mm.node_state({"status": "draft"}), "idle")
        self.assertEqual(mm.node_state({"status": "draft"}, handoff_open=True), "active")


class BuildTests(unittest.TestCase):
    def test_empty(self) -> None:
        for st in (None, {}):
            m = mm.build(st)
            self.assertTrue(m["empty"])
            self.assertEqual(m["lanes"], [])

    def test_one_lane_per_ai_and_semver_columns(self) -> None:
        m = mm.build(five_ai_state())
        self.assertEqual([ln["agent_id"] for ln in m["lanes"]], ["a1", "a2", "a3", "a4", "a5"])
        self.assertEqual([ln["number"] for ln in m["lanes"]], [1, 2, 3, 4, 5])
        self.assertEqual([c["label"] for c in m["columns"]], ["0.1.0", "0.2.0", "0.10.0", "1.0.0"])
        for ln in m["lanes"]:
            self.assertEqual(len(ln["nodes"]), 4)
            for nd in ln["nodes"]:
                self.assertEqual(m["columns"][nd["column"]]["label"], nd["title"].split(" ")[0])
        self.assertEqual(m["counts"]["idle"], 20)

    def test_milestone_tasks_go_to_the_version_column(self) -> None:
        st = five_ai_state()
        st["milestones"] = {"m1": {"milestone_id": "m1", "status": "planned", "task_ids": ["extra"]}}
        st["tasks"]["extra"] = {"task_id": "extra", "title": "x", "status": "in_progress", "owner_agent_id": "a2"}
        st["versions"]["v1"]["milestone_ids"] = ["m1"]  # 0.2.0
        m = mm.build(st)
        nd = next(n for n in m["lanes"][1]["nodes"] if n["task_id"] == "extra")
        self.assertEqual(m["columns"][nd["column"]]["label"], "0.2.0")
        self.assertEqual(nd["slot"], 1)  # side by side with the lane's other 0.2.0 task
        self.assertEqual(m["slots"][nd["column"]], 2)
        self.assertTrue(m["lanes"][1]["live"])

    def test_unclaimed_tasks_go_to_later_and_hidden_are_dropped(self) -> None:
        st = five_ai_state()
        st["tasks"]["loose"] = {"task_id": "loose", "title": "l", "status": "draft", "owner_agent_id": "a1"}
        st["tasks"]["gone"] = {"task_id": "gone", "title": "g", "status": "cancelled", "owner_agent_id": "a1"}
        m = mm.build(st)
        self.assertEqual(m["columns"][-1]["label"], mm.LATER)
        ids = [n["task_id"] for n in m["lanes"][0]["nodes"]]
        self.assertIn("loose", ids)
        self.assertNotIn("gone", ids)

    def test_withdrawn_versions_are_not_columns(self) -> None:
        st = five_ai_state()
        st["versions"]["v0"]["status"] = "withdrawn"  # 1.0.0
        m = mm.build(st)
        self.assertNotIn("1.0.0", [c["label"] for c in m["columns"]])
        self.assertEqual(m["columns"][-1]["label"], mm.LATER)  # its tasks are now unclaimed

    def test_no_versions_uses_milestones_then_next(self) -> None:
        st = five_ai_state()
        st["versions"] = {}
        self.assertEqual([c["label"] for c in mm.build(st)["columns"]], [mm.NEXT])
        st["milestones"] = {"m1": {"milestone_id": "m1", "title": "Alpha", "status": "planned",
                                   "task_ids": list(st["tasks"])}}
        self.assertEqual([c["label"] for c in mm.build(st)["columns"]], ["Alpha"])

    def test_unknown_owner_goes_to_unassigned_last(self) -> None:
        st = five_ai_state()
        st["tasks"]["orphan"] = {"task_id": "orphan", "title": "o", "status": "draft", "owner_agent_id": "ghost"}
        m = mm.build(st)
        self.assertEqual(m["lanes"][-1]["agent_id"], "unassigned")

    def test_team_without_tasks_still_shows_lanes_but_not_pm(self) -> None:
        st = five_ai_state()
        st["tasks"], st["versions"] = {}, {}
        m = mm.build(st)
        self.assertEqual([ln["agent_id"] for ln in m["lanes"]], ["a1", "a2", "a3", "a4", "a5"])

    def test_open_handoff_makes_node_active(self) -> None:
        st = five_ai_state()
        tid = "t-0.1.0-3"
        st["handoffs"] = {"h": {"handoff_id": "h", "task_id": tid, "status": "prompt_exported"}}
        m = mm.build(st)
        nd = next(n for n in m["lanes"][2]["nodes"] if n["task_id"] == tid)
        self.assertEqual(nd["state"], "active")

    def test_build_never_mutates_state(self) -> None:
        st = five_ai_state()
        before = copy.deepcopy(st)
        mm.build(st)
        self.assertEqual(st, before)

    def test_real_project_state(self) -> None:
        import fixtures_ten_agents
        with tempfile.TemporaryDirectory() as tmp:
            fx = fixtures_ten_agents.build(Path(tmp))
            st = fx["ctl"].state() if "ctl" in fx else None
            if st is None:
                from aiwb.v2.controller import ProjectsController
                st = ProjectsController(Path(tmp)).state()
            m = mm.build(st)
            self.assertFalse(m["empty"])
            self.assertEqual(len(m["lanes"]), 9)  # the project manager has no tasks
            self.assertGreater(m["counts"]["active"], 0)


class LayoutTests(unittest.TestCase):
    def test_positions_and_scale(self) -> None:
        m = mm.build(five_ai_state())
        g1, g2 = mm.layout(m, 1.0), mm.layout(m, 2.0)
        self.assertEqual(len(g1["lane_y"]), 5)
        self.assertEqual(g1["lane_y"], sorted(g1["lane_y"]))
        self.assertEqual(g1["col_x"], sorted(g1["col_x"]))
        self.assertLess(g1["hex_x"], g1["col_x"][0])
        self.assertLess(g1["col_x"][-1], g1["end_x"])
        self.assertAlmostEqual(g2["width"], g1["width"] * 2, delta=1)
        ys = {round(y) for (_x, y) in g1["nodes"].values()}
        self.assertEqual(ys, {round(y) for y in g1["lane_y"]})
        self.assertEqual(len(set(g1["nodes"].values())), 20)  # no two circles on top of each other
        cx, cy, cw = g1["capsule"]
        self.assertLess(cx + cw, g1["source"][0])
        self.assertAlmostEqual(cy, (g1["lane_y"][0] + g1["lane_y"][-1]) / 2)


if __name__ == "__main__":
    unittest.main()
