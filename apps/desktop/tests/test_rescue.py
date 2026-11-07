"""Roadmap 5.18.0 (R1 + R6): the short project-manager path.

* A task prompt never asks for two answer formats (the PM's "only AIWB_MANAGER_PROPOSAL" line is replaced there).
* A manager proposal without ``operations`` but with the keys models invent is translated, not refused.
* Nothing usable → a short fix prompt (no dead end, not the whole prompt again).
* An accepted decision is final: shown as FINAL in prompts, and a repeat is dropped.

The answers below are reconstructed from the shapes recorded in the friend's calculator log (four proposal blocks,
three with ``operations: []`` and the keys ``decisions``, ``task_assessment``, ``file_change_proposals``,
``follow_up_tasks``; DEC-0002 decided again and again). The raw log itself is not in the repository.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2.agents import TASK_DELIVERY_RULE, TEMPLATES, task_instructions  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.proposals import NoOperations  # noqa: E402
from aiwb.v2.rescue import duplicate_of, fix_prompt, translate  # noqa: E402


def block(data: dict) -> str:
    return "Analysis first…\n<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps(data) + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>\n"


STATE = {"state_revision": 49,
         "tasks": {"TASK-0001": {"task_id": "TASK-0001", "title": "Docs", "acceptance_criteria": ["a"]},
                   "TASK-0002": {"task_id": "TASK-0002", "title": "Core"}},
         "agents": {"agent-implementer": {}},
         "decisions": {"DEC-0002": {"title": "Number formatting", "status": "accepted", "decision": "Intl"},
                       "DEC-0003": {"title": "Theme", "status": "proposed", "decision": ""}}}


class TaskInstructionsTest(unittest.TestCase):
    def test_bf039_technical_leadership_does_not_create_a_second_manager(self):
        from aiwb.v2.charter_repair import role_of
        for role in ("Lead developer", "Code owner", "Release manager"):
            self.assertEqual(role_of(role), "implementer")
        self.assertEqual(role_of("Tech lead"), "architect")
        self.assertEqual(role_of("Project manager"), "project_manager")

    def test_bf098_wizard_requires_explicit_parent(self):
        from aiwb.ui.project_wizard import ProjectWizard
        from unittest.mock import Mock
        wizard = ProjectWizard.__new__(ProjectWizard)
        wizard.mode = "create"
        wizard.vars = {"name": Mock(get=lambda: "Calc"), "parent": Mock(get=lambda: "")}
        wizard.goal = lambda: "Build calculator"
        self.assertIn("Choose an existing parent folder.", wizard.problems(0))

    def test_pm_task_prompt_has_one_delivery_format(self) -> None:
        out = task_instructions(TEMPLATES["agent-project-manager"])
        self.assertIn(TASK_DELIVERY_RULE, out)
        self.assertFalse([x for x in out if "only as an AIWB_MANAGER_PROPOSAL" in x])
        self.assertEqual(len(out), len(TEMPLATES["agent-project-manager"]["instructions"]))

    def test_other_roles_unchanged_and_old_projects_fixed(self) -> None:
        impl = TEMPLATES["agent-implementer"]
        self.assertEqual(task_instructions(impl), impl["instructions"])
        old = {"instructions": ["Return changes only as an AIWB_MANAGER_PROPOSAL block.",
                                "Also AIWB_MANAGER_PROPOSAL again", "Be brief"]}
        self.assertEqual(task_instructions(old), [TASK_DELIVERY_RULE, "Be brief"])


class TranslateTest(unittest.TestCase):
    def test_bf045_title_assessments_update_existing_tasks_not_duplicates(self):
        r = translate({"task_assessment": [{"title": "Core", "status": "on track"},
            {"title": "Docs", "acceptance_criteria": ["updated"]}, {"title": "Unknown", "priority": "high"}]}, STATE)
        self.assertEqual([o["operation"] for o in r["operations"]], ["update_task"])
        self.assertEqual(r["operations"][0]["task_id"], "TASK-0001")
        self.assertTrue(any("Unknown" in x for x in r["leftover"]))
        for alias in ("TASK-1", "task-0001", "1"):
            out = translate({"task_updates": [{"task_id": alias, "depends_on": ["Core", "missing"]}]}, STATE)
            self.assertEqual(out["operations"][0]["changes"]["depends_on"], ["TASK-0002"])
            self.assertTrue(any("missing" in x for x in out["leftover"]))

    def test_bf046_assessment_comment_never_replaces_objective(self):
        for key in ("description", "goal", "files", "outputs"):
            out = translate({"task_assessment": [{"task_id": "TASK-0002", key: "Looks good so far"}]}, STATE)
            self.assertEqual(out["operations"], [])
        out = translate({"task_updates": [{"task_id": "TASK-0002", "changes": {"description": "New objective"}}]}, STATE)
        self.assertEqual(out["operations"][0]["changes"], {"objective": "New objective"})

    def test_bf045_dependencies_on_new_tasks_of_the_same_answer(self):
        r = translate({"follow_up_tasks": [{"title": "Write tests", "depends_on": ["Build API", "Core"]},
                                           {"title": "Build API"}, {"title": "Ship", "depends_on": ["Nothing"]}]},
                      STATE)
        by_title = {o["title"]: o for o in r["operations"]}
        self.assertEqual(by_title["Write tests"]["depends_on"], ["TASK-0002"])
        self.assertEqual(by_title["Write tests"]["depends_on_refs"], [by_title["Build API"]["temporary_ref"]])
        self.assertTrue(any("Nothing" in x for x in r["leftover"]))
        self.assertEqual(len({o["temporary_ref"] for o in r["operations"]}), 3)
        upd = translate({"task_updates": [{"task_id": "TASK-0002", "depends_on": ["Brand new"]}],
                         "new_tasks": [{"title": "Brand new"}]}, STATE)
        self.assertEqual([o["operation"] for o in upd["operations"]], ["create_task", "add_dependency"])
        self.assertEqual(upd["operations"][1]["task_id"], "TASK-0002")
        self.assertEqual(upd["operations"][1]["depends_on_ref"], upd["operations"][0]["temporary_ref"])

    def test_bf045_ambiguous_title_is_reported_not_guessed(self):
        state = {**STATE, "tasks": {**STATE["tasks"], "TASK-0003": {"task_id": "TASK-0003", "title": "core"}}}
        r = translate({"task_assessment": [{"title": "Core", "priority": "high"}]}, state)
        self.assertEqual(r["operations"], [])
        self.assertTrue(any("ambiguous" in x and "TASK-0002" in x and "TASK-0003" in x for x in r["leftover"]))
        r = translate({"task_updates": [{"task_id": "TASK-0001", "depends_on": ["Core"]}]}, state)
        self.assertEqual(r["operations"], [])
        self.assertTrue(any("ambiguous" in x for x in r["leftover"]))

    def test_bf046_owner_role_is_normalised_and_comments_are_kept(self):
        state = {**STATE, "agents": {"agent-implementer": {"role": "implementer", "enabled": True},
                                     "agent-reviewer": {"role": "reviewer", "enabled": True}}}
        r = translate({"follow_up_tasks": [{"title": "A", "owner_role": "Senior Developer"},
                                           {"title": "B", "role": "Wizard"}]}, state)
        self.assertEqual(r["operations"][0]["owner_role"], "implementer")
        self.assertNotIn("owner_role", r["operations"][1])
        self.assertTrue(any("Wizard" in x for x in r["leftover"]))
        r = translate({"task_assessment": [{"task_id": "TASK-0002", "owner_role": "QA", "status": "at risk",
                                            "description": "Needs a second look", "assessment": "slipping"}]}, state)
        op = r["operations"][0]
        self.assertEqual(op["changes"], {"owner_agent_id": "agent-reviewer"})
        for part in ("slipping", "Needs a second look", "at risk"):
            self.assertIn(part, op["reason"])

    def test_bf047_plain_decision_choice_and_recommendation_sentence(self):
        plain = translate({"decision": "Use SQLite"}, STATE)["operations"][0]
        self.assertEqual(plain["recommendation"], "Use SQLite")
        self.assertEqual(plain["options"], ["Use SQLite"])
        sentence = translate({"decisions": [{"question": "Which database?", "recommendation": "SQLite because it is simple"}]}, STATE)["operations"][0]
        self.assertEqual(sentence["options"], ["SQLite"])
        self.assertEqual(sentence["recommendation"], "SQLite because it is simple")

    def test_bf052_persian_keyboard_variants_do_not_repeat_final_decisions(self):
        state = {"decisions": {"DEC-1": {"title": "انتخاب پایگاه\u200cداده ۱۲", "status": "accepted"}}}
        for title in ("انتخاب پايگاهداده 12", "انتخاب پایگاه داده ١٢", "انتخاب پـایگاهداده ۱۲"):
            self.assertEqual(duplicate_of(title, "", state), "DEC-1", title)

    def test_invented_keys_become_operations(self) -> None:
        r = translate({"operations": [],
                       "decisions": [{"title": "Keyboard support", "options": ["keys", "mouse", "both"],
                                      "recommendation": "both", "affected_task_ids": ["TASK-0002", "TASK-9"]}],
                       "task_assessment": {"TASK-0001": {"status": "on track",
                                                         "acceptance_criteria": ["README explains usage"]},
                                           "TASK-0002": "looks fine"},
                       "follow_up_tasks": [{"title": "History panel", "description": "Last 10 results",
                                            "acceptance": ["shows 10"], "priority": "HIGH"}],
                       "risks": ["Floating point rounding"]}, STATE)
        names = [o["operation"] for o in r["operations"]]
        self.assertEqual(names, ["propose_decision", "update_task", "create_task", "report_risk"])
        dec, upd, new, _ = r["operations"]
        self.assertEqual((dec["options"], dec["recommendation"], dec["affected_task_ids"]),
                         (["keys", "mouse", "both"], "both", ["TASK-0002"]))
        self.assertEqual(upd["changes"], {"acceptance_criteria": ["README explains usage"]})
        self.assertEqual((new["title"], new["objective"], new["acceptance_criteria"], new["priority"]),
                         ("History panel", "Last 10 results", ["shows 10"], "high"))

    def test_final_and_pending_decisions_never_proposed_again(self) -> None:
        r = translate({"decisions": [{"decision_id": "DEC-0002", "decision": "Intl"},
                                     {"title": "number  FORMATTING", "decision": "toFixed"},
                                     {"decision_id": "DEC-0003", "decision": "dark"}]}, STATE)
        self.assertEqual(r["operations"], [])
        self.assertTrue(any("DEC-0002" in f and "final" in f for f in r["fixes"]))
        self.assertTrue(any("DEC-0003" in f for f in r["fixes"]))
        self.assertEqual(duplicate_of("Number formatting", "", STATE), "DEC-0002")
        self.assertEqual(duplicate_of("Theme", "", STATE), "")

    def test_files_and_assessments_only_are_not_operations(self) -> None:
        r = translate({"file_change_proposals": [{"path": "README.md"}],
                       "task_assessment": {"TASK-0001": {"status": "done", "acceptance_criteria": ["a"]}},
                       "risks": ["r"]}, STATE)
        self.assertEqual(r["operations"], [], "a risk alone or an unchanged task is not a reason to import")
        self.assertTrue(any("file change" in x for x in r["leftover"]))

    def test_unknown_task_and_bad_values_are_dropped(self) -> None:
        r = translate({"task_updates": [{"task_id": "TASK-0042", "objective": "x"},
                                        {"task_id": "TASK-0002", "priority": "urgent", "owner": "agent-ghost",
                                         "objective": "Core math"}]}, STATE)
        self.assertEqual(r["operations"], [{"operation": "update_task", "task_id": "TASK-0002",
                                            "changes": {"objective": "Core math"},
                                            "reason": "translated from the answer (5.18.0)"}])
        self.assertIn("a change for unknown task TASK-0042", r["leftover"])

    def test_fix_prompt_is_short_and_lists_final_decisions(self) -> None:
        p = fix_prompt("the proposal has no operations", STATE, ["1 proposed file change(s)"])
        self.assertLess(len(p.splitlines()), 20)
        self.assertIn('"base_state_revision": 49', p)
        self.assertIn("DEC-0002 Number formatting: Intl", p)
        self.assertNotIn("DEC-0003", p)
        self.assertIn("AIWB_MANAGER_PROPOSAL", p)


class ProjectPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        self.c.planning_prompt("A small HTML calculator")
        rev = self.c.project.store.revision
        r = self.c.route_answer(block({"schema_version": "1.0", "base_state_revision": rev, "summary": "plan",
                                       "operations": [
                                           {"operation": "create_task", "temporary_ref": "a", "title": "Docs",
                                            "objective": "Write README", "owner_role": "implementer"},
                                           {"operation": "propose_decision", "title": "Number formatting",
                                            "options": ["Intl", "toFixed"], "recommendation": "Intl"}]}))
        self.c.accept_proposal(r.reference_id, [0, 1])
        self.tid = self.c.project.tasks.list()[0]["task_id"]
        self.did = next(iter(self.c.state()["decisions"]))
        self.c.resolve_decision(self.did, True, decision="Intl", rationale="standard")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_half_right_proposal_is_imported_not_refused(self) -> None:
        r = self.c.route_answer(block({"schema_version": "1.0", "base_state_revision": self.c.project.store.revision,
                                       "operations": [],
                                       "decisions": [{"decision_id": self.did, "decision": "Intl"}],
                                       "task_assessment": [{"task_id": self.tid,
                                                            "acceptance_criteria": ["README explains usage"]}],
                                       "file_change_proposals": [{"path": "README.md", "content": "…"}]}))
        self.assertEqual(r.kind, "proposal", r.message)
        self.assertNotIn("has no operations", r.message)
        self.assertIn("Read from the answer", r.message)
        p = r.record
        self.assertEqual([o["operation"] for o in p["operations"]], ["update_task"])
        self.assertTrue(any("final" in f for f in p["auto_fixes"]))
        self.assertTrue(any("not used" in f for f in p["auto_fixes"]))
        self.c.accept_proposal(p["proposal_id"], [0])
        self.assertEqual(self.c.state()["tasks"][self.tid]["acceptance_criteria"], ["README explains usage"])

    def test_missing_revision_is_tolerated_only_when_rescued(self) -> None:
        r = self.c.route_answer(block({"follow_up_tasks": [{"title": "History", "description": "Last results"}]}))
        self.assertEqual(r.kind, "proposal", r.message)
        self.assertTrue(any("base_state_revision missing" in f for f in r.record["auto_fixes"]))

    def test_nothing_usable_gives_a_short_fix_prompt(self) -> None:
        r = self.c.route_answer(block({"schema_version": "1.0", "base_state_revision": 1, "operations": [],
                                       "decisions": [{"decision_id": self.did, "decision": "Intl"}]}))
        self.assertEqual(r.kind, "proposal_fix", r.message)
        self.assertIn("already decided", r.message)
        self.assertIn("FINAL decisions", r.record["fix_prompt"])
        with self.assertRaises(NoOperations):
            self.c.project.proposals.import_data({"operations": []})

    def test_repeat_of_accepted_decision_is_dropped(self) -> None:
        r = self.c.route_answer(block({"schema_version": "1.0", "base_state_revision": self.c.project.store.revision,
                                       "operations": [{"operation": "propose_decision", "title": "Number formatting",
                                                       "options": ["Intl"]},
                                                      {"operation": "report_risk", "description": "rounding"}]}))
        self.assertEqual(r.kind, "proposal")
        dec = r.record["operations"][0]
        self.assertEqual((dec["valid"], dec["decision"]), (False, "rejected"))
        self.assertIn("final", dec["problem"])

    def test_task_prompt_marks_decisions_final_and_has_one_format(self) -> None:
        st = self.c.state()
        pm = next(a for a in st["agents"].values() if a["role"] == "project_manager")
        h = self.c.project.handoffs.prepare(self.tid, pm["agent_id"])
        from aiwb.v2.handoff import build_prompt
        text = build_prompt(self.c.state(), h, None)
        self.assertIn(f"FINAL — do not decide again: {self.did}", text)
        self.assertNotIn("Return changes only as an AIWB_MANAGER_PROPOSAL", text)
        self.assertIn("<<<AIWB_HANDOFF>>>", text)
        self.assertIn("Accepted decisions are FINAL", self.c.manager_update())


if __name__ == "__main__":
    unittest.main()
