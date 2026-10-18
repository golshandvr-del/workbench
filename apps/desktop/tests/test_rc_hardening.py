"""Release-candidate hardening tests (roadmap v1.14.13).

Cross-cutting checks: no token in errors/records/Git output, network failure
messages, rate-limit backoff, operation lock under concurrency, and the
idempotent/cancel semantics of the Sync & Build orchestrator.
"""
from __future__ import annotations

import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aiwb.git import GitService, GitSyncService  # noqa: E402
from aiwb.git.service import redact_git_text  # noqa: E402
from aiwb.github import orchestrator as orc  # noqa: E402
from aiwb.github.actions import GitHubActionsService, PollPolicy, RepositoryOperationGuard  # noqa: E402
from aiwb.github.api_client import GitHubApiClient, GitHubApiError  # noqa: E402
from aiwb.github.artifacts import GitHubDispatchService  # noqa: E402
from aiwb.github.redaction import redact_github_text  # noqa: E402
from test_orchestrator import TOKEN, WF, FakeGitHub, git  # noqa: E402

CLASSIC = "ghp_" + "Z" * 36


class RedactionTests(unittest.TestCase):
    def test_token_forms_are_scrubbed(self) -> None:
        samples = [
            f"fatal: unable to access 'https://x-access-token:{CLASSIC}@github.com/o/r.git/'",
            f"Authorization: Bearer {TOKEN}",
            f"headers={{'Authorization': 'token {CLASSIC}'}}",
            f"error with {TOKEN} inside",
            f"password={CLASSIC}",
        ]
        for s in samples:
            out = redact_github_text(s)
            self.assertNotIn(CLASSIC, out)
            self.assertNotIn(TOKEN, out)

    def test_known_secret_redacted_even_if_unusual(self) -> None:
        secret = "custom-secret-value-123"
        self.assertNotIn(secret, redact_github_text("x " + secret, known_secrets=(secret,)))

    def test_git_fallback_redacts_url_credentials(self) -> None:
        out = redact_git_text(f"https://user:{CLASSIC}@github.com/o/r.git")
        self.assertNotIn(CLASSIC, out)


class ApiErrorTests(unittest.TestCase):
    def _client(self, exc: BaseException) -> GitHubApiClient:
        def transport(url, headers, timeout):  # noqa: ANN001
            raise exc
        return GitHubApiClient(transport=transport)

    def test_network_errors_never_echo_token(self) -> None:
        for exc in (urllib.error.URLError(f"boom {TOKEN}"), socket.timeout(f"slow {TOKEN}"),
                    OSError(f"reset {TOKEN}"), RuntimeError(f"weird {TOKEN}")):
            with self.assertRaises(GitHubApiError) as cm:
                self._client(exc).get_authenticated_user(TOKEN)
            text = str(cm.exception) + repr(cm.exception)
            self.assertNotIn(TOKEN, text)
            self.assertIn(cm.exception.category, ("network", "timeout"))
            self.assertIsNone(cm.exception.__cause__)  # raised "from None": no chained secret

    def test_rate_limit_backoff_and_401_stop(self) -> None:
        now = [1000.0]
        p = PollPolicy(clock=lambda: now[0])
        p.record_error(GitHubApiError("rate_limit", "x", retry_after_seconds=900))
        self.assertGreaterEqual(p.next_delay(), 899)
        self.assertFalse(p.may_fetch_now())
        p.record_error(GitHubApiError("authentication", "x"))
        self.assertTrue(p.stopped)
        p2 = PollPolicy(clock=lambda: now[0])
        p2.record_error(GitHubApiError("network", "x"))
        d1 = p2.next_delay()
        p2.record_error(GitHubApiError("network", "x"))
        self.assertGreater(p2.next_delay(), d1)  # exponential backoff
        self.assertLessEqual(p2.next_delay(), p2.max_backoff)


class ConcurrencyTests(unittest.TestCase):
    def test_guard_admits_exactly_one_of_many_threads(self) -> None:
        g = RepositoryOperationGuard()
        wins: list[int] = []
        barrier = threading.Barrier(16)

        def worker(i: int) -> None:
            barrier.wait()
            if g.acquire("O/R", "work", f"t{i}"):
                wins.append(i)

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(wins), 1)
        self.assertFalse(g.acquire("o/r", "work", "case-insensitive repo"))
        self.assertTrue(g.acquire("o/r", "other-branch", "other ref is independent"))


class OrchestratorRcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aiwb rc ü ")
        base = Path(self.tmp.name)
        self.base = base
        self.remote, self.work = base / "remote.git", base / "work dir"
        git(base, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(base, "init", "-q", "-b", "main", str(self.work))
        git(self.work, "config", "user.email", "t@example.com"); git(self.work, "config", "user.name", "T")
        (self.work / "a.txt").write_text("1\n"); git(self.work, "add", "a.txt"); git(self.work, "commit", "-q", "-m", "init")
        git(self.work, "remote", "add", "origin", str(self.remote)); git(self.work, "switch", "-q", "-c", "work")
        git(self.work, "push", "-q", "-u", "origin", "work")
        self.gh = FakeGitHub()
        client = GitHubApiClient(transport=self.gh.transport)
        actions = GitHubActionsService(client, write_transport=self.gh.write)
        self.services = dict(actions=actions, dispatch=GitHubDispatchService(actions, request=self.gh.request, stream=self.gh.stream))
        self.store = orc.RecordStore(base / "ops.json")
        self.guard = RepositoryOperationGuard()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make(self, **kw) -> orc.SyncBuildOrchestrator:  # noqa: ANN003
        args = dict(sync=GitSyncService(GitService()), git_root=self.work, project_subpath="", owner="o", repo="r",
                    repository_id=99, branch="work", workflow_file=WF, artifact_pattern="", get_token=lambda: TOKEN,
                    store=self.store, is_sensitive=lambda p: p.endswith(".env"), guard=self.guard, sleep=lambda _s: None)
        args.update(self.services); args.update(kw)
        return orc.SyncBuildOrchestrator(**args)

    def test_second_window_cannot_take_the_same_branch(self) -> None:
        a, b = self.make(), self.make()
        self.assertTrue(a.acquire())
        self.assertFalse(b.acquire())
        a.release()
        self.assertTrue(b.acquire())
        b.release()

    def test_cancel_before_commit_changes_nothing(self) -> None:
        (self.work / "a.txt").write_text("2\n")
        o = self.make(); o.acquire(); o.check()
        head = git(self.work, "rev-parse", "HEAD")
        o.cancel()
        with self.assertRaises(orc.OrchestratorError):
            o.commit(["a.txt"], "x")
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), head)
        self.assertIn("a.txt", git(self.work, "status", "--porcelain"))

    def test_resume_after_lost_push_result_needs_no_second_commit(self) -> None:
        (self.work / "a.txt").write_text("3\n")
        o = self.make(); o.acquire(); o.check()
        sha = o.commit(["a.txt"], "x")
        oid = o.operation_id
        git(self.work, "push", "-q", "origin", "work")  # push "happened" but the app never saw the result
        o.release()
        r = self.make(operation_id=oid); r.acquire()
        self.assertTrue(r.resumed)
        r.push()
        self.assertTrue(r.git.pushed)
        self.assertEqual(git(self.work, "rev-list", "--count", "HEAD"), "2")
        self.assertEqual(r.git.commit_sha, sha)
        r.release()

    def test_records_and_events_contain_no_token(self) -> None:
        (self.work / "a.txt").write_text("4\n")
        events: list[str] = []
        o = self.make(); o.subscribe(lambda s, m: events.append(m)); o.acquire(); o.check()
        o.commit(["a.txt"], "x"); o.push()
        blob = (self.base / "ops.json").read_text(encoding="utf-8") + "\n".join(events)
        self.assertNotIn(TOKEN, blob)
        o.release()

    def test_unreadable_token_is_a_failed_preflight_not_a_crash(self) -> None:
        def boom() -> str:
            raise RuntimeError("credential manager locked " + TOKEN)
        o = self.make(get_token=boom); o.acquire()
        res = o.check()
        self.assertFalse(res.ok)
        self.assertNotIn(TOKEN, " ".join(c.detail for c in res.checks))
        o.release()


class SettingsRecoveryTests(unittest.TestCase):
    def test_corrupt_settings_are_backed_up_not_lost(self) -> None:
        import AI_Workbench as app
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "settings.json"
            p.write_text('{"a": 1,', encoding="utf-8")
            self.assertEqual(app.load_settings_with_recovery(p), {})
            backups = list(Path(t).glob("settings.json.corrupt-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), '{"a": 1,')
            self.assertFalse(p.exists())

    def test_bom_and_unknown_keys_are_kept(self) -> None:
        import AI_Workbench as app
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "settings.json"
            p.write_bytes(b"\xef\xbb\xbf" + b'{"future_key": {"x": 1}, "aiwb_upgrade_sentinel": "keep"}')
            d = app.load_settings_with_recovery(p)
            self.assertEqual(d["aiwb_upgrade_sentinel"], "keep")
            self.assertIn("future_key", d)
            self.assertEqual(app.load_settings_with_recovery(Path(t) / "missing.json"), {})


if __name__ == "__main__":
    unittest.main()
