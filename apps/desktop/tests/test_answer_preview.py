"""Roadmap 5.10.0: live diagnosis of a pasted answer (``aiwb.intake.preview``) — read-only and never raising."""
from __future__ import annotations

import copy
import io
import json
import unittest
import zipfile
from pathlib import Path

from aiwb.intake.preview import preview, preview_zip

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"


def block(data: dict) -> str:
    return "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(data) + "\n<<<AIWB_END_PROJECT_CHARTER>>>"


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.good = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_empty(self):
        p = preview("   ")
        self.assertEqual(p.kind, "empty")
        self.assertFalse(p.ok)

    def test_good_charter_counts(self):
        p = preview(block(self.good))
        self.assertEqual(p.kind, "charter")
        self.assertTrue(p.ok, p.problems)
        self.assertTrue(p.line.startswith("Charter ✓ · 4 AIs · 3 tasks · 2 milestones"), p.line)

    def test_repaired_charter_names_the_fixes(self):
        bad = copy.deepcopy(self.good)
        del bad["coordination"]
        bad["schema_version"] = 1
        text = "Here is the plan:\n```json\n" + json.dumps(bad, indent=1) + "\n```"   # no markers at all
        p = preview(text)
        self.assertEqual(p.kind, "charter")
        self.assertTrue(p.ok, p.problems)
        self.assertIn("auto-fix", p.line)
        self.assertTrue(any("coordination" in f for f in p.fixes), p.fixes)
        self.assertIn("Auto-fix:", p.details())

    def test_ambiguous_charter_is_refused_with_the_reason(self):
        bad = copy.deepcopy(self.good)
        bad["tasks"][0]["depends_on_refs"] = ["t9"]
        p = preview(block(bad))
        self.assertFalse(p.ok)
        self.assertIn("Charter ✗", p.line)
        self.assertIn("unknown task 't9'", p.line)
        self.assertIn("fix prompt", p.line)

    def test_markdown_files(self):
        p = preview("Sure!\n\n**src/a.py**\n```python\nA = 1\n```\n\n### tests/test_a.py\n```python\nimport a\n```\n")
        self.assertEqual((p.kind, p.ok, p.format), ("files", True, "markdown"))
        self.assertEqual(p.paths, ["src/a.py", "tests/test_a.py"])
        self.assertIn("Files ✓ · 2 files · Markdown code blocks", p.line)
        self.assertTrue(any("manifest" in w for w in p.warnings))

    def test_strict_json_files(self):
        js = json.dumps({"files": [{"path": "src/a.py", "content": "A=1"}], "handoff": {"summary": "s"}})
        p = preview(js)
        self.assertEqual((p.kind, p.format), ("files", "json"))
        self.assertFalse(p.warnings, "a JSON answer with a handoff object has its manifest")

    def test_cut_off_answer(self):
        p = preview("**src/a.py**\n```python\ndef f():\n")
        self.assertEqual(p.kind, "truncated")
        self.assertFalse(p.ok)
        self.assertIn("continue", p.line)

    def test_unknown_text(self):
        p = preview("Thanks! I will start tomorrow.")
        self.assertEqual(p.kind, "unknown")
        self.assertIn("Inbox", p.line)

    def test_never_raises(self):
        for junk in ("{", "<<<AIWB_PROJECT_CHARTER>>>", "```", "\x00" * 10, "<<<AIWB_FILE path=\"../x\">>>\n"):
            self.assertIsNotNone(preview(junk).line)

    def test_zip(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("proj/src/a.py", "A = 1\n")
            z.writestr("proj/README.md", "# x\n")
            z.writestr("../evil.txt", "x")
        text, p = preview_zip(b.getvalue(), "proj.zip")
        self.assertTrue(p.ok)
        self.assertEqual(sorted(p.paths), ["README.md", "src/a.py"])
        self.assertIn("ZIP ✓ · 2 files from proj.zip", p.line)
        self.assertIn("skipped", p.line)
        self.assertIn('<<<AIWB_FILE path="src/a.py"', text)
        self.assertEqual(preview(text).paths, p.paths, "the box text diagnoses to the same files")

    def test_broken_zip(self):
        text, p = preview_zip(b"not a zip", "x.zip")
        self.assertEqual(text, "")
        self.assertFalse(p.ok)
        self.assertIn("ZIP ✗", p.line)


if __name__ == "__main__":
    unittest.main()
