"""Roadmap 4.3.0 gate (desktop half): user approval and project files (flowchart F16–F17).

* the shared safe-path fixture (no write outside the project root, nothing under .git / .workbench);
* a pasted delivery is only staged; accepting it writes the files, backs up old content and records
  ``files_integrated`` on the timeline; out-of-scope / unsafe files are never staged;
* ZIP round-trip; a ZIP with an unsafe entry is refused as a whole.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.files import list_files, safe_path, unzip_files, zip_files  # noqa: E402
from aiwb.v2.guide import Guide  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[3] / "packages/contracts/fixtures/files/safe-paths.v1.json"
F4 = "````"


class SafePathTests(unittest.TestCase):
    def test_shared_fixture(self) -> None:
        for c in json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]:
            with self.subTest(c["input"]):
                self.assertEqual(safe_path(c["input"]), c["expect"])


class IntegrateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = ProjectsController(self.root, make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        t = self.c.project.tasks.create({"title": "Calc", "objective": "add", "scope": {"include": ["src/"], "exclude": []},
                                         "acceptance_criteria": ["adds"]})
        self.tid = t["task_id"]
        self.c.project.tasks.transition(self.tid, "ready", "test")
        (self.root / "src").mkdir()
        (self.root / "src" / "calc.py").write_text("old\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def answer(self) -> str:
        h = next(h for h in self.c.state()["handoffs"].values() if h["task_id"] == self.tid)
        man = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": self.tid,
               "task_revision": h["task_revision"], "attempt_id": h["attempt_id"], "outcome": "complete",
               "summary": "done", "completed_items": ["calc"], "unresolved_items": [], "validation_claims": []}

        def f(p: str, body: str) -> str:
            return f'<<<AIWB_FILE path="{p}" action="write">>>\n{F4}\n{body}\n{F4}\n<<<AIWB_END_FILE>>>\n'
        return (f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n" + f("src/calc.py", "def add(a, b):\n    return a + b")
                + f("src/util/__init__.py", "X = 1") + "<<<AIWB_HANDOFF>>>\n" + json.dumps(man) + "\n<<<AIWB_END_HANDOFF>>>\n")

    def step(self) -> dict:
        return next(s for s in self.g.steps() if s["key"].startswith("handoff:"))

    def test_paste_stages_and_accept_integrates(self) -> None:
        self.g.perform(f"task:{self.tid}", "prepare")
        out = self.g.perform(self.step()["key"], "paste", text=self.answer())
        self.assertEqual(sorted(out["staged"]), ["src/calc.py", "src/util/__init__.py"])
        self.assertEqual((self.root / "src" / "calc.py").read_text(encoding="utf-8"), "old\n")  # nothing written yet
        st = self.step()
        self.assertIn("2 delivered file(s)", st["explain"])
        out = self.g.perform(st["key"], "accept_handoff")
        self.assertEqual(sorted(out["files"]), ["src/calc.py", "src/util/__init__.py"])
        self.assertEqual((self.root / "src" / "calc.py").read_text(encoding="utf-8"), "def add(a, b):\n    return a + b\n")
        hid = st["ref"]
        self.assertEqual((self.root / ".workbench/v2/backups" / hid / "src/calc.py").read_text(encoding="utf-8"), "old\n")
        s = self.c.state()
        self.assertTrue(all("content" not in x for x in s["handoffs"][hid]["staged_files"]))
        ev = [e for e in s["events"] if e["type"] == "files_integrated"]
        self.assertEqual(ev[-1]["count"], 2)
        self.assertNotIn(".workbench/v2/state.json", [x["path"] for x in list_files(self.root)])

    def test_bf009_failure_keeps_delivery_open_and_rolls_back_then_retries(self) -> None:
        from unittest.mock import patch
        import os
        from aiwb.v2.models import ModelError
        self.g.perform(f"task:{self.tid}", "prepare")
        self.g.perform(self.step()["key"], "paste", text=self.answer())
        step = self.step()
        hid = step["ref"]
        before = self.c.state()
        replace = os.replace
        def locked(src, dst):
            if Path(dst) == self.root / "src/util/__init__.py":
                raise PermissionError("locked by editor")
            return replace(src, dst)
        with patch("os.replace", side_effect=locked), self.assertRaises(ModelError):
            self.g.perform(step["key"], "accept_handoff")
        self.assertEqual((self.root / "src/calc.py").read_bytes(), b"old\n")
        self.assertFalse((self.root / "src/util/__init__.py").exists())
        self.assertEqual(self.c.state()["handoffs"][hid], before["handoffs"][hid])
        self.assertEqual(self.c.state()["tasks"][self.tid], before["tasks"][self.tid])
        self.assertFalse(list(self.root.glob("**/*.aiwb-tmp")))
        out = self.g.perform(step["key"], "accept_handoff")
        self.assertEqual(len(out["files"]), 2)
        self.assertEqual(self.c.state()["handoffs"][hid]["status"], "accepted")
        backups = self.root / ".workbench/v2/backups"
        self.assertTrue(all(p.read_bytes() == b"old\n" for p in backups.glob("*/src/calc.py")))

    def test_bf009_destination_directory_preflight_writes_nothing(self) -> None:
        from aiwb.v2.models import ModelError
        self.g.perform(f"task:{self.tid}", "prepare")
        self.g.perform(self.step()["key"], "paste", text=self.answer())
        step = self.step()
        (self.root / "src/util/__init__.py").mkdir(parents=True)
        before = self.c.state()
        with self.assertRaises(ModelError):
            self.g.perform(step["key"], "accept_handoff")
        self.assertEqual((self.root / "src/calc.py").read_bytes(), b"old\n")
        self.assertEqual(self.c.state()["handoffs"], before["handoffs"])

    def test_accepting_the_delivery_is_the_review(self) -> None:
        """5.13.0 (gate ≤ 14 clicks): a clean "Accept the delivery" records the user's review approval, so the task
        goes straight to the tests/build step; the review is a real manual_review evidence, never a test result."""
        self.g.perform(f"task:{self.tid}", "prepare")
        self.g.perform(self.step()["key"], "paste", text=self.answer())
        st = self.step()
        self.assertIn("records your review approval", st["explain"])
        out = self.g.perform(st["key"], "accept_handoff")
        self.assertIn(f"{self.tid} approved", out["message"])
        s = self.c.state()
        self.assertEqual(s["tasks"][self.tid]["status"], "validation_pending")
        ev = [(e["type"], e["result"]) for e in s["evidence"].values() if e["subject_id"] == self.tid]
        self.assertIn(("manual_review", "approved"), ev)
        self.assertFalse(any(t in ("test_run", "build_run") for t, _ in ev), "no test result is made up")
        nxt = next(x for x in self.g.steps() if x["key"] == f"task:{self.tid}")
        self.assertTrue(nxt["title"].startswith("Verify"), nxt["title"])

    def test_bf010_empty_file_is_staged_and_written_not_silently_dropped(self) -> None:
        self.g.perform(f"task:{self.tid}", "prepare")
        answer = self.answer().replace("X = 1", "")
        out = self.g.perform(self.step()["key"], "paste", text=answer)
        self.assertEqual(len(out["staged"]), 2)
        self.assertFalse(any(p["severity"] == "error" for p in out["problems"]))
        out = self.g.perform(self.step()["key"], "accept_handoff")
        self.assertEqual(len(out["files"]), 2)
        self.assertEqual((self.root / "src/util/__init__.py").read_bytes(), b"")

    def _assert_staging_limit(self, limits: dict, code: str) -> None:
        from unittest.mock import patch
        self.g.perform(f"task:{self.tid}", "prepare")
        with patch.multiple("aiwb.v2.files", **limits):
            out = self.g.perform(self.step()["key"], "paste", text=self.answer())
        self.assertIn(code, [p["code"] for p in out["problems"]])
        self.assertNotIn("accept_handoff", [a["id"] for a in self.step()["actions"]])
        self.assertEqual((self.root / "src/calc.py").read_bytes(), b"old\n")

    def test_bf010_file_limit_visible_and_blocks_partial_acceptance(self) -> None:
        self._assert_staging_limit({"MAX_FILE": 20}, "too_large")

    def test_bf010_total_limit_visible_and_blocks_partial_acceptance(self) -> None:
        self._assert_staging_limit({"MAX_TOTAL": 20}, "total_too_large")

    def test_bf051_normalized_duplicates_report_last_wins_and_case_prefix_conflicts_block(self) -> None:
        self.g.perform(f"task:{self.tid}", "prepare")
        answer = self.answer().replace('path="src/util/__init__.py"', 'path="./src/calc.py"')
        out = self.g.perform(self.step()["key"], "paste", text=answer)
        self.assertIn("duplicate_path", [p["code"] for p in out["problems"]])
        self.assertEqual(out["staged"], ["src/calc.py"])

    def test_bf051_case_conflict_is_visible_and_blocks_acceptance(self) -> None:
        self.g.perform(f"task:{self.tid}", "prepare")
        out = self.g.perform(self.step()["key"], "paste", text=self.answer().replace(
            'path="src/util/__init__.py"', 'path="src/CALC.py"'))
        self.assertIn("file_conflict", [p["code"] for p in out["problems"]])
        self.assertNotIn("accept_handoff", [a["id"] for a in self.step()["actions"]])

    def test_unsafe_and_out_of_scope_are_never_staged(self) -> None:
        self.g.perform(f"task:{self.tid}", "prepare")
        bad = self.answer().replace('path="src/util/__init__.py"', 'path="../evil.py"').replace(
            'path="src/calc.py"', 'path="docs/x.py"')
        out = self.g.perform(self.step()["key"], "paste", text=bad)
        self.assertNotIn("staged", out)
        self.assertFalse((self.root.parent / "evil.py").exists())

    def test_zip_round_trip_and_zip_slip(self) -> None:
        (self.root / "README.md").write_text("# hi\n", encoding="utf-8")
        data = zip_files(self.root)
        with tempfile.TemporaryDirectory() as other:
            names = unzip_files(Path(other), data)
            self.assertEqual(sorted(names), ["README.md", "src/calc.py"])
            self.assertEqual((Path(other) / "src/calc.py").read_text(encoding="utf-8"), "old\n")
            self.assertEqual(zip_files(Path(other)), data)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("ok.txt", "x")
                z.writestr("../evil.txt", "x")
            with self.assertRaises(ValueError):
                unzip_files(Path(other), buf.getvalue())
            self.assertFalse((Path(other) / "ok.txt").exists())


if __name__ == "__main__":
    unittest.main()
