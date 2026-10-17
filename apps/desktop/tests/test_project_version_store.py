"""Regression tests for project-local semantic version ledger and provenance links."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import conversation_store
import project_version_store as versions
import AI_Workbench as wb


class ProjectVersionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("print('before')\n", encoding="utf-8")
        wb.write_project_manifest(self.root, {"name": "ledger-test", "version": "v1.0.0", "last_task": ""})

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_baseline_then_applied_change_links_version_to_exact_prompt_and_response(self) -> None:
        baseline = versions.ensure_baseline(self.root)
        self.assertEqual(baseline["version"], "v1.0.0")
        prompt = conversation_store.create_prompt_entry(
            self.root, task_id="task-1", task_text="Change greeting", prompt_text="Exact generated prompt",
            stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON, title="Greeting feature", app_version="1.11.0",
        )
        response = {
            "protocol": "workbench-v2", "task_id": "task-1", "summary": "Change greeting",
            "files": [{"path": "src/main.py", "content": "print('after')\n"}], "actions": [],
        }
        wb.save_model_response_snapshot(self.root, response, wb.OUTPUT_FORMAT_JSON)
        conversation_store.attach_model_output(
            self.root, prompt["id"], output_text=json.dumps(response), normalized_output=response,
            status="Validated; awaiting review/apply",
        )
        (self.root / "src" / "main.py").write_text("print('after')\n", encoding="utf-8")
        record = versions.record_applied_version(
            self.root, source_history_entry_id=prompt["id"], task_id="task-1", title="Greeting feature",
            summary="Change greeting", changed_files=["src/main.py"], prompt_text="Exact generated prompt",
            model_output=json.dumps(response), current_version="v1.0.0",
        )
        self.assertEqual(record["version"], "v1.0.1")
        self.assertEqual(record["parent_version"], "v1.0.0")
        self.assertEqual(record["source_history_entry_id"], prompt["id"])
        self.assertEqual(record["changed_files"], ["src/main.py"])
        self.assertEqual(record["prompt_sha256"], hashlib.sha256(b"Exact generated prompt").hexdigest())
        self.assertTrue(record["snapshot_path"].endswith(".json"))
        self.assertTrue((self.root / record["snapshot_path"]).is_file())
        self.assertEqual(versions.list_versions(self.root)[-1]["id"], record["id"])
        manifest = json.loads((self.root / ".workbench" / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "v1.0.1")
        conversation_store.link_project_version(self.root, prompt["id"], version=record["version"], version_record_id=record["id"])
        linked = conversation_store.get_history_entry(self.root, prompt["id"])
        self.assertEqual(linked["project_version"], "v1.0.1")
        self.assertEqual(linked["version_record_id"], record["id"])

    def test_identical_tree_does_not_fabricate_new_patch_version(self) -> None:
        baseline = versions.ensure_baseline(self.root)
        entry = conversation_store.create_prompt_entry(
            self.root, task_id="same-tree", task_text="No-op", prompt_text="No-op prompt",
            stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON,
        )
        current = versions.record_applied_version(
            self.root, source_history_entry_id=entry["id"], task_id="same-tree", title="No-op",
            summary="No file contents changed", changed_files=[], current_version=baseline["version"],
        )
        self.assertEqual(current["version"], baseline["version"])
        self.assertTrue(current.get("already_present"))
        self.assertEqual(len(versions.list_versions(self.root)), 1)
        self.assertIn(entry["id"], current["source_history_entry_ids"])

    def test_history_context_mentions_versions_and_selected_prompt_output(self) -> None:
        baseline = versions.ensure_baseline(self.root)
        entry = conversation_store.create_prompt_entry(
            self.root, task_id="ctx", task_text="Retain compatibility", prompt_text="Specific prompt body",
            stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON, title="Compatibility fix",
        )
        conversation_store.attach_model_output(self.root, entry["id"], output_text='{"summary":"Kept API compatible"}', normalized_output={"summary": "Kept API compatible"}, status="Validated; awaiting review/apply")
        context = versions.history_summary_context(
            self.root,
            requested=[{"scope": "selected_entries", "entry_ids": [entry["id"]], "reason": "Model asks for this exact step"}],
            max_chars=12000,
        )
        self.assertIn(baseline["version"], context)
        self.assertIn(entry["id"], context)
        self.assertIn("Specific prompt body", context)
        self.assertIn("Kept API compatible", context)


    def test_one_shot_minor_bump_is_consumed_only_by_a_real_tree_change(self) -> None:
        baseline = versions.ensure_baseline(self.root)
        versions.set_next_version_bump(self.root, "minor")
        noop_entry = conversation_store.create_prompt_entry(
            self.root, task_id="same-tree", task_text="No-op", prompt_text="No-op prompt",
            stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON,
        )
        noop = versions.record_applied_version(
            self.root, source_history_entry_id=noop_entry["id"], task_id="same-tree", title="No-op",
            summary="No file contents changed", changed_files=[], current_version=baseline["version"],
        )
        self.assertEqual(noop["version"], "v1.0.0")
        self.assertEqual(versions.get_next_version_bump(self.root), "minor", "no-op must not consume the one-shot bump")

        (self.root / "src" / "main.py").write_text("print('minor release')\n", encoding="utf-8")
        entry = conversation_store.create_prompt_entry(
            self.root, task_id="real-change", task_text="Feature release", prompt_text="Feature release prompt",
            stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON,
        )
        record = versions.record_applied_version(
            self.root, source_history_entry_id=entry["id"], task_id="real-change", title="Feature release",
            summary="A new backward-compatible feature", changed_files=["src/main.py"], current_version=baseline["version"],
        )
        self.assertEqual(record["version"], "v1.1.0")
        self.assertEqual(record["version_bump"], "minor")
        self.assertEqual(versions.get_next_version_bump(self.root), "patch", "successful real change resets to default patch")

    def test_major_and_minor_semver_increments_reset_lower_components(self) -> None:
        self.assertEqual(versions._next_version("v2.4.9", "major"), "v3.0.0")
        self.assertEqual(versions._next_version("v2.4.9", "minor"), "v2.5.0")
        self.assertEqual(versions._next_version("v2.4.9", "patch"), "v2.4.10")
        with self.assertRaises(versions.ProjectVersionError):
            versions.set_next_version_bump(self.root, "release candidate")



    def test_incomplete_inventory_never_claims_noop_from_partial_hash(self) -> None:
        baseline = versions.ensure_baseline(self.root)
        entry = conversation_store.create_prompt_entry(
            self.root, task_id="partial", task_text="Large project", prompt_text="Update a file",
            stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON,
        )
        (self.root / "src" / "main.py").write_text("print('changed')\n", encoding="utf-8")
        # Simulate an inventory that hits the configured safety cap and returns the same partial hash.
        with patch.object(versions, "_capture_inventory", return_value=([], baseline["project_tree_sha256"], False, "Simulated safety cap")):
            record = versions.record_applied_version(
                self.root, source_history_entry_id=entry["id"], task_id="partial", title="Large project",
                summary="Inventory incomplete", changed_files=["src/main.py"], current_version=baseline["version"],
            )
        self.assertFalse(record.get("already_present"))
        self.assertEqual(record["version"], "v1.0.1")
        self.assertFalse(record["inventory_complete"])
        self.assertEqual(record["inventory_note"], "Simulated safety cap")

    def test_response_hash_fallback_uses_snapshot_hash_not_hash_of_hex_digest(self) -> None:
        baseline = versions.ensure_baseline(self.root)
        entry = conversation_store.create_prompt_entry(
            self.root, task_id="artifact", task_text="Artifact response", prompt_text="Artifact prompt",
            stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON,
        )
        response_object = {"protocol": "workbench-v2", "summary": "artifact snapshot", "files": []}
        snapshot_bytes = (json.dumps(response_object, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        (self.root / ".workbench").mkdir(exist_ok=True)
        (self.root / ".workbench" / "latest_model_response.json").write_bytes(snapshot_bytes)
        expected_snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
        (self.root / "src" / "main.py").write_text("print('artifact tree changed')\n", encoding="utf-8")
        record = versions.record_applied_version(
            self.root, source_history_entry_id=entry["id"], task_id="artifact", title="Artifact response",
            summary="Artifact-only provenance", changed_files=["src/main.py"], prompt_text="Artifact prompt",
            model_output="", current_version=baseline["version"],
        )
        self.assertEqual(record["normalized_response_sha256"], expected_snapshot_hash)
        self.assertEqual(record["response_sha256"], expected_snapshot_hash)

    def test_history_inventory_excludes_workbench_metadata_and_git(self) -> None:
        (self.root / ".git").mkdir()
        (self.root / ".git" / "secret-like-test-file").write_text("not tracked in hash", encoding="utf-8")
        (self.root / ".venv").mkdir()
        (self.root / ".venv" / "library.py").write_text("ignored", encoding="utf-8")
        baseline = versions.ensure_baseline(self.root)
        paths = {item["path"] for item in baseline["file_manifest"]}
        self.assertIn("src/main.py", paths)
        self.assertNotIn(".git/secret-like-test-file", paths)
        self.assertNotIn(".venv/library.py", paths)
        self.assertFalse(any(path.startswith(".workbench/") for path in paths))


if __name__ == "__main__":
    unittest.main()
