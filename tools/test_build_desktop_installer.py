"""Tests for the reproducible desktop installer builder."""
from __future__ import annotations

import base64
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_desktop_installer as b  # noqa: E402


class BuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = b.load_manifest()

    def test_manifest_matches_app_version(self) -> None:
        b.check_app_version(self.manifest["version"])

    def test_build_is_deterministic(self) -> None:
        p1 = b.build_payload(self.manifest)
        p2 = b.build_payload(self.manifest)
        self.assertEqual(p1, p2)
        self.assertEqual(b.build_bat(p1), b.build_bat(p2))

    def test_payload_contents_match_manifest(self) -> None:
        payload = b.build_payload(self.manifest)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertEqual(zf.namelist(), self.manifest["payload_files"])
            self.assertIsNone(zf.testzip())
            for name, src in self.manifest["payload"]:
                self.assertEqual(zf.read(name), (b.REPO / src).read_bytes())

    def test_bat_structure(self) -> None:
        payload = b.build_payload(self.manifest)
        bat = b.build_bat(payload)
        self.assertNotIn(b"\n", bat.replace(b"\r\n", b""))  # CRLF only
        lines = bat.decode("ascii").split("\r\n")
        self.assertEqual(lines[0], "@echo off")
        self.assertLess(len(lines[3]), 8191)
        b.verify_bat(bat, payload)
        encoded = lines[3].rsplit(" ", 1)[1]
        script = base64.b64decode(encoded).decode("utf-16le")
        self.assertIn("###AIWB_PAYLOAD_BEGIN###", script)
        self.assertIn("install.ps1", script)

    def test_unsafe_or_duplicate_payload_rejected(self) -> None:
        import json as _json
        original = b.MANIFEST.read_text(encoding="utf-8")
        cases = [
            {"path": "../evil.py", "source": "apps/desktop/src/AI_Workbench.py"},
            {"path": "x.py", "source": "../../etc/passwd"},
            {"path": "ai_workbench.PY", "source": "apps/desktop/src/AI_Workbench.py"},
        ]
        try:
            for bad in cases:
                data = _json.loads(original)
                data["payload"].append(bad)
                b.MANIFEST.write_text(_json.dumps(data), encoding="utf-8")
                with self.assertRaises(b.BuildError, msg=str(bad)):
                    b.load_manifest()
        finally:
            b.MANIFEST.write_text(original, encoding="utf-8")

    def test_corrupted_bat_detected(self) -> None:
        payload = b.build_payload(self.manifest)
        bat = bytearray(b.build_bat(payload))
        idx = bat.index(b"###AIWB_PAYLOAD_BEGIN###") + 40
        bat[idx] = ord("A") if bat[idx] != ord("A") else ord("B")
        with self.assertRaises(b.BuildError):
            b.verify_bat(bytes(bat), payload)

    def test_main_writes_artifacts_and_rejects_wrong_tag(self) -> None:
        v = self.manifest["version"]
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(b.main(["--out", tmp, "--check-version", f"v{v}"]), 0)
            names = {p.name for p in Path(tmp).iterdir()}
            self.assertIn(f"AI_Workbench_{v}_Setup.bat", names)
            self.assertIn("release-manifest.json", names)
            meta = json.loads((Path(tmp) / "release-manifest.json").read_text())
            self.assertEqual(meta["version"], v)
            self.assertEqual(b.main(["--out", tmp, "--check-version", "v0.0.1"]), 1)
            self.assertEqual(b.main(["--out", tmp, "--expect-sha256", "0" * 64]), 1)


if __name__ == "__main__":
    unittest.main()
