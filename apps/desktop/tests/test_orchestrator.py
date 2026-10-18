"""Tests for aiwb.github.orchestrator (v1.14.8 One-click Sync & Build).

Real Git repositories with a local bare remote; GitHub is a fake transport.
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.git import GitService, GitSyncService  # noqa: E402
from aiwb.github import orchestrator as orc  # noqa: E402
from aiwb.github.actions import GitHubActionsService, RepositoryOperationGuard  # noqa: E402
from aiwb.github.api_client import GitHubApiClient, HttpResponse  # noqa: E402
from aiwb.github.artifacts import GitHubDispatchService  # noqa: E402

TOKEN = "github_pat_" + "A" * 40
WF = ".github/workflows/build.yml"


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"git {args}: {r.stderr}")
    return r.stdout.strip()


def j(value: object, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {}, json.dumps(value).encode())


class FakeGitHub:
    def __init__(self) -> None:
        self.runs: list[dict] = []
        self.artifacts: dict[int, list[dict]] = {}
        self.blobs: dict[int, bytes] = {}
        self.cancelled: list[int] = []

    def transport(self, url: str, headers: dict, timeout: float) -> HttpResponse:
        parts = urlsplit(url)
        q = parse_qs(parts.query)
        if parts.path.endswith("/actions/workflows"):
            return j({"workflows": [{"id": 7, "name": "Build", "path": WF, "state": "active", "html_url": ""}]})
        if parts.path.endswith("/actions/workflows/7/runs"):
            sha = (q.get("head_sha") or [""])[0]
            return j({"workflow_runs": [r for r in self.runs if not sha or r["head_sha"] == sha]})
        if "/artifacts" in parts.path and "/runs/" in parts.path:
            rid = int(parts.path.split("/runs/")[1].split("/")[0])
            return j({"artifacts": self.artifacts.get(rid, [])})
        return HttpResponse(404, {}, b"{}")

    def request(self, url: str, method: str, headers: dict, body: bytes | None, timeout: float) -> HttpResponse:
        aid = int(url.split("/artifacts/")[1].split("/")[0])
        return HttpResponse(302, {"Location": f"https://pipelines.actions.githubusercontent.com/blob/{aid}"}, b"")

    def stream(self, url: str, timeout: float):
        yield self.blobs[int(url.rsplit("/", 1)[1])]

    def write(self, url: str, method: str, headers: dict, timeout: float) -> int:
        self.cancelled.append(int(url.split("/runs/")[1].split("/")[0]))
        return 202

    def add_run(self, run_id: int, sha: str, branch: str, status: str = "completed", conclusion: str | None = "success") -> None:
        self.runs.insert(0, {"id": run_id, "workflow_id": 7, "name": "Build", "event": "push", "status": status,
                             "conclusion": conclusion, "head_branch": branch, "head_sha": sha, "run_number": 1,
                             "run_attempt": 1, "created_at": "2026-10-18T10:00:00Z", "updated_at": "", "html_url": ""})


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("app.bin", b"binary")
    return buf.getvalue()


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.remote = base / "remote.git"
        self.work = base / "work"
        git(base, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(base, "init", "-q", "-b", "main", str(self.work))
        git(self.work, "config", "user.email", "t@example.com")
        git(self.work, "config", "user.name", "T")
        (self.work / "a.txt").write_text("1\n")
        git(self.work, "add", "a.txt")
        git(self.work, "commit", "-q", "-m", "init")
        git(self.work, "remote", "add", "origin", str(self.remote))
        git(self.work, "push", "-q", "origin", "main")
        git(self.work, "switch", "-q", "-c", "work")
        git(self.work, "push", "-q", "-u", "origin", "work")
        self.gh = FakeGitHub()
        self.store = orc.RecordStore(base / "ops.json")
        self.guard = RepositoryOperationGuard()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make(self, branch: str = "work", **kw) -> orc.SyncBuildOrchestrator:
        client = GitHubApiClient(transport=self.gh.transport)
        actions = GitHubActionsService(client, write_transport=self.gh.write)
        dispatch = GitHubDispatchService(actions, request=self.gh.request, stream=self.gh.stream)
        params = dict(sync=GitSyncService(GitService()), actions=actions, dispatch=dispatch, git_root=self.work,
                      project_subpath="", owner="o", repo="r", repository_id=99, branch=branch, workflow_file=WF,
                      artifact_pattern="", get_token=lambda: TOKEN, store=self.store,
                      is_sensitive=lambda p: p.endswith(".env"), in_scope=lambda p: not p.startswith("other/"),
                      guard=self.guard, sleep=lambda _s: None)
        params.update(kw)
        return orc.SyncBuildOrchestrator(**params)

    def test_happy_path_and_evidence_chain(self) -> None:
        (self.work / "a.txt").write_text("2\n")
        o = self.make(task_id="T1")
        res = o.check()
        self.assertTrue(res.ok, res.checks)
        self.assertEqual(o.state, orc.REVIEW_REQUIRED)
        sha = o.commit(["a.txt"], "change a")
        self.assertEqual(o.commit(["a.txt"], "again"), sha)  # idempotent
        o.push()
        self.assertEqual(git(self.work, "ls-remote", "origin", "refs/heads/work").split()[0], sha)
        self.assertIsNone(o.poll_run())
        self.assertEqual(o.state, orc.CI_QUEUED)
        self.gh.add_run(500, "f" * 40, "work")  # another commit: must be ignored
        self.assertIsNone(o.poll_run())
        self.gh.add_run(501, sha, "work")
        data = make_zip()
        self.gh.blobs[9] = data
        self.gh.artifacts[501] = [{"id": 9, "name": "app", "size_in_bytes": len(data), "expired": False,
                                   "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                                   "workflow_run": {"id": 501, "head_sha": sha, "head_branch": "work", "repository_id": 99}},
                                  {"id": 10, "name": "foreign", "size_in_bytes": 1, "expired": False, "digest": "",
                                   "workflow_run": {"id": 501, "head_sha": "e" * 40, "repository_id": 99}}]
        run = o.wait_for_build(timeout=5)
        self.assertEqual(run.run_id, 501)
        self.assertEqual(o.state, orc.BUILD_PASSED)
        out = o.download_artifacts(Path(self.tmp.name) / "dl")
        self.assertEqual([r["artifact_id"] for r in out], [9])
        self.assertEqual(o.state, orc.ARTIFACT_VERIFIED)
        rec = self.store.get(o.operation_id)
        self.assertEqual(rec["git"]["commit_sha"], sha)
        self.assertEqual(rec["git"]["task_id"], "T1")
        self.assertEqual(rec["build"]["run_id"], 501)
        self.assertEqual(rec["build"]["artifacts"][0]["verification"], "matched")
        self.assertNotIn(TOKEN, json.dumps(rec))
        self.assertIn("Workbench-Run: " + o.operation_id, git(self.work, "log", "-1", "--format=%B"))

    def test_review_flags_block_and_confirm(self) -> None:
        (self.work / "secret.env").write_text("X=1\n")
        (self.work / "other").mkdir()
        (self.work / "other" / "b.txt").write_text("b\n")
        (self.work / ".github" / "workflows").mkdir(parents=True)
        (self.work / WF).write_text("on: push\n")
        o = self.make()
        flags = {i.path: i.flags for i in o.check().items}
        self.assertIn("sensitive", flags["secret.env"])
        self.assertIn("outside_scope", flags["other/b.txt"])
        self.assertIn("workflow_change", flags[WF])
        with self.assertRaises(orc.OrchestratorError):
            o.commit(["secret.env"], "x")
        with self.assertRaises(orc.OrchestratorError):
            o.commit(["other/b.txt"], "x")
        sha = o.commit(["other/b.txt", WF], "x", confirmed_paths=["other/b.txt", WF])
        self.assertEqual(len(sha), 40)
        self.assertIn("secret.env", git(self.work, "status", "--porcelain"))

    def test_protected_branch_refused(self) -> None:
        git(self.work, "switch", "-q", "main")
        o = self.make(branch="main")
        res = o.check()
        self.assertFalse(res.ok)
        self.assertEqual(o.state, orc.PREFLIGHT_FAILED)

    def test_wrong_checkout_refused(self) -> None:
        git(self.work, "switch", "-q", "main")
        self.assertFalse(self.make().check().ok)

    def test_stale_plan_before_commit(self) -> None:
        (self.work / "a.txt").write_text("2\n")
        o = self.make()
        o.check()
        other = Path(self.tmp.name) / "other"
        git(Path(self.tmp.name), "clone", "-q", "-b", "work", str(self.remote), str(other))
        git(other, "-c", "user.email=x@x", "-c", "user.name=x", "commit", "-q", "--allow-empty", "-m", "remote")
        git(other, "push", "-q", "origin", "work")
        with self.assertRaises(orc.OrchestratorError):
            o.commit(["a.txt"], "x")
        self.assertEqual(o.state, orc.STALE_PLAN)
        self.assertIn("a.txt", git(self.work, "status", "--porcelain"))

    def test_push_failure_keeps_commit_and_resume_is_idempotent(self) -> None:
        (self.work / "a.txt").write_text("2\n")
        o = self.make()
        o.check()
        sha = o.commit(["a.txt"], "x")
        git(self.work, "remote", "set-url", "origin", str(Path(self.tmp.name) / "missing.git"))
        with self.assertRaises(orc.OrchestratorError) as cm:
            o.push()
        self.assertIn("kept", str(cm.exception))
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), sha)
        o.release()
        git(self.work, "remote", "set-url", "origin", str(self.remote))
        o2 = self.make(operation_id=o.operation_id)
        self.assertTrue(o2.resumed)
        self.assertEqual(o2.commit(["a.txt"], "ignored"), sha)
        o2.push()
        self.assertTrue(o2.git.pushed)
        self.assertEqual(git(self.work, "rev-list", "--count", "origin/main..HEAD"), "1")

    def test_lost_push_result_detected(self) -> None:
        (self.work / "a.txt").write_text("2\n")
        o = self.make()
        o.check()
        sha = o.commit(["a.txt"], "x")
        git(self.work, "push", "-q", "origin", "work")  # push happened, result "lost"
        o.push()
        self.assertTrue(o.git.pushed)
        self.assertEqual(o.state, orc.PUSHED)
        self.assertEqual(git(self.work, "ls-remote", "origin", "refs/heads/work").split()[0], sha)

    def test_cancel_semantics(self) -> None:
        o = self.make()
        o.check()
        self.assertEqual(o.cancel(), "nothing_changed")
        (self.work / "a.txt").write_text("2\n")
        o = self.make()
        o.check()
        sha = o.commit(["a.txt"], "x")
        self.assertEqual(o.cancel(), "commit_kept")
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), sha)
        o = self.make(operation_id=o.operation_id)
        o.cancel_requested = False
        o.push()
        self.gh.add_run(600, sha, "work", status="in_progress", conclusion=None)
        o.poll_run()
        self.assertEqual(o.state, orc.CI_RUNNING)
        self.assertEqual(o.cancel(), "run_cancel_requested")
        self.assertEqual(self.gh.cancelled, [600])
        self.assertEqual(git(self.work, "ls-remote", "origin", "refs/heads/work").split()[0], sha)

    def test_operation_lock(self) -> None:
        a = self.make()
        a.check()
        b = self.make()
        with self.assertRaises(orc.OrchestratorError):
            b.check()
        a.release()
        self.assertTrue(b.check().ok)

    def test_build_failed_blocks_artifacts(self) -> None:
        (self.work / "a.txt").write_text("2\n")
        o = self.make()
        o.check()
        sha = o.commit(["a.txt"], "x")
        o.push()
        self.gh.add_run(700, sha, "work", conclusion="failure")
        o.wait_for_build(timeout=1)
        self.assertEqual(o.state, orc.BUILD_FAILED)
        with self.assertRaises(orc.OrchestratorError):
            o.matching_artifacts()


class BuildMetadataTests(unittest.TestCase):
    def test_contract_conversion(self) -> None:
        rec = {"git": {"repository": "o/r", "branch": "w", "commit_sha": "A" * 40, "pushed": True},
               "build": {"workflow_file": WF, "run_id": 3, "outcome": "success",
                         "artifacts": [{"artifact_id": 1, "name": "a", "sha256": "e" * 64, "verification": "matched", "path": "/x", "size": 2}]}}
        meta = orc.build_metadata(rec, repository_id=5)
        self.assertEqual(meta["commit_sha"], "a" * 40)
        self.assertNotIn("path", meta["artifacts"][0])
        self.assertIsNone(orc.build_metadata({"git": {"commit_sha": "a" * 40, "pushed": False}, "build": {"run_id": 3}}))

if __name__ == "__main__":
    unittest.main()
