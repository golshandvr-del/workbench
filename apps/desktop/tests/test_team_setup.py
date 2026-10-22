"""Roadmap 5.9.0: the user decides the AI team (audit A1/A5/A8/A9)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.ui import mission_model  # noqa: E402
from aiwb.v2 import ModelError, V2Project  # noqa: E402
from aiwb.v2 import team_setup as ts  # noqa: E402
from aiwb.v2.charter import charter_prompt  # noqa: E402
from aiwb.v2.guide import steps as guide_steps  # noqa: E402


def rows(*workers: tuple[str, str], pm: str = "Project manager") -> list[dict[str, str]]:
    out = [{"name": pm, "role": "project_manager", "model": "", "note": ""}]
    out += [{"name": n, "role": r, "model": "", "note": ""} for n, r in workers]
    return out


BRIEF = {"goal": "A snake game for Windows", "name": "Snake", "platform": "Windows, Python", "constraints": "offline"}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.p = V2Project(self.root, "snake")

    def tearDown(self) -> None:
        self._tmp.cleanup()


class IdsAndRows(unittest.TestCase):
    def test_slug_and_ids(self) -> None:
        self.assertEqual(ts.agent_id_for("Core developer", set()), "agent-core-developer")
        self.assertEqual(ts.agent_id_for("Core developer", {"agent-core-developer"}), "agent-core-developer-2")
        self.assertEqual(ts.agent_id_for("برنامه‌نویس", set(), index=3), "agent-ai-3")
        self.assertEqual(ts.agent_id_for("Project manager", set()), "agent-project-manager-2")
        self.assertEqual(ts.agent_id_for("  GPT-5 (fast) ", set()), "agent-gpt-5-fast")

    def test_resize_keeps_typed_rows(self) -> None:
        r = ts.default_rows(2)
        r[1]["name"] = "Alice"
        grown = ts.resize_rows(r, 5)
        self.assertEqual(len(grown), 6)
        self.assertEqual(grown[1]["name"], "Alice")
        self.assertEqual(len({x["name"] for x in grown}), 6)
        shrunk = ts.resize_rows(grown, 1)
        self.assertEqual([x["name"] for x in shrunk], ["Project manager", "Alice"])
        self.assertEqual(len(ts.resize_rows(grown, 99)), ts.MAX_WORKERS + 1)

    def test_check_rows(self) -> None:
        self.assertEqual(ts.check_rows(ts.default_rows(1)), [])
        self.assertTrue(ts.check_rows(rows()))                                    # PM only
        self.assertTrue(ts.check_rows(rows(("A", "implementer"), ("a", "reviewer"))))  # duplicate (case-insensitive)
        self.assertTrue(ts.check_rows(rows(("", "implementer"))))                 # empty name
        self.assertTrue(ts.check_rows(rows(("A", "project_manager"))))            # second PM
        self.assertTrue(ts.check_rows(rows(("A", "wizard"))))                     # unknown role
        self.assertEqual(ts.check_rows(rows(("A", "Developer"), ("B", "Reviewer / tester"))), [])  # labels work

    def test_role_labels(self) -> None:
        self.assertEqual(ts.role_of("Developer"), "implementer")
        self.assertEqual(ts.role_of("researcher"), "researcher")
        with self.assertRaises(ModelError):
            ts.role_of("boss")


class Wizard(Base):
    def test_no_templates_and_named_agents(self) -> None:
        r = rows(("Core developer", "implementer"), ("برنامه‌نویس دوم", "implementer"), ("QA", "Reviewer / tester"))
        r[3]["model"] = "Claude"
        out = ts.apply_wizard(self.p, BRIEF, r)
        self.assertEqual(out["agents"], ["agent-project-manager", "agent-core-developer", "agent-ai-2", "agent-qa"])
        self.p.open()                                 # what the Workbench does next: must not add templates
        st = self.p.store.load()
        self.assertEqual(set(st["agents"]), set(out["agents"]))
        self.assertEqual(st["agents"]["agent-ai-2"]["name"], "برنامه‌نویس دوم")
        self.assertEqual(st["agents"]["agent-qa"]["role"], "reviewer")
        self.assertEqual(st["agents"]["agent-qa"]["preferred_model_label"], "Claude")
        self.assertEqual(st["settings"]["team_source"], "wizard")
        self.assertEqual(st["settings"]["answer_format"], "aiwb")

    def test_brief_recorded_so_no_question_repeats(self) -> None:
        ts.apply_wizard(self.p, BRIEF, rows(("A", "implementer"), ("B", "implementer"), ("C", "implementer")))
        st = self.p.store.load()
        self.assertEqual(st["settings"]["goal"], BRIEF["goal"])
        self.assertEqual(st["settings"]["brief"]["platform"], BRIEF["platform"])
        self.assertEqual(st["settings"]["team"]["max_parallel_chats"], 3)
        self.assertTrue(st["settings"]["flow"]["started_at"])
        from aiwb.v2.controller import ProjectsController
        steps = guide_steps(ProjectsController(self.root))
        self.assertNotIn("design", [s["key"] for s in steps], "the start form must not be asked again")
        self.assertIn("charter", [s["key"] for s in steps])

    def test_sizes_1_3_5_12(self) -> None:
        for n in (1, 3, 5, 12):
            with self.subTest(n=n), tempfile.TemporaryDirectory() as d:
                p = V2Project(Path(d), "p")
                r = ts.resize_rows(ts.default_rows(1), n)
                out = ts.apply_wizard(p, BRIEF, r)
                self.assertEqual(out["workers"], n)
                st = p.store.load()
                self.assertEqual(len(st["agents"]), n + 1)
                lanes = mission_model.build(st)["lanes"]
                self.assertEqual([ln["name"] for ln in lanes], [x["name"] for x in r[1:]], "lanes = the user's AIs")

    def test_bad_input_rejected_before_writing(self) -> None:
        with self.assertRaises(ModelError):
            ts.apply_wizard(self.p, BRIEF, rows())
        with self.assertRaises(ModelError):
            ts.apply_wizard(self.p, BRIEF, rows(("A", "implementer")), answer_format="pdf")
        self.assertFalse((self.root / ".workbench" / "v2" / "state.json").exists())

    def test_charter_prompt_binds_the_team(self) -> None:
        ts.apply_wizard(self.p, BRIEF, rows(("Core developer", "implementer"), ("QA", "reviewer")))
        st = self.p.store.load()
        prompt = charter_prompt({"goal": BRIEF["goal"]}, st)
        self.assertIn("Team chosen by the user (binding)", prompt)
        self.assertIn('agent-core-developer — "Core developer"', prompt)
        self.assertLess(prompt.index("agent-core-developer"), prompt.index("agent-qa"), "the user's order is kept")
        self.assertNotIn("agent-architect (architect)", prompt)


class EditTeam(Base):
    def setUp(self) -> None:
        super().setUp()
        ts.apply_wizard(self.p, BRIEF, rows(("Alice", "implementer"), ("Bob", "implementer")))

    def test_rename_add_remove(self) -> None:
        r = ts.team_rows(self.p.store.load())
        self.assertEqual([x["name"] for x in r], ["Project manager", "Alice", "Bob"])
        r[0]["name"] = "Boss"
        r[1]["name"] = "Alice (lead)"
        r[1]["role"] = "architect"
        r = r[:2] + [{"name": "Carol", "role": "reviewer", "model": "Gemini"}]
        out = ts.save_team(self.p.store, r)
        self.assertEqual(out["created"], ["agent-carol"])
        self.assertEqual(sorted(out["updated"]), ["agent-alice", "agent-project-manager"])
        self.assertEqual(out["removed"], ["agent-bob"])
        st = self.p.store.load()
        self.assertEqual(st["agents"]["agent-alice"]["name"], "Alice (lead)")
        self.assertEqual(st["agents"]["agent-alice"]["role"], "architect")
        self.assertEqual(st["agents"]["agent-project-manager"]["role"], "project_manager")
        self.assertEqual([x["name"] for x in ts.team_rows(st)], ["Boss", "Alice (lead)", "Carol"])
        self.assertEqual(st["settings"]["team"]["max_parallel_chats"], 2)

    def test_agent_with_work_is_disabled_not_deleted(self) -> None:
        self.p.tasks.create({"title": "core", "owner_agent_id": "agent-bob", "objective": "core", "acceptance_criteria": ["works"]})
        r = ts.team_rows(self.p.store.load())
        self.assertTrue(next(x for x in r if x["agent_id"] == "agent-bob")["has_work"])
        out = ts.save_team(self.p.store, r[:2])
        self.assertEqual(out["disabled"], ["agent-bob"])
        st = self.p.store.load()
        self.assertIn("agent-bob", st["agents"])
        self.assertFalse(st["agents"]["agent-bob"]["enabled"])
        self.assertEqual([x["agent_id"] for x in ts.team_rows(st)], ["agent-project-manager", "agent-alice"])

    def test_every_user_ai_keeps_its_lane(self) -> None:
        self.p.tasks.create({"title": "core", "owner_agent_id": "agent-alice", "objective": "core",
                             "acceptance_criteria": ["works"]})
        lanes = [ln["name"] for ln in mission_model.build(self.p.store.load())["lanes"]]
        self.assertEqual(lanes, ["Alice", "Bob"], "Bob has no task yet but is part of the user's team")

    def test_nothing_changed_writes_nothing(self) -> None:
        rev = self.p.store.load()["state_revision"]
        out = ts.save_team(self.p.store, ts.team_rows(self.p.store.load()))
        self.assertFalse(any(out.values()))
        st = self.p.store.load()
        self.assertFalse([e for e in st["events"] if e.get("type") == "team_edited"])
        self.assertLessEqual(st["state_revision"], rev + 1)


class OldProjects(Base):
    def test_old_project_untouched_and_offer(self) -> None:
        self.p.open()                                  # 5.8.0 behaviour: four templates
        st = self.p.store.load()
        self.assertEqual(len(st["agents"]), 4)
        self.assertEqual(ts.team_prompt_lines(st), [], "old projects keep the old charter prompt")
        self.p.tasks.create({"title": "x", "owner_agent_id": "agent-implementer", "objective": "x", "acceptance_criteria": ["ok"]})
        st = self.p.store.load()
        self.assertEqual(ts.unused_template_agents(st), ["agent-architect", "agent-reviewer"])
        self.assertEqual(V2Project(self.root, "snake").open(), [], "reopening changes nothing by itself")
        self.assertEqual(len(self.p.store.load()["agents"]), 4)
        gone = ts.remove_unused_templates(self.p.store)
        self.assertEqual(gone, ["agent-architect", "agent-reviewer"])
        self.assertEqual(set(self.p.store.load()["agents"]), {"agent-project-manager", "agent-implementer"})

    def test_edited_template_is_not_offered(self) -> None:
        self.p.open()
        self.p.agents.update("agent-architect", {"name": "My architect"})
        self.assertIn("agent-architect", ts.unused_template_agents(self.p.store.load()))


if __name__ == "__main__":
    unittest.main()
