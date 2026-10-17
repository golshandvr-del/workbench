"""Offline regression tests for AI Workbench core logic (no GUI / network required)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import AI_Workbench as wb


class ResponseValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("print('old')\n", encoding="utf-8")
        self.payload = {
            "protocol": wb.PROTOCOL,
            "task_id": "T-1",
            "summary": "update sample",
            "files": [{"path": "src/main.py", "action": "write", "content": "print('new')\n"}],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_response(self) -> None:
        payload, changes = wb.validate_model_response(json.dumps(self.payload), self.root)
        self.assertEqual(payload["task_id"], "T-1")
        self.assertEqual(len(changes), 1)
        self.assertTrue(changes[0].exists)
        self.assertIn("-print('old')", wb.diff_for_change(changes[0]))

    def test_markdown_fence_and_preamble(self) -> None:
        fenced = "```json\n" + json.dumps(self.payload) + "\n```"
        self.assertEqual(wb.parse_model_json(fenced)["protocol"], wb.PROTOCOL)
        noisy = "Here is the result:\n" + json.dumps(self.payload) + "\nDone"
        self.assertEqual(wb.parse_model_json(noisy)["protocol"], wb.PROTOCOL)

    def test_reject_windows_control_characters_in_paths(self) -> None:
        payload = dict(self.payload)
        payload["files"] = [{"path": "src/bad\nname.py", "content": "x"}]
        with self.assertRaisesRegex(wb.WorkbenchError, "Invalid Windows file name"):
            wb.validate_model_response(json.dumps(payload), self.root)

    def test_reject_path_traversal_and_absolute_paths(self) -> None:
        for path in ("../escape.txt", "src/../../escape.txt", "/tmp/escape.txt", "C:/temp/x.txt", "src//main.py"):
            with self.subTest(path=path):
                payload = dict(self.payload)
                payload["files"] = [{"path": path, "content": "x"}]
                with self.assertRaises(wb.WorkbenchError):
                    wb.validate_model_response(json.dumps(payload), self.root)

    def test_reject_commands_or_unknown_fields(self) -> None:
        payload = dict(self.payload)
        payload["commands"] = ["whoami"]
        with self.assertRaises(wb.WorkbenchError):
            wb.validate_model_response(json.dumps(payload), self.root)
        payload = dict(self.payload)
        payload["files"] = [{"path": "src/main.py", "content": "new", "command": "rm -rf"}]
        with self.assertRaises(wb.WorkbenchError):
            wb.validate_model_response(json.dumps(payload), self.root)

    def test_reject_sensitive_files(self) -> None:
        for path in (".env", "secrets/token.json", ".ssh/id_ed25519", "certs/private.pem", ".git/config"):
            with self.subTest(path=path):
                payload = dict(self.payload)
                payload["files"] = [{"path": path, "content": "secret"}]
                with self.assertRaises(wb.WorkbenchError):
                    wb.validate_model_response(json.dumps(payload), self.root)

    def test_reject_symlinks(self) -> None:
        outside = Path(self.temp.name).parent / (Path(self.temp.name).name + "-outside")
        outside.mkdir(exist_ok=True)
        try:
            link = self.root / "link"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable on this platform")
            payload = dict(self.payload)
            payload["files"] = [{"path": "link/pwned.txt", "content": "x"}]
            with self.assertRaises(wb.WorkbenchError):
                wb.validate_model_response(json.dumps(payload), self.root)
        finally:
            try:
                outside.rmdir()
            except OSError:
                pass

    def test_reject_file_directory_collision_in_both_orders(self) -> None:
        for paths in (["bundle", "bundle/main.py"], ["bundle/main.py", "bundle"]):
            payload = dict(self.payload)
            payload["files"] = [{"path": path, "content": "text"} for path in paths]
            with self.subTest(paths=paths), self.assertRaisesRegex(wb.WorkbenchError, "Conflicting file paths"):
                wb.validate_model_response(json.dumps(payload), self.root)

    def test_reject_file_directory_collision_case_insensitively(self) -> None:
        payload = dict(self.payload)
        payload["files"] = [
            {"path": "Bundle/main.py", "content": "child"},
            {"path": "bundle", "content": "parent file"},
        ]
        with self.assertRaisesRegex(wb.WorkbenchError, "Conflicting file paths"):
            wb.validate_model_response(json.dumps(payload), self.root)

    def test_read_prompt_file_revalidates_symlink_parent(self) -> None:
        outside = Path(self.temp.name).parent / (Path(self.temp.name).name + "-prompt-outside")
        outside.mkdir(exist_ok=True)
        (outside / "secret.txt").write_text("SHOULD_NOT_BE_READ", encoding="utf-8")
        original = self.root / "source"
        original.mkdir()
        (original / "context.txt").write_text("innocent", encoding="utf-8")
        moved = self.root / "source-original"
        original.rename(moved)
        try:
            try:
                original.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable on this platform")
            with self.assertRaises(wb.WorkbenchError):
                wb.read_prompt_file(self.root, "source/secret.txt")
        finally:
            try:
                original.unlink()
            except OSError:
                pass
            try:
                (outside / "secret.txt").unlink()
                outside.rmdir()
            except OSError:
                pass

    def test_reject_destination_when_existing_parent_is_a_file(self) -> None:
        (self.root / "src" / "main.py").unlink()
        (self.root / "src").rmdir()
        (self.root / "src").write_text("blocking file", encoding="utf-8")
        payload = dict(self.payload)
        payload["files"] = [{"path": "src/main.py", "content": "print('new')"}]
        with self.assertRaisesRegex(wb.WorkbenchError, "parent component is not a directory"):
            wb.validate_model_response(json.dumps(payload), self.root)

    def test_reject_duplicate_paths_case_insensitive(self) -> None:
        payload = dict(self.payload)
        payload["files"] = [
            {"path": "src/main.py", "content": "A"},
            {"path": "SRC/MAIN.PY", "content": "B"},
        ]
        with self.assertRaises(wb.WorkbenchError):
            wb.validate_model_response(json.dumps(payload), self.root)

    def test_reject_delete_operation(self) -> None:
        payload = dict(self.payload)
        payload["files"] = [{"path": "src/main.py", "action": "delete", "content": ""}]
        with self.assertRaises(wb.WorkbenchError):
            wb.validate_model_response(json.dumps(payload), self.root)


class GeminiAndMarkdownImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_explicit_gemini_blocks_import_multiple_files(self) -> None:
        response = '''Here is the implementation.
<<<AIWB_FILE path="src/main.py" action="write">>>
````python
print("hello")
````
<<<AIWB_END_FILE>>>

<<<AIWB_FILE path="README.md" action="write">>>
````markdown
# Demo
```python
print("example")
```
````
<<<AIWB_END_FILE>>>
'''
        payload, changes, detected = wb.validate_any_model_response(response, self.root)
        self.assertEqual(detected, "AI Workbench file/action blocks")
        self.assertEqual([item.path for item in changes], ["src/main.py", "README.md"])
        self.assertEqual(changes[0].content, 'print("hello")\n')
        self.assertIn("```python", changes[1].content)
        self.assertEqual(payload["protocol"], wb.PROTOCOL)

    def test_explicit_gemini_blocks_accept_reordered_attributes(self) -> None:
        response = '''<<<AIWB_FILE action="write" path="src/main.py">>>
````python
print("Gemini")
````
<<<AIWB_END_FILE>>>'''
        payload, changes, detected = wb.validate_any_model_response(response, self.root)
        self.assertEqual(detected, "AI Workbench file/action blocks")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].path, "src/main.py")
        self.assertEqual(changes[0].content, 'print("Gemini")\n')

    def test_explicit_blocks_reject_absolute_and_traversal_paths(self) -> None:
        for path in ("../outside.py", "C:/outside.py", "/tmp/outside.py"):
            response = f'''<<<AIWB_FILE path="{path}" action="write">>>
````text
hello
````
<<<AIWB_END_FILE>>>'''
            with self.subTest(path=path), self.assertRaises(wb.WorkbenchError):
                wb.validate_any_model_response(response, self.root)

    def test_explicit_blocks_reject_unclosed_and_malformed_markers(self) -> None:
        malformed = '''<<<AIWB_FILE path="src/main.py" action="write">>>
````python
print("hello")
````'''
        with self.assertRaises(wb.WorkbenchError):
            wb.parse_aiwb_file_blocks(malformed)
        with self.assertRaises(wb.WorkbenchError):
            wb.parse_aiwb_file_blocks('<<<AIWB_FILE path=src/main.py>>>')

    def test_markdown_labeled_code_blocks_import(self) -> None:
        response = '''### File: src/main.py
```python
print("main")
```

File: README.md
```markdown
# Demo
```
'''
        payload, changes, detected = wb.validate_any_model_response(response, self.root)
        self.assertEqual(detected, "Labeled Markdown code blocks (best-effort)")
        self.assertEqual([change.path for change in changes], ["src/main.py", "README.md"])
        self.assertIn("labeled Markdown", payload["summary"])

    def test_unnamed_code_fences_are_not_guessed(self) -> None:
        with self.assertRaisesRegex(wb.WorkbenchError, "no reliable filename/path labels"):
            wb.parse_markdown_file_blocks("```python\nprint('unknown')\n```")

    def test_duplicate_paths_in_code_blocks_are_rejected(self) -> None:
        response = '''<<<AIWB_FILE path="src/main.py" action="write">>>
````python
print(1)
````
<<<AIWB_END_FILE>>>
<<<AIWB_FILE path="SRC/MAIN.PY" action="write">>>
````python
print(2)
````
<<<AIWB_END_FILE>>>'''
        with self.assertRaisesRegex(wb.WorkbenchError, "Duplicate path"):
            wb.validate_any_model_response(response, self.root)

    def test_response_format_detection(self) -> None:
        response = '''<<<AIWB_FILE path="src/main.py" action="write">>>
````python
print(1)
````
<<<AIWB_END_FILE>>>'''
        self.assertIn("AI Workbench file/action blocks", wb.detect_model_response_format(response))
        self.assertIn("labeled Markdown", wb.detect_model_response_format("File: main.py\n```python\npass\n```"))

    def test_marker_text_inside_normal_code_block_does_not_switch_protocol(self) -> None:
        markdown = '''File: src/main.py
```python
SENTINEL = "<<<AIWB_FILE path=not-a-real-header>>>"
print(SENTINEL)
```
'''
        _payload, changes, detected = wb.validate_any_model_response(markdown, self.root)
        self.assertEqual(detected, "Labeled Markdown code blocks (best-effort)")
        self.assertIn("not-a-real-header", changes[0].content)

    def test_quoted_path_heading_fallback(self) -> None:
        response = '''Here is the content for `src/main.py`:
```python
print("main")
```'''
        _payload, changes, detected = wb.validate_any_model_response(response, self.root)
        self.assertEqual(detected, "Labeled Markdown code blocks (best-effort)")
        self.assertEqual(changes[0].path, "src/main.py")

    def test_strict_json_autodetection_remains_supported(self) -> None:
        payload = {
            "protocol": wb.PROTOCOL,
            "task_id": "JSON-1",
            "summary": "demo",
            "files": [{"path": "src/main.py", "action": "write", "content": "print('json')\n"}],
        }
        _data, changes, detected = wb.validate_any_model_response(json.dumps(payload), self.root)
        self.assertEqual(detected, "workbench-v1 JSON")
        self.assertEqual(changes[0].path, "src/main.py")


class ZipArtifactImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "workspace"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_zip(self, entries: list[tuple[str, bytes | str]], name: str = "model-artifact.zip") -> Path:
        archive_path = self.base / name
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, content in entries:
                archive.writestr(path, content.encode("utf-8") if isinstance(content, str) else content)
        return archive_path

    def test_plain_gpt_zip_becomes_reviewable_text_changes_without_extracting(self) -> None:
        archive = self.make_zip([
            ("README.md", "# Example\n\nRun `python src/main.py`."),
            ("src/main.py", "print('zip-import-ok')\n"),
        ])
        payload, changes, source = wb.parse_model_zip_archive(archive, self.root)
        self.assertEqual([item.path for item in changes], ["README.md", "src/main.py"])
        self.assertEqual(payload["protocol"], wb.PROTOCOL)
        self.assertIn("ZIP artifact", payload["summary"])
        self.assertEqual(source["filename"], archive.name)
        self.assertEqual(len(source["sha256"]), 64)
        self.assertFalse((self.root / "README.md").exists(), "ZIP import must preview only; it must not extract/write files")

    def test_zip_control_manifest_queues_actions_but_is_not_written_as_project_file(self) -> None:
        control = {
            "protocol": wb.PROTOCOL_V2,
            "task_id": "zip-with-actions",
            "summary": "Project plus reviewed tests",
            "actions": [{"id": "unit-tests", "purpose": "Run unit tests", "command": "python -m unittest", "working_directory": ".", "timeout_seconds": 120}],
            "next_steps": ["Review the test output"],
            "completion_status": "in_progress",
        }
        archive = self.make_zip([
            ("AIWB_RESPONSE.json", json.dumps(control)),
            ("README.md", "# Example"),
            ("main.py", "print('ok')"),
        ])
        payload, changes, source = wb.parse_model_zip_archive(archive, self.root)
        self.assertEqual(payload["protocol"], wb.PROTOCOL_V2)
        self.assertEqual([item.path for item in changes], ["README.md", "main.py"])
        self.assertEqual(payload["actions"][0]["id"], "unit-tests")
        self.assertEqual(payload["next_steps"], ["Review the test output"])
        self.assertTrue(source["control_manifest_present"])
        self.assertNotIn("AIWB_RESPONSE.json", [item.path for item in changes])

    def test_zip_without_root_readme_is_imported_with_visible_review_warning(self) -> None:
        archive = self.make_zip([("src/main.py", "print('no-readme')\n")])
        payload, changes, source = wb.parse_model_zip_archive(archive, self.root)
        self.assertEqual([item.path for item in changes], ["src/main.py"])
        self.assertTrue(source["missing_root_readme"])
        self.assertIn("REVIEW WARNING", payload["summary"])

    def test_zip_readme_warning_survives_max_length_model_summary(self) -> None:
        control = {
            "protocol": wb.PROTOCOL_V2, "task_id": "long-summary", "summary": "S" * 2000,
            "actions": [], "next_steps": [], "completion_status": "in_progress",
        }
        archive = self.make_zip([
            ("AIWB_RESPONSE.json", json.dumps(control)),
            ("main.py", "print('ok')"),
        ])
        payload, _changes, source = wb.parse_model_zip_archive(archive, self.root)
        self.assertEqual(len(payload["summary"]), 2000)
        self.assertIn("REVIEW WARNING", payload["summary"])
        self.assertTrue(source["missing_root_readme"])

    def test_zip_rejects_path_traversal(self) -> None:
        archive = self.make_zip([("../escaped.txt", "do not write")])
        with self.assertRaises(wb.WorkbenchError):
            wb.parse_model_zip_archive(archive, self.root)
        self.assertFalse((self.base / "escaped.txt").exists())

    def test_zip_rejects_sensitive_paths(self) -> None:
        archive = self.make_zip([(".env", "SECRET=not-for-import")])
        with self.assertRaisesRegex(wb.WorkbenchError, "sensitive"):
            wb.parse_model_zip_archive(archive, self.root)

    def test_zip_rejects_symlink_entries(self) -> None:
        archive_path = self.base / "linked.zip"
        item = zipfile.ZipInfo("linked.py")
        item.create_system = 3
        item.external_attr = (0o120777 << 16)
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(item, "outside.py")
        with self.assertRaisesRegex(wb.WorkbenchError, "Links and special"):
            wb.parse_model_zip_archive(archive_path, self.root)

    def test_zip_binary_artifact_is_retained_as_bytes_for_review_and_apply(self) -> None:
        png = bytes([0x89]) + b"PNG\r\n\x1a\n\x00\x01\x02"
        archive = self.make_zip([("icon.png", png)])
        payload, changes, source = wb.parse_model_zip_archive(archive, self.root)
        self.assertEqual(payload["protocol"], wb.PROTOCOL_V2)
        self.assertEqual(len(changes), 1)
        self.assertIsInstance(changes[0].content, bytes)
        self.assertEqual(changes[0].content, png)
        self.assertEqual(source["binary_files_imported"], 1)
        self.assertIn("no text diff is fabricated", wb.diff_for_change(changes[0]))
        self.assertFalse((self.root / "icon.png").exists(), "Import must remain preview-only")
        wb.apply_changes_transactionally(self.root, changes)
        self.assertEqual((self.root / "icon.png").read_bytes(), png)

    def test_zip_text_and_binary_share_path_collision_checks(self) -> None:
        archive = self.make_zip([("src", "text file"), ("src/main.png", b"\x89PNG\x00")])
        with self.assertRaisesRegex(wb.WorkbenchError, "collision"):
            wb.parse_model_zip_archive(archive, self.root)

    def test_zip_rejects_case_insensitive_duplicate_paths(self) -> None:
        archive_path = self.base / "duplicates.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("Readme.md", "one")
            archive.writestr("README.MD", "two")
        with self.assertRaisesRegex(wb.WorkbenchError, "duplicate paths"):
            wb.parse_model_zip_archive(archive_path, self.root)

    def test_zip_rejects_invalid_control_manifest(self) -> None:
        control = {"protocol": wb.PROTOCOL_V2, "files": [{"path": "evil", "content": "x"}], "actions": []}
        archive = self.make_zip([("AIWB_RESPONSE.json", json.dumps(control)), ("README.md", "# Demo")])
        with self.assertRaisesRegex(wb.WorkbenchError, "Unknown fields"):
            wb.parse_model_zip_archive(archive, self.root)



class ApplyTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        (self.root / "a.txt").write_text("old\n", encoding="utf-8")
        self.data = Path(self.temp.name) / "appdata"
        self.env_patcher = patch.dict(os.environ, {"LOCALAPPDATA": str(self.data)})
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()
        self.temp.cleanup()

    def make_changes(self, items: list[dict[str, str]]) -> list[wb.FileChange]:
        payload = {"protocol": wb.PROTOCOL, "files": items}
        _data, changes = wb.validate_model_response(json.dumps(payload), self.root)
        return changes

    def test_apply_creates_backup_and_writes_files(self) -> None:
        changes = self.make_changes([
            {"path": "a.txt", "content": "new\n"},
            {"path": "folder/b.txt", "content": "created\n"},
        ])
        backup_dir = wb.apply_changes_transactionally(self.root, changes)
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"), "new\n")
        self.assertEqual((self.root / "folder" / "b.txt").read_text(encoding="utf-8"), "created\n")
        self.assertEqual((backup_dir / "a.txt").read_text(encoding="utf-8"), "old\n")
        manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["files"]), 2)
        tx_manifest = json.loads((backup_dir / "aiwb-apply-transaction.json").read_text(encoding="utf-8"))
        self.assertEqual(tx_manifest["kind"], "apply")
        self.assertEqual(len(tx_manifest["transaction_id"]), 32)
        self.assertEqual({item["path"] for item in tx_manifest["files"]}, {"a.txt", "folder/b.txt"})
        self.assertEqual(len(tx_manifest["files"][0]["after_sha256"]), 64)

    def test_selective_apply_filter_only_returns_selected_paths(self) -> None:
        changes = self.make_changes([
            {"path": "a.txt", "content": "new\n"},
            {"path": "b.txt", "content": "create\n"},
        ])
        selected = wb.filter_selected_changes(changes, {"b.txt"})
        self.assertEqual([item.path for item in selected], ["b.txt"])
        self.assertEqual(len(changes), 2, "Filtering must not mutate the validated preview list")
        with self.assertRaisesRegex(wb.WorkbenchError, "do not belong"):
            wb.filter_selected_changes(changes, {"not-in-preview.txt"})

    def test_stale_preview_is_rejected(self) -> None:
        changes = self.make_changes([{ "path": "a.txt", "content": "new\n" }])
        (self.root / "a.txt").write_text("changed after preview\n", encoding="utf-8")
        with self.assertRaises(wb.WorkbenchError):
            wb.apply_changes_transactionally(self.root, changes)
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"), "changed after preview\n")

    def test_existing_binary_file_rejected(self) -> None:
        (self.root / "binary.bin").write_bytes(b"\xff\x00")
        with self.assertRaises(wb.WorkbenchError):
            self.make_changes([{ "path": "binary.bin", "content": "text" }])


class SafetyAndGitParsingTests(unittest.TestCase):
    def test_context_ignore_rules_and_negation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/".gitignore").write_text("build/\n*.log\n!keep.log\n",encoding="utf-8")
            self.assertIn(".gitignore", wb.context_ignore_reason(root,"build/output.py"))
            self.assertIn(".gitignore", wb.context_ignore_reason(root,"debug.log"))
            self.assertIsNone(wb.context_ignore_reason(root,"keep.log"))
            self.assertIsNone(wb.context_ignore_reason(root,"src/main.py"))

    def test_sensitive_path_cases(self) -> None:
        self.assertTrue(wb.is_sensitive_path(".env"))
        self.assertTrue(wb.is_sensitive_path("keys/private.pem"))
        self.assertTrue(wb.is_sensitive_path("secrets/prod.json"))
        self.assertFalse(wb.is_sensitive_path(".env.example"))
        self.assertFalse(wb.is_sensitive_path("src/auth.py"))

    def test_detects_secrets(self) -> None:
        self.assertTrue(wb.scan_for_secrets("token = github_pat_" + "a" * 35))
        self.assertTrue(wb.scan_for_secrets("-----BEGIN RSA PRIVATE KEY-----"))
        self.assertEqual(wb.scan_for_secrets("API_KEY=YOUR_API_KEY_HERE"), [])

    def test_git_porcelain_parse(self) -> None:
        parsed = wb.parse_git_status_porcelain(" M src/main.py\0?? new file.txt\0A  hello.py\0")
        self.assertEqual(parsed, [(" M", "src/main.py"), ("??", "new file.txt"), ("A ", "hello.py")])

    def test_remote_redaction(self) -> None:
        self.assertNotIn("topsecret", wb.redact("https://user:topsecret@github.com/owner/repo.git"))
        self.assertIn("[REDACTED_SECRET]", wb.redact("github_pat_" + "a" * 40))

    def test_bounded_command_output(self) -> None:
        import subprocess
        command = subprocess.list2cmdline([__import__("sys").executable, "-c", "print('Z' * 800000)"])
        with tempfile.TemporaryDirectory() as temp:
            result = wb.run_shell_command_bounded(command, Path(temp), timeout=20, max_output_chars=10000)
        self.assertEqual(result["exit_code"], 0)
        self.assertLessEqual(len(result["output"]), 10000 + 100)
        self.assertIn("truncated", result["output"])

    def test_command_timeout(self) -> None:
        import subprocess
        command = subprocess.list2cmdline([__import__("sys").executable, "-c", "import time; time.sleep(10)"])
        with tempfile.TemporaryDirectory() as temp:
            result = wb.run_shell_command_bounded(command, Path(temp), timeout=0.2, max_output_chars=1000)
        self.assertTrue(result["timed_out"])

    def test_git_changed_paths_preserves_leading_space(self) -> None:
        if not __import__("shutil").which("git"):
            self.skipTest("git is unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess = __import__("subprocess")
            subprocess.run(["git", "init", str(root)], capture_output=True, check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "tester@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Workbench Test"], check=True)
            (root / "tracked.txt").write_text("first\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-m", "init"], capture_output=True, check=True)
            (root / " leading name.txt").write_text("new\n", encoding="utf-8")
            changed = wb.git_changed_paths(root)
            self.assertIn(" leading name.txt", changed)

    def test_git_status_and_staged_secret_scan(self) -> None:
        if not __import__("shutil").which("git"):
            self.skipTest("git is unavailable")
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", str(root)], capture_output=True, check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "tester@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Workbench Test"], check=True)
            (root / "code.py").write_text("print('ok')\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "code.py"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-m", "init"], capture_output=True, check=True)
            (root / "code.py").write_text("print('changed')\n", encoding="utf-8")
            info = wb.git_status_info(root)
            self.assertTrue(info["is_repo"])
            self.assertEqual(info["entries"][0][1], "code.py")
            subprocess.run(["git", "-C", str(root), "add", "code.py"], check=True)
            self.assertEqual(wb.scan_staged_blobs(root, ["code.py"]), [])
            secret = "github_pat_" + "Q" * 40
            (root / "leak.py").write_text(f"TOKEN = '{secret}'\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "leak.py"], check=True)
            self.assertTrue(wb.scan_staged_blobs(root, ["leak.py"]))


class ResponseDeliveryPolicyTests(unittest.TestCase):
    def test_delivery_policy_preserves_gpt_zip_transport(self) -> None:
        rule = wb.response_delivery_rule(wb.OUTPUT_FORMAT_GPT_ZIP)
        self.assertIn("real downloadable ZIP", rule)
        self.assertIn("AIWB_RESPONSE.json", rule)
        self.assertIn("strict workbench-v3 JSON", rule)
        self.assertIn("workbench-v2 remains supported for write-only text responses", rule)

    def test_delivery_policy_preserves_gemini_blocks(self) -> None:
        rule = wb.response_delivery_rule(wb.OUTPUT_FORMAT_GEMINI)
        self.assertIn("<<<AIWB_FILE", rule)
        self.assertIn("<<<AIWB_COMMAND", rule)
        self.assertNotIn("downloadable ZIP", rule)

    def test_delivery_policy_falls_back_to_strict_json(self) -> None:
        rule = wb.response_delivery_rule(wb.OUTPUT_FORMAT_JSON)
        self.assertIn('protocol "workbench-v3"', rule)
        self.assertIn("typed `operations`", rule)
        self.assertNotIn("AIWB_FILE", rule)

    def test_repair_prompt_uses_gpt_zip_when_that_transport_was_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wb.save_task_state(root, {"task_text": "Build a multi-file engineering tool", "last_output_format": wb.OUTPUT_FORMAT_GPT_ZIP})
            prompt = wb.build_repair_prompt(root, error="ZIP import failed", failure_stage="import")
            self.assertIn("real downloadable ZIP", prompt)
            self.assertIn("AIWB_RESPONSE.json", prompt)
            self.assertIn("ZIP import failed", prompt)

    def test_continuation_handoff_keeps_gpt_zip_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wb.save_task_state(root, {
                "task_text": "Continue the engineering tool", "last_output_format": wb.OUTPUT_FORMAT_GPT_ZIP,
                "latest_response_format": "GPT ZIP artifact package",
            })
            handoff = wb.build_continuation_handoff_text(root)
            self.assertIn("Required response delivery contract", handoff)
            self.assertIn("real downloadable ZIP", handoff)
            self.assertIn("AIWB_RESPONSE.json", handoff)


class PromptEngineeringTests(unittest.TestCase):
    def test_new_project_prompt_includes_profile_and_complete_deliverable_policy(self) -> None:
        profile = dict(wb.DEFAULT_PROJECT_PROFILE)
        profile.update({
            "target_platform": "Windows desktop",
            "languages": "Python",
            "gui_framework": "PySide6 (Qt)",
            "target_ui_language": "English",
            "packaging": "Windows installer (EXE/MSI) build setup",
        })
        prompt = wb.build_prompt_document(
            task="Build a Smith chart application",
            project_files=[],
            context_files=[],
            omitted_context=[],
            profile=profile,
            configured_project_mode="Auto-detect",
            task_type="Build a new project",
            prompt_stage="Implementation / build",
        )
        self.assertIn("Project state", prompt)
        self.assertIn("Windows desktop", prompt)
        self.assertIn("PySide6 (Qt)", prompt)
        self.assertIn("workbench-v2", prompt)
        self.assertIn("complete final UTF-8 text", prompt)
        self.assertIn("MINIMIZE INTERRUPTIONS", prompt)
        self.assertIn("actions", prompt)
        self.assertIn("Windows installer (EXE/MSI) build setup", prompt)
        self.assertNotIn("D:\\", prompt)
        self.assertIn("New project", prompt)

    def test_existing_project_without_context_warns_against_guessing(self) -> None:
        prompt = wb.build_prompt_document(
            task="Implement authentication",
            project_files=[("src/auth.py", 500), ("README.md", 100)],
            context_files=[],
            omitted_context=[],
            profile=dict(wb.DEFAULT_PROJECT_PROFILE),
            configured_project_mode="Existing project",
            task_type="Implement a feature",
            prompt_stage="Implementation / build",
        )
        self.assertIn("No file contents have been supplied", prompt)
        self.assertIn("workbench-plan-v2", prompt)
        self.assertIn('"requested_context_files"', prompt)
        self.assertIn('"requested_user_uploads"', prompt)
        self.assertIn("This rule overrides JSON, ZIP, and Gemini delivery instructions", prompt)
        self.assertNotIn('"protocol": "workbench-plan-v1"', prompt)
        self.assertIn("src/auth.py", prompt)

    def test_context_request_prompt_uses_plan_protocol_and_exact_paths(self) -> None:
        prompt = wb.build_prompt_document(
            task="Add settings persistence",
            project_files=[("src/app.py", 100), ("pyproject.toml", 200)],
            context_files=[],
            omitted_context=[],
            profile=dict(wb.DEFAULT_PROJECT_PROFILE),
            configured_project_mode="Existing project",
            task_type="Implement a feature",
            prompt_stage="Request exact context files",
        )
        self.assertIn('"protocol": "workbench-plan-v2"', prompt)
        self.assertIn("Only request paths that appear in the visible file tree", prompt)
        self.assertIn("requested_context_files", prompt)

    def test_context_plan_override_uses_one_canonical_schema_across_stages_and_transports(self) -> None:
        cases = [
            ("Request exact context files", wb.OUTPUT_FORMAT_JSON),
            ("Architecture + file manifest plan", wb.OUTPUT_FORMAT_JSON),
            ("Implementation / build", wb.OUTPUT_FORMAT_JSON),
            ("Implementation / build", wb.OUTPUT_FORMAT_GPT_ZIP),
            ("Implementation / build", wb.OUTPUT_FORMAT_GEMINI),
        ]
        for stage, output_format in cases:
            with self.subTest(stage=stage, output_format=output_format):
                prompt = wb.build_prompt_document(
                    task="Change existing installer safely", project_files=[("installer/setup.py", 500)],
                    context_files=[], omitted_context=[], profile=dict(wb.DEFAULT_PROJECT_PROFILE),
                    configured_project_mode="Existing project", task_type="Implement a feature",
                    prompt_stage=stage, output_format=output_format,
                )
                self.assertIn('"protocol": "workbench-plan-v2"', prompt)
                self.assertIn('"requested_context_files"', prompt)
                self.assertIn('"requested_user_uploads"', prompt)
                self.assertIn('"completion_status": "blocked"', prompt)
                self.assertIn("This rule overrides JSON, ZIP, and Gemini delivery instructions", prompt)
                self.assertIn("Do not use legacy `requests`, `request`, or `manual_attachments`", prompt)

    def test_repair_prompt_reuses_the_same_context_plan_contract(self) -> None:
        with tempfile.TemporaryDirectory() as local:
            root = Path(local)
            wb.write_project_json(root, "project.json", {"last_task": "Update installer"})
            prompt = wb.build_repair_prompt(root, error="Unknown top-level keys in context plan: request")
            self.assertIn('"protocol": "workbench-plan-v2"', prompt)
            self.assertIn('"requested_context_files"', prompt)
            self.assertIn("legacy workbench-plan-v1", prompt)

    def test_diagnostic_error_override_is_not_duplicated(self) -> None:
        message = "This is a context plan, not an implementation response."
        report = {"errors": [message], "success": False}
        wb.merge_import_diagnostic_error(report, message)
        self.assertEqual(report["errors"], [message])
        wb.merge_import_diagnostic_error(report, "New outer error")
        self.assertEqual(report["errors"], ["New outer error", message])

    def test_gpt_zip_prompt_requires_archive_manifest_and_usage_guide(self) -> None:
        prompt = wb.build_prompt_document(
            task="Build a small multi-file desktop utility",
            project_files=[], context_files=[], omitted_context=[],
            profile=dict(wb.DEFAULT_PROJECT_PROFILE), configured_project_mode="New project",
            task_type="Build a new project", prompt_stage="Implementation / build",
            output_format=wb.OUTPUT_FORMAT_GPT_ZIP,
            capability_manifest=wb.build_capability_manifest(self.root if hasattr(self, "root") else None, wb.OUTPUT_FORMAT_GPT_ZIP),
        )
        self.assertIn("downloadable ZIP", prompt)
        self.assertIn("AIWB_RESPONSE.json", prompt)
        self.assertIn("README.md", prompt)
        self.assertIn("file/directory map", prompt)
        self.assertIn("Never claim a ZIP attachment exists", prompt)
        self.assertIn("structured JSON fallback", prompt)

    def test_gemini_prompt_requires_named_complete_file_blocks(self) -> None:
        prompt = wb.build_prompt_document(
            task="Build a Windows GUI app",
            project_files=[],
            context_files=[],
            omitted_context=[],
            profile=dict(wb.DEFAULT_PROJECT_PROFILE),
            configured_project_mode="New project",
            task_type="Build a new project",
            prompt_stage="Implementation / build",
            output_format=wb.OUTPUT_FORMAT_GEMINI,
        )
        self.assertIn("workbench-files-v1", prompt)
        self.assertIn('<<<AIWB_FILE path="src/relative/path.ext" action="write" body="raw">>>', prompt)
        self.assertIn("complete final UTF-8 text content", prompt)
        self.assertIn("unlabeled code blocks", prompt)
        self.assertNotIn('"protocol": "workbench-v1"', prompt)

    def test_planning_prompt_stays_json_even_when_gemini_blocks_selected(self) -> None:
        prompt = wb.build_prompt_document(
            task="Plan a new app",
            project_files=[],
            context_files=[],
            omitted_context=[],
            profile=dict(wb.DEFAULT_PROJECT_PROFILE),
            configured_project_mode="New project",
            task_type="Build a new project",
            prompt_stage="Architecture + file manifest plan",
            output_format=wb.OUTPUT_FORMAT_GEMINI,
        )
        self.assertIn('"protocol": "workbench-plan-v2"', prompt)
        self.assertNotIn("workbench-files-v1 (Gemini direct-code mode)", prompt)
        self.assertIn("Selected output contract: Strict JSON manifest", prompt)

    def test_recommended_context_prefers_readme_manifest_and_relevant_source(self) -> None:
        files = [
            ("README.md", 200),
            ("pyproject.toml", 100),
            ("src/smith_chart.py", 300),
            ("src/unrelated_util.py", 200),
            (".env", 60),
        ]
        selected = wb.recommend_context_paths(files, "Smith chart UI and impedance calculation")
        self.assertIn("README.md", selected)
        self.assertIn("pyproject.toml", selected)
        self.assertIn("src/smith_chart.py", selected)
        self.assertNotIn(".env", selected)

    def test_auto_project_mode_detects_empty_workspace(self) -> None:
        self.assertEqual(wb.effective_project_mode("Auto-detect", []), "New project")
        self.assertEqual(wb.effective_project_mode("Auto-detect", [("main.py", 20)]), "Existing project")
        self.assertEqual(wb.effective_project_mode("Existing project", []), "Existing project")


class ModelActionQueueAndContinuationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_workbench_v2_accepts_file_and_batched_actions(self) -> None:
        payload = {
            "protocol": wb.PROTOCOL_V2,
            "task_id": "BATCH-1",
            "summary": "Implement the feature and run the complete predictable test suite.",
            "files": [{"path": "main.py", "action": "write", "content": "print('ready')\n"}],
            "actions": [
                {"id": "unit-tests", "purpose": "Run unit tests", "command": "python -m unittest", "working_directory": ".", "timeout_seconds": 90},
                {"id": "compile", "purpose": "Check syntax", "command": "python -m py_compile main.py", "working_directory": ".", "timeout_seconds": 30},
            ],
            "next_steps": ["Review actual test results."],
            "completion_status": "in_progress",
        }
        normalized, changes = wb.validate_model_response(json.dumps(payload), self.root)
        self.assertEqual(normalized["protocol"], wb.PROTOCOL_V2)
        self.assertEqual(len(changes), 1)
        self.assertEqual([item["id"] for item in normalized["actions"]], ["unit-tests", "compile"])
        self.assertFalse(any(";" in item["command"] for item in normalized["actions"]))

    def test_v2_action_only_response_is_supported(self) -> None:
        command = f'"{sys.executable}" -c "print(42)"'
        payload = {
            "protocol": wb.PROTOCOL_V2,
            "task_id": "ACTIONS-ONLY",
            "summary": "Run the existing tests and report evidence.",
            "files": [],
            "actions": [{"id": "tests", "purpose": "Run unit tests", "command": command, "timeout_seconds": 30}],
            "next_steps": [],
            "completion_status": "in_progress",
        }
        normalized, changes = wb.validate_model_response(json.dumps(payload), self.root)
        self.assertEqual(changes, [])
        self.assertEqual(len(normalized["actions"]), 1)

    def test_action_shell_chaining_and_dangerous_command_rejected(self) -> None:
        cases = [
            "python -m unittest && python build.py",
            "python -m unittest | more",
            "git reset --hard",
            "rm -rf .",
        ]
        for command in cases:
            payload = {
                "protocol": wb.PROTOCOL_V2, "task_id": "BAD", "summary": "test", "files": [],
                "actions": [{"id": "test", "purpose": "Run a command", "command": command}],
                "next_steps": [], "completion_status": "in_progress",
            }
            with self.subTest(command=command), self.assertRaises(wb.WorkbenchError):
                wb.validate_model_response(json.dumps(payload), self.root)

    def test_gemini_action_blocks_parse_without_executing(self) -> None:
        response = '''<<<AIWB_COMMAND id="unit-tests" timeout_seconds="60" working_directory=".">>>
Purpose: Run project unit tests
````powershell
python -m unittest
````
<<<AIWB_END_COMMAND>>>'''
        payload, changes, detected = wb.validate_any_model_response(response, self.root)
        self.assertEqual(changes, [])
        self.assertIn("file/action blocks", detected)
        self.assertEqual(payload["actions"][0]["command"], "python -m unittest")
        self.assertNotIn("status", payload["actions"][0])

    def test_response_snapshot_records_exact_content_hash(self) -> None:
        content = "def answer():\n    return 42\n"
        payload = {
            "protocol": wb.PROTOCOL_V2, "task_id": "SNAP-1", "summary": "Add answer",
            "files": [{"path": "src/answer.py", "action": "write", "content": content}],
            "actions": [], "next_steps": [], "completion_status": "in_progress",
        }
        result = wb.save_model_response_snapshot(self.root, payload, "test format")
        snapshot = wb.read_project_json(self.root, "latest_model_response.json", {})
        self.assertEqual(snapshot["response_sha256"], result["sha256"])
        self.assertEqual(snapshot["payload"]["files"][0]["content"], content)
        self.assertEqual(snapshot["file_manifest"][0]["sha256"], __import__("hashlib").sha256(content.encode()).hexdigest())

    def test_execute_queued_actions_persists_actual_output_and_exit_code(self) -> None:
        command = f'"{sys.executable}" -c "print(42042)"'
        action = {
            "queue_id": "queue-1", "source_task_id": "RUN-1", "id": "print-result",
            "purpose": "Emit a result for the continuation handoff",
            "command": command, "working_directory": ".", "timeout_seconds": 30,
            "review_flags": [], "status": "Pending",
        }
        wb.save_action_queue(self.root, [action])
        result = wb.execute_queued_actions(self.root, ["queue-1"])
        self.assertEqual(result["results"][0]["status"], "Passed")
        self.assertEqual(result["results"][0]["exit_code"], 0)
        self.assertIn("42042", result["results"][0]["output"])
        reloaded = wb.load_action_queue(self.root)
        self.assertEqual(reloaded[0]["status"], "Passed")
        events = wb.read_execution_history(self.root)
        finished = [item for item in events if item.get("type") == "action_finished"]
        self.assertTrue(finished)
        self.assertIn("42042", finished[-1]["output"])

    def test_continuation_handoff_contains_actual_output_and_optional_exact_contents(self) -> None:
        content = "print('known-state')\n"
        (self.root / "main.py").write_text(content, encoding="utf-8")
        payload = {
            "protocol": wb.PROTOCOL_V2, "task_id": "HANDOFF-1", "summary": "Create main.py",
            "files": [{"path": "main.py", "action": "write", "content": content}],
            "actions": [], "next_steps": ["Check the recorded result."], "completion_status": "in_progress",
        }
        wb.save_model_response_snapshot(self.root, payload, "test format")
        wb.save_task_state(self.root, {
            "task_id": "HANDOFF-1", "task_text": "Create a small script", "latest_response_summary": "Create main.py",
            "latest_response_format": "test format", "latest_response_file_paths": ["main.py"],
            "last_applied_files": ["main.py"], "completion_status": "in_progress",
            "latest_response_snapshot_path": ".workbench/latest_model_response.json",
        })
        wb.append_execution_event(self.root, {
            "type": "action_finished", "action_id": "unit-tests", "status": "Failed", "exit_code": 1,
            "command": "python -m unittest", "output": "AssertionError: expected 42", "elapsed": 0.4,
        })
        handoff = wb.build_continuation_handoff_text(self.root)
        self.assertIn("Create a small script", handoff)
        self.assertIn("AssertionError: expected 42", handoff)
        self.assertIn("proposed_sha256", handoff)
        self.assertIn("current file matches model output", handoff)
        full = wb.build_continuation_handoff_text(self.root, include_response_contents=True)
        self.assertIn("print('known-state')", full)

    def test_git_per_user_install_path_is_found_when_not_in_path(self) -> None:
        with tempfile.TemporaryDirectory() as local:
            fake_git = Path(local) / "Programs" / "Git" / "cmd" / "git.exe"
            fake_git.parent.mkdir(parents=True)
            fake_git.write_text("", encoding="utf-8")
            env = {"LOCALAPPDATA": local, "ProgramFiles": "", "ProgramW6432": ""}
            with patch.object(wb.shutil, "which", return_value=None), patch.dict(os.environ, env):
                self.assertEqual(wb.find_git_executable(), str(fake_git))


class ContextPlanValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_context_plan_and_deduplication(self) -> None:
        plan = {
            "protocol": "workbench-plan-v1",
            "task_id": "PLAN-1",
            "summary": "Need the entry point before safely changing the UI.",
            "requested_context_files": [
                {"path": "src/main.py", "reason": "Understand application startup."},
                {"path": "src/main.py", "reason": "Duplicate request."},
            ],
            "proposed_files": [{"path": "src/ui.py", "action": "create", "purpose": "UI module."}],
            "external_requirements": [],
            "clarifying_questions": [],
            "assumptions": [],
        }
        validated = wb.validate_context_plan(json.dumps(plan), self.root)
        self.assertEqual(len(validated["requested_context_files"]), 1)
        self.assertEqual(validated["requested_context_files"][0]["path"], "src/main.py")

    def test_context_plan_rejects_traversal_and_secrets(self) -> None:
        for unsafe_path in ("../outside.py", ".env", "secrets/key.json", "C:/private.txt"):
            with self.subTest(path=unsafe_path):
                plan = {
                    "protocol": "workbench-plan-v1", "summary": "", "requested_context_files": [{"path": unsafe_path, "reason": "test"}],
                    "proposed_files": [], "external_requirements": [], "clarifying_questions": [], "assumptions": [],
                }
                with self.assertRaises(wb.WorkbenchError):
                    wb.validate_context_plan(json.dumps(plan), self.root)

    def test_context_plan_rejects_unknown_keys(self) -> None:
        plan = {
            "protocol": "workbench-plan-v1", "summary": "", "requested_context_files": [],
            "proposed_files": [], "external_requirements": [], "clarifying_questions": [], "assumptions": [], "run_command": "dangerous",
        }
        with self.assertRaises(wb.WorkbenchError):
            wb.validate_context_plan(json.dumps(plan), self.root)

    def test_canonical_v2_context_plan_accepts_all_optional_metadata(self) -> None:
        plan = {
            "protocol": "workbench-plan-v2", "task_id": "plan-v2", "summary": "Need two sources.",
            "requested_context_files": [{"path": "src/main.py", "reason": "Entry point."}],
            "requested_context_ranges": [], "requested_user_uploads": [], "requested_project_history": [],
            "proposed_files": [{"path": "src/config.py", "action": "create", "purpose": "Config module."}],
            "external_requirements": [], "clarifying_questions": [], "assumptions": [],
            "next_steps": ["Review the selected source"], "completion_status": "blocked",
        }
        validated = wb.validate_context_plan(json.dumps(plan), self.root)
        self.assertEqual(validated["protocol"], "workbench-plan-v2")
        self.assertEqual(validated["requested_context_files"][0]["path"], "src/main.py")
        self.assertEqual(validated["next_steps"], ["Review the selected source"])
        self.assertEqual(validated["completion_status"], "blocked")

    def test_ambiguous_legacy_proposed_action_becomes_review_only(self) -> None:
        plan = {
            "protocol": "workbench-plan-v1", "proposed_files": [
                {"path": "src/config.py", "action": "create or modify", "purpose": "Config file."}
            ]
        }
        validated = wb.validate_context_plan(json.dumps(plan), self.root)
        self.assertEqual(validated["proposed_files"][0]["action"], "review")
        self.assertIn("ambiguous", validated["proposed_files"][0]["purpose"])

    def test_legacy_request_rejects_undocumented_nested_fields(self) -> None:
        plan = {"protocol": "workbench-plan-v1", "requests": [{"path": "src/main.py", "mode": "whole_file", "command": "whoami"}]}
        with self.assertRaisesRegex(wb.WorkbenchError, "unsupported keys"):
            wb.validate_context_plan(json.dumps(plan), self.root)

    def test_diagnostics_expose_response_identity_and_actual_top_level_keys(self) -> None:
        plan = {
            "protocol": "workbench-plan-v1", "request": {"path": "src/main.py", "mode": "whole_file"},
            "manual_attechent": [], "completion_status": "blocked", "next_steps": [], "unexpected_field": True,
        }
        raw = json.dumps(plan)
        report = wb.diagnose_model_response(raw, self.root)
        self.assertEqual(report["response_sha256"], __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest())
        self.assertIn("unexpected_field", report["top_level_keys"])
        self.assertIn("context plan", report["format"])
        self.assertTrue(report["errors"])

    def test_imports_reported_legacy_requests_schema_from_user_reproduction(self) -> None:
        plan = {
            "protocol": "workbench-plan-v1",
            "task_id": "imu-installer-context",
            "summary": "The actual source file contents were not included; request exact context before changing the installer.",
            "requests": [
                {"path": "src/main.py", "mode": "whole_file", "reason": "Inspect the actual source."},
                {"path": "README.md", "mode": "whole_file", "reason": "Keep documentation accurate."},
            ],
            "manual_attachments": [],
            "next_steps": ["Add requested files to the next prompt."],
            "completion_status": "in_progress",
        }
        validated = wb.validate_context_plan(json.dumps(plan), self.root)
        self.assertEqual([x["path"] for x in validated["requested_context_files"]], ["src/main.py", "README.md"])
        self.assertEqual(validated["requested_user_uploads"], [])
        self.assertEqual(validated["next_steps"], ["Add requested files to the next prompt."])
        self.assertEqual(validated["completion_status"], "in_progress")

    def test_imports_singular_aliases_typos_and_manual_attachments(self) -> None:
        plan = {
            "protocol": "workbench-plan-v1",
            "request": {"path": "src/main.py", "mode": "whole_file", "reason": "Need source."},
            "manual_attechent": [{"name": "diagram.pdf", "reason": "Binary input", "purpose": "Review drawing."}],
            "completion_status": "blocked", "next_steps": [],
        }
        validated = wb.validate_context_plan(json.dumps(plan), self.root)
        self.assertEqual(validated["requested_context_files"][0]["path"], "src/main.py")
        self.assertEqual(validated["requested_user_uploads"][0]["name"], "diagram.pdf")

    def test_malformed_canonical_field_with_legacy_alias_fails_as_validation_error(self) -> None:
        plan = {
            "protocol": "workbench-plan-v1", "requested_context_files": "not-a-list",
            "requests": [{"path": "src/main.py", "mode": "whole_file", "reason": "Need source."}],
        }
        with self.assertRaisesRegex(wb.WorkbenchError, "requested_context_files.*must be a list"):
            wb.validate_context_plan(json.dumps(plan), self.root)

    def test_unhashable_legacy_values_return_clear_validation_errors(self) -> None:
        cases = [
            {"protocol": "workbench-plan-v1", "requested_project_history": [{"scope": ["recent_summary"], "entry_ids": [], "reason": "x"}]},
            {"protocol": "workbench-plan-v1", "proposed_files": [{"path": "src/config.py", "action": ["create"], "purpose": "x"}]},
            {"protocol": ["workbench-plan-v1"], "requests": []},
        ]
        for plan in cases:
            with self.subTest(plan=plan), self.assertRaises(wb.WorkbenchError):
                wb.validate_context_plan(json.dumps(plan), self.root)

    def test_implementation_protocol_type_mismatch_is_rejected_cleanly(self) -> None:
        for protocol in ([], {}, 4, None):
            payload = {"protocol": protocol, "files": []}
            with self.subTest(protocol=protocol), self.assertRaises(wb.WorkbenchError):
                wb.validate_model_response(json.dumps(payload), self.root)

    def test_legacy_line_range_request_maps_to_canonical_range(self) -> None:
        plan = {
            "protocol": "workbench-plan-v1",
            "requests": [{"path": "src/main.py", "mode": "line_range", "start_line": 2, "end_line": 4, "reason": "Inspect boundary handling."}],
        }
        validated = wb.validate_context_plan(json.dumps(plan), self.root)
        self.assertEqual(validated["requested_context_ranges"], [{"path": "src/main.py", "start_line": 2, "end_line": 4, "reason": "Inspect boundary handling."}])

    def test_legacy_request_alias_does_not_bypass_path_security(self) -> None:
        plan = {"protocol": "workbench-plan-v1", "requests": [{"path": "../outside.py", "mode": "whole_file", "reason": "bad"}]}
        with self.assertRaises(wb.WorkbenchError):
            wb.validate_context_plan(json.dumps(plan), self.root)

    def test_new_plan_protocol_is_detected_and_legacy_plan_diagnostics_are_actionable(self) -> None:
        raw = json.dumps({
            "protocol": "workbench-plan-v1", "task_id": "legacy", "summary": "Need code context.",
            "requests": [{"path": "src/main.py", "mode": "whole_file", "reason": "Inspect parser."}],
            "manual_attachments": [], "completion_status": "blocked", "next_steps": [],
        })
        self.assertIn("context / architecture plan", wb.detect_model_response_format(raw))
        report = wb.diagnose_model_response(raw, self.root)
        self.assertFalse(report["success"], "A plan is not an implementation preview")
        self.assertIn("context plan", report["format"])
        self.assertEqual(report["requested_context_paths"], ["src/main.py"])
        self.assertTrue(any("Import context plan" in finding for finding in report["findings"]))
        self.assertFalse(any("No files were applied" in finding for finding in report["findings"]))


class QuickInstructionTests(unittest.TestCase):
    class FakeText:
        def __init__(self, value: str = "") -> None:
            self.value = value

        def get(self, _start: str, _end: str) -> str:
            return self.value

        def insert(self, _where: str, text: str) -> None:
            self.value += text

    class FakeApp:
        def __init__(self, value: str = "# Prompt\n") -> None:
            self.prompt_output = QuickInstructionTests.FakeText(value)
            self.status = ""

        def set_status(self, value: str) -> None:
            self.status = value

    def test_append_quick_instruction_to_generated_prompt(self) -> None:
        fake = self.FakeApp()
        wb.WorkbenchApp.append_quick_instruction(fake, {"name": "Quality first", "text": "Prefer reliable and maintainable code."})
        self.assertIn("## Additional user instruction: Quality first", fake.prompt_output.value)
        self.assertTrue(fake.prompt_output.value.endswith("Prefer reliable and maintainable code.\n"))
        self.assertIn("Appended", fake.status)

    def test_quick_instruction_is_not_appended_twice(self) -> None:
        marker = "Prefer reliable and maintainable code."
        fake = self.FakeApp(f"# Prompt\n\n{marker}\n")
        original = fake.prompt_output.value
        wb.WorkbenchApp.append_quick_instruction(fake, {"name": "Quality first", "text": marker})
        self.assertEqual(fake.prompt_output.value, original)
        self.assertIn("already present", fake.status)


class ProjectFileRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_python_file_runner_captures_success_output(self) -> None:
        target = self.root / "hello.py"
        target.write_text("import sys\nprint('runner-ok')\nprint('arg=' + sys.argv[1])\n", encoding="utf-8")
        spec = wb.build_project_file_run_spec(self.root, "hello.py", arguments='"value with spaces"', timeout_seconds=10)
        self.assertEqual(spec["kind"], "python")
        result = wb.execute_project_file_run(self.root, spec)
        self.assertEqual(result["status"], "Passed", result)
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("runner-ok", result["output"])
        self.assertIn("arg=value with spaces", result["output"])

    def test_python_file_runner_captures_traceback_and_exit_code(self) -> None:
        target = self.root / "broken.py"
        target.write_text("raise ValueError('specific test failure')\n", encoding="utf-8")
        spec = wb.build_project_file_run_spec(self.root, "broken.py", timeout_seconds=10)
        result = wb.execute_project_file_run(self.root, spec)
        self.assertEqual(result["status"], "Failed")
        self.assertNotEqual(result["exit_code"], 0)
        self.assertIn("ValueError: specific test failure", result["output"])

    def test_runner_rejects_escape_and_unsupported_extensions(self) -> None:
        (self.root / "sample.txt").write_text("not executable", encoding="utf-8")
        outside = self.root.parent / "aiwb_outside.py"
        try:
            outside.write_text("print('outside')", encoding="utf-8")
            with self.assertRaises(wb.WorkbenchError):
                wb.build_project_file_run_spec(self.root, "../aiwb_outside.py")
            with self.assertRaises(wb.WorkbenchError):
                wb.build_project_file_run_spec(self.root, "sample.txt")
        finally:
            outside.unlink(missing_ok=True)

    def test_windows_batch_argv_preserves_script_path_with_spaces(self) -> None:
        argv = wb.build_windows_batch_argv(
            r"C:\Windows\System32\cmd.exe",
            r"C:\Users\Amin\My Projects\LT Lab\build.bat",
            ["--mode", "test run"],
        )
        self.assertEqual(argv[:4], [r"C:\Windows\System32\cmd.exe", "/d", "/s", "/c"])
        self.assertEqual(argv[4], r'""C:\Users\Amin\My Projects\LT Lab\build.bat" --mode "test run""')
        self.assertTrue(argv[4].startswith('""'))
        self.assertTrue(argv[4].endswith('"'))

    def test_ltspice_runner_prepares_batch_command_without_running_it(self) -> None:
        schematic = self.root / "test.asc"
        schematic.write_text("Version 4\nSHEET 1 100 100\n", encoding="utf-8")
        fake = self.root / "LTspice.exe"
        fake.write_text("placeholder", encoding="utf-8")
        spec = wb.build_project_file_run_spec(self.root, "test.asc", ltspice_executable=fake)
        self.assertEqual(spec["kind"], "ltspice")
        self.assertIn("-b", spec["argv"])
        self.assertIn(str(schematic.resolve()), spec["argv"])

    def test_argv_runner_bounds_large_output_during_execution(self) -> None:
        result = wb.run_argv_bounded(
            [sys.executable, "-c", "print('Z' * 800000)"], self.root, timeout=20, max_output_chars=10000,
        )
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(result["output_truncated"])
        self.assertLessEqual(len(result["stdout"]), 10000)
        self.assertEqual(result["stderr"], "")

    def test_argv_runner_timeout_preserves_bounded_partial_output(self) -> None:
        result = wb.run_argv_bounded(
            [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(8)"],
            self.root, timeout=1, max_output_chars=10000,
        )
        self.assertTrue(result["timed_out"])
        self.assertIn("timed out", result["error"].casefold())
        self.assertIn("started", result["stdout"])

    def _make_fake_ltspice_runner(self, body: str) -> Path:
        fake = self.root / "ltspice_fake.sh"
        fake.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        fake.chmod(0o755)
        return fake

    def test_ltspice_runner_marks_missing_new_log_as_unverified_failure(self) -> None:
        schematic = self.root / "test.asc"
        schematic.write_text("Version 4\nSHEET 1 100 100\n", encoding="utf-8")
        fake = self._make_fake_ltspice_runner("exit 0")
        spec = wb.build_project_file_run_spec(self.root, "test.asc", ltspice_executable=fake)
        result = wb.execute_project_file_run(self.root, spec)
        self.assertEqual(result["status"], "Failed")
        self.assertIn("cannot be verified", result["error"])

    def test_ltspice_runner_collects_simulator_log_errors(self) -> None:
        schematic = self.root / "test.asc"
        schematic.write_text("Version 4\nSHEET 1 100 100\n", encoding="utf-8")
        fake = self._make_fake_ltspice_runner('printf "Fatal Error: simulated failure\\n" > "${2%.*}.log"\nexit 0')
        spec = wb.build_project_file_run_spec(self.root, "test.asc", ltspice_executable=fake)
        result = wb.execute_project_file_run(self.root, spec)
        self.assertEqual(result["status"], "Failed", result)
        self.assertTrue(result["detected_simulator_errors"])
        self.assertIn("Fatal Error", result["output"])

    def test_file_run_failure_is_used_in_repair_prompt(self) -> None:
        wb.save_task_state(self.root, {"task_text": "Run the LTspice lab schematic", "workflow_stage": "Action Failed"})
        wb.append_execution_event(self.root, {
            "type": "file_run_finished", "file": "broken.py", "kind": "python",
            "command": "python broken.py", "status": "Failed", "exit_code": 1,
            "timed_out": False, "error": "Process returned 1",
            "output": "Traceback\nValueError: exact runtime failure",
        })
        stage, error, output = wb._failure_evidence_from_history(self.root)
        self.assertEqual(stage, "file run / simulation")
        self.assertEqual(error, "Process returned 1")
        self.assertIn("ValueError: exact runtime failure", output)
        prompt = wb.build_repair_prompt(self.root, error=error, command_output=output, failure_stage=stage)
        self.assertIn("ValueError: exact runtime failure", prompt)
        self.assertIn("broken.py", prompt)

    def test_domain_guidance_supports_non_software_ltspice_artifacts(self) -> None:
        guidance = wb.infer_task_domain_guidance("Create a native LTspice .asc schematic for a MOSFET lab")
        self.assertIn("Do not add an unrelated GUI", guidance)
        self.assertIn(".asc", guidance)
        self.assertIn(".log", guidance)
        profile = wb.profile_for_project_template("Electronics / LTspice simulation")
        self.assertIn("LTspice", profile["runtime_toolchain"])
        self.assertIn("native engineering artifacts", profile["packaging"].casefold())


class V110ResponseReliabilityTests(unittest.TestCase):
    """Regression tests for robust response detection and safe block boundaries."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_v110_raw_file_blocks_preserve_markdown_fences(self) -> None:
        response = '''Here is the complete file set.
<<<AIWB_FILE path="README.md" action="write">>>
# Example

Run this sample:
```powershell
python main.py
```
<<<AIWB_END_FILE>>>
<<<AIWB_FILE path="main.py" action="write">>>
print("hello")
<<<AIWB_END_FILE>>>
'''
        payload, changes, detected = wb.validate_any_model_response(response, self.root)
        self.assertEqual(detected, "AI Workbench file/action blocks")
        self.assertEqual([change.path for change in changes], ["README.md", "main.py"])
        self.assertEqual(changes[0].content, "# Example\n\nRun this sample:\n```powershell\npython main.py\n```\n")
        self.assertEqual(changes[1].content, 'print("hello")\n')

    def test_v110_rejects_two_conflicting_protocol_objects_even_when_fenced(self) -> None:
        first = {"protocol": wb.PROTOCOL_V2, "task_id": "one", "summary": "one", "files": [{"path": "one.txt", "content": "1"}], "actions": []}
        second = {"protocol": wb.PROTOCOL_V2, "task_id": "two", "summary": "two", "files": [{"path": "two.txt", "content": "2"}], "actions": []}
        response = "Here is a response example, followed by the final answer.\n```json\n" + json.dumps(first) + "\n```\nFinal answer:\n" + json.dumps(second)
        with self.assertRaisesRegex(wb.WorkbenchError, "different protocol JSON objects"):
            wb.parse_model_json(response)

    def test_v110_recognizes_whole_aiwb_response_wrapped_in_markdown_fence(self) -> None:
        response = "```text\n<<<AIWB_FILE path=\"hello.txt\" action=\"write\" body=\"raw\">>>\nhello\n<<<AIWB_END_FILE>>>\n```"
        payload, changes, detected = wb.validate_any_model_response(response, self.root)
        self.assertEqual(detected, "AI Workbench file/action blocks")
        self.assertEqual(changes[0].content, "hello\n")

    def test_v110_explicit_raw_mode_preserves_file_that_starts_and_ends_with_markdown_fence(self) -> None:
        file_body = '```markdown\n# Literal fence at file start\n```\n'
        response = (
            '<<<AIWB_FILE path="fenced.md" action="write" body="raw">>>\n'
            + file_body + '<<<AIWB_END_FILE>>>\n'
        )
        _payload, changes, _detected = wb.validate_any_model_response(response, self.root)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].content, file_body)

    def test_v110_raw_command_mode_does_not_interpret_command_text_as_wrapper(self) -> None:
        response = """<<<AIWB_FILE path="main.py" action="write" body="raw">>>
print("ok")
<<<AIWB_END_FILE>>>
<<<AIWB_COMMAND id="smoke" timeout_seconds="30" working_directory="." body="raw">>>
python main.py
<<<AIWB_END_COMMAND>>>
"""
        payload = wb.parse_aiwb_file_blocks(response)
        self.assertEqual(payload["actions"][0]["command"], "python main.py")

    def test_v110_missing_end_marker_before_next_block_is_not_silently_accepted(self) -> None:
        response = '''<<<AIWB_FILE path="build.bat" action="write">>>
````bat
@echo off
echo building
````
<<<AIWB_FILE path="main.py" action="write">>>
print("should not be swallowed")
<<<AIWB_END_FILE>>>
'''
        with self.assertRaisesRegex(wb.WorkbenchError, "missing <<<AIWB_END_FILE>>> before another AIWB block"):
            wb.validate_any_model_response(response, self.root)
        self.assertFalse((self.root / "build.bat").exists())
        self.assertFalse((self.root / "main.py").exists())

    def test_v110_incomplete_json_keeps_json_specific_diagnostic(self) -> None:
        response = '''The response is JSON:
```json
{"protocol":"workbench-v2","files":[}
```
'''
        with self.assertRaisesRegex(wb.WorkbenchError, "No single supported response JSON object"):
            wb.validate_any_model_response(response, self.root)

    def test_v110_unknown_protocol_is_not_misreported_as_unsupported_format(self) -> None:
        response = json.dumps({"protocol": "unknown-v9", "files": [{"path": "a.txt", "content": "x"}]})
        with self.assertRaisesRegex(wb.WorkbenchError, "Invalid protocol version"):
            wb.validate_any_model_response(response, self.root)

    def test_v110_repair_prompt_uses_raw_unfenced_blocks_for_gemini(self) -> None:
        prompt = wb.response_delivery_rule(wb.OUTPUT_FORMAT_GEMINI)
        self.assertIn("NO Markdown fence", prompt)
        self.assertIn('body="raw"', prompt)
        self.assertIn("<<<AIWB_END_FILE>>>", prompt)
        self.assertIn("strict JSON", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ProjectManagerCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.parent = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_validate_project_folder_name(self) -> None:
        self.assertEqual(wb.validate_project_folder_name("Smith Chart Tool"), "Smith Chart Tool")
        self.assertEqual(wb.validate_project_folder_name("تحلیل مدار"), "تحلیل مدار")
        self.assertEqual(wb.validate_project_folder_name(" bad "), "bad")
        for name in ("", "..", "CON", "bad/name", "bad.", "a?b", "LPT1.txt"):
            with self.subTest(name=name):
                with self.assertRaises(wb.WorkbenchError):
                    wb.validate_project_folder_name(name)

    def test_create_project_writes_local_manifest_and_readme(self) -> None:
        project = wb.create_project_folder(self.parent, "Smith Chart Tool", "RF calculator", "Python desktop application", True)
        self.assertTrue(project.is_dir())
        self.assertIn("# Smith Chart Tool", (project / "README.md").read_text(encoding="utf-8"))
        manifest = wb.read_project_manifest(project)
        self.assertEqual(manifest["name"], "Smith Chart Tool")
        self.assertEqual(manifest["description"], "RF calculator")
        self.assertEqual(manifest["profile"]["languages"], "Python")
        self.assertTrue((project / wb.PROJECT_MANIFEST_RELATIVE).is_file())

    def test_create_project_refuses_existing_folder_without_mutating(self) -> None:
        target = self.parent / "existing"
        target.mkdir()
        marker = target / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(wb.WorkbenchError):
            wb.create_project_folder(self.parent, "existing")
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_project_profile_templates(self) -> None:
        python_profile = wb.profile_for_project_template("Python desktop application")
        self.assertEqual(python_profile["gui_framework"], "PySide6 (Qt)")
        web_profile = wb.profile_for_project_template("Web application")
        self.assertEqual(web_profile["target_platform"], "Web application")
        default_profile = wb.profile_for_project_template("Custom / undecided")
        self.assertEqual(default_profile["project_mode"], "New project")

    def test_manifest_round_trip_and_corruption_tolerance(self) -> None:
        root = self.parent / "metadata-project"
        root.mkdir()
        path = wb.write_project_manifest(root, {"name": "metadata-project", "profile": {"languages": "Python"}})
        # The writer returns the resolved path (Windows temp dirs may use 8.3 short names).
        self.assertEqual(path, root.resolve() / wb.PROJECT_MANIFEST_RELATIVE)
        self.assertEqual(wb.read_project_manifest(root)["profile"]["languages"], "Python")
        path.write_text("not json", encoding="utf-8")
        self.assertEqual(wb.read_project_manifest(root), {})

    def test_manifest_rejects_symlinked_metadata_directory(self) -> None:
        root = self.parent / "link-project"
        outside = self.parent / "outside"
        root.mkdir(); outside.mkdir()
        try:
            (root / ".workbench").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlinks unavailable")
        with self.assertRaises(wb.WorkbenchError):
            wb.write_project_manifest(root, {"name": "link-project"})

    def test_project_manifest_is_protected_from_model_writes_and_git(self) -> None:
        self.assertTrue(wb.is_sensitive_path(".workbench/project.json"))
        root = self.parent / "p"
        root.mkdir()
        payload = {"protocol": wb.PROTOCOL, "files": [{"path": ".workbench/project.json", "content": "{}"}]}
        with self.assertRaises(wb.WorkbenchError):
            wb.validate_model_response(json.dumps(payload), root)


class V16CapabilityAndDiagnosticsTests(unittest.TestCase):
    def test_readme_import_preserves_inner_markdown_fences(self) -> None:
        raw = "\n".join([
            '<<<AIWB_FILE action="write" path="README.md">>>',
            '```markdown',
            '# Engineering project',
            '',
            '```powershell',
            'python -m unittest',
            '```',
            '',
            '```python',
            'print("nested fence")',
            '```',
            '```',
            '<<<AIWB_END_FILE>>>',
        ])
        parsed = wb.parse_aiwb_file_blocks(raw)
        self.assertEqual(len(parsed["files"]), 1)
        body = parsed["files"][0]["content"]
        self.assertIn("```powershell", body)
        self.assertIn("```python", body)
        self.assertTrue(body.rstrip().endswith("```"))
        payload, changes = wb.validate_model_response(json.dumps(parsed), self.root)
        self.assertEqual(payload["files"][0]["path"], "README.md")
        self.assertEqual(len(changes), 1)

    def test_markdown_styled_python_dunder_path_is_normalized(self) -> None:
        raw = "\n".join([
            '<<<AIWB_FILE action="write" path="src/ltspice_lab1/**init**.py">>>',
            '```python',
            '"""package init"""',
            '```',
            '<<<AIWB_END_FILE>>>',
        ])
        parsed = wb.parse_aiwb_file_blocks(raw)
        self.assertEqual(parsed["files"][0]["path"], "src/ltspice_lab1/__init__.py")
        self.assertIn("**init**.py -> src/ltspice_lab1/__init__.py", parsed["summary"])
        _payload, changes = wb.validate_model_response(json.dumps(parsed), self.root)
        self.assertEqual(changes[0].path, "src/ltspice_lab1/__init__.py")

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_live_capability_manifest_describes_actual_guardrails_and_selected_format(self) -> None:
        (self.root / "README.md").write_text("Demo", encoding="utf-8")
        wb.save_task_state(self.root, {"workflow_stage": "Tests Run", "task_id": "T-15"})
        manifest = wb.build_capability_manifest(self.root, wb.OUTPUT_FORMAT_GEMINI)
        self.assertIn(wb.APP_VERSION, manifest)
        self.assertIn("Tests Run", manifest)
        self.assertIn("Gemini direct-code blocks", manifest)
        self.assertIn("path/action attributes are accepted in either order", manifest)
        self.assertIn("path/action attributes", manifest) if "path/action attributes" in manifest else self.assertIn("AIWB_FILE", manifest)
        self.assertIn("never run on import", manifest)
        self.assertIn("user must review results", manifest)
        self.assertIn("1 file(s)", manifest)

    def test_diagnostics_accept_reordered_file_marker_attributes(self) -> None:
        raw = '''<<<AIWB_FILE action="write" path="src/new.py">>>
```python
print("ok")
```
<<<AIWB_END_FILE>>>'''
        report = wb.diagnose_model_response(raw, self.root)
        self.assertTrue(report["success"], report)
        self.assertEqual(report["file_count"], 1)
        self.assertEqual(report["paths"], ["src/new.py"])
        self.assertEqual(report["marker_counts"]["file_start"], 1)
        self.assertTrue(any("preview is still required" in x.casefold() for x in report["findings"]))

    def test_diagnostics_report_mismatched_markers_without_applying_files(self) -> None:
        raw = '''<<<AIWB_FILE path="src/new.py" action="write">>>
```python
print("incomplete")
```'''
        report = wb.diagnose_model_response(raw, self.root)
        self.assertFalse(report["success"])
        self.assertEqual(report["marker_counts"]["file_start"], 1)
        self.assertEqual(report["marker_counts"]["file_end"], 0)
        self.assertTrue(any("count mismatch" in x.casefold() for x in report["findings"]))
        self.assertTrue(report["errors"])

    def test_task_state_machine_records_valid_path_and_rejects_illegal_skip(self) -> None:
        state: dict[str, object] = {"task_id": "T-1", "workflow_stage": "Draft"}
        stages = ["Prompt Ready", "Response Received", "Validated", "Files Applied", "Tests Run", "Verified"]
        for stage in stages:
            state, event = wb.transition_task_state_data(state, stage, f"test transition to {stage}")
            self.assertEqual(state["workflow_stage"], stage)
            self.assertEqual(event["to_stage"], stage)
        self.assertEqual(len(state["workflow_history"]), len(stages))
        with self.assertRaises(wb.WorkbenchError):
            wb.transition_task_state_data({"workflow_stage": "Draft"}, "Verified", "must not skip evidence")

    def test_task_state_machine_bounds_history(self) -> None:
        state: dict[str, object] = {"workflow_stage": "Draft", "workflow_history": []}
        for index in range(100):
            # Prompt Ready is a deliberately repeatable restart/revision step.
            state, _event = wb.transition_task_state_data(state, "Prompt Ready", f"iteration {index}")
            state, _event = wb.transition_task_state_data(state, "Draft", f"iteration {index}")
        self.assertLessEqual(len(state["workflow_history"]), 80)

    def test_repair_prompt_uses_actual_error_and_does_not_echo_raw_response(self) -> None:
        wb.save_task_state(self.root, {"task_text": "Build a Smith chart desktop app", "workflow_stage": "Import Failed", "last_response_error": "missing end marker"})
        prompt = wb.build_repair_prompt(
            self.root,
            error="No supported output was detected.",
            failure_stage="import",
            format_name=wb.OUTPUT_FORMAT_GEMINI,
            raw_response="DO_NOT_ECHO_FULL_RAW_MODEL_OUTPUT",
            diagnostics={"format": "AI Workbench blocks", "file_count": 2, "action_count": 0, "findings": ["missing end marker"], "errors": ["No supported output was detected."]},
        )
        self.assertIn("Build a Smith chart desktop app", prompt)
        self.assertIn("No supported output was detected.", prompt)
        self.assertIn("missing end marker", prompt)
        self.assertIn("AIWB_FILE", prompt)
        self.assertNotIn("DO_NOT_ECHO_FULL_RAW_MODEL_OUTPUT", prompt)

    def test_prompt_embeds_live_capability_manifest_for_selected_format(self) -> None:
        prompt = wb.build_prompt_document(
            task="Create a sample project",
            project_files=[], context_files=[], omitted_context=[],
            profile=dict(wb.DEFAULT_PROJECT_PROFILE), configured_project_mode="New project",
            task_type="Build a new project", prompt_stage="Implementation / build",
            output_format=wb.OUTPUT_FORMAT_GEMINI,
            capability_manifest=wb.build_capability_manifest(self.root, wb.OUTPUT_FORMAT_GEMINI),
        )
        self.assertIn("Live Workbench Capability Manifest", prompt)
        self.assertIn(f"Workbench release: {wb.APP_VERSION}", prompt)
        self.assertIn("Gemini direct-code blocks", prompt)
        self.assertIn("Commands", prompt)

    def test_latest_failure_helper_does_not_mistake_passed_action_for_failure(self) -> None:
        wb.save_task_state(self.root, {"task_text": "Run project tests", "last_response_error": "old import error"})
        wb.append_execution_event(self.root, {"type": "action_finished", "action_id": "good", "status": "Passed", "exit_code": 0, "output": "success"})
        wb.append_execution_event(self.root, {"type": "manual_command_finished", "command": "python -m unittest", "status": "Failed", "exit_code": 1, "output": "AssertionError: example failure"})
        stage, error, output = wb._failure_evidence_from_history(self.root)
        self.assertEqual(stage, "command/test execution")
        self.assertEqual(error, "")
        self.assertIn("AssertionError: example failure", output)
        prompt = wb.build_repair_prompt(self.root, error=error, command_output=output, failure_stage=stage)
        self.assertIn("AssertionError: example failure", prompt)
        self.assertNotIn("old import error", prompt)
