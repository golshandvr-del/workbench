"""Roadmap 5.7.0: Projects page cards (aiwb/ui/projects5.py) — pure row mapping."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aiwb.ui import projects5  # noqa: E402


class ProjectRowsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.a, self.b = base / "Alpha", base / "Beta"
        self.a.mkdir()
        self.b.mkdir()
        self.gone = base / "Gone"
        self.records = [
            {"path": str(self.a), "name": "Alpha", "last_opened": "2026-10-01T10:00:00"},
            {"path": str(self.b), "name": "Beta", "description": "web shop", "last_opened": "2026-10-20T09:30:00"},
            {"path": str(self.gone), "name": "Gone", "last_opened": "2026-10-21T08:00:00"},
            "junk", {"name": "no path"},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_active_first_then_most_recent(self):
        rows = projects5.rows(self.records, self.a)
        self.assertEqual([r["name"] for r in rows], ["Alpha", "Gone", "Beta"])
        self.assertEqual([r["state"] for r in rows], ["Active", "Missing", "Ready"])
        self.assertEqual(rows[2]["last_opened"], "2026-10-20 09:30")

    def test_no_active_project(self):
        rows = projects5.rows(self.records, None)
        self.assertNotIn("Active", [r["state"] for r in rows])
        self.assertEqual(len(rows), 3)

    def test_query_matches_name_description_and_path(self):
        self.assertEqual([r["name"] for r in projects5.rows(self.records, None, "SHOP")], ["Beta"])
        self.assertEqual([r["name"] for r in projects5.rows(self.records, None, "alpha")], ["Alpha"])
        self.assertEqual(projects5.rows(self.records, None, "zzz"), [])

    def test_manifest_wins_over_record(self):
        rows = projects5.rows(self.records, None, manifest=lambda p: {"name": p.name + "!", "description": "m"})
        names = {r["name"] for r in rows}
        self.assertIn("Alpha!", names)
        self.assertIn("Gone", names)  # missing folder: manifest not read

    def test_bad_input_is_empty(self):
        self.assertEqual(projects5.rows(None, None), [])  # type: ignore[arg-type]
        self.assertEqual(projects5.rows([], self.a), [])

    def test_short_path(self):
        self.assertEqual(projects5._short("abc"), "abc")
        s = projects5._short("x" * 100, 20)
        self.assertEqual(len(s), 20)
        self.assertTrue(s.startswith("…"))


if __name__ == "__main__":
    unittest.main()
