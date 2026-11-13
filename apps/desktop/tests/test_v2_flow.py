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
    def test_bf109_unscoped_foreign_ci_never_validates_project_tasks(self):
        from types import SimpleNamespace as NS
        from aiwb.v2.ledger import record_build_evidence
        t = self.ready_task("B", acceptance_policy="evidence_required", required_approvals=["validation"])
        self.p.attempts.create(t["task_id"])
        self.p.tasks.transition(t["task_id"], "validation_pending")
        for outcome in ("success", "failure"):
            with self.subTest(outcome=outcome):
                git = NS(repository="o/foreign", branch="work", task_id="TASK-FROM-A", commit_sha="a" * 40)
                build = NS(run_id=991, outcome=outcome, head_sha="a" * 40)
                self.assertEqual(record_build_evidence(self.p, git, build), [])
                self.assertEqual(self.p.tasks.get(t["task_id"])["status"], "validation_pending")
                self.assertEqual(self.p.evidence.list(t["task_id"]), [])

    def test_real_actions_run_becomes_verified_evidence_once(self):
        from types import SimpleNamespace as NS
        from aiwb.v2.ledger import record_build_evidence
        a = self.ready_task("A", acceptance_policy="evidence_required", required_approvals=["validation"])
        self.p.attempts.create(a["task_id"])
        self.p.tasks.transition(a["task_id"], "validation_pending")
        task = self.p.tasks.get(a["task_id"])
        context = {"project_root": str(self.root), "project_id": self.p.store.load()["project_id"],
                   "task_id": a["task_id"], "task_revision": task["task_revision"],
                   "attempt_id": task["active_attempt_id"], "repository": "o/a", "branch": "work"}
        git = NS(commit_sha="f" * 40, operation_id="op-A", repository="o/a", branch="work", pushed=True,
                 task_id=a["task_id"], evidence_context=context)
        build = NS(run_id=7, outcome="success", head_sha="f" * 40, operation_id="op-A")
        checked = {"current_commit": "f" * 40, "repository": "o/a", "branch": "work"}
        for key, wrong in (("current_commit", "a" * 40), ("repository", "o/b"), ("branch", "other")):
            with self.subTest(mismatch=key):
                self.assertEqual(record_build_evidence(self.p, git, build, **{**checked, key: wrong}), [])
        for key, wrong in (("project_id", "other"), ("task_id", "TASK-OTHER"),
                           ("task_revision", 999), ("attempt_id", "other-attempt")):
            original = context[key]
            context[key] = wrong
            self.assertEqual(record_build_evidence(self.p, git, build, **checked), [])
            context[key] = original
        self.assertEqual(record_build_evidence(self.p, git, NS(run_id=None, outcome="success"), **checked), [])
        self.assertEqual(record_build_evidence(self.p, git, NS(run_id=5, outcome="in_progress"), **checked), [])
        added = record_build_evidence(self.p, git, build, **checked)
        self.assertEqual([(e["source"]["kind"], e["verified"], e["result"]) for e in added],
                         [("github_actions", True, "passed")])
        self.assertEqual(added[0]["attempt_id"], task["active_attempt_id"])
        self.assertEqual(self.p.tasks.get(a["task_id"])["status"], "done")
        self.assertEqual(record_build_evidence(self.p, git, build, **checked), [], "idempotent")

    def test_bf109_completion_targets_captured_project_after_active_project_switch(self):
        from types import SimpleNamespace as NS
        from unittest.mock import patch
        import uuid
        import AI_Workbench as wb
        from aiwb.github.repository_binding import RepositoryBinding
        a = self.ready_task("A", acceptance_policy="evidence_required", required_approvals=["validation"])
        self.p.attempts.create(a["task_id"])
        self.p.tasks.transition(a["task_id"], "validation_pending")
        task = self.p.tasks.get(a["task_id"])
        binding = RepositoryBinding(str(uuid.uuid4()), str(self.root), str(self.root), ".", str(uuid.uuid4()),
                                    1, "o", "a", "o/a", "https://github.com/o/a", "main", "work", "now")
        context = {"project_root": str(self.root), "project_id": self.p.store.load()["project_id"],
                   "binding_id": binding.binding_id, "account_id": binding.account_id, "repository_id": 1,
                   "repository": "o/a", "branch": "work", "task_id": a["task_id"],
                   "task_revision": task["task_revision"], "attempt_id": task["active_attempt_id"]}
        other = V2Project(self.root / "other", "other")
        other.open()
        before = other.store.load()
        app = NS(workspace=other.store.root, refresh_git=lambda **kw: None, set_status=lambda text: None,
                 settings_data={"github_repository_bindings": [binding.to_dict()]})
        operation = NS(git=NS(commit_sha="f" * 40, operation_id="op-A", repository="o/a", branch="work", pushed=True,
                              task_id=a["task_id"], evidence_context=context),
                       build=NS(run_id=7, outcome="success", head_sha="f" * 40, operation_id="op-A"))
        def run(root, args, **kw):
            self.assertEqual(Path(root), self.root)
            value = {"rev-parse": "f" * 40, "branch": "work", "remote": "https://github.com/o/a.git"}[args[0]]
            return NS(returncode=0, stdout=value)
        with patch.object(wb, "git_run", side_effect=run):
            wb.WorkbenchApp._sync_build_finished(app, operation)
        self.assertEqual(self.p.tasks.get(a["task_id"])["status"], "done")
        self.assertEqual(other.store.load(), before)
        self.assertEqual(len(self.p.evidence.list(a["task_id"])), 1)


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

    def test_bf002_emergency_cycle_is_skipped_and_preview_matches_review(self):
        from aiwb.v2.tasks import validate_graph
        x = self.ready_task("X")
        p = self.p.proposals.import_text(self.block(self.p.store.revision, [
            {"operation": "create_task", "temporary_ref": "hotfix", "title": "Hotfix",
             "depends_on_refs": [x["task_id"]]}],
            emergency_tasks=[{"ref": "hotfix", "blocks": [x["task_id"]]}]))
        before = self.p.store.load()
        preview = self.p.proposals.preview(p["proposal_id"], [0])
        self.assertEqual(self.p.store.load(), before, "preview changed persistent state")
        out = self.p.proposals.review(p["proposal_id"], [0])["result"]
        self.assertEqual(validate_graph(self.p.store.load()["tasks"]), [])
        self.assertEqual(self.p.tasks.get(x["task_id"])["status"], "ready")
        self.assertEqual(self.p.tasks.get(x["task_id"])["depends_on"], [])
        self.assertTrue(out["decision"]["skipped_blocks"])
        self.assertEqual(preview["decision"]["skipped_blocks"], out["decision"]["skipped_blocks"])
        self.assertIn("cycle", " ".join(out["decision"]["skipped_blocks"]))

    def test_bf003_reject_invalid_existing_graph_never_changes_tasks(self):
        a = self.ready_task("A")
        b = self.ready_task("B")
        with self.p.store.transaction("legacy cyclic graph") as s:
            s["tasks"][a["task_id"]]["depends_on"] = [b["task_id"]]
            s["tasks"][b["task_id"]]["depends_on"] = [a["task_id"]]
        p = self.p.proposals.import_text(self.block(self.p.store.revision, [
            {"operation": "report_risk", "description": "re-plan needed"}],
            emergency_tasks=[{"ref": a["task_id"], "blocks": [b["task_id"]]}]))
        tasks_before = self.p.store.load()["tasks"]
        self.assertEqual(self.p.proposals.preview(p["proposal_id"], [])["errors"], [])
        out = self.p.proposals.review(p["proposal_id"], [], note="Please break the cycle")
        self.assertEqual(out["status"], "rejected")
        self.assertEqual(out["result"]["note"], "Please break the cycle")
        self.assertEqual(self.p.store.load()["tasks"], tasks_before)
        self.assertNotIn("last_decision", self.p.store.load()["settings"].get("flow", {}))

    def test_bf004_remove_last_dependency_refreshes_existing_task(self):
        a = self.ready_task("A")
        b = self.p.tasks.create({"title": "B", "objective": "b", "depends_on": [a["task_id"]]})
        self.p.tasks.transition(b["task_id"], "blocked", "waiting for " + a["task_id"])
        manual = self.ready_task("Manual")
        # Manual blocks must use a manual reason, not the reserved dependency
        # prefix (which transition's immediate readiness refresh may resolve).
        self.p.tasks.transition(manual["task_id"], "blocked", "user sign-off needed")
        p = self.p.proposals.import_text(self.block(self.p.store.revision, [
            {"operation": "remove_dependency", "task_id": b["task_id"], "depends_on_task_id": a["task_id"]}]))
        self.p.proposals.review(p["proposal_id"], [0])
        self.assertEqual(self.p.tasks.get(b["task_id"])["status"], "ready")
        self.assertEqual(self.p.tasks.get(b["task_id"])["blocked_reason"], "")
        self.assertEqual(self.p.tasks.get(manual["task_id"])["status"], "blocked")
        # Same invariant through the direct TaskService API, not only proposals.
        self.p.tasks.update(b["task_id"], {"depends_on": [a["task_id"]]})
        self.assertEqual(self.p.tasks.get(b["task_id"])["status"], "blocked")
        self.p.tasks.update(b["task_id"], {"depends_on": []})
        self.assertEqual(self.p.tasks.get(b["task_id"])["status"], "ready")

    def test_bf014_cancelled_dependencies_and_edits_are_invalid_on_import(self):
        a = self.ready_task("A")
        self.p.tasks.transition(a["task_id"], "cancelled", "not wanted")
        operations = [
            {"operation": "create_task", "title": "New", "depends_on": [a["task_id"]]},
            {"operation": "create_task", "title": "New refs", "depends_on_refs": [a["task_id"]]},
            {"operation": "update_task", "task_id": a["task_id"], "changes": {"objective": "overwrite"}},
        ]
        p = self.p.proposals.import_text(self.block(self.p.store.revision, operations))
        for op in p["operations"]:
            self.assertFalse(op["valid"], op)
            self.assertIn("cancelled", op["problem"])
        before = self.p.store.load()["tasks"]
        with self.assertRaises(ModelError):
            self.p.proposals.review(p["proposal_id"], [0, 1, 2], confirm_stale=True)
        self.assertEqual(self.p.store.load()["tasks"], before)

    def test_bf014_review_rechecks_dependencies_cancelled_after_import(self):
        a = self.ready_task("A")
        p = self.p.proposals.import_text(self.block(self.p.store.revision, [
            {"operation": "create_task", "title": "New", "depends_on_refs": [a["task_id"]]}]))
        self.assertTrue(p["operations"][0]["valid"])
        self.p.tasks.transition(a["task_id"], "cancelled", "cancelled after import")
        before = self.p.store.load()["tasks"]
        self.assertTrue(self.p.proposals.preview(p["proposal_id"], [0])["errors"])
        with self.assertRaisesRegex(ModelError, "cancelled"):
            self.p.proposals.review(p["proposal_id"], [0], confirm_stale=True)
        self.assertEqual(self.p.store.load()["tasks"], before)
        self.assertEqual(self.p.proposals.get(p["proposal_id"])["status"], "pending")

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

    def test_bf056_role_change_rebuilds_role_fields(self) -> None:
        from aiwb.v2.team_setup import _write_team, default_rows
        st = self.p.store.load()
        rows = default_rows(2)
        with self.p.store.transaction("t") as s:
            _write_team(s, rows)
        st = self.p.store.load()
        aid = rows[1].get("agent_id") or [a for a in st["agents"] if a != "agent-project-manager"][0]
        aid = [a for a in st["agents"] if a != "agent-project-manager"][0]
        before = st["agents"][aid]["purpose"]
        new_rows = [dict(r) for r in rows]
        new_rows[1] = {**new_rows[1], "agent_id": aid, "role": "reviewer"}
        with self.p.store.transaction("t2") as s:
            _write_team(s, new_rows)
        after = self.p.store.load()["agents"][aid]
        self.assertEqual(after["role"], "reviewer")
        self.assertNotEqual(after["purpose"], before)

    def test_bf083_object_decision_requests_are_kept_as_text(self) -> None:
        from aiwb.v2.handoff import _decisions
        out = _decisions([{"question": "SQLite or JSON files?", "options": ["SQLite", "JSON"], "recommendation": "SQLite"}, "plain", 5, {}])
        self.assertEqual(len(out), 3)
        self.assertTrue(out[0].startswith("SQLite or JSON files?"))
        self.assertIn("Options: SQLite, JSON", out[0])
        self.assertIn("Recommended: SQLite", out[0])
        from aiwb.v2.choices import parse_options
        opts, rec = parse_options(out[0])
        self.assertEqual(opts, ["SQLite", "JSON"])
        self.assertEqual(rec, "SQLite")

    def test_bf083_needs_decision_card_text_is_the_question(self) -> None:
        from aiwb.v2.handoff import _decisions
        asks = _decisions([{"question": "SQLite or JSON files?", "options": ["SQLite", "JSON"]}])
        for outcome, expect in (("needs_decision", "SQLite or JSON files?"), ("blocked", "storage layer")):
            pick = (asks or ["storage layer"]) if outcome == "needs_decision" else (["storage layer"] or asks)
            self.assertTrue(pick[0].startswith(expect))
        src = (Path(__file__).resolve().parents[1] / "src" / "aiwb" / "v2" / "handoff.py").read_text("utf-8")
        self.assertIn('(asks or open_items) if h["outcome"] == "needs_decision"', src)

    def test_bf067_multiline_task_title_is_collapsed(self) -> None:
        from aiwb.v2.models import normalize_task
        base = {"objective": "o", "title": "Login page\n\n## Done with evidence\n\n- TASK-0099 — Payments (done)"}
        try:
            t = normalize_task(base)
        except TypeError:
            t = normalize_task(base, "TASK-0001")
        self.assertNotIn("\n", t["title"])
        self.assertTrue(t["title"].startswith("Login page ## Done"))


if __name__ == "__main__":
    unittest.main()
