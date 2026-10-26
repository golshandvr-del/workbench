"""5.13.0 (owner audit C1): after installing 5.12.0 over 5.11.0 the window still said 5.11.0.

Root cause: Python trusts ``__pycache__/*.pyc`` while the source keeps its size and mtime. The installer payload gives
every file one fixed date, and a version bump changes a single digit (same size), so the old bytecode kept running.
These tests reproduce exactly that and check both fixes: the launcher clears caches when the version changed, and the
installer drops ``__pycache__`` and force-compiles.
"""
from __future__ import annotations

import os
import py_compile
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import launch_aiwb  # noqa: E402

INSTALLER = Path(__file__).resolve().parents[1] / "installer" / "install.ps1"
FIXED = 1_792_195_200  # one fixed timestamp, like the payload's zip entries


def _install(root: Path, version: str) -> None:
    """Write a tiny 'app' whose files keep the same size and mtime across versions (as the real payload does)."""
    (root / "aiwb").mkdir(parents=True, exist_ok=True)
    files = {root / "aiwb" / "__init__.py": f'__version__ = "{version}"\n',
             root / "app_mod.py": f'APP_VERSION = "{version}"\n'}
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
        os.utime(path, (FIXED, FIXED))


def _run_version(root: Path) -> str:
    out = subprocess.run([sys.executable, "-c", "import app_mod; print(app_mod.APP_VERSION)"], cwd=root,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


class StaleBytecode(unittest.TestCase):
    def test_the_bug_is_real_same_size_same_mtime_keeps_old_bytecode(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _install(root, "5.11.0")
            py_compile.compile(str(root / "app_mod.py"))  # the installer's compileall of the old version
            _install(root, "5.12.0")                       # update copies new sources over: same size, same date
            self.assertEqual(_run_version(root), "5.11.0", "reproduces C1: Python ran the old bytecode")

    def test_launcher_clears_caches_once_when_the_version_changed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _install(root, "5.11.0")
            py_compile.compile(str(root / "app_mod.py"))
            self.assertTrue(launch_aiwb.clear_stale_bytecode(root), "first start: no stamp → clear")
            self.assertEqual((root / launch_aiwb.STAMP).read_text(encoding="utf-8"), "5.11.0")
            py_compile.compile(str(root / "app_mod.py"))
            self.assertFalse(launch_aiwb.clear_stale_bytecode(root), "same version → caches kept (fast start)")
            _install(root, "5.12.0")
            self.assertTrue(launch_aiwb.clear_stale_bytecode(root), "version changed → caches dropped")
            self.assertFalse(list(root.rglob("__pycache__")))
            self.assertEqual(_run_version(root), "5.12.0", "the new version really runs")

    def test_launcher_runs_the_check_before_importing_the_app(self):
        text = (SRC / "launch_aiwb.py").read_text(encoding="utf-8")
        self.assertLess(text.index("clear_stale_bytecode(here)"), text.index("import AI_Workbench"))

    def test_installer_drops_pycache_and_force_compiles(self):
        text = INSTALLER.read_text(encoding="utf-8-sig")
        self.assertIn("-Filter '__pycache__'", text)
        self.assertIn("compileall -f", text)
        self.assertLess(text.index("-Filter '__pycache__'"), text.index("foreach ($fileName in"),
                        "caches are removed before the new sources are copied")

    def test_app_and_package_versions_match(self):
        app = (SRC / "AI_Workbench.py").read_text(encoding="utf-8").split('APP_VERSION = "', 1)[1].split('"', 1)[0]
        self.assertEqual(app, launch_aiwb._version(SRC))


if __name__ == "__main__":
    unittest.main()
