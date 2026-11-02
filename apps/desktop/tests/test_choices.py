"""Roadmap 5.17.0 (R5): clear forms — the question, the options and the recommendation are known and shown."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.v2.choices import (OTHER, decision_choices, form_spec, initial_values,  # noqa: E402
                             parse_options, validate)

OPTIONAL = ("note", "reason", "rationale", "run_id", "commit_sha", "tag", "idea")


class ParseOptionsTest(unittest.TestCase):
    def test_bullets_and_recommendation(self) -> None:
        self.assertEqual(parse_options("Which layout?\n- Grid 4x4\n- Grid 5x4 with memory keys\nRecommendation: Grid 4x4"),
                         (["Grid 4x4", "Grid 5x4 with memory keys"], "Grid 4x4"))

    def test_options_line(self) -> None:
        self.assertEqual(parse_options("Options: keyboard support; mouse only; both. Recommended: both"),
                         (["keyboard support", "mouse only", "both"], "both"))

    def test_lettered(self) -> None:
        self.assertEqual(parse_options("Pick (a) dark theme (b) light theme (c) system")[0],
                         ["dark theme", "light theme", "system"])

    def test_a_or_b_question(self) -> None:
        self.assertEqual(parse_options("Should the calculator use vanilla JS or React?")[0], ["vanilla JS", "React"])
        self.assertEqual(parse_options("Which theme: dark, light or system?")[0], ["dark", "light", "system"])
        self.assertEqual(parse_options("Should the display show history or only the last result?")[0],
                         ["show history", "only the last result"])

    def test_never_invents(self) -> None:
        self.assertEqual(parse_options("Please confirm the scope."), ([], ""))
        self.assertEqual(parse_options("Is this ok or should we redo everything from scratch because the whole "
                                       "approach is wrong?")[0], [])
        self.assertEqual(parse_options(""), ([], ""))


class DecisionChoicesTest(unittest.TestCase):
    def test_decision_record(self) -> None:
        st = {"decisions": {"D1": {"title": "Storage", "problem": "Where to keep history?",
                                   "options": ["localStorage", "none"], "recommendation": "localStorage — simple"}}}
        ch = decision_choices({"key": "decision:D1"}, st)
        self.assertEqual(ch["options"], ["localStorage", "none"])
        self.assertEqual(ch["recommended"], "localStorage")
        self.assertIn("Where to keep history?", ch["question"])
        self.assertIn("Storage", ch["question"])

    def test_task_uses_latest_handoff_decision_requests(self) -> None:
        st = {"tasks": {"T1": {"blocked_reason": "short"}}, "decisions": {},
              "handoffs": {"H1": {"task_id": "T1", "created_at": "1", "decision_requests": ["old?"]},
                           "H2": {"task_id": "T1", "created_at": "2",
                                  "decision_requests": ["Should the calculator use vanilla JS or React?"]}}}
        ch = decision_choices({"key": "task:T1", "explain": "short"}, st)
        self.assertEqual(ch["question"], "Should the calculator use vanilla JS or React?")
        self.assertEqual(ch["options"], ["vanilla JS", "React"])

    def test_task_without_options_keeps_question(self) -> None:
        st = {"tasks": {"T1": {"blocked_reason": "Please confirm the scope."}}, "handoffs": {}, "decisions": {}}
        ch = decision_choices({"key": "task:T1"}, st)
        self.assertEqual(ch, {"question": "Please confirm the scope.", "options": [], "recommended": ""})

    def test_recommendation_not_in_options_is_added_first(self) -> None:
        st = {"decisions": {"D2": {"title": "Theme", "problem": "Pick", "options": ["dark", "light"],
                                   "recommendation": "follow the system setting"}}}
        ch = decision_choices({"key": "decision:D2"}, st)
        self.assertEqual(ch["options"][0], "follow the system setting")
        self.assertEqual(ch["recommended"], "follow the system setting")


class FormSpecTest(unittest.TestCase):
    STEP = {"key": "decision:D1", "title": "Decide: Storage", "explain": "x",
            "choices": {"question": "Where to keep history?", "options": ["localStorage", "none"],
                        "recommended": "localStorage"}}

    def test_one_form_all_fields(self) -> None:
        spec = form_spec(self.STEP, {"label": "Decide…", "needs": ["choice", "rationale"]}, None, OPTIONAL)
        self.assertEqual(spec["title"], "Decide")
        self.assertEqual(spec["question"], "Where to keep history?")
        self.assertEqual([f["kind"] for f in spec["fields"]], ["choice", "note"])
        self.assertTrue(spec["fields"][1]["optional"])
        self.assertEqual(initial_values(spec), {"choice": "localStorage", "rationale": "decided in the guided loop"})

    def test_text_is_never_a_form_field(self) -> None:
        spec = form_spec({"key": "charter"}, {"label": "Paste", "needs": ["text"]}, None, OPTIONAL)
        self.assertEqual(spec["fields"], [])

    def test_result_is_yes_no(self) -> None:
        spec = form_spec({"key": "task:T1"}, {"label": "Record…", "needs": ["result", "run_id"]}, None, OPTIONAL)
        self.assertEqual(spec["fields"][0]["kind"], "yesno")
        self.assertEqual(initial_values(spec)["result"], "passed")

    def test_validate(self) -> None:
        spec = form_spec(self.STEP, {"label": "Decide…", "needs": ["choice", "rationale"]}, None, OPTIONAL)
        self.assertEqual(validate(spec, {"choice": "", "rationale": ""})[0], {})
        self.assertIn("Your decision", validate(spec, {"choice": " "})[1])
        self.assertEqual(validate(spec, {"choice": "none"}), ({"choice": "none", "rationale": ""}, ""))
        self.assertNotEqual(OTHER, "none")


class GuideAttachesChoicesTest(unittest.TestCase):
    def test_decision_step_carries_choices(self) -> None:
        import tempfile

        import AI_Workbench as wb
        from aiwb.v2.controller import ProjectsController
        from aiwb.v2.guide import Guide
        with tempfile.TemporaryDirectory() as d:
            ctl = ProjectsController(Path(d), make_pipeline=wb.make_inbox_pipeline)
            ctl.project.decisions.propose("Storage", "Where to keep history?", options=["localStorage", "none"],
                                          recommendation="none")
            step = next(s for s in Guide(ctl).steps() if s["key"].startswith("decision:"))
            self.assertEqual(step["choices"]["options"], ["localStorage", "none"])
            self.assertEqual(step["choices"]["recommended"], "none")
            self.assertIn("Where to keep history?", step["question"])


if __name__ == "__main__":
    unittest.main()
