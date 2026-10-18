"""Roadmap 2.4.0 (stage 4, Gate A): team settings, team planning prompt, Team Proposal validation and review."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.models import ModelError  # noqa: E402
from aiwb.v2.tasks import validate_graph  # noqa: E402
from aiwb.v2.team import check_team, scopes_overlap, team_settings  # noqa: E402
from aiwb.workspace.controller import WorkspaceController  # noqa: E402


def block(d: dict) -> str:
    return "analysis\n<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps(d) + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctl = ProjectsController(Path(self.tmp.name))
        self.wc = WorkspaceController(self.ctl)

    def tearDown(self):
        self.tmp.cleanup()

    def four_accounts(self):
        for n in ("GPT paid — work", "Gemini", "Claude", "GPT free"):
            self.wc.add_account({"display_name": n, "provider": "Other", "plan": "unknown"})
        self.wc.set_team_settings(max_parallel_chats=2)

    def team_plan(self, **over):
        d = {"schema_version": "1.0", "proposal_type": "team_plan", "base_state_revision": self.ctl.state()["state_revision"],
             "summary": "small team", "assumptions": ["web app"],
             "team": {"pm_counted": True, "total_agents": 5, "additional_workers": 4, "size_rationale": "two independent parts",
                      "simpler_alternative": "one implementer, slower"},
             "operations": [
                 {"operation": "create_agent", "agent_id": "agent-implementer-2", "role": "implementer", "name": "Implementer 2"},
                 {"operation": "assign_account", "agent_id": "agent-implementer-2", "account_profile_id": "ACC-0002"},
                 {"operation": "assign_account", "agent_id": "agent-implementer", "account_profile_id": "ACC-0001"},
                 {"operation": "create_task", "temporary_ref": "new-1", "title": "API", "objective": "api",
                  "owner_agent_id": "agent-implementer", "reviewer_agent_id": "agent-reviewer", "parallel_group": "A",
                  "scope": {"include": ["src/api/**"]}, "acceptance_criteria": ["tests pass"]},
                 {"operation": "create_task", "temporary_ref": "new-2", "title": "UI", "objective": "ui",
                  "owner_agent_id": "agent-implementer-2", "parallel_group": "A", "scope": {"include": ["src/ui/**"]},
                  "acceptance_criteria": ["renders"]},
                 {"operation": "create_task", "temporary_ref": "new-3", "title": "Integrate", "objective": "glue",
                  "owner_agent_id": "agent-implementer", "depends_on_refs": ["new-1", "new-2"],
                  "scope": {"include": ["src/app.py"]}, "acceptance_criteria": ["e2e ok"]}]}
        d.update(over)
        return d


class TeamSettingsTests(Base):
    def test_defaults_and_validation(self):
        self.assertEqual(self.wc.team_settings()["max_parallel_chats"], 2)
        self.assertEqual(self.wc.set_team_settings(max_parallel_chats="3")["max_parallel_chats"], 3)
        for bad in ({"max_parallel_chats": 0}, {"max_parallel_chats": 99}, {"max_parallel_chats": "x"},
                    {"pm_agent_id": "agent-implementer"}, {"priority": "fastest"}, {"unknown": 1}):
            with self.assertRaises(ModelError):
                self.wc.set_team_settings(**bad)
        self.assertEqual(self.wc.pm_choices()[0][0], "agent-project-manager")

    def test_old_project_without_team_settings(self):
        st = self.ctl.state()
        st["settings"].pop("team", None)
        self.assertEqual(team_settings(st)["pm_agent_id"], "agent-project-manager")


class PlanningPromptTests(Base):
    def test_prompt_lists_registered_resources_and_limit(self):
        self.four_accounts()
        p = self.wc.plan_team({"goal": "Todo app", "success": "works offline"})
        for s in ("ACC-0001", "ACC-0004", "at the same time: 2", "pm_counted", "parallel_group", "NOT verified",
                  "never invent accounts", "Success criteria: works offline", "project manager (you)"):
            self.assertIn(s, p)
        self.assertNotIn("password", p.lower().replace("passwords", ""))
        self.assertEqual(self.ctl.state()["settings"]["goal"], "Todo app")

    def test_goal_required_and_no_accounts(self):
        with self.assertRaises(ModelError):
            self.wc.plan_team({"goal": "  "})
        self.assertIn("no account profiles registered", self.wc.plan_team({"goal": "x"}))


class TeamProposalTests(Base):
    def test_gate_a_full_flow(self):
        """Gate A: 4 profiles, 2 parallel chats → team proposal → partial accept → real state, valid graph."""
        self.four_accounts()
        r = self.wc.route_answer(block(self.team_plan()))
        self.assertEqual(r.kind, "proposal")
        v = self.wc.proposal_review(r.reference_id)
        self.assertTrue(any("manager counted" in h for h in v["head"]))
        self.assertTrue(any("5 in total" in h and "4 extra" in h for h in v["head"]))
        self.assertEqual(v["valid_indices"], [0, 1, 2, 3, 4, 5])
        before = self.ctl.state()["state_revision"]
        # nothing applied by import alone
        self.assertNotIn("agent-implementer-2", self.ctl.state()["agents"])
        self.assertEqual(self.ctl.state()["state_revision"], before)
        out = self.wc.accept_proposal(r.reference_id, v["valid_indices"])
        self.assertEqual(out["status"], "accepted")
        st = self.ctl.state()
        self.assertIn("agent-implementer-2", st["agents"])
        self.assertEqual(validate_graph(st["tasks"]), [])
        t1 = st["tasks"][out["result"]["created"]["new-1"]]
        self.assertEqual((t1["owner_agent_id"], t1["reviewer_agent_ids"], t1["parallel_group"]),
                         ("agent-implementer", ["agent-reviewer"], "A"))
        t3 = st["tasks"][out["result"]["created"]["new-3"]]
        self.assertEqual(t3["status"], "blocked")
        rows = {r["agent_id"]: r for r in self.wc.team_rows()}
        self.assertEqual(rows["agent-implementer-2"]["account"], "Gemini")
        self.assertEqual(rows["agent-implementer"]["account"], "GPT paid — work")

    def test_partial_accept_revalidates_dependencies(self):
        self.four_accounts()
        r = self.wc.route_answer(block(self.team_plan()))
        # accept task new-3 without its prerequisites → refused, nothing written
        rev = self.ctl.state()["state_revision"]
        with self.assertRaises(ModelError):
            self.wc.accept_proposal(r.reference_id, [5])
        self.assertEqual(self.ctl.state()["state_revision"], rev)
        # task owned by a new agent without accepting create_agent → refused
        with self.assertRaises(ModelError):
            self.wc.accept_proposal(r.reference_id, [4])
        out = self.wc.accept_proposal(r.reference_id, [0, 1, 4])
        self.assertEqual(out["status"], "partially_accepted")

    def test_invented_account_and_unknown_agents_are_errors(self):
        self.four_accounts()
        ops = [{"operation": "assign_account", "agent_id": "agent-implementer", "account_profile_id": "ACC-0099"},
               {"operation": "assign_account", "agent_id": "agent-ghost", "account_profile_id": "ACC-0001"},
               {"operation": "create_agent", "agent_id": "agent-implementer", "role": "implementer"},
               {"operation": "create_agent", "agent_id": "Bad Id", "role": "implementer"},
               {"operation": "create_agent", "agent_id": "agent-x", "role": "wizard"},
               {"operation": "create_task", "title": "t", "objective": "o", "owner_agent_id": "agent-nobody"}]
        r = self.wc.route_answer(block(self.team_plan(operations=ops)))
        v = self.wc.proposal_review(r.reference_id)
        self.assertEqual(v["valid_indices"], [])
        codes = {i["code"] for i in v["issues"]}
        self.assertTrue({"unknown_account", "unknown_agent", "agent_exists", "bad_agent_id", "bad_role",
                         "unknown_owner"} <= codes, codes)
        with self.assertRaises(ModelError):
            self.wc.accept_proposal(r.reference_id, [0])

    def test_disabled_account_refused(self):
        self.four_accounts()
        self.wc.set_account_enabled("ACC-0002", False)
        ops = [{"operation": "assign_account", "agent_id": "agent-implementer", "account_profile_id": "ACC-0002"}]
        v = self.wc.proposal_review(self.wc.route_answer(block(self.team_plan(operations=ops))).reference_id)
        self.assertIn("account_disabled", {i["code"] for i in v["issues"]})

    def test_counts_parallel_limit_scope_and_reuse_warnings(self):
        self.four_accounts()
        self.wc.set_team_settings(max_parallel_chats=1)
        d = self.team_plan(team={"total_agents": 9})
        d["operations"][4]["scope"] = {"include": ["src/api/client/**"]}
        d["operations"][2]["account_profile_id"] = "ACC-0002"   # both agents on the same account
        res = check_team(d, d["operations"], self.ctl.state())
        codes = [i["code"] for i in res["issues"]]
        for c in ("pm_count_unclear", "declared_vs_actual", "parallel_limit", "scope_overlap", "account_reused", "no_rationale"):
            self.assertIn(c, codes)
        self.assertEqual(res["counts"]["agents_after"], 5)
        self.assertEqual(res["counts"]["widest_group"], 2)

    def test_count_mismatch(self):
        d = self.team_plan(team={"pm_counted": False, "total_agents": 3, "additional_workers": 2, "size_rationale": "x"})
        self.assertIn("count_mismatch", [i["code"] for i in check_team(d, d["operations"], self.ctl.state())["issues"]])

    def test_incomplete_task_warning_not_silent(self):
        d = self.team_plan(operations=[{"operation": "create_task", "title": "vague", "objective": "o"}])
        msgs = [i["message"] for i in check_team(d, d["operations"], self.ctl.state())["issues"]]
        self.assertTrue(any("missing owner, scope, acceptance criteria" in m for m in msgs), msgs)

    def test_old_proposal_contract_unchanged(self):
        d = {"schema_version": "1.0", "base_state_revision": 0, "summary": "s",
             "operations": [{"operation": "create_task", "temporary_ref": "new-1", "title": "A", "objective": "a",
                             "owner_role": "implementer"}]}
        r = self.wc.route_answer(block(d))
        p = self.ctl.project.proposals.get(r.reference_id)
        self.assertFalse(p["is_team"])
        self.assertEqual([i for i in p["team_issues"] if i["level"] == "error"], [])
        self.assertEqual(self.wc.accept_proposal(r.reference_id, [0])["status"], "accepted")

    def test_reject_and_revision_prompt(self):
        self.four_accounts()
        d = self.team_plan()
        d["operations"].append({"operation": "assign_account", "agent_id": "agent-reviewer", "account_profile_id": "ACC-0042"})
        r = self.wc.route_answer(block(d))
        prompt = self.wc.proposal_revision_prompt(r.reference_id, "keep it to 3 agents")
        self.assertIn("ACC-0042", prompt)
        self.assertIn("nothing was applied", prompt)
        self.assertIn("keep it to 3 agents", prompt)
        self.assertEqual(self.wc.reject_proposal(r.reference_id)["status"], "rejected")
        self.assertNotIn("agent-implementer-2", self.ctl.state()["agents"])

    def test_scope_overlap_helper(self):
        self.assertTrue(scopes_overlap({"include": ["src/**"]}, {"include": ["src/ui/**"]}))
        self.assertFalse(scopes_overlap({"include": ["src/api/**"]}, {"include": ["src/ui/**"]}))
        self.assertFalse(scopes_overlap({"include": []}, {"include": ["x"]}))

    def test_ledger_records_team_events_without_raw_text(self):
        self.four_accounts()
        r = self.wc.route_answer(block(self.team_plan()))
        self.wc.accept_proposal(r.reference_id, [0, 1])
        types = [e["event_type"] for e in self.ctl.project.store.ledger.all()]
        for t in ("team_settings_changed", "proposal_imported", "agent_created", "chat_binding_added", "proposal_reviewed"):
            self.assertIn(t, types)
        raw = self.ctl.project.store.ledger.path.read_text(encoding="utf-8")
        self.assertNotIn("two independent parts", raw)


if __name__ == "__main__":
    unittest.main()
