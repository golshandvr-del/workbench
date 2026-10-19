"""3.9.1 / mobile 1.0.1: the "Verify" step can no longer trap the user.

Reported on a phone: after the first delivery the guide showed "Verify TASK-0001" with one action whose
free-text "result" field had no hint, so "Error: result is required" (or "must be passed or failed") was the
only outcome. Now:

* one-tap ``validation_passed`` / ``validation_failed`` actions, lenient words for ``record_validation``;
* ``waive_validation`` accepts the task on review alone when the user cannot run tests — recorded as NOT RUN
  (a flag, a waiver record, a timeline event) and never as passing evidence;
* prompts ask for four-backtick fences so a chat copy keeps indentation and backticks, and such answers parse.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.guide import Guide  # noqa: E402
from aiwb.v2.handoff import FILE_RULES  # noqa: E402
from aiwb.v2.models import ModelError  # noqa: E402


class VerifyStepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        p = self.c.project
        t = p.tasks.create({"title": "Engine", "objective": "calc", "acceptance_criteria": ["adds"]})
        self.tid = t["task_id"]
        p.tasks.transition(self.tid, "ready", "test")
        p.tasks.transition(self.tid, "in_progress", "test")
        p.tasks.transition(self.tid, "validation_pending", "test")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def step(self) -> dict:
        return next(s for s in self.g.steps() if s["key"] == f"task:{self.tid}")

    def test_verify_step_offers_one_tap_choices(self) -> None:
        ids = [a["id"] for a in self.step()["actions"]]
        self.assertEqual(ids[0], "validation_passed")
        self.assertIn("validation_failed", ids)
        self.assertIn("waive_validation", ids)
        self.assertIn("NOT RUN", self.step()["explain"])

    def test_passed_button_needs_no_typing(self) -> None:
        out = self.g.perform(f"task:{self.tid}", "validation_passed")
        self.assertIn("passed", out["message"])
        ev = [e for e in self.c.state()["evidence"].values() if e["subject_id"] == self.tid]
        self.assertEqual([(e["type"], e["result"], e["verified"]) for e in ev], [("test_run", "passed", True)])

    def test_lenient_result_words_and_clear_error(self) -> None:
        self.g.perform(f"task:{self.tid}", "record_validation", result=" OK ", run_id="r1")
        self.assertEqual(self.c.state()["evidence"]["EV-0001"]["result"], "passed")

    def test_unknown_result_word_is_refused_with_guidance(self) -> None:
        with self.assertRaises(ModelError) as cm:
            self.g.perform(f"task:{self.tid}", "record_validation", result="maybe")
        self.assertIn("buttons", str(cm.exception))

    def test_waiver_accepts_on_review_and_stays_honest(self) -> None:
        out = self.g.perform(f"task:{self.tid}", "waive_validation", reason="no Android Studio on my phone")
        self.assertIn("NOT RUN", out["message"])
        st = self.c.state()
        t = st["tasks"][self.tid]
        self.assertEqual(t["acceptance_policy"], "manual_review")
        self.assertEqual(t["validation_waiver"]["result"], "not_run")
        self.assertTrue(any("NOT RUN" in f for f in t["flags"]))
        self.assertFalse(any(e["type"] in ("test_run", "build_run") for e in st["evidence"].values()),
                         "a waiver must never create test/build evidence")
        self.assertIn("validation_waived", [e["type"] for e in st["events"]])
        self.assertEqual(t["status"], "in_review")
        self.g.perform(f"task:{self.tid}", "approve")
        self.assertEqual(self.c.state()["tasks"][self.tid]["status"], "done")

    def test_waiver_is_refused_outside_checking(self) -> None:
        self.g.perform(f"task:{self.tid}", "validation_passed")
        self.g.perform(f"task:{self.tid}", "approve")
        self.assertEqual(self.c.state()["tasks"][self.tid]["status"], "done")
        with self.assertRaises(ModelError):
            self.g.waive_validation(self.tid, "late")

    def test_prompts_ask_for_four_backtick_fences_and_they_parse(self) -> None:
        text = "\n".join(FILE_RULES)
        self.assertIn("````", text)
        self.assertNotIn('body="raw"', text)
        answer = ('<<<AIWB_FILE path="core/Engine.kt" action="write">>>\n````kotlin\nclass E {\n    fun `adds two`() {}\n}\n'
                  '```\ninner\n```\n````\n<<<AIWB_END_FILE>>>\n')
        files = wb.parse_aiwb_file_blocks(answer)["files"]
        self.assertEqual(files[0]["content"], "class E {\n    fun `adds two`() {}\n}\n```\ninner\n```\n")


if __name__ == "__main__":
    unittest.main()
