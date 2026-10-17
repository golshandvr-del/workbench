#!/usr/bin/env python3
"""Reproducible builder for the AI Workbench Windows self-extracting installer.

Inputs (all inside the repository):
  apps/desktop/release_manifest.json   version, payload file list, timestamps
  apps/desktop/<payload files>         application source + install.ps1/uninstall.bat
  tools/installer_bootstrap.ps1        PowerShell bootstrap embedded via -EncodedCommand

Outputs (in --out, default ./dist):
  AI_Workbench_<ver>_Setup.bat                self-extracting installer (CRLF)
  AI_Workbench_v<ver>_Windows_Payload.zip     raw payload ZIP
  AI_Workbench_v<ver>_Source.zip              full source of apps/desktop
  AI_Workbench_v<ver>_SHA256SUMS.txt          checksums of the above
  release-manifest.json                       machine-readable release metadata

The build is deterministic: identical inputs give byte-identical outputs.
v1.14.4 rebuilds byte-for-byte equal to the originally published installer.

Usage:
  python tools/build_desktop_installer.py [--out DIR] [--check-version X.Y.Z]
                                          [--expect-sha256 SHA]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DESKTOP = REPO / "apps" / "desktop"
BOOTSTRAP = REPO / "tools" / "installer_bootstrap.ps1"
MANIFEST = DESKTOP / "release_manifest.json"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
APP_VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*"([^"]+)"', re.M)
BASE64_LINE = 100
ZIP_ATTR = 0o100644 << 16  # regular file, rw-r--r--


class BuildError(Exception):
    pass


def load_manifest() -> dict:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError(f"cannot read {MANIFEST}: {exc}") from exc
    if data.get("schema_version") != 1:
        raise BuildError("release_manifest.json: unsupported schema_version")
    version = data.get("version", "")
    if not VERSION_RE.match(str(version)):
        raise BuildError(f"release_manifest.json: invalid version {version!r}")
    files = data.get("payload_files")
    if not isinstance(files, list) or not files or not all(isinstance(f, str) for f in files):
        raise BuildError("release_manifest.json: 'payload_files' must be a non-empty list of strings")
    if len(set(files)) != len(files):
        raise BuildError("release_manifest.json: duplicate payload file entries")
    for rel in files:
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts or "\\" in rel:
            raise BuildError(f"release_manifest.json: unsafe payload path {rel!r}")
        if not (DESKTOP / rel).is_file():
            raise BuildError(f"payload file missing: apps/desktop/{rel}")
    for required in ("install.ps1", "uninstall.bat", "AI_Workbench.py"):
        if required not in files:
            raise BuildError(f"release_manifest.json: payload must include {required}")
    ts = data.get("zip_timestamp")
    if not (isinstance(ts, list) and len(ts) == 6 and all(isinstance(x, int) for x in ts)):
        raise BuildError("release_manifest.json: 'zip_timestamp' must be [Y,M,D,h,m,s]")
    data["zip_timestamp"] = tuple(ts)
    overrides = data.get("zip_timestamps_override", {}) or {}
    if not isinstance(overrides, dict):
        raise BuildError("release_manifest.json: 'zip_timestamps_override' must be an object")
    clean = {}
    for key, value in overrides.items():
        if key not in files or not (isinstance(value, list) and len(value) == 6 and all(isinstance(x, int) for x in value)):
            raise BuildError(f"release_manifest.json: invalid timestamp override for {key!r}")
        clean[key] = tuple(value)
    data["zip_timestamps_override"] = clean
    return data


def check_app_version(version: str) -> None:
    text = (DESKTOP / "AI_Workbench.py").read_text(encoding="utf-8")
    m = APP_VERSION_RE.search(text)
    if not m:
        raise BuildError("APP_VERSION not found in AI_Workbench.py")
    if m.group(1) != version:
        raise BuildError(f"version mismatch: manifest {version} vs AI_Workbench.py {m.group(1)}")


def build_payload(manifest: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in manifest["payload_files"]:
            info = zipfile.ZipInfo(rel, manifest["zip_timestamps_override"].get(rel, manifest["zip_timestamp"]))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ZIP_ATTR
            info.create_system = 3
            zf.writestr(info, (DESKTOP / rel).read_bytes(), compresslevel=9)
    return buf.getvalue()


def build_source_zip(manifest: dict) -> bytes:
    """Full apps/desktop tree (tracked-style: skips caches) for source releases."""
    buf = io.BytesIO()
    skip_dirs = {"__pycache__", ".pytest_cache", ".workbench"}
    files = sorted(
        p for p in DESKTOP.rglob("*")
        if p.is_file() and not (set(p.relative_to(DESKTOP).parts) & skip_dirs) and p.suffix != ".pyc"
    )
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in files:
            rel = p.relative_to(DESKTOP).as_posix()
            info = zipfile.ZipInfo(f"AI_Workbench_v{manifest['version']}/{rel}", manifest["zip_timestamp"])
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ZIP_ATTR
            info.create_system = 3
            zf.writestr(info, p.read_bytes(), compresslevel=9)
    return buf.getvalue()


def build_bat(payload: bytes) -> bytes:
    script = BOOTSTRAP.read_bytes().decode("utf-8")
    if script.startswith("\ufeff"):
        script = script[1:]
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    if len(encoded) > 8000:
        raise BuildError("bootstrap too long for a cmd.exe line (8191 char limit)")
    head = [
        "@echo off",
        "setlocal DisableDelayedExpansion",
        'set "_AIWB_SELF=%~f0"',
        f"powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}",
        'set "_AIWB_EXIT=%ERRORLEVEL%"',
        'if not "%_AIWB_EXIT%"=="0" (',
        "  echo.",
        "  echo AI Workbench installation failed. See the error above.",
        "  pause",
        ")",
        "exit /b %_AIWB_EXIT%",
    ]
    b64 = base64.b64encode(payload).decode("ascii")
    body = [b64[i:i + BASE64_LINE] for i in range(0, len(b64), BASE64_LINE)]
    lines = head + ["###AIWB_PAYLOAD_BEGIN###"] + body + ["###AIWB_PAYLOAD_END###", ""]
    return "\r\n".join(lines).encode("ascii")


def verify_bat(bat: bytes, payload: bytes) -> None:
    """Decode the installer exactly as the bootstrap does and compare."""
    lines = bat.decode("ascii").split("\r\n")
    begin = lines.index("###AIWB_PAYLOAD_BEGIN###")
    end = lines.index("###AIWB_PAYLOAD_END###")
    decoded = base64.b64decode("".join(l.strip() for l in lines[begin + 1:end]))
    if decoded != payload:
        raise BuildError("self-check failed: embedded payload differs")
    with zipfile.ZipFile(io.BytesIO(decoded)) as zf:
        bad = zf.testzip()
        if bad:
            raise BuildError(f"self-check failed: corrupt entry {bad}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / "dist"))
    ap.add_argument("--check-version", help="fail unless the manifest version equals this (e.g. from a tag)")
    ap.add_argument("--expect-sha256", help="fail unless the Setup.bat hash equals this")
    args = ap.parse_args(argv)
    try:
        manifest = load_manifest()
        version = manifest["version"]
        if args.check_version and args.check_version.lstrip("v") != version:
            raise BuildError(f"tag version {args.check_version} != manifest version {version}")
        check_app_version(version)
        payload = build_payload(manifest)
        bat = build_bat(payload)
        verify_bat(bat, payload)
        source = build_source_zip(manifest)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        artifacts = {
            f"AI_Workbench_{version}_Setup.bat": bat,
            f"AI_Workbench_v{version}_Windows_Payload.zip": payload,
            f"AI_Workbench_v{version}_Source.zip": source,
        }
        for name, data in artifacts.items():
            (out / name).write_bytes(data)
        sums = "".join(f"{sha256(d)}  {n}\n" for n, d in artifacts.items())
        (out / f"AI_Workbench_v{version}_SHA256SUMS.txt").write_text(sums, encoding="ascii", newline="\n")
        meta = {
            "schema_version": 1,
            "app": manifest.get("app", "ai-workbench-desktop"),
            "platform": "windows",
            "version": version,
            "channel": manifest.get("channel", "stable"),
            "installer": f"AI_Workbench_{version}_Setup.bat",
            "artifacts": [{"name": n, "size": len(d), "sha256": sha256(d)} for n, d in artifacts.items()],
        }
        (out / "release-manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        setup_hash = sha256(bat)
        if args.expect_sha256 and args.expect_sha256.lower() != setup_hash:
            raise BuildError(f"Setup.bat sha256 {setup_hash} != expected {args.expect_sha256}")
        print(sums, end="")
        print(f"OK: AI Workbench {version} installer built in {out}")
        return 0
    except BuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
