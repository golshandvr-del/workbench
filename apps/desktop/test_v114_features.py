from __future__ import annotations
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import AI_Workbench as wb
import restore_service
from aiwb import architecture_plan, candidate_store, dependency_analysis, semantic_diff, task_playbooks


class TypedOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_bytes(b"print('old')\n")
        self.app_data = Path(self.temp.name) / "appdata"
        self._app_data_patch = patch.object(wb, "app_data_dir", return_value=self.app_data)
        self._app_data_patch.start()

    def tearDown(self) -> None:
        self._app_data_patch.stop()
        self.temp.cleanup()

    def _parse(self, operation: dict) -> tuple[dict, list[wb.FileChange]]:
        payload = {
            "protocol": "workbench-v3", "task_id": "typed-test", "summary": "typed op test",
            "operations": [operation], "actions": [], "next_steps": [], "completion_status": "in_progress",
        }
        return wb.validate_model_response(payload, self.root)

    def _latest_tx(self) -> dict:
        key = hashlib.sha256(str(self.root.resolve()).casefold().encode("utf-8")).hexdigest()[:20]
        backup_base = self.app_data / "backups" / key
        rows = restore_service.list_transactions(self.root, backup_base)
        self.assertTrue(rows)
        return rows[0]

    def test_delete_apply_and_restore_exact_bytes(self) -> None:
        _payload, changes = self._parse({"id": "del-1", "type": "delete", "path": "src/main.py"})
        wb.apply_changes_transactionally(self.root, changes, summary="delete test")
        self.assertFalse((self.root / "src/main.py").exists())
        tx = self._latest_tx()
        rows = restore_service.preview_restore(self.root, tx)
        self.assertEqual(rows[0]["status"], "ready")
        restore_service.restore_selected(self.root, tx, {"src/main.py"})
        self.assertEqual((self.root / "src/main.py").read_bytes(), b"print('old')\n")

    def test_move_apply_and_restore_both_endpoints(self) -> None:
        original = (self.root / "src/main.py").read_bytes()
        _payload, changes = self._parse({"id": "move-1", "type": "move", "source_path": "src/main.py", "destination_path": "lib/main.py"})
        wb.apply_changes_transactionally(self.root, changes, summary="move test")
        self.assertFalse((self.root / "src/main.py").exists())
        self.assertEqual((self.root / "lib/main.py").read_bytes(), original)
        tx = self._latest_tx()
        self.assertTrue(all(row["status"] == "ready" for row in restore_service.preview_restore(self.root, tx)))
        restore_service.restore_selected(self.root, tx, {"src/main.py", "lib/main.py"})
        self.assertEqual((self.root / "src/main.py").read_bytes(), original)
        self.assertFalse((self.root / "lib/main.py").exists())

    def test_rename_stays_in_same_directory(self) -> None:
        _payload, changes = self._parse({"type": "rename", "source_path": "src/main.py", "destination_path": "src/app.py"})
        wb.apply_changes_transactionally(self.root, changes)
        self.assertFalse((self.root / "src/main.py").exists())
        self.assertEqual((self.root / "src/app.py").read_text(), "print('old')\n")

    def test_move_or_rename_never_overwrites_existing_destination(self) -> None:
        (self.root / "src" / "app.py").write_text("keep", encoding="utf-8")
        with self.assertRaises(wb.WorkbenchError):
            self._parse({"type": "rename", "source_path": "src/main.py", "destination_path": "src/app.py"})
        self.assertEqual((self.root / "src" / "app.py").read_text(), "keep")


    def test_duplicate_typed_operation_ids_are_rejected(self) -> None:
        payload = {
            "protocol": "workbench-v3", "task_id": "dup-id", "summary": "duplicate ids",
            "operations": [
                {"id": "same", "type": "write", "path": "src/a.py", "content": "a"},
                {"id": "SAME", "type": "write", "path": "src/b.py", "content": "b"},
            ], "actions": [], "next_steps": [], "completion_status": "in_progress",
        }
        with self.assertRaises(wb.WorkbenchError):
            wb.validate_model_response(payload, self.root)

    def test_legacy_protocols_remain_write_only(self) -> None:
        payload = {"protocol": "workbench-v2", "task_id": "old", "summary": "legacy", "files": [{"path": "src/main.py", "content": "print('new')\n"}], "actions": [], "next_steps": [], "completion_status": "in_progress"}
        _normalized, changes = wb.validate_model_response(payload, self.root)
        self.assertEqual(changes[0].operation, "write")
        bad = {"protocol": "workbench-v2", "files": [{"path": "src/main.py", "action": "delete"}]}
        with self.assertRaises(wb.WorkbenchError): wb.validate_model_response(bad, self.root)


