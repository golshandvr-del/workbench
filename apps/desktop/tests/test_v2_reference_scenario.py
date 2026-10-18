"""Roadmap 1.20.1 / 2.0.0 gate: the Future Roadmap §18 reference scenario end-to-end, through the
public services only (no direct edits of the store file), plus its failure variants."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import AI_Workbench as wb  # noqa: E402
from aiwb.inbox import repair as inbox_repair  # noqa: E402
from aiwb.v2 import V2Project, build_snapshot  # noqa: E402
from aiwb.v2.proposals import manager_update_prompt, planning_prompt  # noqa: E402
from aiwb.v2.publisher import GitHubStateClient, StatePublisher  # noqa: E402
from aiwb.v2.snapshot import fallback_summary  # noqa: E402
from test_v2_flow import FakeGitHub, manifest  # noqa: E402


def proposal(base, ops):
    return ("Here is my plan.\n<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps(
        {"schema_version": "1.0", "base_state_revision": base, "summary": "plan", "operations": ops})
        + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>\n")


def block(path, body, end=True):
    s = f'<<<AIWB_FILE path="{path}" action="write" body="raw">>>\n{body}\n'
    return s + ("<<<AIWB_END_FILE>>>\n" if end else "")


class ReferenceScenario(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "README.md").write_text("demo\n", encoding="utf-8")
        self.p = V2Project(self.root, "todo-demo")
        self.p.open()
        self.gh = FakeGitHub()
        self.now = [5000.0]
        with self.p.store.transaction("enable publish") as s:
            s["settings"]["publish"]["enabled"] = True
        self.pub = StatePublisher(self.p.store, clock=lambda: self.now[0],
                                  client_factory=lambda: GitHubStateClient("tok", "o", "r", transport=self.gh),
                                  source_info=lambda: {"repository": "o/r", "branch": "main", "commit_sha": "base1",
                                                       "local_changes_pending": False, "local_changes_count": 0})
        self.pipe = wb.make_inbox_pipeline(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def paste(self, text):
        """Every model answer goes through the raw-first Inbox before any V2 service sees it."""
        cap = self.pipe.capture_text(text, source="paste")
        return cap.response.response_id

    def test_reference_scenario(self):
        p = self.p
        # 1-2: goal -> project-manager planning prompt
        prompt = planning_prompt({"goal": "Todo app with desktop and mobile", "constraints": ["offline first"]},
                                 p.agents.list())
        self.assertIn("AIWB_MANAGER_PROPOSAL", prompt)
        # 3-5: GPT answer pasted, parsed, validated, shown, approved -> stable IDs
        rid = self.paste(proposal(p.store.revision, [
            {"operation": "create_task", "temporary_ref": "arch", "title": "Architecture", "objective": "storage + sync contract",
             "owner_role": "architect", "acceptance_policy": "manual_review"},
            {"operation": "create_task", "temporary_ref": "core", "title": "Core library", "objective": "todo core",
             "owner_role": "implementer", "depends_on_refs": ["arch"], "scope": {"include": ["core/**"]},
             "acceptance_policy": "evidence_required", "required_approvals": ["validation"]},
            {"operation": "create_task", "temporary_ref": "mobile", "title": "Mobile screen", "objective": "list screen",
             "owner_role": "implementer", "depends_on_refs": ["arch"], "scope": {"include": ["mobile/**"]},
             "acceptance_policy": "evidence_required", "required_approvals": ["validation"]}]))
        prop = p.proposals.import_text(self.pipe.store.read_text(rid), response_id=rid, kind="plan")
        self.assertEqual(p.tasks.list(), [])
        ids = p.proposals.review(prop["proposal_id"], [0, 1, 2])["result"]["created"]
        arch, core, mobile = ids["arch"], ids["core"], ids["mobile"]
        self.assertTrue(all(i.startswith("TASK-") for i in ids.values()))
        self.assertEqual(p.tasks.get(core)["status"], "blocked")
        # 6-7: architect prompt -> Gemini answer -> handoff -> review -> decision recorded
        p.tasks.transition(arch, "ready")
        h = p.handoffs.prepare(arch, "agent-architect")
        p.handoffs.mark_exported(h["handoff_id"])
        rid = self.paste(manifest(h, summary="JSON file storage, last-writer-wins sync",
                                  decision_requests=["Storage: JSON file vs SQLite"]))
        out = p.handoffs.ingest(h["handoff_id"], rid, self.pipe.store.read_text(rid))
        self.assertEqual(out["status"], "reconciled")
        p.handoffs.resolve(h["handoff_id"], True)
        d = p.decisions.propose("Storage", "JSON file vs SQLite", options=["json", "sqlite"])
        p.decisions.resolve(d["decision_id"], True, decision="JSON file", rationale="simple, offline")
        p.evidence.record(type="manual_review", subject_type="task", subject_id=arch, source_kind="user", result="approved")
        self.assertEqual(p.evidence.evaluate_task(arch)["status"], "done")
        # 8: two independent tasks are now ready and may run in parallel (disjoint scopes)
        self.assertEqual((p.tasks.get(core)["status"], p.tasks.get(mobile)["status"]), ("ready", "ready"))
        self.assertIn(tuple(sorted((core, mobile))), [tuple(sorted(x)) for x in p.tasks.parallel_candidates()])
        # 9: core -> implementer (GPT), mobile -> a copied mobile agent (Gemini); separate prompts/answers
        p.agents.copy("agent-implementer", "agent-mobile", "Mobile implementer")
        p.agents.update("agent-mobile", {"preferred_model_label": "Gemini"})
        hc = p.handoffs.prepare(core, "agent-implementer", expected_paths=["core/a.py", "core/b.py", "core/c.py",
                                                                         "core/d.py", "core/e.py"])
        hm = p.handoffs.prepare(mobile, "agent-mobile", expected_paths=["mobile/list.kt"])
        self.assertIn("JSON file", hc["prompt"], "approved decision travels with the handoff")
        self.assertIn("NO access to earlier chats", hm["prompt"])
        # 10: core answer is incomplete: 4 of 5 files intact, 5th cut off -> salvage + focused repair
        raw = (f"AIWB_ATTEMPT_ID: {hc['attempt_id']}\n" + "".join(block(f"core/{n}.py", f"{n.upper()} = 1") for n in "abcd")
               + block("core/e.py", "E = ", end=False))
        rid = self.paste(raw)
        outcome = self.pipe.process(rid)
        self.assertEqual(outcome.status, "partial")
        self.assertEqual(sorted(outcome.salvage_paths), [f"core/{n}.py" for n in "abcd"])
        plan = inbox_repair.plan_repair(outcome, self.pipe.attempts, base_revision="x", task_id="")
        self.assertIn("core/e.py", plan.section)
        self.assertNotIn("A = 1", plan.section)
        hashes = {c: "0" * 64 for c in outcome.salvage_paths}
        rec = p.handoffs.ingest(hc["handoff_id"], rid, raw, file_hashes=hashes)
        self.assertIn("missing file: core/e.py", rec["unresolved_items"])
        self.assertEqual(rec["outcome"], "partial")
        # mobile answer complete
        rid_m = self.paste(manifest(hm, summary="list screen"))
        p.handoffs.ingest(hm["handoff_id"], rid_m, self.pipe.store.read_text(rid_m), file_hashes={"mobile/list.kt": "1" * 64})
        # 11: review/apply is user-gated: nothing was written to the project
        self.assertFalse((self.root / "core").exists())
        p.handoffs.resolve(hc["handoff_id"], True)
        p.handoffs.resolve(hm["handoff_id"], True)
        # 12: validation: core passes (real runner), mobile only has the model claim -> Not Verified
        for t in (core, mobile):
            p.tasks.transition(t, "validation_pending")
        p.evidence.record(type="test_run", subject_type="task", subject_id=core, source_kind="workbench_process_runner",
                          result="passed", run_id="RUN-7", commit_sha="base1")
        self.assertEqual(p.evidence.evaluate_task(core, current_commit="base1")["status"], "done")
        mob = p.evidence.evaluate_task(mobile, current_commit="base1")
        self.assertEqual(mob["status"], "validation_pending")
        self.assertTrue(mob["reported"], "model claim kept as reported, not verified")
        # 13: snapshot published to GitHub with base commit, statuses, evidence and blocker
        self.assertEqual(self.pub.tick(force=True)["status"], "published")
        snap1 = json.loads(self.gh.files()[".aiwb/project-state.json"])
        self.assertEqual(snap1["source"]["commit_sha"], "base1")
        md = self.gh.files()[".aiwb/PROJECT_STATUS.md"]
        self.assertIn(mobile, md)
        # 14-15: manager update -> proposal: keep mobile blocked until tests + add a test task; partial accept
        st = p.store.load()
        snap = build_snapshot(st)
        up = manager_update_prompt(snap, state_url="https://github.com/o/r/blob/aiwb-state/.aiwb/project-state.json",
                                   fallback=fallback_summary(snap, st))
        self.assertIn(f"base_state_revision {snap['state_revision']}", up)
        rid = self.paste(proposal(snap["state_revision"], [
            {"operation": "create_task", "temporary_ref": "mtest", "title": "Mobile tests", "objective": "instrumented tests",
             "owner_role": "implementer", "scope": {"include": ["mobile/test/**"]}},
            {"operation": "request_more_evidence", "task_id": mobile, "reason": "no real test run"},
            {"operation": "update_task", "task_id": mobile, "changes": {"status": "done"}}]))
        prop2 = p.proposals.import_text(self.pipe.store.read_text(rid), response_id=rid)
        self.assertFalse(prop2["stale"])
        res = p.proposals.review(prop2["proposal_id"], [0, 1])  # user rejects the 'mark done' operation
        self.assertEqual(res["status"], "partially_accepted")
        self.assertNotEqual(p.tasks.get(mobile)["status"], "done")
        # 16: next snapshot published; it shows what changed and which revision to use next
        self.assertEqual(self.pub.tick(force=True)["status"], "published")
        snap2 = json.loads(self.gh.files()[".aiwb/project-state.json"])
        self.assertGreater(snap2["state_revision"], snap1["state_revision"])
        self.assertNotEqual(snap2["content_hash"], snap1["content_hash"])
        self.assertIn("Mobile tests", self.gh.files()[".aiwb/PROJECT_STATUS.md"])
        self.assertTrue(p.next_actions())

    def test_failure_variants(self):
        p = self.p
        t = p.tasks.transition(p.tasks.create({"title": "A", "objective": "a", "owner_agent_id": "agent-implementer"})["task_id"], "ready")
        tid = t["task_id"]
        # offline + invalid token: queue keeps state, nothing lost
        self.gh.fail = [(503, {})]
        self.assertEqual(self.pub.tick(force=True)["kind"], "network")
        self.now[0] += 1000
        self.gh.fail = [(401, {})]
        self.assertEqual(self.pub.tick()["kind"], "auth")
        self.assertTrue(self.pub.pending)
        self.pub.resume()
        self.assertEqual(self.pub.tick(force=True)["status"], "published")
        # late answer + old revision
        h1 = p.handoffs.prepare(tid, "agent-implementer")
        h2 = p.handoffs.prepare(tid, "agent-implementer")
        self.assertEqual(p.handoffs.ingest(h1["handoff_id"], "late", manifest(h1))["status"], "stale")
        old_rev = p.store.revision
        p.tasks.update(tid, {"objective": "changed"})
        st = p.proposals.import_text(proposal(old_rev, [{"operation": "reorder_priority", "task_id": tid, "priority": "high"}]))
        self.assertTrue(st["stale"])
        # two concurrent writers: both changes kept
        def bump(i):
            p.tasks.create({"title": f"c{i}", "objective": "x"})
        ths = [threading.Thread(target=bump, args=(i,)) for i in range(8)]
        [x.start() for x in ths]
        [x.join() for x in ths]
        self.assertEqual(len(p.tasks.list()), 9)
        # validation failure sends the task back
        p.handoffs.ingest(h2["handoff_id"], "r", manifest(h2))
        p.handoffs.resolve(h2["handoff_id"], True, reason="reconciled after objective change")
        p.evidence.record(type="test_run", subject_type="task", subject_id=tid, source_kind="workbench_process_runner",
                          result="failed", run_id="R1")
        self.assertIn(p.evidence.evaluate_task(tid)["status"], ("in_progress", "in_review"))
        self.assertNotEqual(p.tasks.get(tid)["status"], "done")


if __name__ == "__main__":
    unittest.main()
