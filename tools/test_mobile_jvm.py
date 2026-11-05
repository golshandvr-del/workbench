"""Compile and run Mobile's platform-independent JVM tests without an Android SDK.

Requires Python 3 and JDK 17+. Downloads hash-pinned Maven dependencies to a
user cache, compiles to a temporary directory, and runs JUnit. This is NOT an
APK, Android lint, instrumentation, or device compatibility gate.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MAVEN = "https://repo.maven.apache.org/maven2/"
# group, artifact, version, SHA-256; compiler/runtime versions are independent of AGP.
ARTIFACTS = (
    ("org.jetbrains.kotlin", "kotlin-compiler-embeddable", "2.2.0", "b2f743ea5ba12f69e0f35e5d8d46069d74c8e2861087548a7e0e14a784bc4cf1"),
    ("org.jetbrains.kotlin", "kotlin-stdlib", "2.2.0", "65d12d85a3b865c160db9147851712a64b10dadd68b22eea22a95bf8a8670dca"),
    ("org.jetbrains.kotlin", "kotlin-script-runtime", "2.2.0", "4ed97fd1e0c9bb1d0948ed5e63cc91456313a59518295b92b2c1514aef556150"),
    ("org.jetbrains.kotlin", "kotlin-reflect", "1.6.10", "3277ac102ae17aad10a55abec75ff5696c8d109790396434b496e75087854203"),
    ("org.jetbrains.kotlin", "kotlin-daemon-embeddable", "2.2.0", "a26cc8e2d8619197cc4d115bea7766e9aa8e0f1e7876ea044ee1b9f305654601"),
    ("org.jetbrains.kotlinx", "kotlinx-coroutines-core-jvm", "1.8.0", "9860906a1937490bf5f3b06d2f0e10ef451e65b95b269f22daf68a3d1f5065c5"),
    ("org.jetbrains", "annotations", "13.0", "ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478"),
    ("junit", "junit", "4.13.2", "8e495b634469d64fb8acfa3495a065cbacc8a0fff55ce1e31007be4c16dc57d3"),
    ("org.hamcrest", "hamcrest-core", "1.3", "66fdef91e9739348df7a096aa384a5685f4e875584cce89386a7a47251c4d8e9"),
    ("org.json", "json", "20260814", "7dd2de1533e766e2b6c07d8194da85145ad313a167a4760050f5c9b6839604fe"),
    ("com.google.zxing", "core", "3.5.3", "8d8064c1636fdaef7189dd9055c7d59950a8940a12f2293956446ec3c109fd82"),
)


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def dependencies(cache: Path) -> list[Path]:
    cache.mkdir(parents=True, exist_ok=True)
    jars = []
    for group, name, version, expected in ARTIFACTS:
        jar = cache / f"{name}-{version}.jar"
        if not jar.is_file() or digest(jar) != expected:
            url = f"{MAVEN}{group.replace('.', '/')}/{name}/{version}/{jar.name}"
            fd, temp_name = tempfile.mkstemp(prefix="download-", dir=cache)
            try:
                with os.fdopen(fd, "wb") as dest, urllib.request.urlopen(url, timeout=60) as response:
                    shutil.copyfileobj(response, dest)
                temp = Path(temp_name)
                if digest(temp) != expected:
                    raise RuntimeError(f"Dependency checksum mismatch: {jar.name}")
                os.replace(temp, jar)
            finally:
                Path(temp_name).unlink(missing_ok=True)
        jars.append(jar)
    return jars


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "aiwb-jvm")
    parser.add_argument("classes", nargs="*", help="Optional JUnit class names (default: every Mobile JVM test)")
    args = parser.parse_args()
    java = shutil.which("java")
    if java is None:
        parser.error("JDK 17+ is required (java not found)")
    jars = dependencies(args.cache)
    compiler_cp = os.pathsep.join(map(str, jars))
    runtime_cp = os.pathsep.join(str(jar) for jar in jars if jar.name.startswith(
        ("kotlin-stdlib-", "junit-", "hamcrest-", "annotations-", "json-", "core-")))
    base = ROOT / "apps/mobile/android/app/src"
    source = base / "main/java/io/github/golshandvr/aiworkbench"
    tests = sorted((base / "test/java/io/github/golshandvr/aiworkbench").glob("*Test.kt"))
    sources = sorted((source / "core").glob("*.kt")) + [source / f"{name}.kt" for name in (
        "CompanionClient", "CompanionCrypto", "QrDecode", "ReleaseInfo", "ReleaseManifest")]
    classes = args.classes or [f"io.github.golshandvr.aiworkbench.{test.stem}" for test in tests]
    with tempfile.TemporaryDirectory(prefix="aiwb-jvm-") as tmp:
        output = Path(tmp) / "tests.jar"
        subprocess.run([java, "-Xmx768m", "-cp", compiler_cp,
                        "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler", "-no-stdlib", "-no-reflect",
                        "-jvm-target", "17", "-classpath", runtime_cp, "-d", str(output),
                        *map(str, sources + tests)], cwd=ROOT, check=True, timeout=300)
        return subprocess.run([java, "-Xmx768m", "-cp", str(output) + os.pathsep + runtime_cp,
                               "org.junit.runner.JUnitCore", *classes], cwd=ROOT, timeout=300).returncode


if __name__ == "__main__":
    raise SystemExit(main())
