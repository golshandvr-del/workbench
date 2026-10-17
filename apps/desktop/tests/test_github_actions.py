"""Tests for aiwb.github.actions (v1.14.6 Build Center read model)."""
from __future__ import annotations

import base64
import json
import unittest
from urllib.parse import parse_qs, urlsplit

from aiwb.github.actions import (
    GitHubActionsService, PollPolicy, RepositoryOperationGuard, WorkflowInfo, WorkflowRun,
    check_workflow_binding, correlate_runs_with_commit, parse_workflow_triggers,
)
from aiwb.github.api_client import GitHubApiClient, GitHubApiError, HttpResponse

TOKEN = "github_pat_" + "A" * 40
SHA_A = "a" * 40
SHA_B = "b" * 40


def resp(value: object, status: int = 200, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status, headers or {}, json.dumps(value).encode())


class Router:
    """Fake transport keyed by URL path (query ignored unless the route has '?')."""

    def __init__(self, routes: dict[str, HttpResponse]):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        self.calls.append(url)
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        path = urlsplit(url).path
        if path not in self.routes:
            return resp({"message": "Not Found"}, 404)
        return self.routes[path]


def content(text: str) -> HttpResponse:
    return resp({"encoding": "base64", "content": base64.b64encode(text.encode()).decode()})


def run(run_id: int, sha: str, *, branch: str = "feat", status: str = "completed", conclusion: str | None = "success", created: str = "2026-10-17T10:00:00Z", attempt: int = 1) -> dict:
    return {"id": run_id, "workflow_id": 7, "name": "CI", "event": "push", "status": status, "conclusion": conclusion,
            "head_branch": branch, "head_sha": sha, "run_number": run_id, "run_attempt": attempt,
            "created_at": created, "updated_at": created, "run_started_at": created,
            "html_url": f"https://github.com/o/r/actions/runs/{run_id}", "actor": {"login": "dev"}}


def svc(routes: dict[str, HttpResponse], write=None) -> tuple[GitHubActionsService, Router]:
    router = Router(routes)
    return GitHubActionsService(GitHubApiClient(transport=router), write_transport=write), router


class TriggerParsingTests(unittest.TestCase):
    def test_forms(self) -> None:
        self.assertEqual(parse_workflow_triggers("on: push\njobs: {}\n"), ("push",))
        self.assertEqual(parse_workflow_triggers("on: [push, pull_request]\n"), ("push", "pull_request"))
        self.assertEqual(parse_workflow_triggers("on: {push: {branches: [main]}, workflow_dispatch: {}}\n"), ("push", "workflow_dispatch"))
        block = "name: CI\non:\n  push:\n    branches: [main]\n  workflow_dispatch:\n    inputs:\n      x: {}\njobs:\n  a: {}\n"
        self.assertEqual(parse_workflow_triggers(block), ("push", "workflow_dispatch"))
        self.assertEqual(parse_workflow_triggers("'on':\n  - push\n  - workflow_dispatch\n"), ("push", "workflow_dispatch"))
        self.assertEqual(parse_workflow_triggers("true:\n  push:\n"), ("push",))  # YAML 1.1 'on' == true

    def test_comments_and_absent(self) -> None:
        self.assertEqual(parse_workflow_triggers("on:  # triggers\n  push:  # x\n  # workflow_dispatch:\n"), ("push",))
        self.assertIsNone(parse_workflow_triggers("name: x\njobs: {}\n"))
        self.assertIsNone(parse_workflow_triggers("on: [push\n"))

    def test_nested_workflow_dispatch_word_is_not_a_trigger(self) -> None:
        text = "on:\n  push:\n    paths: ['workflow_dispatch']\njobs:\n  workflow_dispatch:\n    runs-on: x\n"
        self.assertEqual(parse_workflow_triggers(text), ("push",))


