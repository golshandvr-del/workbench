"""Tests for roadmap 1.16.2: smart repair plan from Inbox evidence and the redacted
local diagnostics bundle."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import AI_Workbench as wb  # noqa: E402
from aiwb import diagnostics  # noqa: E402
from aiwb.inbox import declared_attempt_id, prompt_identity_block  # noqa: E402
from aiwb.inbox.repair import MAX_REPAIR_CHAIN, plan_repair, repair_chain_depth  # noqa: E402

TOKEN = "ghp_" + "Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2"


def block(path: str, body: str, end: bool = True) -> str:
    s = f'<<<AIWB_FILE path="{path}" action="write" body="raw">>>\n{body}\n'
    return s + ("<<<AIWB_END_FILE>>>\n" if end else "")


class RepairPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()
        (self.root / "keep.py").write_text("x = 1\n", encoding="utf-8")
        wb.save_task_state(self.root, {"task_id": "task-1", "task_text": "Add a and b"})
        self.pipe = wb.make_inbox_pipeline(self.root)
        self.att = self.pipe.attempts.new(task_id="task-1", task_revision="r", base_revision="b",
                                          expected_paths=["a.py", "b.py", "c.py"])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def outcome(self, text: str):
        cap = self.pipe.capture_text(text)
        return self.pipe.process(cap.response.response_id)

    def test_plan_lists_keep_and_redo_and_registers_child_attempt(self) -> None:
        out = self.outcome(prompt_identity_block(self.att) + "\n" + block("a.py", "A=1") + block("b.py", "B", end=False))
        plan = plan_repair(out, self.pipe.attempts, task_id="task-1")
        self.assertEqual(plan.keep, ["a.py"])
        self.assertEqual(plan.redo, ["b.py", "c.py"])
        self.assertIsNotNone(plan.attempt)
        self.assertEqual(plan.attempt.kind, "repair")
        self.assertEqual(plan.attempt.parent_attempt_id, self.att.attempt_id)
        self.assertEqual(plan.attempt.expected_paths, ["b.py", "c.py"])
        self.assertEqual(declared_attempt_id(plan.section), plan.attempt.attempt_id)
        self.assertIn("do NOT regenerate", plan.section)
        self.assertIn("[partial_parse]", plan.section)
        self.assertIn(self.att.attempt_id, plan.section)

    def test_chain_limit_stops_endless_repairs(self) -> None:
        parent = self.att
        for _ in range(MAX_REPAIR_CHAIN):
            parent = self.pipe.attempts.new(task_id="task-1", task_revision="r", base_revision="b",
                                            kind="repair", parent_attempt_id=parent.attempt_id)
        self.assertEqual(repair_chain_depth(self.pipe.attempts, parent.attempt_id), MAX_REPAIR_CHAIN)
        out = self.outcome(prompt_identity_block(parent) + "\n" + block("a.py", "1", end=False))
        plan = plan_repair(out, self.pipe.attempts)
        self.assertTrue(plan.needs_decision)
        self.assertIsNone(plan.attempt)
        self.assertIn("STOP", plan.section)

    def test_chain_depth_is_cycle_safe(self) -> None:
        a = self.pipe.attempts.new(task_id="t", task_revision="", base_revision="", kind="repair")
        b = self.pipe.attempts.new(task_id="t", task_revision="", base_revision="", kind="repair",
                                   parent_attempt_id=a.attempt_id)
        items = self.pipe.attempts._load()
        for it in items:
            if it.attempt_id == a.attempt_id:
                it.parent_attempt_id = b.attempt_id
        self.pipe.attempts._save(items)
        self.assertEqual(repair_chain_depth(self.pipe.attempts, b.attempt_id), 2)

    def test_build_repair_prompt_embeds_inbox_section_identity_first(self) -> None:
        out = self.outcome(prompt_identity_block(self.att) + "\n" + block("a.py", "A=1") + block("b.py", "B", end=False))
        plan = plan_repair(out, self.pipe.attempts, task_id="task-1")
        prompt = wb.build_repair_prompt(self.root, error="cut off", failure_stage="import", inbox_evidence=plan.section)
        self.assertTrue(prompt.startswith("AIWB_ATTEMPT_ID: " + plan.attempt.attempt_id))
        self.assertIn("Response Inbox", prompt)
        self.assertIn("- a.py", prompt)
        self.assertNotIn("A=1", prompt)  # raw content is never echoed
        self.assertIn("Do not claim the code was run", prompt)

    def test_repair_prompt_without_evidence_is_unchanged(self) -> None:
        prompt = wb.build_repair_prompt(self.root, error="boom", failure_stage="runtime/test")
        self.assertTrue(prompt.startswith("# AI Workbench — Repair Task"))


class DiagnosticsBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "Secret Project ü"
        self.root.mkdir()
        (self.root / "src.py").write_text("TOP_SECRET_SOURCE = 1\n", encoding="utf-8")
        wb.save_task_state(self.root, {"task_id": "task-9", "task_text": "PRIVATE TASK TEXT",
                                       "workflow_stage": "Import Failed",
                                       "last_response_error": f"push to https://x:{TOKEN}@github.com failed"})
        wb.append_execution_event(self.root, {"type": "action_finished", "status": "failed",
                                              "output": "TOP_SECRET_SOURCE leaked in output",
                                              "message": f"error in {self.root}/src.py token={TOKEN}"})
        pipe = wb.make_inbox_pipeline(self.root)
        cap = pipe.capture_text("RAW RESPONSE BODY\n" + block("a.py", "1", end=False))
        pipe.process(cap.response.response_id)
        self.log = base / "app.log"
        self.log.write_text(f"Traceback in {Path.home()}/x.py\nAuthorization: Bearer {TOKEN}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def collect(self, **kw):
        return diagnostics.collect_bundle(self.root, app_version=wb.APP_VERSION, app_log=self.log, redact=wb.redact,
                                          read_json=wb.read_project_json, **kw)

    def test_default_bundle_excludes_private_data(self) -> None:
        entries = self.collect()
        names = [e.name for e in entries]
        self.assertEqual(names, ["report.json", "app_log_tail.txt", "execution_events_recent.json",
                                 "task_state.json", "inbox_parse_results.json"])
        blob = "\n".join(e.content for e in entries)
        for secret in (TOKEN, "TOP_SECRET_SOURCE", "PRIVATE TASK TEXT", "RAW RESPONSE BODY", str(self.root),
                       str(Path.home())):
            self.assertNotIn(secret, blob, secret)
        self.assertIn("<PROJECT>", blob)
        report = json.loads(entries[0].content)
        self.assertTrue(report["report_id"].startswith("diag-"))
        self.assertEqual(report["workbench_version"], wb.APP_VERSION)
        inbox_rows = json.loads(entries[-1].content)
        self.assertEqual(inbox_rows[0]["status"], "failed")
        self.assertIn("truncated", inbox_rows[0]["issue_codes"])

    def test_opt_ins_are_separate_and_marked(self) -> None:
        entries = self.collect(include_task_text=True, include_full_history=True)
        opt = {e.name for e in entries if e.optional}
        self.assertEqual(opt, {"task_text.txt", "execution_history_full.json"})
        self.assertIn("PRIVATE TASK TEXT", next(e.content for e in entries if e.name == "task_text.txt"))
        self.assertNotIn(TOKEN, "\n".join(e.content for e in entries))
        self.assertIn("[opt-in]", diagnostics.preview_text(entries))

    def test_write_bundle_matches_preview_and_never_overwrites(self) -> None:
        entries = self.collect()
        dest = Path(self.tmp.name) / "diag.zip"
        diagnostics.write_bundle(entries, dest)
        with zipfile.ZipFile(dest) as zf:
            self.assertEqual(zf.namelist(), [e.name for e in entries])
            self.assertEqual(zf.read("task_state.json").decode(), entries[3].content)
        with self.assertRaises(FileExistsError):
            diagnostics.write_bundle(entries, dest)

    def test_no_project_selected(self) -> None:
        entries = diagnostics.collect_bundle(None, app_version="x", app_log=None, redact=wb.redact)
        self.assertEqual([e.name for e in entries], ["report.json", "execution_events_recent.json"])



class PathScrubTests(unittest.TestCase):
    def test_json_escaped_and_slash_variants(self) -> None:
        from aiwb import diagnostics as d
        win = "C:\\Users\\RUNNER~1\\AppData\\Local\\Temp\\tmpx\\Secret Project"
        text = json.dumps({"m": "error in " + win + "\\src.py"}) + " " + win.replace("\\", "/") + "/a.py"
        out = d._scrub_paths(text, {win: "<PROJECT>"})
        self.assertNotIn("Secret Project", out)
        self.assertEqual(out.count("<PROJECT>"), 2)
        self.assertNotIn("RUNNER~1", d._scrub_paths("see C:\\\\Users\\\\RUNNER~1\\\\x", {}))


if __name__ == "__main__":
    unittest.main()
