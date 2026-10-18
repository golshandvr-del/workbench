"""Roadmap 1.18.0–1.20.1 (slices 2C–2G): handoff, ledgers, snapshot/publisher, proposals, next action."""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.v2 import ModelError, V2Project, build_snapshot  # noqa: E402
from aiwb.v2.handoff import find_manifest  # noqa: E402
from aiwb.v2.proposals import check_probe, manager_update_prompt, planning_prompt  # noqa: E402
from aiwb.v2.publisher import ApiResult, GitHubStateClient, PublishError, StatePublisher  # noqa: E402
from aiwb.v2.snapshot import fallback_summary, render_status_md  # noqa: E402


def manifest(h, **kw):
    data = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": h["task_id"],
            "task_revision": h["task_revision"], "attempt_id": h["attempt_id"], "outcome": "complete",
            "summary": "did it", "completed_items": ["x"], "validation_claims": ["all tests pass"], **kw}
    return f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n<<<AIWB_HANDOFF>>>\n{json.dumps(data)}\n<<<AIWB_END_HANDOFF>>>\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = V2Project(self.root, "demo")
        self.p.open()

    def tearDown(self):
        self.tmp.cleanup()

    def ready_task(self, title="T", **kw):
        t = self.p.tasks.create({"title": title, "objective": "do " + title, "owner_agent_id": "agent-implementer",
                                 "acceptance_criteria": ["works"], **kw})
        return self.p.tasks.transition(t["task_id"], "ready")


class HandoffTests(Base):
    def test_prompt_is_self_contained_and_flow_to_review(self):
        t = self.ready_task("A")
        d = self.p.decisions.propose("Storage", "where", options=["json", "sqlite"])
        self.p.decisions.resolve(d["decision_id"], True, decision="json file", rationale="simple")
        h = self.p.handoffs.prepare(t["task_id"], "agent-implementer", expected_paths=["a.py", "b.py"])
        for must in ("NO access to earlier chats", t["title"], "json file", "AIWB_HANDOFF", h["attempt_id"], "- [ ] works"):
            self.assertIn(must, h["prompt"])
        self.assertEqual(self.p.tasks.get(t["task_id"])["status"], "in_progress")
        self.p.handoffs.mark_exported(h["handoff_id"])
        out = self.p.handoffs.ingest(h["handoff_id"], "resp-1", manifest(h), file_hashes={"a.py": "1" * 64})
        self.assertEqual(out["status"], "reconciled")
        self.assertEqual(out["outcome"], "partial", "missing expected file downgrades complete")
        self.assertIn("missing file: b.py", out["unresolved_items"])
        self.assertEqual(out["artifact_refs"][0]["logical_path"], "a.py")
        ev = self.p.evidence.list(t["task_id"])
        self.assertEqual([(e["type"], e["verified"]) for e in ev], [("model_report", False)])
        self.p.handoffs.resolve(h["handoff_id"], True)
        self.assertEqual(self.p.tasks.get(t["task_id"])["status"], "in_review")
        self.assertFalse((self.root / "a.py").exists(), "import never writes files")

    def test_second_agent_continues_from_previous_handoff(self):
        t = self.ready_task("A")
        h1 = self.p.handoffs.prepare(t["task_id"], "agent-architect")
        self.p.handoffs.ingest(h1["handoff_id"], "r1", manifest(h1, summary="contract designed", unresolved_items=["UI"]))
        self.p.handoffs.resolve(h1["handoff_id"], True)
        h2 = self.p.handoffs.prepare(t["task_id"], "agent-implementer")
        self.assertIn("Previous handoff " + h1["handoff_id"], h2["prompt"])
        self.assertIn("contract designed", h2["prompt"])
        self.assertIn("Claimed (NOT verified): all tests pass", h2["prompt"])
        self.assertEqual(self.p.handoffs.get(h2["handoff_id"])["from_agent_id"], "agent-architect")

    def test_wrong_attempt_stale_and_late_answers(self):
        t = self.ready_task("A")
        other = self.ready_task("B")
        h = self.p.handoffs.prepare(t["task_id"], "agent-implementer")
        ho = self.p.handoffs.prepare(other["task_id"], "agent-implementer")
        with self.assertRaises(ModelError):
            self.p.handoffs.ingest(h["handoff_id"], "r", manifest(ho))
        self.assertEqual(self.p.handoffs.get(h["handoff_id"])["source_response_id"], "", "not linked")
        newer = self.p.handoffs.prepare(t["task_id"], "agent-implementer")
        late = self.p.handoffs.ingest(h["handoff_id"], "r-late", manifest(h))
        self.assertEqual(late["status"], "stale")
        self.assertEqual(self.p.tasks.get(t["task_id"])["active_attempt_id"], newer["attempt_id"], "active not switched")
        with self.assertRaises(ModelError):
            self.p.handoffs.resolve(h["handoff_id"], True)
        self.p.tasks.update(t["task_id"], {"objective": "changed goal"})
        rec = self.p.handoffs.ingest(newer["handoff_id"], "r2", manifest(newer))
        self.assertIn(rec["status"], ("reconciliation_required", "stale"))
        self.assertTrue(any("revision" in r for r in rec["stale_reasons"]))

    def test_broken_manifest_keeps_going_and_is_reported(self):
        t = self.ready_task("A")
        h = self.p.handoffs.prepare(t["task_id"], "agent-implementer")
        with self.assertRaises(ModelError):
            find_manifest("<<<AIWB_HANDOFF>>>{bad<<<AIWB_END_HANDOFF>>>")
        out = self.p.handoffs.ingest(h["handoff_id"], "r", "<<<AIWB_HANDOFF>>>{bad<<<AIWB_END_HANDOFF>>>",
                                     file_hashes={"a.py": "2" * 64})
        self.assertTrue(out["issues"])
        self.assertEqual(len(out["artifact_refs"]), 1)


