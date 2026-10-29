"""Roadmap 5.14.0: Quick mode — one AI chat (aiwb/v2/quick.py), the engine without Tk."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aiwb.v2 import quick  # noqa: E402

AIWB_ANSWER = """AIWB_ATTEMPT_ID: Q-0001
<<<AIWB_FILE path="src/app.py" action="write">>>
````
print("hello")
````
<<<AIWB_END_FILE>>>
<<<AIWB_FILE path="README.md" action="write">>>
````
# Demo
````
<<<AIWB_END_FILE>>>
"""

JSON_ANSWER = json.dumps({"files": [{"path": "src/app.py", "content": "print('json')\n"},
                                    {"path": "docs/notes.txt", "content": "n\n"}], "notes": "x"})


def zip_answer() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("src/app.py", "print('zip')\n")
        z.writestr("src/util.py", "X = 1\n")
    return buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "demo"
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()


class PromptTests(Base):
    def test_needs_a_job(self):
        with self.assertRaises(quick.QuickError):
            quick.build_prompt(self.root, "  ")

    def test_empty_folder_and_format_rules(self):
        for fmt, word in (("aiwb", "AIWB_FILE"), ("json", '"files"'), ("zip", "ZIP")):
            p = quick.build_prompt(self.root, "Make a snake game", fmt)
            self.assertIn("Make a snake game", p)
            self.assertIn("The folder is empty", p)
            self.assertIn(word, p)
            self.assertIn("## How to send your answer back", p, "every prompt asks for one code block (B1)")
        self.assertEqual([r["round_id"] for r in quick.state(self.root)["rounds"]], ["Q-0001", "Q-0002", "Q-0003"])

    def test_inventory_and_included_files(self):
        (self.root / "src").mkdir()
        (self.root / "src/a.py").write_text("A = 1\n", encoding="utf-8")
        (self.root / ".git").mkdir()
        (self.root / ".git/config").write_text("x", encoding="utf-8")
        p = quick.build_prompt(self.root, "Fix A", include=["src/a.py", "../etc/passwd", "missing.py"])
        self.assertIn("- src/a.py (6 bytes)", p)
        self.assertIn("A = 1", p)
        self.assertNotIn(".git/config", p)
        self.assertIn("Not included:", p)
        self.assertIn("missing.py", p)

    def test_big_file_is_not_included(self):
        (self.root / "big.txt").write_text("x" * (quick.MAX_INCLUDE_BYTES + 1), encoding="utf-8")
        p = quick.build_prompt(self.root, "Read it", include=["big.txt"])
        self.assertIn("too big to include", p)


class AnswerTests(Base):
    def test_three_formats(self):
        a = quick.read_answer(AIWB_ANSWER)
        self.assertEqual(a["format"], "aiwb")
        self.assertEqual([f["path"] for f in a["files"]], ["src/app.py", "README.md"])
        j = quick.read_answer(JSON_ANSWER)
        self.assertEqual(j["format"], "json")
        self.assertEqual(j["files"][0]["content"], "print('json')\n")
        z = quick.read_answer(zip_bytes=zip_answer())
        self.assertEqual(z["format"], "zip")
        self.assertEqual(sorted(f["path"] for f in z["files"]), ["src/app.py", "src/util.py"])

    def test_markdown_with_file_names(self):
        md = "Here you go.\n\n**src/app.py**\n```python\nprint('md')\n```\n"
        a = quick.read_answer(md)
        self.assertEqual(a["format"], "markdown")
        self.assertEqual(a["files"][0]["path"], "src/app.py")

    def test_windows_copy_damage_is_repaired(self):
        damaged = "\n".join(line + "\\" if line.strip() else line for line in AIWB_ANSWER.splitlines())
        a = quick.read_answer(damaged)
        self.assertEqual(len(a["files"]), 2)
        self.assertTrue(a["fixes"], "the repair is listed")

    def test_cut_off_answer_gets_a_continue_prompt(self):
        cut = AIWB_ANSWER.split("<<<AIWB_FILE path=\"README.md\"")[0] + '<<<AIWB_FILE path="README.md" action="write">>>\n````\n# De'
        a = quick.read_answer(cut)
        self.assertTrue(a["truncated"])
        self.assertIn("README.md", a["continue_prompt"])

    def test_unsafe_paths_are_skipped(self):
        bad = json.dumps({"files": [{"path": "../evil.py", "content": "x"}, {"path": ".git/hooks/x", "content": "x"},
                                    {"path": "ok.py", "content": "ok\n"}]})
        a = quick.read_answer(bad)
        self.assertEqual([f["path"] for f in a["files"]], ["ok.py"])
        self.assertTrue(any("unsafe" in p for p in a["problems"]))

    def test_no_files_says_what_to_do(self):
        a = quick.read_answer("Sure! I will do it.")
        self.assertEqual(a["files"], [])
        self.assertTrue(a["problems"])


class ApplyRestoreTests(Base):
    def test_plan_apply_restore_roundtrip(self):
        (self.root / "src").mkdir()
        (self.root / "src/app.py").write_text("old\n", encoding="utf-8")
        (self.root / "README.md").write_text("# Demo\n", encoding="utf-8")
        items = quick.plan(self.root, quick.read_answer(AIWB_ANSWER)["files"])
        status = {i["path"]: i["status"] for i in items}
        self.assertEqual(status, {"src/app.py": "changed", "README.md": "same"})
        self.assertIn("-old", items[0]["diff"])
        self.assertEqual(quick.summary(items), "0 new · 1 changed · 1 unchanged")
        rec = quick.apply(self.root, items, task="hello")
        self.assertEqual(rec["written"], ["src/app.py"])
        self.assertEqual((self.root / "src/app.py").read_text(encoding="utf-8"), 'print("hello")\n')
        self.assertEqual(quick.last_apply(self.root)["apply_id"], "A-0001")
        out = quick.restore(self.root)
        self.assertEqual(out["restored"], ["src/app.py"])
        self.assertEqual((self.root / "src/app.py").read_text(encoding="utf-8"), "old\n")
        self.assertIsNone(quick.last_apply(self.root))
        with self.assertRaises(quick.QuickError):
            quick.restore(self.root)

    def test_restore_removes_new_files_and_keeps_later_edits(self):
        items = quick.plan(self.root, quick.read_answer(zip_bytes=zip_answer())["files"])
        self.assertEqual({i["status"] for i in items}, {"new"})
        quick.apply(self.root, items)
        (self.root / "src/util.py").write_text("X = 2  # edited by hand\n", encoding="utf-8")
        out = quick.restore(self.root)
        self.assertEqual(out["restored"], ["src/app.py"])
        self.assertEqual(out["kept"], ["src/util.py"])
        self.assertFalse((self.root / "src/app.py").exists())
        self.assertIn("edited by hand", (self.root / "src/util.py").read_text(encoding="utf-8"))

    def test_nothing_to_apply(self):
        (self.root / "ok.py").write_text("ok\n", encoding="utf-8")
        items = quick.plan(self.root, [{"path": "ok.py", "content": "ok\n"}])
        with self.assertRaises(quick.QuickError):
            quick.apply(self.root, items)

    def test_quick_files_live_under_workbench_quick(self):
        quick.apply(self.root, quick.plan(self.root, [{"path": "a.txt", "content": "a\n"}]))
        self.assertTrue((self.root / ".workbench/quick/quick.json").is_file())
        self.assertNotIn(".workbench/quick/quick.json", [p for p, _n in quick.inventory(self.root)])


class GuidedTests(Base):
    def test_to_guided_keeps_files_and_uses_last_job(self):
        quick.build_prompt(self.root, "An offline todo app")
        quick.apply(self.root, quick.plan(self.root, [{"path": "app.py", "content": "pass\n"}]))
        from aiwb.v2 import team_setup
        out = quick.to_guided(self.root, "", team_setup.default_rows(2))
        self.assertEqual(out["workers"], 2)
        self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "pass\n")
        st = json.loads((self.root / ".workbench/v2/state.json").read_text(encoding="utf-8"))
        self.assertIn("An offline todo app", json.dumps(st))
        self.assertTrue(quick.state(self.root)["converted"])
        with self.assertRaises(quick.QuickError):
            quick.to_guided(self.root, "again", team_setup.default_rows(1))


if __name__ == "__main__":
    unittest.main()
