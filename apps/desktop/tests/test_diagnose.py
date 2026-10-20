"""Roadmap 4.2.0 gate (desktop half): smart problem detection matches the shared corpus (flowchart F13–F15)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.v2.diagnose import diagnose  # noqa: E402

CORPUS = Path(__file__).resolve().parents[3] / "packages/contracts/fixtures/diagnose/diagnose-corpus.v1.json"


class DiagnoseCorpusTests(unittest.TestCase):
    def test_every_corpus_case(self):
        cases = json.loads(CORPUS.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 17)
        for c in cases:
            with self.subTest(c["id"]):
                r = diagnose(c["text"], **c["context"])
                self.assertEqual([p["code"] for p in r["problems"]], c["codes"])
                self.assertEqual(r["acceptable"], c["acceptable"])


if __name__ == "__main__":
    unittest.main()
