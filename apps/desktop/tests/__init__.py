"""Desktop test package.

Run from ``apps/desktop``:  ``python -m unittest discover -s tests -t .``

Application modules live in ``src/`` (installed flat into the program folder).
Importing this package puts ``src/`` on ``sys.path`` so tests use the same
``import AI_Workbench`` / ``import aiwb`` names as the installed app.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
