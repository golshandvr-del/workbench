"""Unit and local-Git integration tests for GitHub Repository Browser and bindings."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from aiwb.github.api_client import GitHubApiClient, GitHubApiError, GitHubRepository, HttpResponse
from aiwb.github.repository_binding import (
    RemoteConfigurationRequired, RepositoryBinding, RepositoryBindingError, rollback_origin,
    canonical_repository_url, configure_origin, find_binding, inspect_local_repository,
    load_bindings, make_binding, parse_github_remote, remove_binding, upsert_binding,
)
from aiwb.git import GitService

TOKEN = "github_pat_" + "R" * 40


def repo_payload(repo_id: int, *, owner: str = "octocat", name: str | None = None, private: bool = False, fork: bool = False, archived: bool = False) -> dict[str, object]:
    name = name or f"repo-{repo_id}"
    return {
        "id": repo_id, "name": name, "full_name": f"{owner}/{name}",
        "owner": {"login": owner}, "private": private, "fork": fork, "archived": archived,
        "default_branch": "main", "updated_at": "2026-10-17T12:00:00Z",
        "description": "Example description", "html_url": f"https://github.com/{owner}/{name}",
        "permissions": {"push": not private},
    }


class QueueTransport:
    def __init__(self, *responses: HttpResponse):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, str], float]] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        self.calls.append((url, dict(headers), timeout))
        if not self.responses:
            raise AssertionError("Unexpected extra API request")
        return self.responses.pop(0)


def json_response(value: object, status: int = 200, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status, headers or {}, json.dumps(value).encode("utf-8"))


class RepositoryApiTests(unittest.TestCase):
    def test_lists_all_pages_and_uses_safe_pagination(self):
        transport = QueueTransport(
            json_response([repo_payload(1), repo_payload(2)], headers={"X-RateLimit-Remaining": "40"}),
            json_response([repo_payload(3, private=True)], headers={"X-RateLimit-Remaining": "39"}),
        )
        listing = GitHubApiClient(transport=transport).list_repositories(TOKEN, per_page=2)
        self.assertEqual([repo.repository_id for repo in listing.repositories], [1, 2, 3])
        self.assertEqual(listing.pages_loaded, 2)
        self.assertFalse(listing.truncated)
        self.assertEqual([parse_qs(urlsplit(call[0]).query)["page"][0] for call in transport.calls], ["1", "2"])
        self.assertTrue(all(call[1]["Authorization"] == f"Bearer {TOKEN}" for call in transport.calls))
        self.assertTrue(all("visibility" in parse_qs(urlsplit(call[0]).query) for call in transport.calls))

    def test_deduplicates_repository_ids_and_reports_safety_cap(self):
        transport = QueueTransport(
            json_response([repo_payload(1), repo_payload(2)]),
            json_response([repo_payload(2), repo_payload(3)]),
        )
        listing = GitHubApiClient(transport=transport).list_repositories(TOKEN, per_page=2, max_pages=2)
        self.assertEqual([repo.repository_id for repo in listing.repositories], [1, 2, 3])
        self.assertTrue(listing.truncated)
        self.assertEqual(listing.pages_loaded, 2)

    def test_validates_repo_metadata_and_repository_url(self):
        bad = repo_payload(1)
        bad["html_url"] = "https://attacker.example/octocat/repo-1"
        with self.assertRaises(GitHubApiError) as caught:
            GitHubApiClient(transport=QueueTransport(json_response([bad]))).list_repositories(TOKEN, per_page=2)
        self.assertEqual(caught.exception.category, "invalid_response")

    def test_handles_permission_rate_limit_and_empty_list(self):
        with self.assertRaises(GitHubApiError) as caught:
            GitHubApiClient(transport=QueueTransport(HttpResponse(403, {}, b'{"message":"private"}'))).list_repositories(TOKEN)
        self.assertEqual(caught.exception.category, "permission_or_policy")
        with self.assertRaises(GitHubApiError) as rate:
            GitHubApiClient(transport=QueueTransport(HttpResponse(403, {"X-RateLimit-Remaining": "0", "Retry-After": "12"}, b'{"message":"rate limit"}'))).list_repositories(TOKEN)
        self.assertEqual(rate.exception.category, "rate_limit")
        empty = GitHubApiClient(transport=QueueTransport(json_response([]))).list_repositories(TOKEN)
        self.assertEqual(empty.repositories, ())
        self.assertEqual(empty.pages_loaded, 1)

    def test_rejects_bad_pagination_bounds(self):
        client = GitHubApiClient(transport=QueueTransport())
        for kwargs in ({"per_page": 0}, {"per_page": 101}, {"max_pages": 0}, {"max_pages": 101}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                client.list_repositories(TOKEN, **kwargs)


class RemoteParsingTests(unittest.TestCase):
    def test_parses_supported_remote_shapes_without_returning_credentials(self):
        cases = {
            "https://github.com/octocat/Hello-World.git": ("octocat", "Hello-World"),
            "https://user:secret@github.com/octocat/Hello-World": ("octocat", "Hello-World"),
            "git@github.com:octocat/Hello-World.git": ("octocat", "Hello-World"),
            "ssh://git@github.com/octocat/Hello-World.git": ("octocat", "Hello-World"),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_github_remote(raw), expected)
        for raw in ("https://github.com.evil.example/octocat/r", "https://example.com/octocat/r", "file:///tmp/r", "https://github.com/octocat", "https://github.com/octocat/r?token=secret"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_github_remote(raw))

    def test_binding_records_are_validated_and_upserted_by_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp).resolve()
            account_id = str(uuid.uuid4())
            repo = GitHubRepository(1, "octocat", "demo", "octocat/demo", False, False, False, "main", None, None, "https://github.com/octocat/demo", True)
            context = type("Context", (), {
                "project_path": project, "local_git_root": project, "project_subpath": ".", "current_branch": "main"
            })()
            binding = make_binding(context, account_id, repo)
            rows = upsert_binding([], binding)
            self.assertEqual(len(load_bindings(rows)), 1)
            self.assertEqual(find_binding(rows, project).repository_id, 1)
            tampered = dict(rows[0]); tampered["project_subpath"] = "../outside"
            self.assertIsNone(RepositoryBinding.from_dict(tampered))
            self.assertEqual(remove_binding(rows, project), [])
            self.assertEqual(canonical_repository_url(repo), "https://github.com/octocat/demo.git")


class LocalGitBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aiwb-repo-binding-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo_dir = self.root / "monorepo"
        (self.repo_dir / "apps" / "desktop").mkdir(parents=True)
        self.project = self.repo_dir / "apps" / "desktop"
        subprocess.run(["git", "init", "-b", "main", str(self.repo_dir)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo_dir), "config", "user.name", "AIWB Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo_dir), "config", "user.email", "aiwb-test@example.invalid"], check=True)
        (self.repo_dir / "README.md").write_text("test\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo_dir), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.repo_dir), "commit", "-m", "initial"], check=True, capture_output=True)
        self.git = GitService()
        self.github_repo = GitHubRepository(777, "octocat", "desktop", "octocat/desktop", False, False, False, "main", None, "test", "https://github.com/octocat/desktop", True)

    def test_inspects_monorepo_subpath_without_mutating_remote(self):
        context = inspect_local_repository(self.git, self.project, self.github_repo)
        self.assertEqual(context.local_git_root, self.repo_dir)
        self.assertEqual(context.project_subpath, "apps/desktop")
        self.assertFalse(context.origin_present)
        with self.assertRaises(RemoteConfigurationRequired) as caught:
            configure_origin(self.git, context, self.github_repo, "keep")
        self.assertEqual(caught.exception.kind, "missing")
        self.assertNotEqual(subprocess.run(["git", "-C", str(self.repo_dir), "remote"], capture_output=True, text=True).stdout.strip(), "origin")

    def test_requires_explicit_add_or_replace_and_confirms_result(self):
        context = inspect_local_repository(self.git, self.project, self.github_repo)
        configure_origin(self.git, context, self.github_repo, "add")
        self.assertEqual(parse_github_remote(subprocess.run(["git", "-C", str(self.repo_dir), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()), ("octocat", "desktop"))
        subprocess.run(["git", "-C", str(self.repo_dir), "remote", "set-url", "origin", "https://github.com/other/repo.git"], check=True)
        context2 = inspect_local_repository(self.git, self.project, self.github_repo)
        self.assertEqual(context2.existing_remote_repository, "other/repo")
        with self.assertRaises(RemoteConfigurationRequired) as caught:
            configure_origin(self.git, context2, self.github_repo, "keep")
        self.assertEqual(caught.exception.kind, "mismatch")
        configure_origin(self.git, context2, self.github_repo, "replace")
        self.assertTrue(inspect_local_repository(self.git, self.project, self.github_repo).origin_matches)

    def test_rollback_removes_new_origin_and_never_exposes_old_remote_credentials(self):
        context = inspect_local_repository(self.git, self.project, self.github_repo)
        configure_origin(self.git, context, self.github_repo, "add")
        self.assertTrue(rollback_origin(self.git, context))
        remote_list = subprocess.run(["git", "-C", str(self.repo_dir), "remote"], capture_output=True, text=True, check=True).stdout
        self.assertNotIn("origin", remote_list.splitlines())
        secret_remote = "https://user:supersecret@github.com/other/private.git"
        subprocess.run(["git", "-C", str(self.repo_dir), "remote", "add", "origin", secret_remote], check=True)
        context2 = inspect_local_repository(self.git, self.project, self.github_repo)
        self.assertEqual(context2.existing_remote_repository, "other/private")
        self.assertNotIn("supersecret", repr(context2))
        self.assertNotIn("supersecret", str(RemoteConfigurationRequired("mismatch", context2.existing_remote_repository)))
        self.assertTrue(rollback_origin(self.git, context2))
        restored = subprocess.run(["git", "-C", str(self.repo_dir), "remote", "get-url", "origin"], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(restored, secret_remote)

    def test_non_git_path_is_rejected(self):
        outside = self.root / "not-a-repository"
        outside.mkdir()
        with self.assertRaisesRegex(RepositoryBindingError, "not inside a local Git repository"):
            inspect_local_repository(self.git, outside, self.github_repo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
