"""Roadmap 5.8.0 (audit A4): the Project Profile the user saved reaches the Charter prompt.

Before 5.8.0 "Save profile" stored platform, language and framework in ``.workbench/project.json`` but the
'design the whole project' prompt never read them, so the project manager chat guessed the stack again.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.v2.charter import profile_lines  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402


class ProfileLinesTests(unittest.TestCase):
    def test_defaults_say_nothing(self):
        self.assertEqual(profile_lines({"languages": "Let AI recommend", "target_platform": "Other / undecided",
                                        "gui_framework": "Not applicable unless the task requires a UI"}), [])
        self.assertEqual(profile_lines(None), [])
        self.assertEqual(profile_lines("x"), [])

    def test_real_choices_are_listed(self):
        out = profile_lines({"target_platform": "Windows desktop", "languages": "Python", "gui_framework": "Tkinter"})
        self.assertIn("- Target platform: Windows desktop", out)
        self.assertIn("- Language(s): Python", out)
        self.assertIn("- GUI / application framework: Tkinter", out)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_saved_profile_is_in_the_prompt(self):
        (self.root / ".workbench").mkdir()
        (self.root / ".workbench" / "project.json").write_text(json.dumps(
            {"profile": {"target_platform": "Windows desktop", "languages": "C#", "gui_framework": "WPF"}}),
            encoding="utf-8")
        prompt = ProjectsController(self.root).charter_prompt({"goal": "A snake game"})
        self.assertIn("Technical profile chosen by the user", prompt)
        self.assertIn("- Language(s): C#", prompt)
        self.assertIn("- GUI / application framework: WPF", prompt)

    def test_no_or_broken_profile_is_harmless(self):
        c = ProjectsController(self.root)
        self.assertEqual(c.project_profile(), {})
        self.assertNotIn("Technical profile", c.charter_prompt({"goal": "A snake game"}))
        (self.root / ".workbench").mkdir(exist_ok=True)
        (self.root / ".workbench" / "project.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(c.project_profile(), {})


if __name__ == "__main__":
    unittest.main()
