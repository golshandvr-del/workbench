"""Live diagnosis for the paste box (roadmap 5.10.0): what an answer *is*, before anything is imported.

``preview(text, state)`` is read-only and never raises. It tells the user, while they paste:

* the kind of answer — Project Charter, manager proposal, files (AIWB blocks / Markdown / Strict JSON / ZIP),
  context request, or nothing Workbench can read;
* the counts that matter (AIs · tasks · milestones for a charter, files for a task answer);
* the automatic fixes Workbench will make (never hidden) and the problems it will refuse.

``line`` is one short sentence for the paste box's status line, e.g.
``"Charter ✓ · 4 AIs · 9 tasks · 2 auto-fixes"`` or ``"Charter ✗ · tasks[0].depends_on_refs: unknown task 't9'"``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CONTEXT_RE = re.compile(r"<<<AIWB_CONTEXT_REQUEST>>>")
PROPOSAL_RE = re.compile(r"<<<AIWB_MANAGER_PROPOSAL>>>")
HANDOFF_RE = re.compile(r"(?s)<<<AIWB_HANDOFF>>>.*?<<<AIWB_END_HANDOFF>>>")


@dataclass
class Preview:
    kind: str = "empty"            # empty | charter | proposal | files | context_request | truncated | unknown
    ok: bool = False               # True when importing would succeed
    line: str = ""                 # one-line summary for the status line
    counts: dict[str, int] = field(default_factory=dict)
    fixes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    format: str = ""

    def details(self, limit: int = 6) -> str:
        """A few lines below the status line: fixes, problems, warnings, file names."""
        out: list[str] = []
        for title, items in (("Problem", self.problems), ("Auto-fix", self.fixes), ("Warning", self.warnings)):
            out += [f"{title}: {x}" for x in items[:limit]]
            if len(items) > limit:
                out.append(f"… {len(items) - limit} more {title.lower()}(s)")
        if self.paths:
            shown = ", ".join(self.paths[:limit]) + (f" … (+{len(self.paths) - limit})" if len(self.paths) > limit else "")
            out.append("Files: " + shown)
        return "\n".join(out)


def _plural(n: int, word: str, plural: str = "") -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def preview(text: str, state: dict[str, Any] | None = None) -> Preview:
    try:
        return _preview(text or "", state)
    except Exception as exc:  # noqa: BLE001 - live diagnosis must never break the paste box
        return Preview("unknown", False, f"Could not check this answer ({type(exc).__name__}); it can still be pasted.")


def _preview(text: str, state: dict[str, Any] | None) -> Preview:
    if not text.strip():
        return Preview("empty", False, "Paste the whole answer of the chat here (or load a ZIP).")
    from ..v2.charter import has_charter, parse_charter
    if has_charter(text):
        r = parse_charter(text, state)
        data = r.get("data") or {}
        n_ai = len([a for a in (data.get("team") or {}).get("agents", []) if isinstance(a, dict)])
        n_t = len(data.get("tasks") or [])
        n_m = len((data.get("roadmap") or {}).get("milestones") or [])
        p = Preview("charter", bool(r["ok"]), counts={"ais": n_ai, "tasks": n_t, "milestones": n_m},
                    fixes=list(r.get("fixes") or []), problems=list(r.get("errors") or []),
                    warnings=list(r.get("warnings") or []))
        if p.ok:
            p.line = f"Charter ✓ · {_plural(n_ai, 'AI')} · {_plural(n_t, 'task')} · {_plural(n_m, 'milestone')}"
            if p.fixes:
                p.line += f" · {_plural(len(p.fixes), 'auto-fix', 'auto-fixes')}"
            if p.warnings:
                p.line += f" · {_plural(len(p.warnings), 'warning')}"
        else:
            p.line = f"Charter ✗ · {_plural(len(p.problems), 'problem')}: {p.problems[0] if p.problems else 'unreadable'}"
            p.line += " — paste it anyway to get a fix prompt for the model."
        return p
    if PROPOSAL_RE.search(text):
        return Preview("proposal", True, "Manager proposal ✓ — paste it to review its changes.")
    if CONTEXT_RE.search(text):
        return Preview("context_request", True, "Context request ✓ — the model asks for files or answers.")
    from .answer_files import extract
    ex = extract(text)
    paths = [f["path"] for f in ex.files]
    if ex.files:
        p = Preview("files", not ex.truncated, counts={"files": len(ex.files)}, fixes=list(ex.fixes),
                    problems=list(ex.problems), paths=paths, format=ex.format)
        if ex.truncated:
            p.kind = "truncated"
            p.line = (f"Cut off ✗ · {_plural(len(ex.files), 'file')} so far ({ex.label}) — paste it to get a continue "
                      "prompt.")
            return p
        p.line = f"Files ✓ · {_plural(len(ex.files), 'file')} · {ex.label}"
        if not HANDOFF_RE.search(text) and not ex.manifest:
            p.warnings.append("no AIWB_HANDOFF manifest — the answer is linked to the task you pasted it for")
        if p.fixes:
            p.line += f" · {_plural(len(p.fixes), 'auto-fix', 'auto-fixes')}"
        if p.problems:
            p.line += f" · {_plural(len(p.problems), 'skipped item')}"
        return p
    if HANDOFF_RE.search(text):
        return Preview("files", True, "Handoff report ✓ · no files (summary and open items only).",
                       counts={"files": 0})
    from .normalize import truncation_report
    if ex.truncated or truncation_report(text).truncated:
        return Preview("truncated", False, "Cut off ✗ — the answer ends in the middle; paste it to get a continue prompt.",
                       problems=list(ex.problems))
    return Preview("unknown", False, "Nothing Workbench can read yet: no charter, no files, no handoff. "
                   "It will be kept in the Inbox if you paste it.", problems=list(ex.problems))


def preview_zip(data: bytes, name: str = "answer.zip") -> tuple[str, Preview]:
    """``(canonical answer text, preview)`` for a ZIP the user loaded."""
    from .answer_files import canonical_zip
    try:
        text, ex = canonical_zip(data, name=name)
    except Exception as exc:  # noqa: BLE001 - a broken ZIP is reported, never raised into the UI
        return "", Preview("unknown", False, f"ZIP ✗ · {exc}", problems=[str(exc)])
    paths = [f["path"] for f in ex.files]
    if not ex.files:
        return "", Preview("unknown", False, "ZIP ✗ · no usable files in " + name, problems=list(ex.problems))
    p = Preview("files", True, f"ZIP ✓ · {_plural(len(ex.files), 'file')} from {name}", counts={"files": len(ex.files)},
                fixes=list(ex.fixes), problems=list(ex.problems), paths=paths, format="zip")
    if p.fixes:
        p.line += f" · {_plural(len(p.fixes), 'auto-fix', 'auto-fixes')}"
    if p.problems:
        p.line += f" · {_plural(len(p.problems), 'skipped item')}"
    return text, p
