"""Tests for aiwb.inbox (roadmap 1.16.0/1.16.1): raw-first storage, classification,
staged pipeline with the real Workbench validators, salvage, attempts and error codes."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import AI_Workbench as wb  # noqa: E402
from aiwb.inbox import (AttemptRegistry, ERROR_CODES, ImportIssue, ImportPipeline, InboxStore,  # noqa: E402
                        declared_attempt_id, explain, prompt_identity_block, repair_prompt, salvage_aiwb_blocks)
from aiwb.inbox.classify import classify, looks_truncated  # noqa: E402
from aiwb.inbox.errors import classify_error_message  # noqa: E402

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def block(path: str, body: str, end: bool = True) -> str:
    s = f'<<<AIWB_FILE path="{path}" action="write" body="raw">>>\n{body}\n'
    return s + ("<<<AIWB_END_FILE>>>\n" if end else "")


def make_pipeline(root: Path, task=("t-1",), rev=("r1",)) -> ImportPipeline:
    def validate(text: str):
        return wb.validate_any_model_response(text, root)

    def parse_block(seg: str):
        return wb.parse_aiwb_file_blocks(seg)

    def validate_payload(payload):
        return wb.validate_model_response(json.dumps(payload), root)

    def path_problem(p: str) -> str:
        try:
            wb.validate_relative_path(root, p)
            return ""
        except wb.WorkbenchError as exc:
            return wb.redact(str(exc))

    return ImportPipeline(InboxStore(root), AttemptRegistry(root), validate,
                          current_task_id=lambda: task[0], current_base_revision=lambda: rev[0],
                          redact=wb.redact, path_problem=path_problem, parse_block=parse_block,
                          validate_payload=validate_payload)


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = InboxStore(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_raw_is_byte_identical_and_deduplicated(self) -> None:
        raw = "\ufeffhello\r\nwörld\r\n".encode("utf-8") + b"\xff"
        rec, dup = self.store.capture(raw, source="paste")
        self.assertFalse(dup)
        self.assertEqual(self.store.read_raw(rec.response_id), raw)
        rec2, dup2 = self.store.capture(raw, source="file")
        self.assertTrue(dup2)
        self.assertEqual(rec2.response_id, rec.response_id)
        self.assertEqual(len(self.store.list()), 1)

    def test_parse_results_never_touch_raw(self) -> None:
        rec, _ = self.store.capture("x", source="paste")
        for i in range(25):
            self.store.add_parse_result(rec.response_id, {"status": "failed", "n": i})
        r = self.store.get(rec.response_id)
        self.assertEqual(len(r.parse_results), 20)
        self.assertEqual(r.parse_results[-1]["n"], 24)
        self.assertEqual(self.store.read_text(rec.response_id), "x")
        with self.assertRaises(ValueError):
            self.store.update(rec.response_id, sha256="0")

    def test_tampered_raw_is_detected_and_ids_are_safe(self) -> None:
        rec, _ = self.store.capture("abc", source="paste")
        (self.store.raw_dir / f"{rec.response_id}.raw").write_text("abd", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.read_raw(rec.response_id)
        with self.assertRaises(ValueError):
            self.store.read_raw("../../etc/passwd")

    def test_too_large_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.store.capture(b"x" * (12 * 1024 * 1024 + 1), source="paste")

    def test_concurrent_capture_keeps_every_response(self) -> None:
        errs = []

        def work(i: int) -> None:
            try:
                self.store.capture(f"r{i}", source="paste")
            except Exception as exc:  # noqa: BLE001
                errs.append(exc)
        ts = [threading.Thread(target=work, args=(i,)) for i in range(16)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errs, [])
        self.assertEqual(len(self.store.list()), 16)

    def test_corrupt_index_does_not_crash(self) -> None:
        self.store.root.mkdir(parents=True, exist_ok=True)
        self.store.index_path.write_text("{broken", encoding="utf-8")
        self.assertEqual(self.store.list(), [])
        rec, _ = self.store.capture("new", source="paste")
        self.assertEqual(self.store.get(rec.response_id).response_id, rec.response_id)


class ClassifyTests(unittest.TestCase):
    def test_suggestions(self) -> None:
        self.assertEqual(classify(block("a.py", "x"))[0].parser, "aiwb_blocks")
        self.assertEqual(classify('{"protocol": "workbench-v2", "files": []}')[0].parser, "json")
        self.assertEqual(classify('{"protocol": "workbench-context-v1"}')[0].parser, "context_plan")
        self.assertEqual(classify("just some prose"), [])

    def test_truncation(self) -> None:
        self.assertTrue(looks_truncated(block("a.py", "x", end=False)))
        self.assertTrue(looks_truncated('{"protocol": "workbench-v2", "files": [{"path": "a'))
        self.assertTrue(looks_truncated("```python\nprint(1)\n"))
        self.assertFalse(looks_truncated(block("a.py", "x")))
        self.assertFalse(looks_truncated('{"a": 1}'))


class AttemptTests(unittest.TestCase):
    def test_identity_roundtrip_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            reg = AttemptRegistry(Path(t))
            a = reg.new(task_id="t", task_revision="tr", base_revision="b", expected_paths=["b.py", "a.py", "a.py"])
            self.assertEqual(a.expected_paths, ["a.py", "b.py"])
            self.assertEqual(declared_attempt_id(prompt_identity_block(a) + "\nmore"), a.attempt_id)
            self.assertEqual(declared_attempt_id(f"**AIWB_ATTEMPT_ID:** `{a.attempt_id}`"), a.attempt_id)
            self.assertEqual(declared_attempt_id("AIWB_ATTEMPT_ID: att-bad"), "")
            reg.mark(a.attempt_id, "answered")
            self.assertEqual(reg.get(a.attempt_id).status, "answered")
            self.assertEqual(reg.latest_for_task("t").attempt_id, a.attempt_id)
            with self.assertRaises(ValueError):
                reg.mark(a.attempt_id, "bogus")


class ErrorCodeTests(unittest.TestCase):
    def test_every_code_explains_and_unknown_rejected(self) -> None:
        for code, (stage, _t, _n) in ERROR_CODES.items():
            text = explain(ImportIssue(code, stage, "d"))
            self.assertIn(f"[{code}]", text)
            self.assertIn("Next:", text)
            self.assertIn("no project file was changed", text)
        with self.assertRaises(ValueError):
            ImportIssue("nope", "parse")

    def test_message_mapping(self) -> None:
        self.assertEqual(classify_error_message("The model response is empty."), "empty_response")
        self.assertEqual(classify_error_message("File block for 'a' is missing <<<AIWB_END_FILE>>>."), "truncated")
        self.assertEqual(classify_error_message("Path must be relative: /etc/x"), "unsafe_path")
        self.assertEqual(classify_error_message("This is a context plan, not an implementation response."), "context_plan")


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj ü"
        self.root.mkdir()
        (self.root / "keep.txt").write_text("orig\n", encoding="utf-8")
        self.task, self.rev = ["t-1"], ["r1"]
        self.pipe = make_pipeline(self.root, self.task, self.rev)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_text(self, text: str, **kw):
        cap = self.pipe.capture_text(text, **kw)
        self.assertIsNotNone(cap.response)
        return self.pipe.process(cap.response.response_id)

    def assert_no_project_writes(self) -> None:
        files = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")
                       if p.is_file() and ".workbench" not in p.parts)
        self.assertEqual(files, ["keep.txt"])
        self.assertEqual((self.root / "keep.txt").read_text(encoding="utf-8"), "orig\n")

    def test_valid_blocks_parse_without_writing(self) -> None:
        out = self.run_text(block("src/a.py", "print(1)") + block("b.txt", "hi"))
        self.assertEqual(out.status, "parsed", [i.to_dict() for i in out.issues])
        self.assertTrue(out.can_preview)
        self.assertEqual(sorted(c.path for c in out.changes), ["b.txt", "src/a.py"])
        self.assert_no_project_writes()
        self.assertEqual(self.pipe.store.get(out.response.response_id).status, "parsed")

    def test_valid_json(self) -> None:
        out = self.run_text(json.dumps({"protocol": "workbench-v2", "summary": "s",
                                        "files": [{"path": "x.py", "content": "1\n"}]}))
        self.assertEqual(out.status, "parsed", [i.to_dict() for i in out.issues])

    def test_empty_and_duplicate_capture(self) -> None:
        self.assertEqual(self.pipe.capture_text("  \n").issue.code, "empty_response")
        a = self.pipe.capture_text("same")
        b = self.pipe.capture_text("same")
        self.assertTrue(b.duplicate)
        self.assertEqual(b.issue.code, "duplicate_response")
        self.assertEqual(a.response.response_id, b.response.response_id)

    def test_truncated_json_keeps_raw_and_explains(self) -> None:
        raw = '{"protocol": "workbench-v2", "summary": "s", "files": [{"path": "a.py", "content": "pri'
        out = self.run_text(raw)
        self.assertEqual(out.status, "failed")
        self.assertIn("truncated", [i.code for i in out.issues])
        self.assertEqual(self.pipe.store.read_text(out.response.response_id), raw)
        self.assert_no_project_writes()

    def test_unknown_prose(self) -> None:
        out = self.run_text("Sure! Here is how you could do it, in words only.")
        self.assertEqual(out.status, "failed")
        self.assertTrue(out.issues)
        self.assertEqual(out.salvage_paths, [])

    def test_partial_salvage_keeps_complete_blocks_only(self) -> None:
        raw = block("ok.py", "1") + block("also.py", "2") + block("cut.py", "3", end=False)
        out = self.run_text(raw)
        self.assertEqual(out.status, "partial", [i.to_dict() for i in out.issues])
        self.assertEqual(out.salvage_paths, ["also.py", "ok.py"])
        self.assertIn("cut.py", out.salvage.broken)
        self.assertEqual(sorted(c.path for c in out.changes), ["also.py", "ok.py"])
        self.assertIn("partial_parse", [i.code for i in out.issues])
        prompt = repair_prompt(out.salvage, attempt_id="att-20261018-000000-deadbeef")
        self.assertIn("cut.py", prompt)
        self.assertIn("do NOT resend", prompt)
        self.assert_no_project_writes()

    def test_salvage_rejects_unsafe_and_duplicate_paths(self) -> None:
        raw = block("ok.py", "1") + block("../x.py", "2") + block("d.py", "a") + block("d.py", "b") + block("c.py", "3", end=False)
        out = self.run_text(raw)
        self.assertEqual(out.salvage_paths, ["ok.py"])
        self.assertIn("../x.py", out.salvage.broken)
        self.assertEqual(out.salvage.duplicates, ["d.py"])
        self.assert_no_project_writes()

    def test_unsafe_path_in_full_response(self) -> None:
        out = self.run_text(json.dumps({"protocol": "workbench-v2", "summary": "s",
                                        "files": [{"path": "../evil.py", "content": "x"}]}))
        self.assertEqual(out.status, "failed")
        self.assertFalse(out.can_preview)
        self.assert_no_project_writes()

    def test_attempt_reconcile_ok_mismatch_stale_unknown(self) -> None:
        reg = self.pipe.attempts
        a = reg.new(task_id="t-1", task_revision="1", base_revision="r1", expected_paths=["a.py"])
        out = self.run_text(prompt_identity_block(a) + "\n" + block("a.py", "1"))
        self.assertEqual(out.status, "parsed")
        self.assertEqual(out.attempt.attempt_id, a.attempt_id)
        self.assertEqual(reg.get(a.attempt_id).status, "answered")

        other = reg.new(task_id="t-OLD", task_revision="1", base_revision="r1")
        out = self.run_text(prompt_identity_block(other) + "\n" + block("a.py", "2"))
        self.assertIn("attempt_mismatch", [i.code for i in out.issues])
        self.assertFalse(out.can_preview)

        self.rev[0] = "r2"
        out = self.run_text(prompt_identity_block(a) + "\n" + block("a.py", "3"))
        self.assertIn("stale_base", [i.code for i in out.issues])
        self.assertTrue(out.can_preview)  # warning only

        out = self.run_text("AIWB_ATTEMPT_ID: att-20200101-000000-00000000\n" + block("a.py", "4"))
        self.assertIn("attempt_unknown", [i.code for i in out.issues])

    def test_missing_expected_path_reported_in_salvage(self) -> None:
        a = self.pipe.attempts.new(task_id="t-1", task_revision="1", base_revision="r1",
                                   expected_paths=["a.py", "b.py", "c.py"])
        out = self.run_text(prompt_identity_block(a) + "\n" + block("a.py", "1") + block("b.py", "2", end=False))
        self.assertEqual(out.status, "partial")
        self.assertEqual(out.salvage.missing, ["c.py"])

    def test_reparse_uses_stored_raw_and_appends_result(self) -> None:
        out = self.run_text(block("a.py", "1"))
        again = self.pipe.reparse(out.response.response_id)
        self.assertEqual(again.status, "parsed")
        self.assertEqual(len(self.pipe.store.get(out.response.response_id).parse_results), 2)

    def test_token_redacted_in_issue_details(self) -> None:
        raw = json.dumps({"protocol": "workbench-v2", "summary": "s",
                          "files": [{"path": f"https://x:{TOKEN}@github.com/a.py", "content": "x"}]})
        out = self.run_text(raw)
        stored = json.dumps(self.pipe.store.get(out.response.response_id).parse_results)
        self.assertNotIn(TOKEN, stored)
        self.assertNotIn(TOKEN, " ".join(explain(i) for i in out.issues))

    def test_malicious_zip_names_never_reach_salvage(self) -> None:
        # ZIP adapter is separate; ensure salvage alone refuses absolute/drive paths
        res = salvage_aiwb_blocks(block("C:/x.py", "1") + block("/etc/p", "2") + block("fine.py", "3"))
        self.assertEqual(sorted(res.complete), ["fine.py"])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.txt", "x")
        self.assertTrue(buf.getvalue())


if __name__ == "__main__":
    unittest.main()