class LedgerTests(Base):
    def test_model_claim_never_completes_task(self):
        t = self.ready_task("A")
        h = self.p.handoffs.prepare(t["task_id"], "agent-implementer")
        self.p.handoffs.ingest(h["handoff_id"], "r", manifest(h))
        self.p.handoffs.resolve(h["handoff_id"], True)
        with self.assertRaises(ModelError):
            self.p.evidence.record(type="test_run", subject_type="task", subject_id=t["task_id"], source_kind="model",
                                   result="passed", run_id="x")
        self.p.evidence.record(type="manual_review", subject_type="task", subject_id=t["task_id"], source_kind="user",
                               result="approved")
        r = self.p.evidence.evaluate_task(t["task_id"])
        self.assertEqual(r["status"], "validation_pending")
        self.assertTrue(r["reported"])
        self.assertIn("model claims do not count", " ".join(r["reasons"]))
        self.p.evidence.record(type="test_run", subject_type="task", subject_id=t["task_id"],
                               source_kind="workbench_process_runner", result="failed", run_id="RUN-1", commit_sha="c1")
        self.assertEqual(self.p.evidence.evaluate_task(t["task_id"])["status"], "in_progress")
        self.p.tasks.transition(t["task_id"], "validation_pending")
        self.p.evidence.record(type="test_run", subject_type="task", subject_id=t["task_id"],
                               source_kind="workbench_process_runner", result="passed", run_id="RUN-2", commit_sha="c2")
        self.assertEqual(self.p.evidence.evaluate_task(t["task_id"], current_commit="c9")["status"], "validation_pending",
                         "evidence for another commit does not count")
        self.assertEqual(self.p.evidence.evaluate_task(t["task_id"], current_commit="c2")["status"], "done")

    def test_old_revision_evidence_does_not_count_and_done_unblocks(self):
        a = self.ready_task("A", acceptance_policy="evidence_required", required_approvals=["validation"])
        b = self.p.tasks.create({"title": "B", "objective": "b", "depends_on": [a["task_id"]]})
        self.p.tasks.transition(b["task_id"], "blocked", "waiting for " + a["task_id"])
        self.p.attempts.create(a["task_id"])
        self.p.tasks.transition(a["task_id"], "validation_pending")
        self.p.evidence.record(type="build_run", subject_type="task", subject_id=a["task_id"], source_kind="github_actions",
                               result="passed", run_id="9")
        self.p.tasks.update(a["task_id"], {"acceptance_criteria": ["stricter"]})
        self.assertEqual(self.p.evidence.evaluate_task(a["task_id"])["status"], "validation_pending")
        self.p.evidence.record(type="build_run", subject_type="task", subject_id=a["task_id"], source_kind="github_actions",
                               result="passed", run_id="10")
        self.assertEqual(self.p.evidence.evaluate_task(a["task_id"])["status"], "done")
        self.assertEqual(self.p.tasks.get(b["task_id"])["status"], "ready")

    def test_decisions_kept_and_block_tasks(self):
        t = self.ready_task("A")
        d = self.p.decisions.propose("Use X", "?", affected_task_ids=[t["task_id"]])
        self.assertEqual(self.p.tasks.get(t["task_id"])["status"], "needs_decision")
        with self.assertRaises(ModelError):
            self.p.decisions.resolve(d["decision_id"], False)
        self.p.decisions.resolve(d["decision_id"], False, rationale="too slow")
        self.assertEqual(self.p.tasks.get(t["task_id"])["status"], "ready")
        again = self.p.decisions.propose("use x", "?")
        self.assertEqual(again["previously_rejected"], [d["decision_id"]])
        self.assertEqual(self.p.decisions.get(d["decision_id"])["status"], "rejected")
        ok = self.p.decisions.propose("Use Y", "?")
        self.p.decisions.resolve(ok["decision_id"], True, decision="Y", rationale="fast")
        new = self.p.decisions.propose("Use Z", "?", supersedes=ok["decision_id"])
        self.p.decisions.resolve(new["decision_id"], True, decision="Z", rationale="faster")
        self.assertEqual(self.p.decisions.get(ok["decision_id"])["superseded_by"], new["decision_id"])


