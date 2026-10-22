"""Roadmap 6.1.0: packages/contracts/fixtures/mission/mission-map.v1.json equals the desktop Mission Map model.

The mobile ``MissionModelTest`` builds the same cases and must get the same map, so the fixture is the parity bridge.
Run ``python tools/gen_mission_fixture.py`` after changing ``aiwb/ui/mission_model.py``.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next((p for p in HERE.parents if (p / "tools" / "gen_mission_fixture.py").is_file()), None)


@unittest.skipIf(ROOT is None, "tools/gen_mission_fixture.py is only in the repository (not in an installed copy)")
class MissionFixtureTest(unittest.TestCase):
    def test_fixture_is_fresh(self) -> None:
        assert ROOT is not None
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_mission_fixture.py"), "--check"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
