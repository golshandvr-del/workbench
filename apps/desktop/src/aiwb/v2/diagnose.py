"""Smart problem detection and the troubleshooting prompt (roadmap 4.2.0, flowchart F13–F15, correction C5).

"Is the output acceptable?" has two layers: this automatic diagnosis, then the user's judgement. The diagnosis is
a pure function of the pasted answer and what the task expected; the phone has the same rules (``core/Diagnose.kt``)
and both are checked against ``packages/contracts/fixtures/diagnose/diagnose-corpus.v1.json``.

Problem codes (``error`` = the answer is not acceptable as it is; ``warning`` = the user should look):

* ``truncated`` (error) — a file block, a fence or the manifest was opened and never closed;
* ``no_manifest`` (error; a warning when the answer delivers files — 5.10.0, Markdown / JSON / ZIP answers rarely
  carry one) — no ``AIWB_HANDOFF`` manifest;
* ``wrong_attempt`` (error) — the answer names another attempt;
* ``unsafe_path`` (error) — absolute path or ``..``;
* ``out_of_scope`` (error) — a file outside the task's allowed paths;
* ``empty_file`` (error) — a file block with no content;
* ``missing_deliverable`` (error) — an expected file was not delivered;
* ``failed_outcome`` (error) — the AI itself reports ``failed`` / ``blocked``;
* ``copy_damage`` (warning) — a code file not inside a four-backtick fence, or Python whose indentation was lost;
* ``unverified_test_claim`` (warning) — the AI claims tests pass; a model claim is never evidence.

After ``TROUBLESHOOT_ATTEMPTS`` troubleshooting prompts for the same task the guide escalates to the project manager.
"""
from __future__ import annotations

import json
import re
from typing import Any

FILE_HEAD = re.compile(r'^\s*<<<AIWB_FILE\s+(.*?)\s*>>>\s*$')
FILE_END = "<<<AIWB_END_FILE>>>"
ATTR = re.compile(r'(\w+)="([^"]*)"')
ATTEMPT = re.compile(r"^\s*AIWB_ATTEMPT_ID:\s*(\S+)", re.M)
MAN_OPEN, MAN_END = "<<<AIWB_HANDOFF>>>", "<<<AIWB_END_HANDOFF>>>"
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
TEST_CLAIM = re.compile(r"\b(all\s+)?tests?\s+(pass(ed|es)?|green|succeed(ed|s)?)\b|\bbuild\s+(passed|succeeded)\b", re.I)
CODE_EXT = (".py", ".kt", ".kts", ".java", ".js", ".ts", ".tsx", ".jsx", ".dart", ".go", ".rs", ".c", ".cpp", ".h",
            ".cs", ".swift", ".rb", ".php", ".gradle", ".yml", ".yaml")
SEVERITY = {"truncated": "error", "no_manifest": "error", "wrong_attempt": "error", "unsafe_path": "error",
            "out_of_scope": "error", "empty_file": "error", "missing_deliverable": "error", "failed_outcome": "error",
            "copy_damage": "warning", "unverified_test_claim": "warning"}


def parse_files(text: str) -> tuple[list[dict[str, Any]], bool]:
    """AIWB file blocks as [{path, body, fenced}], and whether the last block was left open."""
    files: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        if cur is None:
            m = FILE_HEAD.match(line)
            if m:
                cur = {"path": dict(ATTR.findall(m.group(1))).get("path", ""), "lines": []}
            continue
        if line.strip() == FILE_END:
            files.append(_close(cur))
            cur = None
        else:
            cur["lines"].append(line)
    if cur is not None:
        files.append(_close(cur))
    return files, cur is not None


def _close(cur: dict[str, Any]) -> dict[str, Any]:
    lines = list(cur["lines"])
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    fenced = bool(lines) and bool(FENCE.match(lines[0]))
    fence_balanced = True
    if fenced:
        mark = FENCE.match(lines[0]).group(1)
        fence_balanced = len(lines) > 1 and lines[-1].strip() == mark
        lines = lines[1:-1] if fence_balanced else lines[1:]
    return {"path": cur["path"], "body": "\n".join(lines), "fenced": fenced, "fence_balanced": fence_balanced}


def task_paths(task: dict[str, Any]) -> list[str]:
    """Where a task may write: ``allowed_paths`` plus ``scope.include`` (empty = not restricted)."""
    out = [str(x) for x in task.get("allowed_paths") or []]
    out += [str(x) for x in ((task.get("scope") or {}).get("include") or []) if str(x) not in out]
    return out