class ArchitecturePlanTests(unittest.TestCase):
    def test_schema_round_trip_and_atomic_project_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = architecture_plan.new_plan("Modular app", "Keep UI separate from domain logic.")
            plan["modules"] = [{"name": "Protocol service", "path": "aiwb/protocol.py", "responsibilities": "Validate model operation contracts", "depends_on": []}]
            saved = architecture_plan.save_plan(root, plan)
            self.assertTrue(saved.is_file())
            loaded = architecture_plan.load_plan(root)
            self.assertEqual(loaded["title"], "Modular app")
            self.assertEqual(loaded["modules"][0]["path"], "aiwb/protocol.py")
            self.assertEqual(architecture_plan.parse_plan(json.dumps(loaded))["protocol"], architecture_plan.PROTOCOL)

    def test_rejects_traversal_and_unknown_fields(self) -> None:
        plan = architecture_plan.new_plan("Unsafe", "Test paths")
        plan["proposed_files"] = [{"path": "../outside.py", "action": "create", "purpose": "escape"}]
        with self.assertRaises(architecture_plan.ArchitecturePlanError): architecture_plan.validate_plan(plan)
        plan = architecture_plan.new_plan("Unknown", "Test strict schema")
        plan["arbitrary"] = True
        with self.assertRaises(architecture_plan.ArchitecturePlanError): architecture_plan.validate_plan(plan)


class CandidateStoreTests(unittest.TestCase):
    def test_candidates_are_local_bounded_and_merge_as_explicit_v3_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a = candidate_store.save_candidate(root, name="GPT A", payload={"protocol": "workbench-v1", "files": [{"path": "src/a.py", "action": "write", "content": "A"}]}, raw_response="A raw", source_format="test")
            b = candidate_store.save_candidate(root, name="Gemini B", payload={"protocol": "workbench-v1", "files": [{"path": "src/a.py", "action": "write", "content": "B"}]}, raw_response="B raw", source_format="test")
            rows = candidate_store.list_candidates(root)
            self.assertEqual(len(rows), 2)
            merged = candidate_store.merge_candidate_payloads("workbench-v3", [{"path": "src/a.py", "candidate_id": b["id"], "operation": {"type": "write", "path": "src/a.py", "content": "B"}}], rows)
            self.assertEqual(merged["protocol"], "workbench-v3")
            self.assertEqual(merged["operations"][0]["content"], "B")
            self.assertEqual(merged["actions"], [])
            with self.assertRaises(candidate_store.CandidateStoreError):
                candidate_store.merge_candidate_payloads("workbench-v3", [], rows)


class PlaybookAndAnalysisTests(unittest.TestCase):
    def test_playbooks_have_deterministic_steps_and_fail_closed(self) -> None:
        rendered = task_playbooks.render_playbook("bugfix")
        self.assertIn("regression test", rendered)
        with self.assertRaises(ValueError): task_playbooks.render_playbook("unlisted")

    def test_dependency_impact_resolves_python_imports_and_reverse_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "lib.py").write_text("def f(): return 1\n", encoding="utf-8")
            (root / "app.py").write_text("from lib import f\nprint(f())\n", encoding="utf-8")
            graph = dependency_analysis.scan_dependency_graph(root)
            self.assertIn("lib.py", graph["reverse"])
            self.assertIn("app.py", graph["reverse"]["lib.py"])
            impact = dependency_analysis.analyze_project_impact(root, ["lib.py"])
            self.assertIn("app.py", impact["direct_dependents"])
            self.assertIn("advisory", dependency_analysis.format_impact_report(impact).casefold())


    def test_semantic_diff_detects_modified_python_definition(self) -> None:
        report = semantic_diff.analyze_semantic_diff("src/main.py", "def f():\n    return 1\n", "def f():\n    return 2\n")
        self.assertEqual(report["confidence"], "Python AST")
        self.assertEqual(report["modified"]["definitions"], ["function f"])

    def test_json_semantic_diff_reports_added_path_and_changed_value(self) -> None:
        report = semantic_diff.analyze_semantic_diff("settings.json", '{"timeout": 10, "net": {"enabled": true}}', '{"timeout": 30, "net": {"enabled": true, "retries": 2}}')
        self.assertEqual(report["confidence"], "JSON structural paths")
        self.assertIn("$/net/retries", report["added"]["json_paths"])
        self.assertTrue(any("$/timeout" in item for item in report["modified"]["json_values"]))

    def test_csv_semantic_diff_reports_keyed_row_and_cell_changes(self) -> None:
        before = "id,name,qty\n1,bolt,2\n2,nut,3\n"
        after = "id,name,qty\n1,bolt,4\n3,washer,8\n"
        report = semantic_diff.analyze_semantic_diff("parts.csv", before, after)
        self.assertEqual(report["confidence"], "CSV keyed rows")
        self.assertIn("id=3", report["added"]["rows"])
        self.assertIn("id=2", report["removed"]["rows"])
        self.assertTrue(any("id=1, qty" in item for item in report["modified"]["cells"]))

    def test_semantic_diff_reports_python_symbol_addition(self) -> None:
        report = semantic_diff.analyze_semantic_diff("src/main.py", "def old():\n    pass\n", "def old():\n    pass\ndef added():\n    return 2\n")
        self.assertEqual(report["confidence"], "Python AST")
        self.assertIn("function added", report["added"]["definitions"])
        self.assertIn("Bounded unified diff", semantic_diff.format_semantic_report(report))


if __name__ == "__main__":
    unittest.main()
