#!/usr/bin/env python3
"""Prepare a desktop release: bump versions and register new payload files.

    python tools/bump_desktop_release.py 1.14.8 \
        --module github/orchestrator.py --test test_orchestrator.py

* APP_VERSION in AI_Workbench.py, ``__version__`` in aiwb/__init__.py and the
  API client User-Agent;
* release_manifest.json version, renames the Windows checklist entry and adds
  new aiwb modules / unit tests / top-level files;
* install.ps1 lists (keeps BOM/line endings);
* creates docs/release/vX/WINDOWS_RELEASE_CHECKLIST_vX.md from the previous one
  if missing.
Idempotent: running twice changes nothing.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DESKTOP = REPO / "apps/desktop"


def _rw(path: Path, fn) -> None:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    crlf = "\r\n" in text
    new = fn(text.replace("\r\n", "\n"))
    if crlf:
        new = new.replace("\n", "\r\n")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8"))


def _add_to_ps_list(text: str, var: str, items: list[str], after: str | None = None) -> str:
    m = re.search(r"(foreach \(\$" + var + r" in @\()([^)]*)(\)\))", text)
    assert m, var
    current = re.findall(r"'([^']+)'", m.group(2))
    for item in items:
        if item in current:
            continue
        if after and after in current:
            current.insert(current.index(after) + 1, item)
            after = item
        else:
            current.append(item)
    return text[: m.start(2)] + ", ".join(f"'{c}'" for c in current) + text[m.end(2):]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("--module", action="append", default=[], help="aiwb-relative module, e.g. github/x.py")
    ap.add_argument("--test", action="append", default=[], help="unit test file in apps/desktop/tests")
    ap.add_argument("--top", action="append", default=[], help="top-level src file, e.g. foo.py")
    a = ap.parse_args()
    v = a.version
    assert re.fullmatch(r"\d+\.\d+\.\d+", v)

    _rw(DESKTOP / "src/AI_Workbench.py", lambda s: re.sub(r'^APP_VERSION = "[^"]+"', f'APP_VERSION = "{v}"', s, count=1, flags=re.M))
    _rw(DESKTOP / "src/aiwb/__init__.py", lambda s: re.sub(r'__version__ = "[^"]+"', f'__version__ = "{v}"', s, count=1))
    _rw(DESKTOP / "src/aiwb/github/api_client.py", lambda s: re.sub(r'user_agent: str = "AI-Workbench/[^"]+"', f'user_agent: str = "AI-Workbench/{v}"', s, count=1))

    mpath = DESKTOP / "release_manifest.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    old_version = m["version"]
    m["version"] = v
    payload = m["payload"]
    paths = [e["path"] for e in payload]
    old_check = next((p for p in paths if p.startswith("WINDOWS_RELEASE_CHECKLIST_v")), None)
    new_check = f"WINDOWS_RELEASE_CHECKLIST_v{v}.md"
    checklist_dir = REPO / f"docs/release/v{v}"
    checklist_dir.mkdir(parents=True, exist_ok=True)
    new_check_file = checklist_dir / new_check
    if old_check and old_check != new_check:
        for e in payload:
            if e["path"] == old_check:
                if not new_check_file.exists():
                    prev = REPO / e["source"]
                    new_check_file.write_text(prev.read_text(encoding="utf-8").replace(old_version, v), encoding="utf-8")
                e["path"] = new_check
                e["source"] = f"docs/release/v{v}/{new_check}"

    def insert_after(prefix_match, path: str, source: str) -> None:
        cur = [e["path"] for e in payload]
        if path in cur:
            return
        idx = max((i for i, p in enumerate(cur) if prefix_match(p)), default=len(cur) - 1)
        payload.insert(idx + 1, {"path": path, "source": source})

    for mod in a.module:
        insert_after(lambda p: p.startswith("aiwb/"), f"aiwb/{mod}", f"apps/desktop/src/aiwb/{mod}")
    for t in a.test:
        insert_after(lambda p: p.startswith("test_"), t, f"apps/desktop/tests/{t}")
    for t in a.top:
        insert_after(lambda p: p.endswith(".py") and "/" not in p and not p.startswith("test_"), t, f"apps/desktop/src/{t}")
    mpath.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")

    def ps(s: str) -> str:
        if old_check and old_check != new_check:
            s = s.replace(f"'{old_check}'", f"'{new_check}'")
        s = _add_to_ps_list(s, "fileName", a.test + a.top)
        s = _add_to_ps_list(s, "moduleName", a.module)
        return s
    _rw(DESKTOP / "installer/install.ps1", ps)
    print(f"bumped {old_version} -> {v}; modules={a.module} tests={a.test} top={a.top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
