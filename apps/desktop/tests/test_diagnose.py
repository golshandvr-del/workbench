"""Roadmap 4.2.0 gate (desktop half): smart problem detection matches the shared corpus (flowchart F13–F15)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import tempfile  # noqa: E402

import AI_Workbench as wb  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.diagnose import diagnose  # noqa: E402
from aiwb.v2.guide import TROUBLESHOOT_ATTEMPTS, Guide  # noqa: E402

CORPUS = Path(__file__).resolve().parents[3] / "packages/contracts/fixtures/diagnose/diagnose-corpus.v1.json"


class DiagnoseCorpusTests(unittest.TestCase):
    def test_every_corpus_case(self):
        cases = json.loads(CORPUS.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 17)
        for c in cases:
            with self.subTest(c["id"]):
                r = diagnose(c["text"], **c["context"])
                self.assertEqual([p["code"] for p in r["problems"]], c["codes"])
                self.assertEqual(r["acceptable"], c["acceptable"])


class TroubleshootLoopTests(unittest.TestCase):
    """F13 -> F15 -> F11 loop: at most TROUBLESHOOT_ATTEMPTS prompts, then the project manager (correction C1)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        t = self.c.project.tasks.create({"title": "Calc", "objective": "add", "allowed_paths": ["src/"],
                                         "acceptance_criteria": ["adds"]})
        self.tid = t["task_id"]
        self.c.project.tasks.transition(self.tid, "ready", "test")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def broken_answer(self) -> str:
        h = next(h for h in self.c.state()["handoffs"].values() if h["task_id"] == self.tid
                 and h["status"] in ("prepared", "prompt_exported"))
        man = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": self.tid,
               "task_revision": h["task_revision"], "attempt_id": h["attempt_id"], "outcome": "complete",
               "summary": "done", "completed_items": ["x"], "unresolved_items": [], "validation_claims": []}
        return (f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n" + '<<<AIWB_FILE path="../evil.py" action="write">>>\n````\nx=1\n````\n'
                "<<<AIWB_END_FILE>>>\n<<<AIWB_HANDOFF>>>\n" + json.dumps(man) + "\n<<<AIWB_END_HANDOFF>>>\n")

    def handoff_step(self) -> dict:
        return next(s for s in self.g.steps() if s["key"].startswith("handoff:"))

    def test_loop_then_escalate(self) -> None:
        self.g.perform(f"task:{self.tid}", "prepare")
        for n in range(1, TROUBLESHOOT_ATTEMPTS + 1):
            out = self.g.perform(self.handoff_step()["key"], "paste", text=self.broken_answer())
            self.assertIn("unsafe_path", out["message"])
            st = self.handoff_step()
            self.assertEqual(st["actions"][0]["id"], "troubleshoot")
            out = self.g.perform(st["key"], "troubleshoot")
            self.assertIn(f"troubleshooting request {n}", out["prompt"])
            self.assertIn("[unsafe_path]", out["prompt"])
        self.g.perform(self.handoff_step()["key"], "paste", text=self.broken_answer())
        st = self.handoff_step()
        self.assertEqual(st["actions"][0]["id"], "escalate")
        out = self.g.perform(st["key"], "escalate")
        self.assertTrue(out["prompt"])
        s = self.c.state()
        self.assertEqual(s["tasks"][self.tid]["status"], "blocked")
        types = [e["type"] for e in s["events"]]
        self.assertEqual(types.count("troubleshooting_prompt"), TROUBLESHOOT_ATTEMPTS)
        self.assertIn("task_escalated", types)


if __name__ == "__main__":
    unittest.main()
