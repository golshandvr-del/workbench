"""AI Workbench launcher (roadmap 5.0.0): the splash appears at once, then the app is imported and built.

Running ``AI_Workbench.py`` directly recompiles that 11 000-line file on every start (a script is never cached).
Importing it as a module lets Python reuse ``__pycache__`` (the installer pre-compiles it), and the splash is on
screen before the heavy imports begin. The desktop shortcut starts this file; ``AI_Workbench.py`` still works.
"""
from __future__ import annotations

import sys
from pathlib import Path


def run() -> int:
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    import tkinter as tk

    from aiwb.ui.startup import Splash, enable_dpi_awareness

    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    splash = Splash(root, title="AI Workbench", version=_version(here))
    splash.progress(0.15)
    import AI_Workbench  # noqa: E402 — imported after the splash on purpose

    splash.progress(0.45)
    root.deiconify()
    return AI_Workbench.main(root, splash)


def _version(here: Path) -> str:
    try:
        text = (here / "aiwb" / "__init__.py").read_text(encoding="utf-8")
        return text.split('__version__ = "', 1)[1].split('"', 1)[0]
    except (OSError, IndexError):
        return ""


if __name__ == "__main__":
    raise SystemExit(run())
