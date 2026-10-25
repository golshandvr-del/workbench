"""Roadmap 5.12.0 (owner audit B2): a context request as real chats write it is read, and the paste preview tells
the truth (it uses the same reader as the import).

The owner's GPT answer (``docs/audit/owner-5.11/``) used ``required_files``, had no ``type``, listed a folder
(``src/catia_bridge/``) and carried ``handoff_id``. 5.11.0 showed "Context request ✓" and then refused it.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb import context_request as cr  # noqa: E402
from aiwb.intake.preview import preview  # noqa: E402

OWNER = Path(__file__).resolve().parents[3] / "docs" / "audit" / "owner-5.11" / "HO-0006_gpt_answer_context_request.txt"


def block(data: object) -> str:
    return "<<<AIWB_CONTEXT_REQUEST>>>\n" + json.dumps(data) + "\n<<<AIWB_END_CONTEXT_REQUEST>>>"


class ForgivingReaderTests(unittest.TestCase):
    @unittest.skipUnless(OWNER.is_file(), "the owner's real answer lives in the repository")
    def test_owner_answer(self):
        text = OWNER.read_text(encoding="utf-8")
        r = cr.parse_request(text)
        self.assertEqual([(i.path, i.mode) for i in r.items],
                         [("src/contracts/models.py", "full_file"), ("src/contracts/__init__.py", "full_file"),
                          ("docs/contracts/catia-bridge-spec.md", "full_file"), ("src/catia_bridge/", "folder")])
        self.assertEqual(r.attempt_id, "att-20261023-192855-0ba9959e")
        self.assertEqual(r.handoff_id, "HO-0006")
        self.assertTrue(any("required_files" in f for f in r.fixes), r.fixes)
        p = preview(text)
        self.assertTrue(p.ok, p.line)
        self.assertIn("4 files", p.line)

    @unittest.skipUnless(OWNER.is_file(), "the owner's real answer lives in the repository")
    def test_owner_answer_copied_as_rendered_text(self):
        text = OWNER.read_text(encoding="utf-8").replace("\r", "")
        damaged = "\n".join(line + "\\" if line.strip() else line for line in text.split("\n"))
        r = cr.parse_request(damaged)
        self.assertEqual(len(r.items), 4)
        self.assertTrue(any(f.startswith("copy_damage:") for f in r.fixes), r.fixes)
        self.assertTrue(preview(damaged).ok)

    def test_synonyms_and_plain_paths(self):
        for key in ("files", "required_files", "requested_files", "files_needed", "paths", "context_files"):
            r = cr.parse_request(block({key: ["a.py", {"file": "b.py"}, {"filename": "c.py", "mode": "whole"}]}))
            self.assertEqual([(i.path, i.mode) for i in r.items],
                             [("a.py", "full_file"), ("b.py", "full_file"), ("c.py", "full_file")], key)

    def test_range_shorthands(self):
        r = cr.parse_request(block({"files": [{"path": "a.py", "start_line": 3, "end_line": "9"},
                                              {"path": "b.py", "mode": "lines", "ranges": [[1, 4]]}]}))
        self.assertEqual([(i.path, i.mode, i.ranges) for i in r.items],
                         [("a.py", "range", [(3, 9)]), ("b.py", "range", [(1, 4)])])

    def test_single_item_and_string_question(self):
        r = cr.parse_request(block({"files": "a.py", "questions": "Which Python version?"}))
        self.assertEqual([i.path for i in r.items], ["a.py"])
        self.assertEqual(r.questions, ["Which Python version?"])

    def test_missing_end_marker_and_json_comments(self):
        r = cr.parse_request('<<<AIWB_CONTEXT_REQUEST>>>\n{"files": ["a.py",], // need it\n}')
        self.assertEqual([i.path for i in r.items], ["a.py"])

    def test_preview_tells_the_truth(self):
        bad = "<<<AIWB_CONTEXT_REQUEST>>>\n{\"reason\": \"x\"}\n<<<AIWB_END_CONTEXT_REQUEST>>>"
        p = preview(bad)
        self.assertEqual(p.kind, "context_request")
        self.assertFalse(p.ok)
        self.assertIn("✗", p.line)

    def test_folder_expands_to_its_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pkg" / "sub").mkdir(parents=True)
            (root / "pkg" / "a.py").write_text("A = 1\n", encoding="utf-8")
            (root / "pkg" / "sub" / "b.py").write_text("B = 2\n", encoding="utf-8")
            (root / "pkg" / "__pycache__").mkdir()
            (root / "pkg" / "__pycache__" / "a.pyc").write_bytes(b"x")
            r = cr.parse_request(block({"files": ["pkg/", "empty/"]}))
            out = cr.resolve(r, root, path_problem=lambda p: "", is_sensitive=lambda p: False)
            ready = sorted(x.path for x in out if x.deliverable)
            self.assertEqual(ready, ["pkg/a.py", "pkg/sub/b.py"])
            self.assertTrue(any(x.path == "empty/" and x.status == "missing" for x in out))

    def test_folder_outside_the_project_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            r = cr.parse_request(block({"files": ["../"]}))
            out = cr.resolve(r, Path(d), path_problem=lambda p: "", is_sensitive=lambda p: False)
            self.assertFalse(any(x.deliverable for x in out))


if __name__ == "__main__":
    unittest.main()