class WorkflowDiscoveryTests(unittest.TestCase):
    def test_lists_workflows_with_dispatch_state(self) -> None:
        routes = {
            "/repos/o/r/actions/workflows": resp({"total_count": 3, "workflows": [
                {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active", "html_url": "https://github.com/o/r/blob/main/.github/workflows/ci.yml"},
                {"id": 2, "name": "Release", "path": ".github/workflows/release.yaml", "state": "disabled_manually", "html_url": "https://evil.example/x"},
                {"id": 3, "name": "Dependabot", "path": "dynamic/dependabot/dependabot-updates", "state": "active"},
                {"id": 4, "name": "Broken", "path": ".github/workflows/broken.yml", "state": "active"},
            ]}),
            "/repos/o/r/contents/.github/workflows/ci.yml": content("on:\n  push:\n  workflow_dispatch:\n"),
            "/repos/o/r/contents/.github/workflows/release.yaml": content("on:\n  push:\n    tags: ['v*']\n"),
            "/repos/o/r/contents/.github/workflows/broken.yml": resp({}, 404),
        }
        service, _ = svc(routes)
        wfs = service.list_workflows(TOKEN, "o", "r")
        self.assertEqual([w.path for w in wfs], [".github/workflows/broken.yml", ".github/workflows/ci.yml", ".github/workflows/release.yaml"])
        by = {w.workflow_id: w for w in wfs}
        self.assertEqual(by[1].manual_dispatch, "available")
        self.assertEqual(by[2].manual_dispatch, "not_available")
        self.assertEqual(by[4].manual_dispatch, "unknown")  # unreadable file is never assumed dispatchable
        self.assertEqual(by[2].html_url, "")  # non-GitHub link dropped
        self.assertFalse(by[2].is_active)

    def test_binding_staleness(self) -> None:
        wfs = [WorkflowInfo(1, "CI", ".github/workflows/ci.yml", "active", ""), WorkflowInfo(2, "Old", ".github/workflows/old.yml", "disabled_manually", "")]
        self.assertEqual(check_workflow_binding(None, wfs), "unset")
        self.assertEqual(check_workflow_binding(".github/workflows/ci.yml", wfs), "ok")
        self.assertEqual(check_workflow_binding(".github/workflows/old.yml", wfs), "disabled")
        self.assertEqual(check_workflow_binding(".github/workflows/renamed.yml", wfs), "stale")

    def test_invalid_repo_names_rejected_before_request(self) -> None:
        service, router = svc({})
        for owner, repo in (("o/../x", "r"), ("o", ".."), ("", "r"), ("o", "r?x=1")):
            with self.assertRaises(GitHubApiError):
                service.list_workflows(TOKEN, owner, repo)
        self.assertEqual(router.calls, [])


class RunTests(unittest.TestCase):
    def test_runs_sorted_and_filtered_query(self) -> None:
        routes = {"/repos/o/r/actions/workflows/7/runs": resp({"workflow_runs": [
            run(1, SHA_A, created="2026-10-17T09:00:00Z"),
            run(2, SHA_B, created="2026-10-17T11:00:00Z", status="in_progress", conclusion=None),
            {"id": 3, "head_sha": "not-a-sha"},
        ]})}
        service, router = svc(routes)
        runs = service.list_runs(TOKEN, "o", "r", workflow_id=7, branch="feat", head_sha=SHA_B.upper().lower())
        self.assertEqual([r.run_id for r in runs], [2, 1])
        q = parse_qs(urlsplit(router.calls[0]).query)
        self.assertEqual(q["branch"], ["feat"]); self.assertEqual(q["head_sha"], [SHA_B])
        self.assertEqual(runs[0].outcome, "running")
        self.assertFalse(runs[0].is_finished)

    def test_outcomes_are_distinguished(self) -> None:
        def outcome(status: str, conclusion: str | None) -> str:
            return WorkflowRun(1, 1, "", "", status, conclusion, "", SHA_A, 1, 1, "", "", "", "").outcome
        self.assertEqual(outcome("completed", "success"), "success")
        self.assertEqual(outcome("completed", "failure"), "failure")
        self.assertEqual(outcome("completed", "cancelled"), "cancelled")
        self.assertEqual(outcome("completed", "skipped"), "skipped")
        self.assertEqual(outcome("completed", "weird"), "completed_unknown")
        self.assertEqual(outcome("queued", None), "queued")

    def test_correlation_never_reports_other_commit(self) -> None:
        runs = [WorkflowRun(i, 7, "CI", "push", "completed", "success", b, s, i, 1, c, c, c, "")
                for i, s, b, c in ((1, SHA_A, "feat", "2026-10-17T09:00:00Z"), (2, SHA_A, "other", "2026-10-17T12:00:00Z"))]
        old = correlate_runs_with_commit(runs, SHA_B, branch="feat")
        self.assertEqual(old.state, "only_older_runs"); self.assertIsNone(old.run); self.assertEqual(old.newest_other.run_id, 1)
        hit = correlate_runs_with_commit(runs, SHA_A, branch="feat")
        self.assertEqual((hit.state, hit.run.run_id), ("matched", 1))
        self.assertEqual(correlate_runs_with_commit([], SHA_A).state, "no_run_for_commit")
        with self.assertRaises(ValueError):
            correlate_runs_with_commit(runs, "abc123")

    def test_rerun_attempt_preferred(self) -> None:
        c = "2026-10-17T09:00:00Z"
        runs = [WorkflowRun(5, 7, "CI", "push", "completed", "failure", "f", SHA_A, 5, 1, c, c, c, ""),
                WorkflowRun(5, 7, "CI", "push", "completed", "success", "f", SHA_A, 5, 2, c, c, c, "")]
        self.assertEqual(correlate_runs_with_commit(runs, SHA_A).run.run_attempt, 2)

    def test_jobs_failed_steps(self) -> None:
        routes = {"/repos/o/r/actions/runs/9/jobs": resp({"jobs": [
            {"id": 1, "name": "build", "status": "completed", "conclusion": "failure", "html_url": "https://github.com/o/r/actions/runs/9/job/1",
             "steps": [{"number": 1, "name": "checkout", "status": "completed", "conclusion": "success"},
                       {"number": 2, "name": "test", "status": "completed", "conclusion": "failure"}]},
        ]})}
        service, _ = svc(routes)
        jobs = service.list_jobs(TOKEN, "o", "r", 9)
        self.assertEqual([s.name for s in jobs[0].failed_steps], ["test"])
        self.assertTrue(jobs[0].log_url.startswith("https://github.com/"))

    def test_error_categories(self) -> None:
        for status, headers, category in ((401, {}, "authentication"), (403, {}, "permission_or_policy"),
                                          (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "0"}, "rate_limit"),
                                          (429, {"retry-after": "30"}, "rate_limit"), (502, {}, "server")):
            service, _ = svc({"/repos/o/r/actions/runs": resp({}, status, headers)})
            with self.assertRaises(GitHubApiError) as ctx:
                service.list_runs(TOKEN, "o", "r")
            self.assertEqual(ctx.exception.category, category, (status, headers))

    def test_timeout_category(self) -> None:
        def boom(url, headers, timeout):
            raise TimeoutError()
        service = GitHubActionsService(GitHubApiClient(transport=boom))
        with self.assertRaises(GitHubApiError) as ctx:
            service.list_runs(TOKEN, "o", "r")
        self.assertEqual(ctx.exception.category, "timeout")