class BuildEvidenceTests(Base):
    def test_real_actions_run_becomes_verified_evidence_once(self):
        from types import SimpleNamespace as NS
        from aiwb.v2.ledger import record_build_evidence
        a = self.ready_task("A", acceptance_policy="evidence_required", required_approvals=["validation"])
        self.p.attempts.create(a["task_id"])
        self.p.tasks.transition(a["task_id"], "validation_pending")
        git = NS(commit_sha="f" * 40)
        self.assertEqual(record_build_evidence(self.p, git, NS(run_id=None, outcome="success")), [])
        self.assertEqual(record_build_evidence(self.p, git, NS(run_id=5, outcome="in_progress")), [])
        added = record_build_evidence(self.p, git, NS(run_id=7, outcome="success"))
        self.assertEqual([(e["source"]["kind"], e["verified"], e["result"]) for e in added],
                         [("github_actions", True, "passed")])
        self.assertEqual(self.p.tasks.get(a["task_id"])["status"], "done")
        self.assertEqual(record_build_evidence(self.p, git, NS(run_id=7, outcome="success")), [], "idempotent")


class FakeGitHub:
    def __init__(self):
        self.refs, self.blobs, self.trees, self.commits = {"main": "c0"}, {}, {"t0": {}}, {"c0": {"tree": "t0"}}
        self.calls, self.fail = [], []
        self.default = "main"

    def __call__(self, method, url, headers, body):
        path = url.split("/repos/o/r", 1)[1]
        self.calls.append((method, path))
        if self.fail:
            st, hdr = self.fail.pop(0)
            return ApiResult(st, {"message": "x"}, hdr)
        data = json.loads(body) if body else None
        n = len(self.calls)
        if method == "GET" and path == "":
            return ApiResult(200, {"default_branch": self.default}, {})
        if method == "GET" and path.startswith("/git/ref/heads/"):
            b = path.rsplit("/", 1)[1]
            return ApiResult(200, {"object": {"sha": self.refs[b]}}, {}) if b in self.refs else ApiResult(404, {}, {})
        if method == "GET" and path.startswith("/git/commits/"):
            return ApiResult(200, {"tree": {"sha": self.commits[path.rsplit("/", 1)[1]]["tree"]}}, {})
        if method == "GET" and path.startswith("/contents/"):
            fp, ref = path[len("/contents/"):].split("?ref=")
            files = self.trees[self.commits[self.refs[ref]]["tree"]] if ref in self.refs else {}
            if fp not in files:
                return ApiResult(404, {}, {})
            return ApiResult(200, {"content": base64.b64encode(files[fp].encode()).decode()}, {})
        if method == "POST" and path == "/git/blobs":
            self.blobs[f"b{n}"] = data["content"]
            return ApiResult(201, {"sha": f"b{n}"}, {})
        if method == "POST" and path == "/git/trees":
            files = dict(self.trees[data["base_tree"]])
            files.update({e["path"]: self.blobs[e["sha"]] for e in data["tree"]})
            self.trees[f"t{n}"] = files
            return ApiResult(201, {"sha": f"t{n}"}, {})
        if method == "POST" and path == "/git/commits":
            self.commits[f"c{n}"] = {"tree": data["tree"], "parents": data["parents"], "message": data["message"]}
            return ApiResult(201, {"sha": f"c{n}"}, {})
        if method == "POST" and path == "/git/refs":
            self.refs[data["ref"].split("/")[-1]] = data["sha"]
            return ApiResult(201, {}, {})
        if method == "PATCH" and path.startswith("/git/refs/heads/"):
            assert data["force"] is False
            self.refs[path.rsplit("/", 1)[1]] = data["sha"]
            return ApiResult(200, {}, {})
        return ApiResult(404, {}, {})

    def files(self, branch="aiwb-state"):
        return self.trees[self.commits[self.refs[branch]]["tree"]]


