#!/usr/bin/env python3
"""Mark a ROADMAP step done and move the "active" marker to the next step.

    python tools/mark_roadmap_step.py 1.14.7 --evidence "`aiwb/github/artifacts.py`, ..." \
        --next 1.14.8 --next-anchor v1148--one-click-sync--build-orchestrator [--released desktop-v1.14.7]

Updates ROADMAP.md (table row, checklist of the step's section, header lines),
the audit table and the README status line. Plain text edits, idempotent.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step")
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--next", dest="nxt")
    ap.add_argument("--next-title", default="")
    ap.add_argument("--next-anchor", default="")
    ap.add_argument("--released", default="")
    ap.add_argument("--section-heading", default="", help="heading prefix of the step section, default '### v<step>'")
    a = ap.parse_args()
    p = REPO / "ROADMAP.md"
    s = p.read_text(encoding="utf-8")
    esc = re.escape(a.step)
    # table row: | **1.14.7** | **Title** | ⬜ **گام فعال** | — |   or   | 1.14.7 | Title | ⬜ | — |
    row = re.compile(r"^\| (?:\*\*)?" + esc + r"(?:\*\*)? \| (?:\*\*)?(.+?)(?:\*\*)? \| [^|]*\| [^|]*\|$", re.M)
    m = row.search(s)
    if not m:
        raise SystemExit(f"row for {a.step} not found")
    title = m.group(1)
    ev = a.evidence + (f"؛ Release `{a.released}`" if a.released else "")
    s = s[: m.start()] + f"| {a.step} | {title} | ✅ | {ev} |" + s[m.end():]
    if a.nxt:
        en = re.escape(a.nxt)
        m2 = re.compile(r"^\| (?:\*\*)?" + en + r"(?:\*\*)? \| (?:\*\*)?(.+?)(?:\*\*)? \| ([^|]*)\| ([^|]*)\|$", re.M).search(s)
        if m2:
            ntitle = a.next_title or m2.group(1)
            state = m2.group(2).strip()
            state = "⬜ **گام فعال**" if state.startswith("⬜") else state.replace("**گام فعال**", "").strip() + " **گام فعال**"
            s = s[: m2.start()] + f"| **{a.nxt}** | **{ntitle}** | {state} | {m2.group(3).strip()} |" + s[m2.end():]
            a.next_title = ntitle
    heading = a.section_heading or f"### v{a.step}"
    i = s.find(heading)
    if i >= 0:
        j = s.find("\n### ", i + 1)
        j2 = s.find("\n## ", i + 1)
        end = min(x for x in (j, j2, len(s)) if x != -1)
        s = s[:i] + s[i:end].replace("- [ ]", "- [x]") + s[end:]
    if a.released and a.released.startswith("desktop-v"):
        s = re.sub(r"\*\*نسخهٔ Desktop منتشرشده:\*\* `[^`]+`", f"**نسخهٔ Desktop منتشرشده:** `{a.released}`", s)
    if a.released and a.released.startswith("mobile-v"):
        s = re.sub(r"\*\*نسخهٔ Mobile منتشرشده:\*\* `[^`]+`", f"**نسخهٔ Mobile منتشرشده:** `{a.released}`", s)
    if a.nxt:
        anchor = f"(#{a.next_anchor})" if a.next_anchor else ""
        s = re.sub(r"^\*\*گام فعال بعدی:\*\* .*$", f"**گام فعال بعدی:** [`v{a.nxt}` — {a.next_title}]{anchor}" if anchor else f"**گام فعال بعدی:** `v{a.nxt}` — {a.next_title}", s, count=1, flags=re.M)
    p.write_text(s, encoding="utf-8")

    audit = REPO / "docs/audit/IMPLEMENTATION_AUDIT_FA.md"
    t = audit.read_text(encoding="utf-8")
    m3 = re.compile(r"^\| (?:\*\*)?" + esc + r"(?:\*\*)? \| (?:\*\*)?(.+?)(?:\*\*)? \| [^|]*\| [^|]*\|$", re.M).search(t)
    if m3:
        t = t[: m3.start()] + f"| {a.step} | {m3.group(1)} | ✅ | {a.evidence} |" + t[m3.end():]
        t = re.sub(r"^\| \*\*([0-9.]+)\*\* \| \*\*(.+?)\*\* \| \*\*✅\*\* \|", r"| \1 | \2 | ✅ |", t, flags=re.M)
    audit.write_text(t, encoding="utf-8")

    readme = REPO / "README.md"
    r = readme.read_text(encoding="utf-8")
    if a.released.startswith("desktop-v"):
        r = re.sub(r"(\| `apps/desktop` \| )\*\*[0-9.]+\*\*", r"\g<1>**" + a.released[len("desktop-v"):] + "**", r)
    r = re.sub(r"Done: 1\.14\.1–[0-9.]+,", f"Done: 1.14.1–{a.step},", r) if a.step.startswith("1.14") else r
    if a.nxt:
        r = re.sub(r"\*\*Next: [^*]+\*\*", f"**Next: {a.nxt} {a.next_title}**", r, count=1)
    readme.write_text(r, encoding="utf-8")
    print(f"marked {a.step} done; next {a.nxt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
