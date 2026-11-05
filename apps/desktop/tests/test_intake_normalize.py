"""Gate 3.2.0 — reliable intake of model output (roadmap 3.x, problem P7).

The shared corpus ``packages/contracts/fixtures/intake/chat-copy-corpus.v1.json`` holds
real chat-copy breakage patterns (ChatGPT / Gemini / Claude / Windows clipboard).
* every *broken* case imports to exactly the expected files;
* every *healthy* case imports unchanged (the raw-first path is taken);
* every *truncated* case is detected and gets a "continue" prompt.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import AI_Workbench as wb  # noqa: E402
from aiwb.intake import continue_prompt, normalize, normalize_json_text, truncation_report  # noqa: E402

CORPUS = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures" / "intake" / "chat-copy-corpus.v1.json"


def load() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@unittest.skipUnless(CORPUS.exists(), "shared contracts corpus is only present in the repository checkout")
class CorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = load()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def files(self, text: str) -> dict[str, str]:
        payload, _changes, _fmt = wb.validate_any_model_response(text, self.root)
        return {f["path"]: f["content"] for f in payload["files"]}

    def test_corpus_size(self) -> None:
        self.assertGreaterEqual(len(self.data["broken"]), 30)

    def test_every_broken_case_imports(self) -> None:
        for case in self.data["broken"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(self.files(case["text"]), case["expect_files"])

    def test_healthy_cases_unchanged(self) -> None:
        for case in self.data["healthy"]:
            with self.subTest(case=case["id"]):
                payload, _c, fmt = wb.validate_any_model_response(case["text"], self.root)
                self.assertNotIn("cleaned", fmt)
                self.assertEqual({f["path"]: f["content"] for f in payload["files"]}, case["expect_files"])

    def test_normalize_only_cases(self) -> None:
        for case in self.data["normalize_only"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(json.loads(normalize(case["text"]).text), case["expect_json"])

    def test_truncated_cases_detected_with_continue_prompt(self) -> None:
        for case in self.data["truncated"]:
            with self.subTest(case=case["id"]):
                rep = truncation_report(case["text"])
                self.assertTrue(rep.truncated)
                self.assertEqual(rep.reason, case["reason"])
                if "open" in case:
                    self.assertEqual(rep.open_path, case["open"])
                    self.assertEqual(rep.completed_paths, case["done"])
                prompt = continue_prompt(rep, attempt_id="a1")
                self.assertIn("cut off", prompt)
                self.assertIn("<<<AIWB_END_FILE>>>", prompt)

    def test_complete_answers_are_not_truncated(self) -> None:
        for case in self.data["healthy"] + self.data["broken"]:
            with self.subTest(case=case["id"]):
                self.assertFalse(truncation_report(case["text"]).truncated)


class NormalizeUnitTests(unittest.TestCase):
    def test_clean_text_reports_no_fixes(self) -> None:
        self.assertFalse(normalize('<<<AIWB_FILE path="a" action="write">>>\nx\n<<<AIWB_END_FILE>>>\n').changed)

    def test_body_is_not_rewritten(self) -> None:
        body = 'He said \u201chi\u201d &amp; \\_x\\_ <<<not a marker'
        text = f'<<<AIWB_FILE path="a.md" action="write" body="raw">>>\n{body}\n<<<AIWB_END_FILE>>>\n'
        self.assertIn(body, normalize(text).text)

    def test_json_strings_untouched(self) -> None:
        src = '{"a": "// not a comment, /* nor this */", "b": [1, 2,],}'
        out = normalize_json_text(src)
        self.assertEqual(json.loads(out.text), {"a": "// not a comment, /* nor this */", "b": [1, 2]})

    def test_bf054_invisible_unicode_survives_repaired_headers_and_json(self):
        body = "می\u200cروم 👩\u200d💻 x\u00a0y"
        text = '<<<AIWB_FILE path=“a.txt” body="raw">>>\n' + body + '\n<<<AIWB_END_FILE>>>'
        self.assertIn(body, normalize(text).text)
        js = json.dumps({"files": [{"path": "a.txt", "content": body}]}, ensure_ascii=False)
        self.assertEqual(json.loads(normalize(js[:-1] + ",}").text)["files"][0]["content"], body)

    def test_bf054_smart_delimited_json_keeps_joiners(self):
        body = "می\u200cروم 👩\u200d💻 x\u00a0y"
        text = '{“content”: “' + body + '”,}'
        self.assertEqual(json.loads(normalize(text).text)["content"], body)

    def test_bf093_raw_folder_slashes_and_shell_continuations_survive(self):
        from aiwb.intake.normalize import strip_copy_damage
        for char in ("/", "\\"):
            body = "\n".join("folder" + str(i) + char for i in range(5))
            text = '<<<AIWB_FILE path=".gitignore" body="raw">>>\n' + body + '\n<<<AIWB_END_FILE>>>'
            self.assertEqual(strip_copy_damage(text), text)

    def test_bf094_trailing_comma_repair_keeps_smart_quotes_inside_ascii_strings(self):
        text = '{"files": [{"path": "a.txt", "content": "Click “Save”, then go"}],}'
        out = normalize_json_text(text)
        self.assertTrue(out.changed)
        self.assertEqual(json.loads(out.text)["files"][0]["content"], "Click “Save”, then go")

    def test_bf092_balanced_json_preserves_typographic_quotes(self):
        from aiwb.intake.lenient import find_object
        text = json.dumps({"files": [{"path": "a.txt", "content": "Press “Save” now"}]}, ensure_ascii=False)
        found = find_object(text, keys=("files",))
        self.assertFalse(found.truncated)
        self.assertEqual(json.loads(found.text), json.loads(text))

    def test_bf053_stray_prose_brace_does_not_hide_complete_files(self):
        from aiwb.intake.answer_files import extract
        text = 'Example { placeholder\n' + json.dumps({"files": [{"path": "a.txt", "content": "ok"}]})
        ex = extract(text)
        self.assertFalse(ex.truncated)
        self.assertEqual(ex.files, [{"path": "a.txt", "content": "ok\n"}])

    def test_valid_json_untouched(self) -> None:
        self.assertFalse(normalize_json_text('{"a": 1}').changed)


if __name__ == "__main__":
    unittest.main()
