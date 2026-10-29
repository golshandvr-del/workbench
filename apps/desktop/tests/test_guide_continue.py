"""Roadmap 5.15.0 (scenario S4): a cut-off guided answer → continue prompt → the rest → no file is lost.

The continue prompt tells the chat "these files arrived complete — do NOT resend them". Before 5.15.0 the rest the
chat then sent was read alone, so the files of the first part were never staged (lost). Now the guide keeps the
complete files of the cut-off answer with the continue step and puts them back in front of the rest; the rest is
linked to the handoff the cut-off answer was for, even without an ``AIWB_ATTEMPT_ID`` line.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
IN_REPO = (HERE / "answer_corpus.py").is_file() and (HERE / "fixtures" / "answers" / "corpus.json").is_file()
sys.path.insert(0, str(HERE.parent / "src"))
if IN_REPO:
    _spec = importlib.util.spec_from_file_location("answer_corpus", HERE / "answer_corpus.py")
    ac = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ac)

from aiwb.v2.guide import complete_files, merge_files, merge_partial  # noqa: E402

F4 = "````"


def block(path: str, body: str) -> str:
    return f'<<<AIWB_FILE path="{path}" action="write">>>\n{F4}\n{body}{F4}\n<<<AIWB_END_FILE>>>\n'


def opened(path: str, body: str) -> str:
    return f'<<<AIWB_FILE path="{path}" action="write">>>\n{F4}\n{body}'


class HelperTests(unittest.TestCase):
    def test_complete_files_leave_out_the_open_block(self):
        got = complete_files(block("a.py", "A = 1\n") + opened("b.py", "B = ("))
        # the parser drops the block's last newline (writing adds it back)
        self.assertEqual([(f["path"], f["content"].rstrip("\n")) for f in got], [("a.py", "A = 1")])

    def test_complete_files_of_a_whole_answer_keep_everything(self):
        got = complete_files(block("a.py", "A = 1\n") + block("b.py", "B = 2\n"))
        self.assertEqual([f["path"] for f in got], ["a.py", "b.py"])

    def test_merge_files_later_copy_wins(self):
        got = merge_files([{"path": "a", "content": "1"}, {"path": "b", "content": "1"}],
                          [{"path": "b", "content": "2"}])
        self.assertEqual(got, [{"path": "a", "content": "1"}, {"path": "b", "content": "2"}])

    def test_merge_partial_puts_back_what_the_rest_does_not_resend(self):
        text = merge_partial([{"path": "a.py", "content": "A = 1\n"}], block("b.py", "B = 2\n"), "att-1")
        files = {f["path"]: f["content"].rstrip("\n") for f in complete_files(text)}
        self.assertEqual(files, {"a.py": "A = 1", "b.py": "B = 2"})
        self.assertIn("AIWB_ATTEMPT_ID: att-1", text)

    def test_merge_partial_a_resent_file_wins_and_nothing_missing_is_unchanged(self):
        rest = block("a.py", "A = 2\n") + block("b.py", "B = 2\n")
        self.assertEqual(merge_partial([{"path": "a.py", "content": "A = 1\n"}], rest), rest)
        self.assertEqual(merge_partial([], rest), rest)


@unittest.skipUnless(IN_REPO, "the answer corpus lives in the repository, not in an installed copy")
class ContinueTests(unittest.TestCase):
    def setUp(self):
        self.s = ac.Scenario()
        self.step = self.s.to_first_task()
        self.h = self.s.c.state()["handoffs"][self.step["ref"]]

    def tearDown(self):
        self.s.close()

    def manifest(self) -> str:
        h = self.h
        man = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": h["task_id"],
               "task_revision": h["task_revision"], "attempt_id": h["attempt_id"], "outcome": "complete",
               "summary": "core", "completed_items": ["core"], "unresolved_items": [], "validation_claims": []}
        return "<<<AIWB_HANDOFF>>>\n" + json.dumps(man) + "\n<<<AIWB_END_HANDOFF>>>\n"

    def paste_cut(self) -> dict:
        cut = (f"AIWB_ATTEMPT_ID: {self.h['attempt_id']}\n" + block("src/todo/a.py", "A = 1\n")
               + opened("src/todo/b.py", "B = ("))
        out = self.s.g.perform(self.step["key"], "paste", text=cut)
        self.assertEqual(out["kind"], "truncated")
        self.assertIn("do NOT resend them: src/todo/a.py", out["prompt"])
        return out

    def staged(self) -> list[str]:
        h = self.s.c.state()["handoffs"][self.step["ref"]]
        return sorted(f["path"] for f in h.get("staged_files") or [])

    def test_the_rest_keeps_the_files_that_arrived_complete(self):
        self.paste_cut()
        rest = f"AIWB_ATTEMPT_ID: {self.h['attempt_id']}\n" + block("src/todo/b.py", "B = 2\n") + self.manifest()
        out = self.s.g.perform("continue", "paste", text=rest)
        self.assertEqual(out["kind"], "handoff", out["message"])
        self.assertEqual(self.staged(), ["src/todo/a.py", "src/todo/b.py"])
        self.assertNotIn("continue", [s["key"] for s in self.s.g.steps()])

    def test_the_rest_without_attempt_line_is_linked_to_the_cut_off_handoff(self):
        self.paste_cut()
        out = self.s.g.perform("continue", "paste", text=block("src/todo/b.py", "B = 2\n"))
        self.assertEqual(out["kind"], "handoff", out["message"])
        self.assertEqual(self.staged(), ["src/todo/a.py", "src/todo/b.py"])

    def test_a_second_cut_off_keeps_what_the_first_saved(self):
        self.paste_cut()
        out = self.s.g.perform("continue", "paste", text=block("src/todo/b.py", "B = 2\n") + opened("src/todo/c.py", "C"))
        self.assertEqual(out["kind"], "truncated")
        cont = self.s.c.state()["settings"]["guide"]["continue"]
        self.assertEqual(sorted(f["path"] for f in cont["partial"]), ["src/todo/a.py", "src/todo/b.py"])
        self.assertEqual(cont["for"], self.step["key"])
        out = self.s.g.perform("continue", "paste", text=block("src/todo/c.py", "C = 3\n") + self.manifest())
        self.assertEqual(out["kind"], "handoff", out["message"])
        self.assertEqual(self.staged(), ["src/todo/a.py", "src/todo/b.py", "src/todo/c.py"])


if __name__ == "__main__":
    unittest.main()
