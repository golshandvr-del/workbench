"""Tests for aiwb.git.sync (v1.14.5 Safe Git Review & Sync Plan).

Uses real Git repositories with a local bare "remote" so fetch/push/ff and
divergence behave exactly as with GitHub, without network access.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aiwb.git import sync as gs
from aiwb.git.service import GitService

GIT = shutil.which("git")


def _git(cwd: Path, *args: str) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
    r = subprocess.run([GIT, "-C", str(cwd), *args], capture_output=True, text=True, env=env, check=False)
    if r.returncode != 0:
        raise AssertionError(f"git {args} failed: {r.stderr}")
    return r.stdout


class PorcelainV2ParserTests(unittest.TestCase):
    def test_parses_branch_headers_and_all_kinds(self) -> None:
        raw = "\0".join([
            "# branch.oid " + "a" * 40,
            "# branch.head feature/x",
            "# branch.upstream origin/feature/x",
            "# branch.ab +2 -1",
            "1 M. N... 100644 100644 100644 " + "b" * 40 + " " + "c" * 40 + " staged.txt",
            "1 .M N... 100644 100644 100644 " + "b" * 40 + " " + "c" * 40 + " un staged.txt",
            "1 .D N... 100644 100644 000000 " + "b" * 40 + " " + "c" * 40 + " gone.txt",
            "2 R. N... 100644 100644 100644 " + "b" * 40 + " " + "c" * 40 + " R100 new name.txt",
            "old name.txt",
            "u UU N... 100644 100644 100644 100644 " + "b" * 40 + " " + "c" * 40 + " " + "d" * 40 + " both.txt",
            "? new.txt",
            " ? lead",  # malformed -> ignored
            "",
        ])
        branch, entries = gs.parse_porcelain_v2(raw)
        self.assertEqual(branch.branch, "feature/x")
        self.assertEqual(branch.upstream, "origin/feature/x")
        self.assertEqual((branch.ahead, branch.behind, branch.has_upstream_counts), (2, 1, True))
        by_path = {e.path: e for e in entries}
        self.assertEqual(by_path["staged.txt"].labels(), ("staged",))
        self.assertEqual(by_path["un staged.txt"].labels(), ("unstaged",))
        self.assertIn("deleted", by_path["gone.txt"].labels())
        self.assertEqual(by_path["new name.txt"].orig_path, "old name.txt")
        self.assertIn("renamed", by_path["new name.txt"].labels())
        self.assertEqual(by_path["both.txt"].labels(), ("conflict",))
        self.assertEqual(by_path["new.txt"].labels(), ("untracked",))
        self.assertEqual(len(entries), 6)

    def test_initial_and_detached(self) -> None:
        b, _ = gs.parse_porcelain_v2("# branch.oid (initial)\0# branch.head (detached)\0")
        self.assertEqual((b.head_sha, b.branch), ("", ""))


class ClassifyTests(unittest.TestCase):
    def snap(self, *, branch="feature", upstream="origin/feature", ahead=0, behind=0, entries=(), counts=True):
        return gs.ReviewSnapshot(Path("."), gs.BranchInfo("a" * 40, branch, upstream, ahead, behind, counts), tuple(entries))

    def test_decision_table(self) -> None:
        dirty = (gs.ReviewEntry("f", ".", "M", "changed"),)
        conflict = (gs.ReviewEntry("f", "U", "U", "conflict"),)
        cases = [
            (self.snap(), gs.CLEAN, ()),
            (self.snap(ahead=1), gs.LOCAL_AHEAD, ("push",)),
            (self.snap(behind=2), gs.REMOTE_AHEAD, ("fast_forward",)),
            (self.snap(behind=2, entries=dirty), gs.DIRTY, ("commit_selected",)),
            (self.snap(ahead=1, behind=1), gs.DIVERGED, ()),
            (self.snap(entries=conflict, behind=1), gs.CONFLICT, ()),
            (self.snap(upstream="", counts=False), gs.NO_UPSTREAM, ("push",)),
            (self.snap(branch=""), gs.DETACHED, ()),
        ]
        for snap, state, actions in cases:
            with self.subTest(state=state):
                plan = gs.classify_sync_state(snap)
                self.assertEqual(plan.state, state)
                self.assertEqual(plan.allowed_actions, actions)
        self.assertTrue(gs.classify_sync_state(self.snap(ahead=1, behind=1)).manual_options)

    def test_protected_branch_never_allows_push(self) -> None:
        for name in ("main", "Master"):
            plan = gs.classify_sync_state(self.snap(branch=name, upstream="origin/" + name, ahead=3))
            self.assertNotIn("push", plan.allowed_actions)
            self.assertTrue(any("blocked" in w for w in plan.warnings))

    def test_commit_message_trailers_and_validation(self) -> None:
        msg = gs.build_commit_message("Fix parser", task_id="T-12", run_id="run_3", apply_id="")
        self.assertEqual(msg, "Fix parser\n\nWorkbench-Task: T-12\nWorkbench-Run: run_3")
        with self.assertRaises(Exception):
            gs.build_commit_message("   ")
        with self.assertRaises(Exception):
            gs.build_commit_message("x", task_id="bad value\nInjected: y")


@unittest.skipUnless(GIT, "git is unavailable")
class RealRepositorySyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.remote = base / "remote.git"
        self.a = base / "a"
        self.b = base / "b"
        _git(base, "init", "-q", "--bare", "-b", "main", str(self.remote))
        _git(base, "clone", "-q", str(self.remote), str(self.a))
        self._config(self.a)
        (self.a / "base.txt").write_bytes(b"base\n")
        _git(self.a, "add", "base.txt")
        _git(self.a, "commit", "-q", "-m", "base")
        _git(self.a, "push", "-q", "origin", "HEAD:refs/heads/main")
        _git(self.a, "switch", "-q", "-c", "feature")
        _git(self.a, "push", "-q", "-u", "origin", "feature")
        _git(base, "clone", "-q", "-b", "feature", str(self.remote), str(self.b))
        self._config(self.b)
        self.svc = gs.GitSyncService(GitService(), secret_check=lambda root, paths: [p for p in paths if p.endswith(".env")])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _config(self, repo: Path) -> None:
        for k, v in (("user.name", "t"), ("user.email", "t@e"), ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
            _git(repo, "config", k, v)

    def _remote_commit(self, name: str) -> None:
        (self.b / name).write_bytes(name.encode() + b"\n")
        _git(self.b, "add", name)
        _git(self.b, "commit", "-q", "-m", name)
        _git(self.b, "push", "-q", "origin", "feature")

    def test_review_snapshot_classifies_real_changes(self) -> None:
        (self.a / "base.txt").write_bytes(b"changed\n")
        (self.a / "new file.txt").write_bytes(b"n\n")
        (self.a / "staged.txt").write_bytes(b"s\n")
        _git(self.a, "add", "staged.txt")
        snap = self.svc.review_snapshot(self.a)
        labels = {e.path: e.labels() for e in snap.entries}
        self.assertEqual(labels["base.txt"], ("unstaged",))
        self.assertEqual(labels["new file.txt"], ("untracked",))
        self.assertEqual(labels["staged.txt"], ("staged",))
        self.assertIn("changed", self.svc.file_diff(self.a, next(e for e in snap.entries if e.path == "base.txt")))
        _git(self.a, "rm", "-q", "-f", "base.txt")
        self.assertIn("deleted", {e.path: e.labels() for e in self.svc.review_snapshot(self.a).entries}["base.txt"])

    def test_remote_ahead_fast_forward_only_when_clean(self) -> None:
        self._remote_commit("r1.txt")
        plan = self.svc.build_plan(self.a)
        self.assertEqual(plan.state, gs.REMOTE_AHEAD)
        self.assertTrue(plan.fetched)
        ok = self.svc.fast_forward(self.a, plan)
        self.assertTrue(ok.ok, ok.message)
        self.assertTrue((self.a / "r1.txt").exists())
        self.assertEqual(self.svc.build_plan(self.a).state, gs.CLEAN)

    def test_dirty_tree_blocks_fast_forward_without_touching_files(self) -> None:
        self._remote_commit("r1.txt")
        (self.a / "base.txt").write_bytes(b"local edit\n")
        plan = self.svc.build_plan(self.a)
        self.assertEqual(plan.state, gs.DIRTY)
        self.assertFalse(plan.can_fast_forward)
        self.assertFalse(self.svc.fast_forward(self.a, plan).ok)
        self.assertEqual((self.a / "base.txt").read_bytes(), b"local edit\n")
        self.assertFalse((self.a / "r1.txt").exists())

    def test_stale_plan_fast_forward_refused(self) -> None:
        self._remote_commit("r1.txt")
        plan = self.svc.build_plan(self.a)
        (self.a / "base.txt").write_bytes(b"edited after plan\n")
        self.assertFalse(self.svc.fast_forward(self.a, plan).ok)

    def test_diverged_stops_with_manual_options_and_push_rejected(self) -> None:
        self._remote_commit("r1.txt")
        (self.a / "l1.txt").write_bytes(b"l\n")
        _git(self.a, "add", "l1.txt")
        _git(self.a, "commit", "-q", "-m", "l1")
        plan = self.svc.build_plan(self.a)
        self.assertEqual(plan.state, gs.DIVERGED)
        self.assertEqual(plan.allowed_actions, ())
        self.assertGreaterEqual(len(plan.manual_options), 2)
        self.assertFalse(self.svc.safe_push(self.a, plan).ok)

    def test_selected_commit_and_push_with_remote_recheck(self) -> None:
        (self.a / "keep.txt").write_bytes(b"k\n")
        (self.a / "other.txt").write_bytes(b"o\n")
        plan = self.svc.build_plan(self.a)
        msg = gs.build_commit_message("Add keep", task_id="T-1")
        res = self.svc.commit_and_push(self.a, ["keep.txt"], msg, plan)
        self.assertTrue(res.ok, res.message)
        self.assertTrue(res.commit_created)
        files = _git(self.a, "show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(files, ["keep.txt"])
        self.assertIn("Workbench-Task: T-1", _git(self.a, "log", "-1", "--format=%B"))
        self.assertIn("other.txt", {e.path for e in self.svc.review_snapshot(self.a).entries})
        self.assertEqual(_git(self.a, "rev-parse", "HEAD").strip(), _git(self.a, "rev-parse", "origin/feature").strip())

    def test_preexisting_staged_changes_are_never_mixed_in(self) -> None:
        (self.a / "mine.txt").write_bytes(b"m\n")
        (self.a / "theirs.txt").write_bytes(b"t\n")
        _git(self.a, "add", "theirs.txt")
        head = _git(self.a, "rev-parse", "HEAD")
        res = self.svc.commit_selected(self.a, ["mine.txt"], "x")
        self.assertFalse(res.ok)
        self.assertIn("theirs.txt", res.details)
        self.assertEqual(_git(self.a, "rev-parse", "HEAD"), head)

    def test_secret_check_blocks_commit(self) -> None:
        (self.a / "prod.env").write_bytes(b"TOKEN=x\n")
        res = self.svc.commit_selected(self.a, ["prod.env"], "x")
        self.assertFalse(res.ok)
        self.assertIn("best-effort", res.message)

    def test_remote_changed_after_plan_refuses_push(self) -> None:
        (self.a / "l.txt").write_bytes(b"l\n")
        _git(self.a, "add", "l.txt")
        _git(self.a, "commit", "-q", "-m", "l")
        plan = self.svc.build_plan(self.a)
        self.assertEqual(plan.state, gs.LOCAL_AHEAD)
        self._remote_commit("race.txt")   # concurrent remote update after planning
        res = self.svc.safe_push(self.a, plan)
        self.assertFalse(res.ok)
        self.assertIn("changed since the plan", res.message)
        self.assertNotEqual(_git(self.a, "rev-parse", "HEAD").strip(), self.remote_head())

    def test_commit_created_but_push_failed_is_reported_distinctly(self) -> None:
        plan = self.svc.build_plan(self.a)
        self._remote_commit("race.txt")
        (self.a / "x.txt").write_bytes(b"x\n")
        res = self.svc.commit_and_push(self.a, ["x.txt"], "x", plan)
        self.assertFalse(res.ok)
        self.assertTrue(res.commit_created)
        self.assertIn("WAS created, but push failed", res.message)

    def test_push_blocked_on_main(self) -> None:
        _git(self.a, "switch", "-q", "main")
        (self.a / "m.txt").write_bytes(b"m\n")
        _git(self.a, "add", "m.txt")
        _git(self.a, "commit", "-q", "-m", "m")
        plan = self.svc.build_plan(self.a)
        self.assertFalse(plan.can_push)
        forced = gs.SyncPlan(**{**gs._plan_dict(plan), "allowed_actions": ("push",)})
        self.assertIn("blocked", self.svc.safe_push(self.a, forced).message)

    def test_new_branch_without_upstream_first_push(self) -> None:
        _git(self.a, "switch", "-q", "-c", "topic")
        (self.a / "t.txt").write_bytes(b"t\n")
        _git(self.a, "add", "t.txt")
        _git(self.a, "commit", "-q", "-m", "t")
        plan = self.svc.build_plan(self.a)
        self.assertEqual(plan.state, gs.NO_UPSTREAM)
        res = self.svc.safe_push(self.a, plan)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(self.svc.build_plan(self.a).state, gs.CLEAN)

    def remote_head(self) -> str:
        return _git(self.remote, "rev-parse", "refs/heads/feature").strip()


if __name__ == "__main__":
    unittest.main()
