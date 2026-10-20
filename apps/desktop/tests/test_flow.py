"""Roadmap 4.0.0 gate: the owner's algorithm (``project-flow.v1``) — nodes F1–F8 on the desktop.

* The flow in code equals the shared contract fixture (the phone checks the same fixture).
* Every edge points to a known node; every node is reachable from F1; the loops of the flowchart exist.
* Walking a real project through the guide visits F1 → F4 → F5 → F6 → F7 → F8 → F9 in order, and the start form
  records name, goal, platform, constraints and the number of AIs, and starts the timeline once.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2 import flow  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.guide import Guide  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FLOW = REPO / "packages/contracts/fixtures/flow/project-flow.v1.json"
CHARTER = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"


class ContractTests(unittest.TestCase):
    def test_code_matches_the_shared_fixture(self):
        fixture = json.loads(FLOW.read_text(encoding="utf-8"))
        mine = flow.as_contract()
        for k in ("phases", "nodes", "edges", "limits"):
            self.assertEqual(mine[k], fixture[k], k)

    def test_graph_is_sound(self):
        ids = {n[0] for n in flow.NODES}
        self.assertEqual(len(ids), 28)
        for a, b, _ in flow.EDGES:
            self.assertIn(a, ids)
            self.assertIn(b, ids)
        seen, todo = set(), ["F1"]
        while todo:
            n = todo.pop()
            if n not in seen:
                seen.add(n)
                todo += [b for a, b, _ in flow.EDGES if a == n]
        self.assertEqual(seen, ids, "every node is reachable from F1")
        for loop in (("F15", "F11"), ("F21", "F10"), ("F25", "F10"), ("F27", "F1")):
            self.assertIn(loop, {(a, b) for a, b, _ in flow.EDGES})
        for n in flow.NODES:
            self.assertIn(n[3], flow.PHASES)
            self.assertIn(n[2], ("app", "user", "github"))
        decisions = {a for a, _, w in flow.EDGES if w}
        self.assertEqual(decisions, {"F13", "F21", "F23", "F25", "F27"})


class WalkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)

    def tearDown(self):
        self.tmp.cleanup()

    def node(self) -> str:
        return self.g.flow()["node"]

    def test_start_to_split_follows_the_flowchart(self):
        visited = [self.node()]
        self.assertEqual(visited[0], "F1")
        step = self.g.steps()[0]
        self.assertEqual(step["key"], "design")
        self.assertEqual(step["actions"][0]["needs"], ["goal", "name", "platform", "constraints", "ais"])
        out = self.g.perform("design", "design", goal="A simple Android calculator", name="Calc",
                             platform="Android, Kotlin", constraints="offline", ais="3")
        self.assertIn("- Name: Calc", out["prompt"])
        self.assertIn("Platform / technology: Android, Kotlin", out["prompt"])
        self.assertIn("Maximum chats the user will follow at the same time: 3", out["prompt"])
        st = self.c.state()
        self.assertEqual(st["settings"]["team"]["max_parallel_chats"], 3)
        self.assertEqual([e["type"] for e in st["events"]].count("project_started"), 1)
        visited.append(self.node())
        self.g.perform("charter", "copy")
        visited.append(self.node())
        self.g.perform("charter", "sent")
        visited.append(self.node())
        data = json.loads(CHARTER.read_text(encoding="utf-8"))
        data["base_state_revision"] = self.c.state()["state_revision"]
        text = "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(data) + "\n<<<AIWB_END_PROJECT_CHARTER>>>"
        self.assertEqual(self.g.perform("charter", "paste", text=text)["kind"], "proposal")
        visited.append(self.node())
        key = self.g.steps()[0]["key"]
        self.g.perform(key, "accept")
        visited.append(self.node())
        self.assertEqual(visited, ["F1", "F5", "F6", "F7", "F8", visited[-1]])
        self.assertIn(visited[-1], ("F9", "F10"))
        # changing the details later does not start the timeline twice
        self.c.state()

    def test_start_form_validates_the_number_of_ais(self):
        for bad in ("0", "13", "many"):
            with self.assertRaises(Exception):
                self.g.perform("design", "design", goal="x", ais=bad)
        self.assertEqual(self.node(), "F1")
        self.g.perform("design", "design", goal="x")
        self.g.perform("charter", "design", goal="y", name="Renamed")
        st = self.c.state()
        self.assertEqual(st["settings"]["brief"]["name"], "Renamed")
        self.assertEqual([e["type"] for e in st["events"]].count("project_started"), 1)

    def test_archived_and_completed_nodes(self):
        with self.c.project.store.transaction("t") as s:
            s["settings"]["goal"] = "x"
            s["settings"]["flow"] = {"started_at": "2026-10-20T00:00:00Z", "completed_at": "2026-10-21T00:00:00Z"}
        self.assertEqual(self.node(), "F27")
        with self.c.project.store.transaction("t") as s:
            s["settings"]["flow"]["archived_at"] = "2026-10-22T00:00:00Z"
        self.assertEqual(self.node(), "F28")


if __name__ == "__main__":
    unittest.main()
