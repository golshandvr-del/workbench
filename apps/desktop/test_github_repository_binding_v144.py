"""Regression tests for v1.14.4 Monorepo-aware repository bindings."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from aiwb.git.service import GitService
from aiwb.github.api_client import GitHubRepository
from aiwb.github.repository_binding import (
    RepositoryBinding,
    RepositoryBindingError,
    build_initial_push_review,
    classify_scoped_paths,
    find_binding,
    make_binding,
    migrate_binding_records,
    refresh_binding_repository_metadata,
    update_binding_preferences,
    upsert_binding,
)


def repo(repo_id: int, owner: str = "octocat", name: str = "demo", default_branch: str = "main") -> GitHubRepository:
    return GitHubRepository(repo_id, owner, name, f"{owner}/{name}", True, False, False, default_branch,
                            "2026-10-17T12:00:00Z", "Repository fixture",
                            f"https://github.com/{owner}/{name}", True)


class BindingModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aiwb-binding-v144-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.monorepo = self.root / "repo-root"
        (self.monorepo / "apps" / "desktop").mkdir(parents=True)
        (self.monorepo / "apps" / "mobile").mkdir(parents=True)
        self.account_id = str(uuid.uuid4())

    def context(self, project: Path, branch: str = "workbench/feature"):
        relative = project.resolve().relative_to(self.monorepo.resolve()).as_posix() or "."
        return type("Context", (), {
            "project_path": project.resolve(), "local_git_root": self.monorepo.resolve(),
            "project_subpath": relative, "current_branch": branch,
        })()

    def test_schema_v1_migrates_idempotently_to_v2_with_defaults(self):
        binding = make_binding(self.context(self.monorepo / "apps" / "desktop"), self.account_id, repo(101))
        row = binding.to_dict()
        row["schema_version"] = 1
        for key in ("workflow_file", "artifact_pattern", "release_channel", "last_known_remote_sha", "last_synced_at", "metadata_refreshed_at"):
            row.pop(key)
        first = migrate_binding_records([row])
        self.assertTrue(first.changed)
        self.assertEqual(first.migrated_count, 1)
        self.assertEqual(first.invalid_count, 0)
        self.assertEqual(first.records[0]["schema_version"], 2)
        self.assertEqual(first.records[0]["release_channel"], "dev")
        second = migrate_binding_records(list(first.records))
        self.assertFalse(second.changed)
        self.assertEqual(second.migrated_count, 0)
        self.assertEqual(second.records, first.records)

    def test_multiple_projects_can_share_same_repository_id_at_distinct_subpaths(self):
        desktop = make_binding(self.context(self.monorepo / "apps" / "desktop"), self.account_id, repo(101))
        mobile = make_binding(self.context(self.monorepo / "apps" / "mobile"), self.account_id, repo(101))
        rows = upsert_binding([], desktop)
        rows = upsert_binding(rows, mobile)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["project_subpath"] for row in rows}, {"apps/desktop", "apps/mobile"})
        self.assertEqual({row["repository_id"] for row in rows}, {101})
        self.assertEqual(find_binding(rows, Path(desktop.project_path)).project_subpath, "apps/desktop")
        self.assertEqual(find_binding(rows, Path(mobile.project_path)).project_subpath, "apps/mobile")

    def test_migration_reports_invalid_and_duplicate_rows_for_backup_recovery(self):
        valid = make_binding(self.context(self.monorepo / "apps" / "desktop"), self.account_id, repo(101)).to_dict()
        duplicate_same_project = dict(valid)
        invalid = dict(valid)
        invalid["project_subpath"] = "../../outside"
        report = migrate_binding_records([valid, duplicate_same_project, invalid])
        self.assertEqual(len(report.records), 1)
        self.assertEqual(report.duplicate_count, 1)
        self.assertEqual(report.invalid_count, 1)
        self.assertTrue(report.changed)

    def test_binding_preferences_are_validated_and_saved_as_schema_v2(self):
        binding = make_binding(self.context(self.monorepo / "apps" / "desktop"), self.account_id, repo(101))
        updated = update_binding_preferences(
            binding, working_branch="feature/review", workflow_file=".github/workflows/desktop-ci.yml",
            artifact_pattern="AIWorkbench-*.zip", release_channel="beta",
        )
        self.assertEqual(updated.schema_version, 2)
        self.assertEqual(updated.workflow_file, ".github/workflows/desktop-ci.yml")
        self.assertEqual(updated.release_channel, "beta")
        self.assertEqual(RepositoryBinding.from_dict(updated.to_dict()), updated)
        for values in (
            {"working_branch": "bad branch", "workflow_file": None, "artifact_pattern": "", "release_channel": "dev"},
            {"working_branch": "feature/good", "workflow_file": "../evil.yml", "artifact_pattern": "", "release_channel": "dev"},
            {"working_branch": "feature/good", "workflow_file": None, "artifact_pattern": "../../secret.zip", "release_channel": "dev"},
            {"working_branch": "feature/good", "workflow_file": None, "artifact_pattern": "", "release_channel": "production"},
        ):
            with self.subTest(values=values), self.assertRaises(RepositoryBindingError):
                update_binding_preferences(binding, **values)

    def test_renamed_repository_metadata_refreshes_by_numeric_id_only(self):
        old = make_binding(self.context(self.monorepo / "apps" / "desktop", branch="main"), self.account_id, repo(101))
        renamed = repo(101, "octocat-new", "renamed", "trunk")
        refreshed = refresh_binding_repository_metadata(old, renamed, account_id=self.account_id)
        self.assertEqual(refreshed.repository_id, 101)
        self.assertEqual(refreshed.full_name, "octocat-new/renamed")
        self.assertEqual(refreshed.html_url, "https://github.com/octocat-new/renamed")
        self.assertEqual(refreshed.default_branch, "trunk")
        self.assertEqual(refreshed.working_branch, "trunk", "tracking the old default branch should follow a default-branch rename")
        custom_branch = update_binding_preferences(old, working_branch="feature/my-work", workflow_file=None, artifact_pattern="", release_channel="dev")
        refreshed_custom = refresh_binding_repository_metadata(custom_branch, renamed, account_id=self.account_id)
        self.assertEqual(refreshed_custom.working_branch, "feature/my-work")
        with self.assertRaises(RepositoryBindingError):
            refresh_binding_repository_metadata(old, renamed, account_id=str(uuid.uuid4()))
        with self.assertRaises(RepositoryBindingError):
            refresh_binding_repository_metadata(old, repo(999), account_id=self.account_id)


class ScopeAndInitialPushReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aiwb-monorepo-review-v144-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "monorepo"
        self.project = self.root / "apps" / "desktop"
        self.project.mkdir(parents=True)
        subprocess.run(["git", "init", "-b", "workbench/initial-sync-test", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "AIWB Test"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "aiwb@example.invalid"], check=True)
        (self.project / "README.md").write_text("safe project data\n", encoding="utf-8")
        (self.root / "outside.txt").write_text("outside project subpath\n", encoding="utf-8")
        (self.project / ".env").write_text("API_KEY=not-a-real-key-but-secret-looking-value-12345\n", encoding="utf-8")
        (self.project / "config.txt").write_text("github_pat_" + "A" * 36 + "\n", encoding="utf-8")
        (self.project / "bundle.bin").write_bytes(b"x" * 256)
        subprocess.run(["git", "-C", str(self.root), "add", "apps/desktop/README.md"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "initial"], check=True, capture_output=True)
        self.git = GitService()

    def test_path_scope_is_component_aware_and_rejects_traversal(self):
        inside, outside = classify_scoped_paths("apps/desktop", (
            "apps/desktop/main.py", "apps/desktopish/not-code.py", "README.md", "apps/desktop/sub dir/a.txt", "../evil.txt", ".git/config"
        ))
        self.assertEqual(inside, ("apps/desktop/main.py", "apps/desktop/sub dir/a.txt"))
        self.assertEqual(outside, ("apps/desktopish/not-code.py", "README.md", "../evil.txt", ".git/config"))

    def test_initial_push_review_lists_scope_risks_sizes_and_gitignore_suggestions_without_mutating(self):
        before = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain=v1", "-z"], capture_output=True, text=True, check=True).stdout
        review = build_initial_push_review(self.git, self.root, "apps/desktop", large_file_bytes=100)
        by_path = {item.path: item for item in review.files}
        self.assertIn("apps/desktop/README.md", by_path)
        self.assertTrue(by_path["apps/desktop/README.md"].in_project_scope)
        self.assertFalse(by_path["outside.txt"].in_project_scope)
        self.assertTrue(by_path["apps/desktop/.env"].sensitive_path)
        self.assertTrue(by_path["apps/desktop/config.txt"].secret_signature)
        self.assertTrue(by_path["apps/desktop/bundle.bin"].large_file)
        self.assertEqual(review.gitignore_path, str(self.project / ".gitignore"))
        self.assertFalse(review.gitignore_exists)
        self.assertIn(".env*", review.proposed_gitignore_entries)
        after = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain=v1", "-z"], capture_output=True, text=True, check=True).stdout
        self.assertEqual(before, after, "review must not stage or mutate files")

    def test_review_rejects_non_git_root(self):
        plain = self.base / "plain"
        plain.mkdir()
        with self.assertRaises(RepositoryBindingError):
            build_initial_push_review(self.git, plain, ".")


if __name__ == "__main__":
    unittest.main(verbosity=2)