class PublisherTests(Base):
    def setUp(self):
        super().setUp()
        self.gh = FakeGitHub()
        self.now = [1000.0]
        with self.p.store.transaction("enable") as s:
            s["settings"]["publish"]["enabled"] = True
        self.pub = StatePublisher(self.p.store, client_factory=lambda: GitHubStateClient("tok", "o", "r", transport=self.gh),
                                  source_info=lambda: {"repository": "o/r", "branch": "main", "commit_sha": "abc",
                                                       "local_changes_pending": True, "local_changes_count": 2},
                                  clock=lambda: self.now[0])

    def test_atomic_publish_noop_and_change(self):
        self.ready_task("A")
        r = self.pub.tick(force=True)
        self.assertEqual(r["status"], "published")
        files = self.gh.files()
        self.assertEqual(sorted(files), [".aiwb/PROJECT_STATUS.md", ".aiwb/project-state.json"])
        snap = json.loads(files[".aiwb/project-state.json"])
        self.assertEqual((snap["source"]["commit_sha"], snap["source"]["local_changes_pending"]), ("abc", True))
        self.assertEqual(self.gh.refs["main"], "c0", "code branch untouched")
        commits_before = len(self.gh.commits)
        self.assertEqual(self.pub.tick(force=True)["status"], "noop")
        self.assertEqual(len(self.gh.commits), commits_before)
        self.ready_task("B")
        self.pub.mark_dirty("task created")
        self.assertEqual(self.pub.tick()["status"], "debouncing")
        self.now[0] += 10
        self.assertEqual(self.pub.tick()["status"], "published")
        self.assertIn("B", self.gh.files()[".aiwb/PROJECT_STATUS.md"])
        for blob in self.gh.blobs.values():
            self.assertNotIn(str(self.root), blob)
            self.assertNotIn("do A", blob, "objective/prompt text is not needed in the published projection")

    def test_offline_retry_rate_limit_auth_and_conflict(self):
        self.ready_task("A")
        self.gh.fail = [(503, {})]
        self.assertEqual(self.pub.tick(force=True)["kind"], "network")
        self.assertEqual(self.pub.tick()["status"], "waiting")
        self.now[0] += 31
        self.gh.fail = [(429, {"Retry-After": "120"})]
        self.assertEqual(self.pub.tick()["kind"], "rate_limit")
        self.now[0] += 60
        self.assertEqual(self.pub.tick()["status"], "waiting")
        self.now[0] += 61
        self.assertEqual(self.pub.tick()["status"], "published")
        self.ready_task("B")
        self.gh.refs["aiwb-state"] = "c0"  # someone else moved the branch
        r = self.pub.tick(force=True)
        self.assertEqual(r["kind"], "conflict")
        self.assertEqual(self.gh.refs["aiwb-state"], "c0", "no overwrite on conflict")
        self.assertEqual(self.pub.tick()["status"], "paused")
        q = json.loads(self.pub.qpath.read_text())
        self.assertIn("conflict", q["paused"])
        self.pub.resume()
        self.gh.fail = [(401, {})]
        self.assertEqual(self.pub.tick(force=True)["kind"], "auth")
        self.assertEqual(self.pub.tick()["status"], "paused")

    def test_protected_branch_and_other_project_refused(self):
        with self.assertRaises(PublishError):
            GitHubStateClient("t", "o", "r", transport=self.gh).commit_files("main", {"a": "b"}, "m", expected_head="c0")
        with self.p.store.transaction("x") as s:
            s["settings"]["publish"]["branch"] = "aiwb-state"
        self.gh.refs["aiwb-state"] = "cX"
        self.gh.commits["cX"] = {"tree": "tX"}
        self.gh.trees["tX"] = {".aiwb/project-state.json": json.dumps({"project_id": "someone-else"})}
        self.assertEqual(self.pub.tick(force=True)["kind"], "conflict")

    def test_queue_survives_restart(self):
        self.ready_task("A")
        self.gh.fail = [(503, {})]
        self.pub.tick(force=True)
        pub2 = StatePublisher(self.p.store, client_factory=self.pub.client_factory, clock=lambda: self.now[0])
        self.assertEqual(pub2.tick()["status"], "waiting")
        self.assertTrue(pub2.pending)


