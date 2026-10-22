"""Roadmap 5.8.0 (audit A11/A15): every call of a shared UI helper must match the helper's signature.

The 5.7.0 paste boxes crashed with ``place_dialog() missing 1 required positional argument: 'height'`` because the
GUI smokes never opened the real dialog. This test binds every ``ui_layout.<fn>(...)`` / ``layout.<fn>(...)`` call in
the application source to the real function signature, statically, so a wrong call can never ship again.
"""
from __future__ import annotations

import ast
import inspect
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from aiwb.ui import layout  # noqa: E402

ALIASES = {"ui_layout", "layout"}


def _calls() -> list[tuple[Path, ast.Call, str]]:
    out = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id in ALIASES):
                out.append((path, node, node.func.attr))
    return out


class UiCallSignatures(unittest.TestCase):
    def test_every_layout_call_binds(self) -> None:
        calls = _calls()
        self.assertGreater(len(calls), 10, "the scan found the layout calls")
        bad = []
        for path, node, name in calls:
            fn = getattr(layout, name, None)
            if fn is None:
                bad.append(f"{path.name}:{node.lineno} ui_layout.{name} does not exist")
                continue
            if not callable(fn) or inspect.isclass(fn):
                continue
            if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
                continue
            args = [object()] * len(node.args)
            kwargs = {k.arg: object() for k in node.keywords}
            try:
                inspect.signature(fn).bind(*args, **kwargs)
            except TypeError as exc:
                bad.append(f"{path.relative_to(SRC)}:{node.lineno} ui_layout.{name}(…): {exc}")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_place_dialog_calls_pass_a_size(self) -> None:
        for path, node, name in _calls():
            if name == "place_dialog":
                with self.subTest(at=f"{path.name}:{node.lineno}"):
                    self.assertGreaterEqual(len(node.args), 3, "place_dialog(win, width, height[, parent])")
                    self.assertIsInstance(node.args[1], (ast.Constant, ast.Name, ast.BinOp, ast.Call, ast.Attribute))


if __name__ == "__main__":
    unittest.main()
