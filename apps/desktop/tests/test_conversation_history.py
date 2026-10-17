"""Regression tests for project-local prompt/output history and context handoff."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import conversation_store as store
import AI_Workbench as wb


class ConversationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_prompt_sequence_output_error_and_metadata_persist(self) -> None:
        start = store.create_prompt_entry(
            self.root, task_id="T-1", task_text="Improve parser", prompt_text="PROMPT START",
            stage="Architecture plan", output_format=wb.OUTPUT_FORMAT_JSON, app_version="1.9.0",
        )
        store.attach_model_output(self.root, start["id"], output_text='{"protocol":"workbench-plan-v1"}', status="Context plan received")
        step = store.create_prompt_entry(
            self.root, task_id="T-1", task_text="Improve parser", prompt_text="PROMPT STEP 1",
            stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_GPT_ZIP, parent_entry_id=start["id"], app_version="1.9.0",
        )
        self.assertEqual(start["label"], "Start")
        self.assertEqual(step["label"], "Step 1")
        store.attach_model_output(self.root, step["id"], normalized_output={"summary": "new file", "files": []}, status="Validated")
        store.record_manual_error(self.root, step["id"], stage="Test failure", details="Expected 3, got 4", file_path="src/main.py", steps="Run test_parser.py")
        store.update_history_entry(self.root, step["id"], {"title": "Parser regression", "feature": "Parser", "project_version": "2.4.0", "notes": "Investigate off-by-one"})

        reopened = store.list_history(self.root)
        self.assertEqual(len(reopened), 2)
        saved = store.get_history_entry(self.root, step["id"])
        self.assertEqual(saved["model_output"], "")
        self.assertEqual(saved["normalized_output"]["summary"], "new file")
        self.assertEqual(saved["manual_error"]["details"], "Expected 3, got 4")
        self.assertEqual(saved["feature"], "Parser")
        self.assertEqual(saved["project_version"], "2.4.0")
        self.assertEqual(saved["notes"], "Investigate off-by-one")

    def test_prompt_edit_creates_linked_revision_without_overwriting_original(self) -> None:
        source = store.create_prompt_entry(
            self.root, task_id="rev-1", task_text="Refactor parser", prompt_text="ORIGINAL PROMPT",
            stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_GPT_ZIP,
            feature="Parser", project_version="2.1.0", app_version="1.9.0",
        )
        store.update_context_requests(self.root, source["id"], ranges=[{"path": "src/main.py", "start_line": 2, "end_line": 3, "reason": "inspect"}], uploads=[{"name": "manual.pdf", "reason": "external", "purpose": "reference"}])
        revision = store.create_prompt_revision(self.root, source["id"], "EDITED PROMPT", app_version="1.9.0")
        self.assertEqual(revision["kind"], "prompt-revision")
        self.assertEqual(revision["label"], "Step 1")
        self.assertEqual(revision["parent_entry_id"], source["id"])
        self.assertEqual(revision["prompt_text"], "EDITED PROMPT")
        self.assertEqual(revision["requested_context_ranges"][0]["path"], "src/main.py")
        self.assertEqual(revision["requested_user_uploads"][0]["name"], "manual.pdf")
        self.assertEqual(store.get_history_entry(self.root, source["id"])["prompt_text"], "ORIGINAL PROMPT")

    def test_history_index_rejects_more_than_configured_entry_limit(self) -> None:
        base = self.root / ".workbench" / "conversation_history"
        (base / "entries").mkdir(parents=True)
        rows = [{"id": f"{index:032x}", "task_id": "x"} for index in range(store.MAX_ENTRIES + 1)]
        (base / "index.json").write_text(json.dumps({"schema_version": store.SCHEMA_VERSION, "entries": rows}), encoding="utf-8")
        with self.assertRaises(store.ConversationStoreError):
            store.list_history_metadata(self.root)

    def test_range_reader_returns_exact_numbered_lines(self) -> None:
        content, start, end = wb.read_prompt_file_range(self.root, "src/main.py", 2, 4)
        self.assertEqual((start, end), (2, 4))
        self.assertEqual(content, "2: two\n3: three\n4: four")
        with self.assertRaises(wb.WorkbenchError):
            wb.read_prompt_file_range(self.root, "src/main.py", 0, 2)
        with self.assertRaises(wb.WorkbenchError):
            wb.read_prompt_file_range(self.root, "src/main.py", 1, 501)

    def test_context_plan_accepts_ranges_and_manual_uploads(self) -> None:
        raw = json.dumps({
            "protocol": "workbench-plan-v1", "task_id": "ctx1", "summary": "Need exact source lines",
            "requested_context_files": [],
            "requested_context_ranges": [{"path": "src/main.py", "start_line": 2, "end_line": 4, "reason": "inspect parser"}],
            "requested_user_uploads": [{"name": "timing.pdf", "reason": "reference is binary", "purpose": "confirm constraints"}],
            "proposed_files": [], "external_requirements": [], "clarifying_questions": [], "assumptions": [],
        })
        plan = wb.validate_context_plan(raw, self.root)
        self.assertEqual(plan["requested_context_ranges"][0]["start_line"], 2)
        self.assertEqual(plan["requested_user_uploads"][0]["name"], "timing.pdf")

    def test_context_plan_rejects_invalid_ranges(self) -> None:
        plan = {
            "protocol": "workbench-plan-v1", "requested_context_ranges": [
                {"path": "src/main.py", "start_line": 8, "end_line": 2, "reason": "bad"}
            ],
        }
        with self.assertRaises(wb.WorkbenchError):
            wb.validate_context_plan(json.dumps(plan), self.root)

    def test_continuation_handoff_includes_active_history_and_manual_error(self) -> None:
        entry = store.create_prompt_entry(
            self.root, task_id="handoff-1", task_text="Fix parser regression",
            prompt_text="Implementation prompt with full context", stage="Implementation / build",
            output_format=wb.OUTPUT_FORMAT_JSON, app_version="1.9.0",
        )
        store.attach_model_output(self.root, entry["id"], output_text="model reply", status="Validated")
        store.record_manual_error(
            self.root, entry["id"], stage="Runtime", details="NameError: parse_config is undefined",
            file_path="src/main.py", steps="Run python src/main.py",
        )
        repair = store.create_prompt_entry(
            self.root, task_id="handoff-1", task_text="Fix parser regression",
            prompt_text="Fix the observed NameError", stage="Repair · Runtime",
            output_format=wb.OUTPUT_FORMAT_JSON, kind="repair", parent_entry_id=entry["id"],
            app_version="1.9.0",
        )
        state = wb.load_task_state(self.root)
        state.update({"task_text": "Fix parser regression", "active_prompt_entry_id": repair["id"], "task_id": "handoff-1", "last_output_format": wb.OUTPUT_FORMAT_JSON, "latest_response_format": wb.OUTPUT_FORMAT_JSON})
        wb.save_task_state(self.root, state)
        wb.append_execution_event(self.root, {"type": "manual_runtime_error_reported", "task_id": "handoff-1", "status": "failed", "failure_stage": "Runtime", "file": "src/main.py", "message": "NameError: parse_config is undefined", "output": "NameError: parse_config is undefined", "history_entry_id": entry["id"]})
        handoff = wb.build_continuation_handoff_text(self.root)
        self.assertIn("Project conversation thread", handoff)
        self.assertIn("Active conversation step", handoff)
        self.assertIn("Relevant evidence from linked previous steps", handoff)
        self.assertIn("NameError: parse_config is undefined", handoff)
        self.assertIn("src/main.py", handoff)
        self.assertIn(entry["id"], handoff)
        stage, error, _output = wb._failure_evidence_from_history(self.root)
        self.assertEqual(stage, "Runtime")
        self.assertIn("NameError: parse_config is undefined", error)

    def test_oversized_history_index_is_rejected_before_full_read(self) -> None:
        base = self.root / ".workbench" / "conversation_history"
        (base / "entries").mkdir(parents=True)
        (base / "index.json").write_text(" " * (store.MAX_INDEX_BYTES + 1), encoding="utf-8")
        with self.assertRaises(store.ConversationStoreError):
            store.list_history_metadata(self.root)


    def test_checkpoint_requires_validated_output_and_is_cleared_when_output_changes(self) -> None:
        entry = store.create_prompt_entry(
            self.root, task_id="checkpoint", task_text="Fix parser", prompt_text="Prompt A",
            stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON,
        )
        store.attach_model_output(self.root, entry["id"], output_text="garbage", status="Import rejected", error="Bad protocol")
        with self.assertRaises(store.ConversationStoreError):
            store.mark_project_history_saved(self.root, entry["id"], saved=True)
        store.attach_model_output(
            self.root, entry["id"], output_text='{"protocol":"workbench-v2"}',
            normalized_output={"protocol": "workbench-v2"}, status="Validated; awaiting review/apply",
        )
        saved = store.mark_project_history_saved(self.root, entry["id"], saved=True)
        self.assertTrue(saved["project_history_saved"])
        self.assertEqual(len(saved["project_history_saved_sha256"]), 64)
        changed = store.attach_model_output(self.root, entry["id"], output_text="replacement response", status="Import rejected", error="Invalid")
        self.assertFalse(changed["project_history_saved"])
        self.assertEqual(changed["project_history_saved_sha256"], "")

    def test_tree_reparent_prevents_cycles_reorders_siblings_and_delete_lifts_children(self) -> None:
        first = store.create_prompt_entry(self.root, task_id="tree", task_text="Tree test", prompt_text="one", stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON)
        second = store.create_prompt_entry(self.root, task_id="tree", task_text="Tree test", prompt_text="two", stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON)
        third = store.create_prompt_entry(self.root, task_id="tree", task_text="Tree test", prompt_text="three", stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON)
        store.reparent_history_entry(self.root, second["id"], first["id"])
        store.reparent_history_entry(self.root, third["id"], second["id"])
        with self.assertRaises(store.ConversationStoreError):
            store.reparent_history_entry(self.root, first["id"], third["id"])
        self.assertTrue(store.reorder_history_entry(self.root, third["id"], -1) is False)  # only child of second
        store.delete_history_entry(self.root, second["id"])
        third_after = store.get_history_entry(self.root, third["id"])
        self.assertEqual(third_after["parent_entry_id"], first["id"])
        self.assertIsNone(store.get_history_entry(self.root, second["id"]))

    def test_context_plan_persists_requested_project_history(self) -> None:
        entry = store.create_prompt_entry(
            self.root, task_id="history-request", task_text="Inspect previous decisions", prompt_text="Ask for history",
            stage="Request exact context files", output_format=wb.OUTPUT_FORMAT_JSON,
        )
        request = {"scope": "recent_summary", "entry_ids": [], "reason": "Need earlier design constraints"}
        stored = store.update_context_requests(self.root, entry["id"], ranges=[], uploads=[], history_requests=[request])
        self.assertEqual(stored["requested_project_history"], [request])
        plan = {
            "protocol": "workbench-plan-v1", "task_id": "history-request", "summary": "Need version links",
            "requested_context_files": [], "requested_context_ranges": [], "requested_user_uploads": [],
            "requested_project_history": [{"scope": "version_links", "entry_ids": [], "reason": "Trace the prompt that introduced the API"}],
            "proposed_files": [], "external_requirements": [], "clarifying_questions": [], "assumptions": [],
        }
        parsed = wb.validate_context_plan(json.dumps(plan), self.root)
        self.assertEqual(parsed["requested_project_history"][0]["scope"], "version_links")

    def test_implementation_prompt_receives_project_history_when_requested(self) -> None:
        prompt = wb.build_prompt_document(
            task="Continue existing design", project_files=[("src/main.py", 30)], context_files=[], omitted_context=[],
            profile=wb.DEFAULT_PROJECT_PROFILE, configured_project_mode="Existing project", task_type="Implement a feature",
            prompt_stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON,
            project_history_context="VERSION v1.2.3 — decision: preserve stable command contract.",
        )
        self.assertIn("VERSION v1.2.3", prompt)
        self.assertIn("Project history context", prompt)

    def test_prompt_includes_manual_upload_checklist(self) -> None:
        prompt = wb.build_prompt_document(
            task="Inspect simulation", project_files=[("src/main.py", 20)], context_files=[], omitted_context=[],
            profile=wb.DEFAULT_PROJECT_PROFILE, configured_project_mode="Existing project", task_type="Implement a feature",
            prompt_stage="Implementation / build", output_format=wb.OUTPUT_FORMAT_JSON,
            requested_user_uploads=[{"name": "scope_capture.png", "reason": "binary output", "purpose": "compare waveforms"}],
        )
        self.assertIn("scope_capture.png", prompt)
        self.assertIn("the user must upload", prompt)
        self.assertIn("These files are not attached automatically", prompt)


if __name__ == "__main__":
    unittest.main()
