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
