"""Project Charter (roadmap 3.4.0): prompt, contract, tolerant import, review → agents/milestones/versions/tasks."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2.charter import (REQUIRED_SECTIONS, charter_fix_prompt, charter_prompt, parse_charter,  # noqa: E402
                             validate_charter)
from aiwb.v2.controller import ProjectsController  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"
SCHEMA = REPO / "packages/contracts/schemas/project-charter.v1.schema.json"


def block(data: dict | str) -> str:
    body = data if isinstance(data, str) else json.dumps(data, indent=1)
    return "Here is the plan.\n<<<AIWB_PROJECT_CHARTER>>>\n" + body + "\n<<<AIWB_END_PROJECT_CHARTER>>>\nThanks"


class CharterPromptTests(unittest.TestCase):
    def test_prompt_asks_for_every_required_part(self):
        p = charter_prompt({"goal": "Todo app"}, {"agents": {}, "settings": {}, "state_revision": 7})
        low = p.lower()
        for need in ("architecture", "modules", "how many ai chats work in parallel", "why", "file", "shared contracts",
                     "sync points", "conflicts", "roadmap", "milestones", "version", "tasks of every ai",
                     "start prompt", "<<<aiwb_project_charter>>>", "<<<aiwb_end_project_charter>>>", "state revision: 7"):
            self.assertIn(need, low, need)
        for sec in REQUIRED_SECTIONS:
            self.assertIn(f'"{sec}"', p, sec)


class CharterValidationTests(unittest.TestCase):
    def setUp(self):
        self.good = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_is_valid_for_code_and_schema(self):
        self.assertEqual(validate_charter(self.good)["errors"], [])
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(self.good)

    def test_each_missing_section_is_named(self):
        for sec in REQUIRED_SECTIONS:
            bad = copy.deepcopy(self.good)
            del bad[sec]
            errs = validate_charter(bad)["errors"]
            self.assertIn(f"{sec}: section missing", errs, sec)

    def test_precise_messages_for_broken_parts(self):
        bad = copy.deepcopy(self.good)
        bad["tasks"][1]["owner_agent_id"] = "agent-nobody"
        bad["tasks"][2]["milestone_ref"] = "m9"
        bad["roadmap"]["milestones"][1]["version"] = "0.0.9"
        bad["coordination"]["file_ownership"][1]["paths"] = ["src/core/ui/**"]
        bad["start_prompts"] = bad["start_prompts"][:2]
        bad["tasks"][0]["depends_on_refs"] = ["t2"]
        errs = "\n".join(validate_charter(bad)["errors"])
        self.assertIn("tasks[1].owner_agent_id: agent-nobody is not in team.agents", errs)
        self.assertIn("tasks[2].milestone_ref: m9 is not a roadmap milestone", errs)
        self.assertIn("roadmap.milestones[1].version: 0.0.9 does not grow", errs)
        self.assertIn("own the same path", errs)
        self.assertIn("start_prompts: no start prompt for agent-mobile-dev", errs)
        self.assertIn("dependency cycle", errs)

    def test_chat_copy_damage_is_repaired(self):
        raw = json.dumps(self.good, indent=1).replace('"schema_version"', '\u201cschema_version\u201d', 0)
        raw = raw[:-1].rstrip() + ",\n}"  # trailing comma
        text = "\u200b" + block(raw).replace("<<<AIWB_PROJECT_CHARTER>>>", "\\<\\<\\<AIWB\\_PROJECT\\_CHARTER>>>")
        r = parse_charter(text)
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(r["fixes"])

    def test_cut_off_answer_is_reported(self):
        text = "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(self.good)[:500]
        r = parse_charter(text)
        self.assertFalse(r["ok"])
        self.assertIn("cut off", r["errors"][0])
        self.assertIn("cut off", charter_fix_prompt(r))

    def test_fix_prompt_lists_problems_and_asks_for_the_full_block(self):
        bad = copy.deepcopy(self.good)
        del bad["coordination"]
        r = parse_charter(block(bad))
        fp = charter_fix_prompt(r)
        self.assertIn("coordination: section missing", fp)
        self.assertIn("<<<AIWB_PROJECT_CHARTER>>>", fp)
        self.assertIn("COMPLETE", fp)


class CharterImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        self.good = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_import_creates_agents_tasks_milestones_versions(self):
        prompt = self.c.charter_prompt({"goal": "Offline todo app"})
        self.assertIn("AIWB_PROJECT_CHARTER", prompt)
        self.good["base_state_revision"] = self.c.state()["state_revision"]
        r = self.c.route_answer(block(self.good))
        self.assertEqual(r.kind, "proposal", r.message)
        st = self.c.state()
        self.assertEqual(st["tasks"], {}, "nothing is applied before review")
        self.assertEqual(st["milestones"], {})
        p = r.record
        out = self.c.accept_proposal(p["proposal_id"], [o["index"] for o in p["operations"] if o["valid"]])
        self.assertEqual(out["status"], "accepted", out.get("result"))
        st = self.c.state()
        self.assertTrue({"agent-core-dev", "agent-desktop-dev", "agent-mobile-dev"} <= set(st["agents"]))
        tasks = {t["title"]: t for t in st["tasks"].values()}
        self.assertEqual(set(tasks), {"Core library", "Desktop UI", "Mobile UI"})
        self.assertEqual(tasks["Core library"]["status"], "ready")
        self.assertEqual(tasks["Desktop UI"]["status"], "blocked")
        self.assertEqual(tasks["Desktop UI"]["depends_on"], [tasks["Core library"]["task_id"]])
        self.assertEqual(tasks["Mobile UI"]["owner_agent_id"], "agent-mobile-dev")
        ms = sorted(st["milestones"].values(), key=lambda m: m["milestone_id"])
        self.assertEqual([m["title"] for m in ms], ["Core ready", "Both apps usable"])
        self.assertEqual(ms[1]["task_ids"], sorted([tasks["Desktop UI"]["task_id"], tasks["Mobile UI"]["task_id"]]))
        self.assertEqual(sorted(v["label"] for v in st["versions"].values()), ["0.1.0", "0.2.0"])
        self.assertTrue(all(v["status"] == "proposed" for v in st["versions"].values()))
        ch = self.c.charter()
        self.assertEqual(ch["proposal_id"], p["proposal_id"])
        sp = self.c.charter_start_prompt("agent-desktop-dev")
        self.assertIn("NO access", sp)
        self.assertIn("src/desktop/**", sp)
        self.assertIn("Shared contract Core API", sp)
        self.assertIn("Desktop UI", sp)

    def test_partial_acceptance_keeps_unaccepted_tasks_out_of_milestones(self):
        self.good["base_state_revision"] = self.c.state()["state_revision"]
        p = self.c.route_answer(block(self.good)).record
        idx = [o["index"] for o in p["operations"] if o["valid"] and o["raw"].get("title") != "Mobile UI"]
        self.c.accept_proposal(p["proposal_id"], idx)
        ms = [m for m in self.c.state()["milestones"].values() if m["title"] == "Both apps usable"][0]
        self.assertEqual(len(ms["task_ids"]), 1)

    def test_incomplete_charter_is_rejected_with_fix_prompt(self):
        bad = copy.deepcopy(self.good)
        del bad["start_prompts"]
        before = self.c.state()["state_revision"]
        r = self.c.route_answer(block(bad))
        self.assertEqual(r.kind, "charter_rejected")
        self.assertIn("start_prompts: section missing", r.message)
        self.assertIn("start_prompts: section missing", r.record["fix_prompt"])
        self.assertEqual(self.c.state()["proposals"], {})
        self.assertEqual(self.c.state()["state_revision"], before)


if __name__ == "__main__":
    unittest.main()