class ProposalTests(Base):
    def block(self, base, ops, **kw):
        return ("Analysis…\n<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps({"schema_version": "1.0", "base_state_revision": base,
                "summary": "s", "operations": ops, **kw}) + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>")

    def test_plan_with_forward_refs_and_partial_accept(self):
        rev = self.p.store.revision
        p = self.p.proposals.import_text(self.block(rev, [
            {"operation": "create_task", "temporary_ref": "a", "title": "API", "objective": "api", "owner_role": "implementer",
             "depends_on_refs": ["b"]},
            {"operation": "create_task", "temporary_ref": "b", "title": "Contract", "objective": "c", "owner_role": "architect"},
            {"operation": "report_risk", "description": "tight"},
            {"operation": "frobnicate"}]))
        self.assertFalse(p["stale"])
        self.assertFalse(p["operations"][3]["valid"])
        self.assertEqual(self.p.tasks.list(), [], "import alone changes nothing")
        prev = self.p.proposals.preview(p["proposal_id"], [0])
        self.assertTrue(prev["errors"], "depends on b which is not accepted")
        out = self.p.proposals.review(p["proposal_id"], [0, 1, 2])
        self.assertEqual(out["status"], "accepted")
        ids = out["result"]["created"]
        api = self.p.tasks.get(ids["a"])
        self.assertEqual((api["depends_on"], api["owner_agent_id"], api["origin"]),
                         ([ids["b"]], "agent-implementer", "manager_proposal"))
        with self.assertRaises(ModelError):
            self.p.proposals.review(p["proposal_id"], [0])

    def test_cycle_unknown_ids_stale_and_no_done(self):
        a = self.ready_task("A")
        b = self.p.tasks.create({"title": "B", "objective": "b", "depends_on": [a["task_id"]]})
        base = self.p.store.revision
        cyc = self.p.proposals.import_text(self.block(base, [{"operation": "add_dependency", "task_id": a["task_id"],
                                                              "depends_on_task_id": b["task_id"]}]))
        with self.assertRaises(ModelError):
            self.p.proposals.review(cyc["proposal_id"], [0])
        self.assertEqual(self.p.tasks.get(a["task_id"])["depends_on"], [])
        bad = self.p.proposals.import_text(self.block(base, [{"operation": "update_task", "task_id": "TASK-9999", "changes": {}},
                                                             {"operation": "update_task", "task_id": a["task_id"],
                                                              "changes": {"status": "done"}}]))
        self.assertFalse(bad["operations"][0]["valid"])
        with self.assertRaises(ModelError):
            self.p.proposals.review(bad["proposal_id"], [1])
        self.p.tasks.update(a["task_id"], {"objective": "moved on"})
        st = self.p.proposals.import_text(self.block(base, [{"operation": "reorder_priority", "task_id": a["task_id"],
                                                             "priority": "high"}]))
        self.assertTrue(st["stale"])
        with self.assertRaises(ModelError):
            self.p.proposals.review(st["proposal_id"], [0])
        self.assertEqual(self.p.proposals.review(st["proposal_id"], [0], confirm_stale=True)["status"], "accepted")
        self.assertEqual(self.p.tasks.get(a["task_id"])["priority"], "high")
        for missing in ("no block", self.block("x", [{"operation": "report_risk"}]), self.block(1, [])):
            with self.assertRaises(ModelError):
                self.p.proposals.import_text(missing)

    def test_prompts_and_probe(self):
        pp = planning_prompt({"goal": "Build a todo app"}, self.p.agents.list())
        self.assertIn("AIWB_MANAGER_PROPOSAL", pp)
        self.assertIn("agent-architect", pp)
        st = self.p.store.load()
        snap = build_snapshot(st)
        up = manager_update_prompt(snap, state_url="https://github.com/o/r/blob/aiwb-state/.aiwb/project-state.json",
                                   fallback=fallback_summary(snap, st))
        self.assertIn("CANNOT READ STATE", up)
        self.assertIn(f"base_state_revision {snap['state_revision']}", up)
        self.assertEqual(check_probe("STATE_REVISION=7", 7), "readable")
        self.assertEqual(check_probe("STATE_REVISION=6", 7), "wrong")
        self.assertEqual(check_probe("sorry, CANNOT READ STATE", 7), "unreadable")