def _in_scope(path: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    for a in allowed:
        a = a.strip()
        base = a.rstrip("*").rstrip("/")
        if not base or path == base or path.startswith(base + "/") or (a.endswith("*") and path.startswith(a.rstrip("*"))):
            return True
    return False


def _python_indent_lost(body: str) -> bool:
    lines = [ln for ln in body.split("\n") if ln.strip() and not ln.strip().startswith("#")]
    for a, b in zip(lines, lines[1:]):
        if re.match(r"^\s*(def|class|if|for|while|with|try|elif|else|except|finally)\b.*:\s*$", a):
            if len(b) - len(b.lstrip()) <= len(a) - len(a.lstrip()):
                return True
    return False


def _manifest(text: str) -> tuple[dict[str, Any] | None, bool]:
    """(manifest or None, open-but-not-closed)."""
    i = text.find(MAN_OPEN)
    if i < 0:
        return None, False
    j = text.find(MAN_END, i)
    if j < 0:
        return None, True
    body = text[i + len(MAN_OPEN):j].strip().strip("`").strip()
    if body.startswith("json"):
        body = body[4:]
    try:
        data = json.loads(body)
    except ValueError:
        return {}, False
    return (data if isinstance(data, dict) else {}), False


def diagnose(text: str, *, attempt_id: str = "", allowed_paths: list[str] | None = None,
             expected_paths: list[str] | None = None) -> dict[str, Any]:
    """Problems of one pasted AI answer. Returns {"acceptable", "problems": [{code, severity, message, path}]}."""
    probs: list[dict[str, Any]] = []

    def add(code: str, message: str, path: str = "", severity: str = "") -> None:
        probs.append({"code": code, "severity": severity or SEVERITY[code], "message": message, "path": path})

    text = text or ""
    files, open_file = parse_files(text)
    man, man_open = _manifest(text)
    if open_file:
        add("truncated", f"the file block {files[-1]['path'] or '(no path)'} was never closed — the answer was cut off",
            files[-1]["path"])
    elif man_open:
        add("truncated", "the AIWB_HANDOFF manifest was opened and never closed — the answer was cut off")
    if man is None and not man_open:
        add("no_manifest", "there is no AIWB_HANDOFF manifest (summary, outcome, open items)",
            severity="warning" if files else "")
    m = ATTEMPT.search(text)
    claimed = (m.group(1) if m else "") or str((man or {}).get("attempt_id", ""))
    if attempt_id and claimed and claimed != attempt_id:
        add("wrong_attempt", f"the answer is for attempt {claimed}, this prompt was {attempt_id}")
    for f in files:
        p = f["path"]
        if not p or p.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", p) or ".." in p.replace("\\", "/").split("/"):
            add("unsafe_path", f"unsafe file path {p!r}", p)
            continue
        if not _in_scope(p, list(allowed_paths or [])):
            add("out_of_scope", f"{p} is outside this task's allowed paths ({', '.join(allowed_paths or [])})", p)
        if f["fenced"] and not f["fence_balanced"] and not open_file:
            add("truncated", f"the code fence in {p} was never closed", p)
        if not f["body"].strip():
            add("empty_file", f"{p} is empty", p)
            continue
        if p.lower().endswith(CODE_EXT) and not f["fenced"]:
            add("copy_damage", f"{p} is not inside a four-backtick fence; indentation or backticks may be lost", p)
        elif p.lower().endswith(".py") and _python_indent_lost(f["body"]):
            add("copy_damage", f"{p} lost its indentation (a block line is not followed by an indented line)", p)
    delivered = {f["path"] for f in files}
    for p in expected_paths or []:
        if p not in delivered:
            add("missing_deliverable", f"expected file {p} was not delivered", p)
    outcome = str((man or {}).get("outcome", ""))
    if outcome in ("failed", "blocked"):
        add("failed_outcome", f"the AI reports the outcome '{outcome}'")
    claims = (man or {}).get("validation_claims") or []
    if claims or TEST_CLAIM.search(text):
        add("unverified_test_claim", "the AI claims tests/build passed — that is not evidence; run them or record NOT RUN")
    return {"acceptable": not any(p["severity"] == "error" for p in probs), "problems": probs}


def troubleshoot_prompt(state: dict[str, Any], h: dict[str, Any], new: dict[str, Any], problems: list[dict[str, Any]],
                        attempt_no: int) -> str:
    """F15: ask the same AI to fix exactly the problems found — nothing else."""
    from .handoff import FILE_RULES
    t = state["tasks"][h["task_id"]]
    errs = [p for p in problems if p["severity"] == "error"] or problems
    lines = [f"AIWB_ATTEMPT_ID: {new['attempt_id']}", "(Repeat the line above as the first line of your answer.)", "",
             f"# AI Workbench — troubleshooting request {attempt_no} for {t['task_id']} {t['title']}",
             "Your previous answer could not be accepted. Fix ONLY these problems and send the corrected files "
             "completely; do not change anything else.", "", "## Problems found"]
    lines += [f"- [{p['code']}] {p['message']}" for p in errs]
    warns = [p for p in problems if p["severity"] == "warning" and p not in errs]
    if warns:
        lines += ["", "## Also check"] + [f"- [{p['code']}] {p['message']}" for p in warns]
    if task_paths(t):
        lines += ["", "## You may only write these paths"] + [f"- {x}" for x in task_paths(t)]
    lines += ["", "## Acceptance criteria"] + ([f"- [ ] {c}" for c in t.get("acceptance_criteria", [])] or ["- (none)"])
    lines += ["", "## Format", *FILE_RULES, "- Then one manifest:", MAN_OPEN,
              json.dumps({"schema_version": "1.0", "handoff_id": new["handoff_id"], "task_id": new["task_id"],
                          "task_revision": new["task_revision"], "attempt_id": new["attempt_id"],
                          "outcome": "complete|partial", "summary": "…", "completed_items": ["…"],
                          "unresolved_items": [], "validation_claims": []}, ensure_ascii=False), MAN_END]
    return "\n".join(lines)
