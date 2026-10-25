"""Roadmap 5.12.0 (owner audit B1): an answer copied as rendered text from a chat on Windows still works.

Selecting a rendered ChatGPT answer and pressing Ctrl+C (instead of the code block's Copy button) turns every line
break outside a code block into a Markdown hard break: the line ends with ``\\``. Underscores become ``\\_``.
``normalize.strip_copy_damage`` undoes exactly that, and only when the damage is clear.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.intake.answer_files import extract  # noqa: E402
from aiwb.intake.normalize import normalize, strip_copy_damage  # noqa: E402

OWNER = Path(__file__).resolve().parents[3] / "docs" / "audit" / "owner-5.11" / "HO-0006_gpt_answer_context_request.txt"


def damage(text: str, ch: str = "\\") -> str:
    """What the Windows copy of a rendered answer does: every non-empty line outside code gets ``ch``."""
    out, inside = [], False
    for line in text.replace("\r", "").split("\n"):
        if line.strip().startswith("```"):
            inside = not inside
            out.append(line)
            continue
        out.append(line + ch if line.strip() and not inside else line)
    return "\n".join(out)


class CopyDamageTests(unittest.TestCase):
    @unittest.skipUnless(OWNER.is_file(), "the owner's real answer lives in the repository")
    def test_owner_answer_round_trip(self):
        clean = OWNER.read_text(encoding="utf-8").replace("\r", "")
        fixes: list[str] = []
        self.assertEqual(strip_copy_damage(damage(clean), fixes), clean)
        self.assertTrue(any(f.startswith("copy_damage:") for f in fixes), fixes)

    def test_clean_text_is_untouched(self):
        for text in ("plain answer", "a/b/c\nx/y\n", '{"a": "b\\\\"}', "path C:\\\\x\\\\\n"):
            fixes: list[str] = []
            self.assertEqual(strip_copy_damage(text, fixes), text)
            self.assertEqual(fixes, [])

    def test_code_inside_fences_is_kept(self):
        text = "Install first.\nRun this:\n```bash\ncmd a \\\n  --b \\\n  --c \\\n  d\n```\nThat is all."
        self.assertEqual(strip_copy_damage(text), text)   # prose clean → nothing to do
        damaged = damage(text)
        self.assertEqual(strip_copy_damage(damaged), text)  # prose damaged, the shell continuations survive

    def test_file_block_with_escaped_markers(self):
        raw = ('Here you go:\\\n\\\n<<<AIWB\\_FILE path="src/a\\_b.py" action="write">>>\\\n````\nx = "a\\\\"\n'
               'y\\_z = 1\n````\n<<<AIWB\\_END\\_FILE>>>\\\nDone.\\')
        ex = extract(raw)
        self.assertEqual([f["path"] for f in ex.files], ["src/a_b.py"])
        self.assertEqual(ex.files[0]["content"].rstrip("\n"), 'x = "a\\\\"\ny\\_z = 1')  # body verbatim

    def test_slash_variant(self):
        text = "{\n  \"a\": 1,\n  \"b\": [\n    2\n  ]\n}"
        fixes: list[str] = []
        self.assertEqual(strip_copy_damage(damage(text, "/"), fixes), text)
        self.assertIn("slashes", fixes[0])

    def test_normalize_reports_the_fix(self):
        text = damage('{\n  "type": "x",\n  "files": ["a"]\n}')
        n = normalize(text)
        self.assertTrue(any(f.startswith("copy_damage:") for f in n.fixes), n.fixes)
        self.assertNotIn("\\", n.text)

    def test_few_lines_are_not_guessed(self):
        self.assertEqual(strip_copy_damage("one\\\ntwo"), "one\\\ntwo")


if __name__ == "__main__":
    unittest.main()
