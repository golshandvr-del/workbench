"""Regression tests for the modular local-Git service boundary in v1.14.1."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from aiwb.git import GitCommandError, GitCommandRunner, GitService, GitStatusEntry
from aiwb.git.service import parse_porcelain_v1_z


class PorcelainParsingTests(unittest.TestCase):
    def test_preserves_unicode_whitespace_and_embedded_newline_in_path(self) -> None:
        raw = "??  leading space/نام فایل.txt\0 M line\nbreak.py\0 D deleted file.py\0"
        entries = parse_porcelain_v1_z(raw)
        self.assertEqual(
            [(entry.status, entry.path) for entry in entries],
            [("??", " leading space/نام فایل.txt"), (" M", "line\nbreak.py"), (" D", "deleted file.py")],
        )
        self.assertTrue(entries[0].is_untracked)
        self.assertTrue(entries[2].is_deleted)

    def test_malformed_records_are_ignored(self) -> None:
        self.assertEqual(parse_porcelain_v1_z("\0x\0??\0?? good.txt\0"), (GitStatusEntry("??", "good.txt"),))

    def test_entry_exposes_index_and_worktree_columns(self) -> None:
        entry = GitStatusEntry("M ", "source.py")
        self.assertEqual(entry.index_status, "M")
        self.assertEqual(entry.worktree_status, " ")
        self.assertEqual(entry.as_legacy_tuple(), ("M ", "source.py"))


class GitCommandRunnerTests(unittest.TestCase):
    def test_uses_argv_shell_false_and_disables_terminal_prompt(self) -> None:
        fake_subprocess = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr=""))
        runner = GitCommandRunner(
            executable_provider=lambda: r"C:\Program Files\Git\cmd\git.exe",
            subprocess_runner=fake_subprocess,
            env_provider=lambda: {"EXISTING": "preserved"},
            quiet_kwargs_provider=lambda: {},
        )
        result = runner.run(Path(r"C:\work space\project"), ["status", "--porcelain=v1", "--untracked-files=all", "-z"], timeout=17)
        self.assertEqual(result.returncode, 0)
        command = fake_subprocess.call_args.args[0]
        kwargs = fake_subprocess.call_args.kwargs
        self.assertEqual(command, [r"C:\Program Files\Git\cmd\git.exe", "-C", r"C:\work space\project", "status", "--porcelain=v1", "--untracked-files=all", "-z"])
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["timeout"], 17)
        self.assertEqual(kwargs["env"]["EXISTING"], "preserved")
        self.assertEqual(kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")

    def test_missing_git_is_actionable(self) -> None:
        runner = GitCommandRunner(executable_provider=lambda: None, subprocess_runner=Mock())
        with self.assertRaisesRegex(GitCommandError, "Git was not found"):
            runner.run(Path("."), ["status"])

    def test_rejects_invalid_arguments_and_timeout_before_launch(self) -> None:
        process = Mock()
        runner = GitCommandRunner(executable_provider=lambda: "git", subprocess_runner=process, quiet_kwargs_provider=lambda: {})
        with self.assertRaisesRegex(GitCommandError, "sequence of strings"):
            runner.run(Path("."), "status")  # type: ignore[arg-type]
        with self.assertRaisesRegex(GitCommandError, "NUL"):
            runner.run(Path("."), ["status\0--all"])
        with self.assertRaisesRegex(GitCommandError, "timeout"):
            runner.run(Path("."), ["status"], timeout=0)
        with self.assertRaisesRegex(GitCommandError, "root contains an invalid NUL"):
            runner.run(Path("bad\x00root"), ["status"])
        process.assert_not_called()

    def test_timeout_is_converted_to_service_error(self) -> None:
        def timed_out(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(cmd="git", timeout=4)
        runner = GitCommandRunner(executable_provider=lambda: "git", subprocess_runner=timed_out, quiet_kwargs_provider=lambda: {})
        with self.assertRaisesRegex(GitCommandError, "timed out after 4 seconds"):
            runner.run(Path("."), ["status"], timeout=4)

    def test_version_errors_are_returned_as_redacted_status_text(self) -> None:
        failed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="bad github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890")
        runner = GitCommandRunner(executable_provider=lambda: "git", subprocess_runner=Mock(return_value=failed), quiet_kwargs_provider=lambda: {})
        result = runner.version_text()
        self.assertIn("[REDACTED_SECRET]", result)
        self.assertNotIn("github_pat_", result)


class GitServiceSnapshotTests(unittest.TestCase):
    def test_snapshot_and_legacy_shape_share_the_same_data(self) -> None:
        fake_runner = Mock()
        status_calls = [
            subprocess.CompletedProcess([], 0, "true\n", ""),
            subprocess.CompletedProcess([], 0, "feature/test\n", ""),
            subprocess.CompletedProcess([], 0, "https://user:secret@example.test/repo.git\n", ""),
            subprocess.CompletedProcess([], 0, " M src/main.py\0?? notes.txt\0", ""),
        ]
        fake_runner.run.side_effect = status_calls + status_calls
        service = GitService(runner=fake_runner, redactor=lambda value: value.replace("user:secret@", "[REDACTED]@"))
        snapshot = service.status_snapshot(Path("."))
        self.assertTrue(snapshot.is_repo)
        self.assertEqual(snapshot.branch, "feature/test")
        self.assertEqual(snapshot.remote, "https://[REDACTED]@example.test/repo.git")
        self.assertEqual(snapshot.changed_paths, ("src/main.py", "notes.txt"))
        self.assertEqual(service.status_info(Path(".")), {
            "is_repo": True,
            "branch": "feature/test",
            "remote": "https://[REDACTED]@example.test/repo.git",
            "entries": [(" M", "src/main.py"), ("??", "notes.txt")],
        })

    def test_non_repository_returns_legacy_compatible_status(self) -> None:
        fake_runner = Mock()
        fake_runner.run.return_value = subprocess.CompletedProcess([], 128, "", "not a repo")
        service = GitService(runner=fake_runner)
        self.assertEqual(service.status_info(Path(".")), {
            "is_repo": False,
            "branch": "(not a Git repository)",
            "remote": "(none)",
            "entries": [],
        })


@unittest.skipUnless(os.name != "nt", "The newline-in-filename integration case is POSIX-only.")
class GitIntegrationTests(unittest.TestCase):
    def test_real_git_status_preserves_unicode_and_newline_paths(self) -> None:
        import shutil
        git = shutil.which("git")
        if not git:
            self.skipTest("Git executable is unavailable")
        with tempfile.TemporaryDirectory(prefix="aiwb git service ") as temp:
            root = Path(temp)
            subprocess.run([git, "init", "-q", str(root)], check=True, capture_output=True)
            unicode_dir = root / "sub dir"
            unicode_dir.mkdir()
            (unicode_dir / "فایل.txt").write_text("ok", encoding="utf-8")
            (root / "line\nbreak.py").write_text("print('ok')", encoding="utf-8")
            service = GitService()
            paths = service.changed_paths(root)
            self.assertIn("sub dir/فایل.txt", paths)
            self.assertIn("line\nbreak.py", paths)
            snapshot = service.status_snapshot(root)
            self.assertEqual(set(snapshot.changed_paths), set(paths))


if __name__ == "__main__":
    unittest.main()
