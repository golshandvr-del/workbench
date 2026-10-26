"""Roadmap 5.13.0 gate (owner audit B4): what the user reads speaks the user's words.

Owner's test of 5.11.0: "agent-implementer" instead of the name the user gave, "Flow F11 · waves left 2", handoff
ids. Every guide step (title, explanation, button labels) of the scripted runs of the guide, charter, context-step,
wave, close-out and reference-scenario tests is scanned here: no ``agent-…`` id, no flowchart node (``F11``), no
``wave``, no ``handoff``, no ``HO-0001`` / attempt id. Prompts are not scanned — they are read by the AIs.
"""
from __future__ import annotations

import io
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

import aiwb.v2.guide as G  # noqa: E402

INTERNAL = re.compile(r"\bagent-[a-z0-9-]+|\bF\d{1,2}\b|\bwaves?\b|\bhandoffs?\b|\bHO-\d+|\bATT-\d+|\battempt_id\b", re.I)
SCENARIOS = ("test_v2_guide", "test_v2_charter", "test_context_step", "test_waves", "test_closeout",
             "test_v2_reference_scenario", "test_v2_flow")


def leaks(steps: list[dict]) -> list[tuple[str, str, str]]:
    """``(step key, internal word, text)`` for every internal word in what the user reads."""
    out = []
    for s in steps:
        for text in [s["title"], s["explain"]] + [a["label"] for a in s["actions"]]:
            for m in INTERNAL.finditer(text):
                out.append((s["key"], m.group(0), text[:160]))
    return out


class UserWordsTests(unittest.TestCase):
    def test_guide_steps_never_show_internal_words(self):
        seen: list[int] = [0]
        found: dict[tuple[str, str], str] = {}
        orig = G.steps

        def scanned(ctl):
            out = orig(ctl)
            seen[0] += len(out)
            for key, word, text in leaks(out):
                found.setdefault((key.split(":")[0], word.lower()), text)
            return out

        G.steps = scanned
        try:
            suite = unittest.TestSuite()
            for name in SCENARIOS:
                if (HERE / f"{name}.py").is_file():
                    suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
            res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        finally:
            G.steps = orig
        self.assertTrue(res.wasSuccessful(), [str(t) for t, _ in res.failures + res.errors][:5])
        self.assertGreater(seen[0], 200, "the scripted runs must reach many guide steps")
        self.assertEqual(found, {}, "internal words in what the user reads")

    def test_names_replace_ids_but_prompts_stay(self):
        st = {"agents": {"agent-dev": {"name": "Coder"}, "agent-dev-2": {"name": "Second coder"}}}
        step = {"key": "handoff:HO-1", "title": "Paste agent-dev-2's answer", "explain": "agent-dev waits",
                "actions": [{"id": "copy", "label": "Copy into agent-dev's chat", "needs": [], "primary": True}],
                "prompt": "You are agent-dev", "agent_id": "agent-dev"}
        out = G._in_user_words(st, [step])[0]
        self.assertEqual(out["title"], "Paste Second coder's answer")
        self.assertEqual(out["explain"], "Coder waits")
        self.assertEqual(out["actions"][0]["label"], "Copy into Coder's chat")
        self.assertEqual((out["prompt"], out["agent_id"]), ("You are agent-dev", "agent-dev"))
        self.assertEqual(leaks([out]), [])


if __name__ == "__main__":
    unittest.main()
