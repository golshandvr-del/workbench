"""Roadmap 5.10.0 gate: the answer corpus (``tests/fixtures/answers/``) — whatever the model returned, it works.

* every stored answer replays into a fresh project with the result its case expects;
* at least 40 answers, from GPT, Claude, Gemini, DeepSeek and Copilot styles, including chat copy damage, rendered
  Markdown and a cut-off answer;
* ≥ 95 % of the answers that should be usable are accepted, and 100 % of the rest come back with a precise prompt
  (fix prompt naming the problem, or a continue prompt);
* the stored files are exactly what ``build_corpus.py`` makes (the corpus is reproducible and nothing was edited by
  hand without the script).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
IN_REPO = (HERE / "answer_corpus.py").is_file() and (HERE / "fixtures" / "answers" / "corpus.json").is_file()
if IN_REPO:
    sys.path.insert(0, str(HERE.parent / "src"))
    _spec = importlib.util.spec_from_file_location("answer_corpus", HERE / "answer_corpus.py")
    ac = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ac)
_SKIP = "the answer corpus lives in the repository (tests/fixtures/answers), not in an installed copy"


def _builder():
    spec = importlib.util.spec_from_file_location("build_corpus", ac.ANSWERS / "build_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def outcome(r: dict) -> str:
    if r["ok"]:
        return "accept"
    if r["kind"] == "truncated":
        return "continue"
    if r.get("prompt") or r.get("errors"):
        return "fix_prompt"
    return "nothing"


@unittest.skipUnless(IN_REPO, _SKIP)
class CorpusShapeTests(unittest.TestCase):
    def test_size_and_spread(self):
        cases = ac.cases()
        self.assertGreaterEqual(len(cases), 40)
        styles = " ".join(c["style"] for c in cases)
        for chat in ("GPT", "Claude", "Gemini", "DeepSeek", "Copilot"):
            self.assertIn(chat, styles, chat)
        self.assertTrue(any(c["expect"] == "continue" for c in cases), "a cut-off answer")
        self.assertTrue(any("copy" in c["style"].lower() for c in cases), "chat copy damage")
        self.assertTrue(any(c["file"].endswith(".zip") for c in cases), "a ZIP")
        self.assertTrue({"charter", "files"} <= {c["kind"] for c in cases})
        ids = [c["id"] for c in cases]
        self.assertEqual(len(ids), len(set(ids)))
        for c in cases:
            self.assertTrue((ac.ANSWERS / c["file"]).is_file(), c["file"])
            self.assertIn(c["expect"], ("accept", "fix_prompt", "continue"), c["id"])
            self.assertTrue(c["source"], c["id"])

    def test_corpus_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            _builder().build(Path(tmp))
            made = sorted(p.name for p in Path(tmp).iterdir())
            stored = sorted(p.name for p in ac.ANSWERS.iterdir() if p.name not in ("build_corpus.py", "__pycache__"))
            self.assertEqual(made, stored)
            for name in made:
                if name.endswith(".zip"):   # same entries and contents (zip headers may differ by zlib version)
                    import zipfile
                    a, b = zipfile.ZipFile(Path(tmp) / name), zipfile.ZipFile(ac.ANSWERS / name)
                    self.assertEqual(sorted(a.namelist()), sorted(b.namelist()), name)
                    for n in a.namelist():
                        self.assertEqual(a.read(n), b.read(n), f"{name}:{n}")
                    continue
                self.assertEqual((Path(tmp) / name).read_bytes(), (ac.ANSWERS / name).read_bytes(),
                                 f"{name} differs from build_corpus.py — rebuild the corpus")

    def test_crlf_answers_kept_byte_for_byte(self):
        crlf = [c for c in ac.cases() if "CRLF" in c["style"]]
        self.assertTrue(crlf)
        for c in crlf:
            self.assertIn(b"\r\n", ac.answer_bytes(c), c["file"])


@unittest.skipUnless(IN_REPO, _SKIP)
class CorpusReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {c["id"]: (c, ac.replay(c)) for c in ac.cases()}

    def test_every_case_as_expected(self):
        for cid, (c, r) in self.results.items():
            with self.subTest(cid):
                self.assertEqual(outcome(r), c["expect"], f"{c['file']}: {r['kind']} — {r['message']} "
                                                          f"{r.get('errors', '')}")

    def test_gate_95_percent_and_precise_prompts(self):
        usable = [(c, r) for c, r in self.results.values() if c["expect"] == "accept"]
        accepted = [c for c, r in usable if r["ok"]]
        self.assertGreaterEqual(len(accepted) / len(usable), 0.95,
                                [c["id"] for c, r in usable if not r["ok"]])
        for c, r in self.results.values():
            if c["expect"] == "accept":
                continue
            with self.subTest(c["id"]):
                self.assertFalse(r["ok"])
                if c["kind"] == "charter":
                    self.assertTrue(r["prompt"].strip(), "a prompt the user can send back")
                if c["expect"] == "fix_prompt":
                    # the prompt / smart check names the exact problem, not just "invalid"
                    detail = r["prompt"] + " ".join(r.get("errors", []))
                    self.assertRegex(detail, r"t9|agent-designer|src/cli/main\.py", c["id"])
                if c["expect"] == "continue":
                    self.assertRegex(r["prompt"] or r["message"], r"(?i)cut off|continue|again")

    def test_charters_keep_the_plan(self):
        for cid, (c, r) in self.results.items():
            if c["kind"] == "charter" and r["ok"]:
                with self.subTest(cid):
                    self.assertEqual(r["tasks"], 4, r["message"])

    def test_files_land_in_scope(self):
        want = sorted(json.loads(json.dumps(list(_builder().FILES))))
        for cid, (c, r) in self.results.items():
            if c["kind"] == "files" and r["ok"]:
                with self.subTest(cid):
                    self.assertEqual(sorted(r["staged"]), want, r["message"])


if __name__ == "__main__":
    unittest.main()
