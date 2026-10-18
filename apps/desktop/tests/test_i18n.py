"""2.1.x: one FA/EN glossary, statuses never colour-only, prioritised warnings, no logic on translated text."""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb import i18n  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.models import TASK_STATUSES, ModelError  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "aiwb"


class GlossaryTests(unittest.TestCase):
    def test_glossary_complete_and_unambiguous(self):
        self.assertEqual(i18n.check_glossary(), [])
        self.assertEqual(set(i18n.STATUS), set(TASK_STATUSES))
        for k in TASK_STATUSES:
            for lang in i18n.LANGUAGES:
                sym, word = i18n.status(k, lang)
                self.assertTrue(sym.strip() and word.strip(), (k, lang))

    def test_done_reported_verified_blocked_not_run_distinct(self):
        labels = {i18n.status("done")[1], i18n.status("blocked")[1], i18n.evidence_label("reported"),
                  i18n.evidence_label("verified"), i18n.evidence_label("not_run")}
        self.assertEqual(len(labels), 5)
        syms = {i18n.STATUS["done"][0], i18n.STATUS["blocked"][0], i18n.EVIDENCE["reported"][0],
                i18n.EVIDENCE["not_run"][0], i18n.EVIDENCE["failed"][0]}
        self.assertEqual(len(syms), 5)
        self.assertEqual(i18n.evidence_state({"verified": False, "result": "passed"}), "reported")
        self.assertEqual(i18n.evidence_state({"verified": True, "result": "failed"}), "failed")

    def test_no_logic_compares_against_persian_text(self):
        persian = re.compile(r"[\u0600-\u06FF]")
        for p in list((SRC / "v2").glob("*.py")):
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if persian.search(line) and re.search(r"==|!=|\bin\b\s*\(|startswith|endswith", line):
                    self.fail(f"{p.name}:{n} compares against translated text")


class ControllerLanguageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = ProjectsController(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_language_switch_is_display_only(self):
        t = self.c.project.tasks.create({"title": "A", "objective": "a"})
        self.c.project.tasks.transition(t["task_id"], "ready")
        rev = self.c.project.store.revision
        en = self.c.task_rows()[0]
        self.c.set_language("fa")
        fa = self.c.task_rows()[0]
        self.assertEqual(en["status"], fa["status"], "keys stay the same")
        self.assertNotEqual(en["status_text"], fa["status_text"])
        self.assertEqual(fa["status_text"], "آمادهٔ شروع")
        self.assertIn("Task", self.c.next_action_text())
        self.assertEqual(self.c.project.store.revision, rev)
        self.assertEqual(ProjectsController(self.root).lang, "fa")
        with self.assertRaises(ModelError):
            self.c.set_language("de")

    def test_warnings_prioritised_and_deduplicated(self):
        a = self.c.project.tasks.create({"title": "A", "objective": "a"})
        b = self.c.project.tasks.create({"title": "B", "objective": "b", "depends_on": [a["task_id"]]})
        self.c.project.tasks.transition(b["task_id"], "blocked", "waiting for A")
        self.c.project.tasks.transition(a["task_id"], "ready")
        self.c.project.decisions.propose("Pick DB", "?", affected_task_ids=[a["task_id"]])

        class Pub:
            pending = False

            def queue(self):
                return {"paused": "auth: token rejected"}
        self.c.publisher = Pub()
        items = self.c.warning_items()
        sev = [x["severity"] for x in items]
        self.assertEqual(sev, sorted(sev, key=i18n.SEVERITY_ORDER.index))
        self.assertEqual(items[0]["severity"], "blocking")
        self.assertIn("paused", items[0]["text"])
        self.assertTrue(any(x["text"].startswith("Decision needed") for x in items))
        self.assertTrue(any(x["text"].startswith("Blocked: B") for x in items))
        texts = [x["text"] for x in items]
        self.assertEqual(len(texts), len(set(texts)))
        self.c.set_language("fa")
        self.assertTrue(self.c.warning_items()[0]["text"].startswith("انتشار وضعیت"))


if __name__ == "__main__":
    unittest.main()