class CancelTests(unittest.TestCase):
    def _run(self, status: str = "in_progress") -> WorkflowRun:
        return WorkflowRun(9, 7, "CI", "push", status, None, "f", SHA_A, 9, 1, "", "", "", "")

    def test_requires_confirmation_and_unfinished(self) -> None:
        calls = []
        service, _ = svc({}, write=lambda *a: calls.append(a) or 202)
        with self.assertRaises(GitHubApiError):
            service.cancel_run(TOKEN, "o", "r", self._run(), confirmed=False)
        with self.assertRaises(GitHubApiError):
            service.cancel_run(TOKEN, "o", "r", self._run("completed"), confirmed=True)
        self.assertEqual(calls, [])
        self.assertEqual(service.cancel_run(TOKEN, "o", "r", self._run(), confirmed=True), "requested")
        url, method, headers, _ = calls[0]
        self.assertEqual((urlsplit(url).path, method), ("/repos/o/r/actions/runs/9/cancel", "POST"))

    def test_cancel_errors(self) -> None:
        for status, category in ((403, "permission_or_policy"), (409, "conflict"), (401, "authentication"), (500, "request")):
            service, _ = svc({}, write=lambda *a, s=status: s)
            with self.assertRaises(GitHubApiError) as ctx:
                service.cancel_run(TOKEN, "o", "r", self._run(), confirmed=True)
            self.assertEqual(ctx.exception.category, category)


class PollingTests(unittest.TestCase):
    def test_backoff_rate_limit_and_auth_stop(self) -> None:
        now = [1000.0]
        p = PollPolicy(clock=lambda: now[0])
        self.assertTrue(p.may_fetch_now())
        p.record_success(any_running=True)
        self.assertFalse(p.may_fetch_now())  # cache window
        self.assertAlmostEqual(p.next_delay(), 10.0)
        p.record_success(any_running=False)
        self.assertAlmostEqual(p.next_delay(), 60.0)
        p.record_error(GitHubApiError("server", "x"))
        first = p.next_delay()
        p.record_error(GitHubApiError("server", "x"))
        self.assertGreater(p.next_delay(), first)
        p.record_error(GitHubApiError("rate_limit", "x", retry_after_seconds=900))
        self.assertGreaterEqual(p.next_delay(), 900)
        p.record_error(GitHubApiError("authentication", "x"))
        self.assertTrue(p.stopped)
        now[0] += 10_000
        self.assertFalse(p.may_fetch_now())


class GuardTests(unittest.TestCase):
    def test_conflicting_operations(self) -> None:
        g = RepositoryOperationGuard()
        self.assertTrue(g.acquire("O/R", "feat", "sync"))
        self.assertFalse(g.acquire("o/r", "feat", "build"))
        self.assertEqual(g.holder("o/r", "feat"), "sync")
        self.assertTrue(g.acquire("o/r", "main", "build"))
        g.release("o/r", "feat")
        self.assertTrue(g.acquire("o/r", "feat", "build"))


if __name__ == "__main__":
    unittest.main()
