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
    clear_stale_bytecode(here)
    import tkinter as tk

    from aiwb.ui.startup import Splash, enable_dpi_awareness

    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    splash = Splash(root, title="AI Workbench", version=_version(here))
    splash.progress(0.15)
    import AI_Workbench  # noqa: E402 — imported after the splash on purpose

    splash.progress(0.45)
    return AI_Workbench.main(root, splash)


STAMP = ".aiwb_version"


def clear_stale_bytecode(here: Path) -> bool:
    """5.13.0 (owner audit C1): drop ``__pycache__`` when the installed version changed since the last start.

    Python reuses a ``.pyc`` while the source keeps its size and mtime. Installer files all carry one fixed date and a
    version bump changes a single digit, so after updating 5.11.0 → 5.12.0 the old bytecode of ``AI_Workbench.py``
    kept running. The version is read from the *source* (never from bytecode) before anything of the app is imported.
    Returns True when caches were removed.
    """
    version = _version(here)
    stamp = here / STAMP
    try:
        if not version or stamp.read_text(encoding="utf-8").strip() == version:
            return False
    except OSError:
        pass  # no stamp yet (first start after an install or an update) → clear once
    import shutil
    for cache in [p for p in here.rglob("__pycache__") if p.is_dir()]:
        shutil.rmtree(cache, ignore_errors=True)
    try:
        stamp.write_text(version, encoding="utf-8")
    except OSError:
        pass  # read-only install: caches are cleared every start, still correct
    return True


def _version(here: Path) -> str:
    try:
        text = (here / "aiwb" / "__init__.py").read_text(encoding="utf-8")
        return text.split('__version__ = "', 1)[1].split('"', 1)[0]
    except (OSError, IndexError):
        return ""


if __name__ == "__main__":
    raise SystemExit(run())
