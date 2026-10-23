"""Roadmap 5.10.0 (A13): files from AIWB blocks, Markdown, Strict JSON and ZIP — parser and the guided loop."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.intake.answer_files import (canonical, canonical_zip, clean_path, extract, fence_for,  # noqa: E402
                                      zip_files)
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.diagnose import parse_files  # noqa: E402
from aiwb.v2.guide import Guide  # noqa: E402


def make_zip(entries: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in entries.items():
            z.writestr(name, body)
    return buf.getvalue()


class PathTests(unittest.TestCase):
    def test_paths_are_taken_from_labels_only(self):
        self.assertEqual(clean_path("`src/app.py`"), "src/app.py")
        self.assertEqual(clean_path("src/app.py — the main loop"), "src/app.py")
        self.assertEqual(clean_path("./src/app.py (new)"), "src/app.py")
        self.assertEqual(clean_path("Dockerfile"), "Dockerfile")
        for bad in ("Example usage", "1.2.3", "https://x.org/a.js", "my file.py", "src/", ""):
            self.assertEqual(clean_path(bad), "", bad)


class MarkdownTests(unittest.TestCase):
    def test_every_common_label_style(self):
        md = "\n".join([
            "Here is the implementation.", "",
            "**src/game.py**", "```python", "def main():", "    print('hi')", "```", "",
            "### tests/test_game.py", "```python", "import unittest", "```", "",
            "`README.md`:", "```markdown", "# Snake", "```", "",
            "File: src/util.py", "", "```python", "X = 1", "```", "",
            "Here is `src/conf.json`:", "```json", "{}", "```", "",
            '```python title="src/b.py"', "B = 2", "```", "",
            "```js", "// file: web/app.js", "let a = 1;", "```", "",
            "1. **`src/c.py`**", "```python", "C = 3", "```", "",
            "Run it:", "```bash", "python src/game.py", "```"])
        ex = extract(md)
        self.assertEqual(ex.format, "markdown")
        self.assertEqual([f["path"] for f in ex.files],
                         ["src/game.py", "tests/test_game.py", "README.md", "src/util.py", "src/conf.json", "src/b.py",
                          "web/app.js", "src/c.py"])
        self.assertEqual(ex.files[0]["content"], "def main():\n    print('hi')\n")
        self.assertFalse(ex.truncated)

    def test_unlabelled_code_is_never_given_a_name(self):
        self.assertEqual(extract("Try this:\n```python\nprint(1)\n```\n").files, [])
        ex = extract("**a.py**\n```python\nA=1\n```\nAnd also:\n```python\nprint(2)\n```\n")
        self.assertEqual([f["path"] for f in ex.files], ["a.py"])
        self.assertIn("without a file name were ignored", " ".join(ex.fixes))

    def test_inner_triple_backticks_survive_a_longer_fence(self):
        body = "# Title\n\n```python\nx = 1\n```\n"
        ex = extract("**README.md**\n````markdown\n" + body + "````\n")
        self.assertEqual(ex.files[0]["content"], body)

    def test_cut_off_markdown_is_reported(self):
        ex = extract("**src/a.py**\n```python\ndef f():\n    pass\n")
        self.assertTrue(ex.truncated)

    def test_last_version_of_a_repeated_file_wins(self):
        ex = extract("**a.py**\n```\nA=1\n```\n**a.py**\n```\nA=2\n```\n")
        self.assertEqual(ex.files, [{"path": "a.py", "content": "A=2\n"}])
        self.assertIn("given twice", " ".join(ex.fixes))


class JsonTests(unittest.TestCase):
    def test_strict_json_with_handoff_and_attempt(self):
        js = ("```json\n" + json.dumps({"attempt_id": "att-0001", "files": [{"path": "src/a.py", "content": "x=1"}],
                                         "handoff": {"summary": "ok", "outcome": "complete"}}) + "\n```")
        ex = extract(js)
        self.assertEqual((ex.format, ex.attempt_id), ("json", "att-0001"))
        self.assertEqual(ex.files, [{"path": "src/a.py", "content": "x=1\n"}])
        self.assertEqual(ex.manifest, {"summary": "ok", "outcome": "complete"})
        text, _ = canonical(js)
        self.assertEqual(parse_files(text)[0][0]["path"], "src/a.py")
        self.assertIn("<<<AIWB_HANDOFF>>>", text)

    def test_json_variants_are_read_and_reported(self):
        js = '{"protocol": "workbench-v1", "summary": "two files", "files": {"a.py": ["x = 1", "y = 2"], "b.txt": "hi"},}'
        ex = extract("Answer:\n" + js)
        self.assertEqual(ex.format, "json")
        self.assertEqual(ex.files, [{"path": "a.py", "content": "x = 1\ny = 2\n"}, {"path": "b.txt", "content": "hi\n"}])
        joined = " ".join(ex.fixes)
        self.assertIn("dictionary", joined)
        self.assertIn("list of lines", joined)
        self.assertIn("JSON repaired", joined)
        self.assertEqual(ex.manifest, {"summary": "two files"})

    def test_deletes_and_broken_items_are_skipped_with_a_reason(self):
        ex = extract(json.dumps({"files": [{"path": "a.py", "action": "delete"}, {"content": "x"},
                                           {"path": "b.py", "code": "B=1"}]}))
        self.assertEqual([f["path"] for f in ex.files], ["b.py"])
        self.assertEqual(len(ex.problems), 2)


class AiwbTests(unittest.TestCase):
    def test_escaped_markers_are_repaired_and_listed(self):
        esc = ('\\<\\<\\<AIWB\\_FILE path="src/b.py" action="write"\\>\\>\\>\n````\nprint(1)\n````\n'
               '\\<\\<\\<AIWB\\_END\\_FILE\\>\\>\\>')
        text, ex = canonical(esc)
        self.assertEqual(ex.format, "aiwb")
        self.assertIn("repaired", ex.fixes[0])
        self.assertEqual(parse_files(text)[0][0], {"path": "src/b.py", "body": "print(1)", "fenced": True,
                                                   "fence_balanced": True})

    def test_clean_aiwb_answers_come_back_unchanged(self):
        t = 'AIWB_ATTEMPT_ID: att-1\n<<<AIWB_FILE path="a.py" action="write">>>\n````\nA=1\n````\n<<<AIWB_END_FILE>>>\n'
        out, ex = canonical(t)
        self.assertEqual(out, t)
        self.assertEqual(ex.attempt_id, "att-1")

    def test_fence_is_longer_than_any_backtick_run_in_the_body(self):
        self.assertEqual(fence_for("a"), "````")
        self.assertEqual(fence_for("`````x"), "``````")


class ZipTests(unittest.TestCase):
    def test_zip_round_trip_with_manifest_root_folder_and_unsafe_entries(self):
        data = make_zip({"snake/README.md": "# s", "snake/src/x.py": "a=1\r\n", "__MACOSX/._x": "x",
                         "snake/AIWB_HANDOFF.json": json.dumps({"summary": "zip", "outcome": "complete",
                                                                "attempt_id": "att-9"}),
                         "../evil.txt": "x", "snake/img.png": b"\x89PNG\x00\x00binary"})
        text, ex = canonical_zip(data, name="snake.zip")
        self.assertEqual(ex.files, [{"path": "README.md", "content": "# s"}, {"path": "src/x.py", "content": "a=1\n"}])
        self.assertEqual(ex.attempt_id, "att-9")
        self.assertEqual(ex.manifest["summary"], "zip")
        probs = " ".join(ex.problems)
        self.assertIn("../evil.txt is an unsafe path", probs)
        self.assertIn("img.png is a binary file", probs)
        self.assertIn("top folder", " ".join(ex.fixes))
        files, _ = parse_files(text)
        self.assertEqual([f["path"] for f in files], ["README.md", "src/x.py"])
        self.assertEqual(files[1]["body"], "a=1")

    def test_limits_of_1x_are_kept(self):
        self.assertIn("not a readable ZIP", zip_files(b"not a zip").problems[0])
        big = make_zip({"a.txt": "x" * (600 * 1024)})
        self.assertIn("larger than 512 KB", zip_files(big).problems[0])
        many = make_zip({f"f{i}.txt": "x" for i in range(105)})
        ex = zip_files(many)
        self.assertEqual(len(ex.files), 100)
        self.assertIn("more than 100 files", " ".join(ex.problems))


class GuidedLoopTests(unittest.TestCase):
    """The answer formats inside the real guided loop: paste → link → stage → accept → files on disk."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = ProjectsController(self.root, make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        p = self.c.project
        t = p.tasks.create({"title": "Calc", "objective": "add()", "owner_agent_id": "agent-implementer",
                            "scope": {"include": ["src/**"], "exclude": []}, "acceptance_criteria": ["add works"]})
        p.tasks.transition(t["task_id"], "ready", "test")
        self.task = t["task_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def _handoff_step(self):
        step = next(s for s in self.g.steps() if s["key"] == f"task:{self.task}")
        self.g.perform(step["key"], "prepare")
        step = next(s for s in self.g.steps() if s["key"].startswith("handoff:"))
        self.g.perform(step["key"], "copy")
        self.g.perform(step["key"], "sent")
        return next(s for s in self.g.steps() if s["key"].startswith("handoff:"))

    def _accept_and_read(self, step):
        h = self.c.project.handoffs.get(step["ref"])
        self.assertTrue(h["staged_files"], h)
        self.g.perform(step["key"], "accept_handoff")
        return (self.root / "src/calc.py").read_text(encoding="utf-8")

    def test_markdown_answer_without_manifest_creates_the_file(self):
        step = self._handoff_step()
        out = self.g.perform(step["key"], "paste", text="Sure!\n\n**src/calc.py**\n```python\ndef add(a, b):\n"
                                                        "    return a + b\n```\n")
        self.assertEqual(out["kind"], "handoff", out["message"])
        self.assertIn("1 file(s) read from Markdown code blocks", out["message"])
        self.assertEqual(out["staged"], ["src/calc.py"])
        self.assertFalse([p for p in out["problems"] if p["severity"] == "error"], out["problems"])
        self.assertEqual(self._accept_and_read(step), "def add(a, b):\n    return a + b\n")

    def test_strict_json_answer_creates_the_file(self):
        step = self._handoff_step()
        h = self.c.project.handoffs.get(step["ref"])
        js = json.dumps({"attempt_id": h["attempt_id"], "files": [{"path": "src/calc.py", "content": "A = 1\n"}],
                         "handoff": {"summary": "calc done", "outcome": "complete"}})
        out = self.g.perform(step["key"], "paste", text=js)
        self.assertEqual(out["kind"], "handoff", out["message"])
        self.assertEqual(self.c.project.handoffs.get(step["ref"])["summary"], "calc done")
        self.assertEqual(self._accept_and_read(step), "A = 1\n")

    def test_zip_answer_creates_the_file(self):
        step = self._handoff_step()
        text, ex = canonical_zip(make_zip({"src/calc.py": "Z = 1\n"}))
        out = self.g.perform(step["key"], "paste", text=text)
        self.assertEqual(out["kind"], "handoff", out["message"])
        self.assertEqual(self._accept_and_read(step), "Z = 1\n")

    def test_answer_for_another_attempt_is_not_guessed(self):
        step = self._handoff_step()
        out = self.g.perform(step["key"], "paste",
                             text="AIWB_ATTEMPT_ID: att-9999\n**src/calc.py**\n```python\nA=1\n```\n")
        self.assertEqual(out["kind"], "rejected", out["message"])
        self.assertFalse(self.c.project.handoffs.get(step["ref"]).get("staged_files"))

    def test_cut_off_markdown_answer_asks_to_continue_and_links_nothing(self):
        step = self._handoff_step()
        out = self.g.perform(step["key"], "paste", text="**src/calc.py**\n```python\ndef add(a, b):\n")
        self.assertEqual(out["kind"], "truncated", out["message"])
        self.assertIn("cut off", out["prompt"])
        self.assertFalse(self.c.project.handoffs.get(step["ref"]).get("staged_files"))


if __name__ == "__main__":
    unittest.main()