class NextActionTests(Base):
    def test_actions_follow_state(self):
        (self.root / "e").mkdir()
        empty = V2Project(self.root / "e")
        empty.open()
        self.assertEqual(empty.next_actions()[0]["type"], "plan_project")
        t = self.ready_task("A")
        self.assertEqual(self.p.next_actions()[0]["type"], "start_task")
        h = self.p.handoffs.prepare(t["task_id"], "agent-implementer")
        self.assertEqual(self.p.next_actions()[0]["type"], "copy_prompt")
        self.p.handoffs.mark_exported(h["handoff_id"])
        self.assertEqual(self.p.next_actions()[0]["type"], "import_response")
        self.p.handoffs.ingest(h["handoff_id"], "r", manifest(h))
        self.assertEqual(self.p.next_actions()[0]["type"], "review_handoff")
        d = self.p.decisions.propose("Pick", "?", affected_task_ids=[t["task_id"]])
        first = self.p.next_actions()[0]
        self.assertEqual((first["type"], first["reference_id"]), ("resolve_decision", d["decision_id"]))
        self.assertTrue(first["needs_approval"])
        md = render_status_md(build_snapshot(self.p.store.load()), self.p.store.load())
        self.assertIn("Next action", md)


if __name__ == "__main__":
    unittest.main()
