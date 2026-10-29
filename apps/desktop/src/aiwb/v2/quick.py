"""Quick mode — one AI chat (roadmap 5.14.0), the engine (pure: no Tk).

The 1.x loop for a single chat, rebuilt on the 5.10+ answer reader instead of the classic Prompt / AI Response pages:

    describe the job → :func:`build_prompt` (project files + chosen file contents + the answer format)
    → paste the chat's answer (text, or the ZIP it gave) → :func:`read_answer` (AIWB blocks, Markdown, Strict JSON or
    ZIP; Windows copy damage repaired; a cut-off answer gets a continue prompt)
    → :func:`plan` (each file new / changed / unchanged, with a diff) → :func:`apply` (one backup, atomic writes)
    → :func:`restore` (undo the last apply; a file edited since is never overwritten).

A Quick folder can later become a multi-AI (Guided) project with :func:`to_guided` — the files stay where they are.
Everything Quick writes lives under ``.workbench/quick/``.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiwb.intake import answer_files
from aiwb.intake.normalize import continue_prompt, strip_copy_damage, truncation_report

QUICK_DIR = Path(".workbench") / "quick"
FORMATS: tuple[tuple[str, str], ...] = (
    ("aiwb", "AIWB file blocks (recommended)"),
    ("json", "Strict JSON"),
    ("zip", "GPT ZIP"),
)
SKIP_DIRS = {".git", ".workbench", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode", "dist", "build"}
MAX_INVENTORY = 500
MAX_INCLUDE_BYTES = 200_000   # one chosen file
MAX_INCLUDE_TOTAL = 600_000   # all chosen files together

FORMAT_RULES: dict[str, list[str]] = {
    "aiwb": [
        "- Send every new or changed file complete, one AIWB file block per file. Wrap each file body in a fence of "
        "FOUR backticks (````) so indentation and backticks survive the copy:",
        "<<<AIWB_FILE path=\"relative/path.ext\" action=\"write\">>>", "````", "(the complete file)", "````",
        "<<<AIWB_END_FILE>>>",
    ],
    "json": [
        "- Answer with ONE JSON object and nothing after it:",
        '{"files": [{"path": "relative/path.ext", "content": "the complete file"}], "notes": "what you changed"}',
        "- Complete files only; escape newlines and quotes as JSON requires. No comments.",
    ],
    "zip": [
        "- Put every new or changed file in ONE downloadable ZIP with the project's folder layout (relative paths).",
        "- If you cannot create files, send AIWB file blocks instead:",
        "<<<AIWB_FILE path=\"relative/path.ext\" action=\"write\">>>", "````", "(the complete file)", "````",
        "<<<AIWB_END_FILE>>>",
    ],
}


class QuickError(Exception):
    """A Quick step that cannot go on (the message is shown to the user as is)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dir(root: Path) -> Path:
    return Path(root) / QUICK_DIR


def _load(root: Path) -> dict[str, Any]:
    p = _dir(root) / "quick.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("rounds", [])
            data.setdefault("applies", [])
            return data
    except (OSError, ValueError):
        pass
    return {"schema_version": 1, "rounds": [], "applies": [], "converted": ""}


def _save(root: Path, data: dict[str, Any]) -> None:
    d = _dir(root)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "quick.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, d / "quick.json")


def state(root: Path) -> dict[str, Any]:
    """What Quick remembers for this folder: rounds (task, format, prompt size), applies, conversion. Reading only."""
    return _load(root)


def mark(root: Path) -> dict[str, Any]:
    """Make ``root`` a Quick folder (New Project › Quick): writes ``.workbench/quick/quick.json`` once."""
    data = _load(root)
    data.setdefault("created", _now())
    _save(root, data)
    return data


def is_quick(root: Path) -> bool:
    """True for a Quick folder that is not (yet) a multi-AI project — Home then offers the Quick window."""
    root = Path(root)
    if (root / ".workbench" / "v2" / "state.json").is_file():
        return False
    return (_dir(root) / "quick.json").is_file()


# --------------------------------------------------------------------------- the prompt

def inventory(root: Path) -> list[tuple[str, int]]:
    """The project's files (relative path, size), without tool folders; at most :data:`MAX_INVENTORY`."""
    root = Path(root)
    out: list[tuple[str, int]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            try:
                out.append((p.relative_to(root).as_posix(), p.stat().st_size))
            except OSError:
                continue
            if len(out) >= MAX_INVENTORY:
                return out
    return out


def build_prompt(root: Path, task: str, fmt: str = "aiwb", include: list[str] | tuple[str, ...] = ()) -> str:
    """The prompt for one chat: the job, the project's file list, the chosen files' contents and the answer format.

    Also remembered as a round in ``quick.json``. Raises :class:`QuickError` without a job description.
    """
    from aiwb.v2.handoff import with_answer_rule
    task = (task or "").strip()
    if not task:
        raise QuickError("Describe the job first (what the AI should make or change).")
    fmt = fmt if fmt in FORMAT_RULES else "aiwb"
    root = Path(root).resolve()
    data = _load(root)
    rid = f"Q-{len(data['rounds']) + 1:04d}"
    files = inventory(root)
    lines = [f"AIWB_ATTEMPT_ID: {rid}", "", "# The job", "", task, "", "# The project", ""]
    lines += [f"Folder: {root.name}"]
    if files:
        lines += ["Files (path, size):"] + [f"- {p} ({n:,} bytes)" for p, n in files]
        if len(files) >= MAX_INVENTORY:
            lines.append(f"- … (only the first {MAX_INVENTORY} are listed)")
    else:
        lines.append("The folder is empty: create the project from scratch.")
    total, shown, skipped = 0, [], []
    for rel in include:
        p = answer_files.safe_path(rel)
        target = (root / p) if p else None
        if not p or target is None or not target.is_file():
            skipped.append(f"{rel} (not a file of this project)")
            continue
        size = target.stat().st_size
        if size > MAX_INCLUDE_BYTES or total + size > MAX_INCLUDE_TOTAL:
            skipped.append(f"{p} (too big to include — ask for the part you need)")
            continue
        try:
            body = target.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            skipped.append(f"{p} (not a text file)")
            continue
        total += size
        fence = answer_files.fence_for(body)
        shown += ["", f"## {p}", fence, body.rstrip("\n"), fence]
    if shown:
        lines += ["", "# Files you need to see (current content)"] + shown
    if skipped:
        lines += ["", "Not included: " + "; ".join(skipped) + "."]
    lines += ["", "# What to send back", "",
              "- Change only what the job needs. Keep every other file as it is.",
              "- Never send a file partly or with \"...\" in place of code: always the complete file."]
    lines += FORMAT_RULES[fmt]
    prompt = with_answer_rule("\n".join(lines))
    data["rounds"].append({"round_id": rid, "at": _now(), "task": task[:2000], "format": fmt,
                           "included": [p for p in include][:50], "prompt_chars": len(prompt)})
    _save(root, data)
    return prompt


# --------------------------------------------------------------------------- the answer

def read_answer(text: str = "", *, zip_bytes: bytes | None = None, zip_name: str = "answer.zip") -> dict[str, Any]:
    """Every file the answer delivers, whatever its format. Never raises.

    Returns ``files`` ([{path, content}], safe paths only), ``format`` (aiwb / markdown / json / zip / ""), ``label``,
    ``fixes`` (automatic repairs, in words), ``problems`` and — for a cut-off answer — ``truncated`` + ``continue_prompt``.
    """
    fixes: list[str] = []
    if zip_bytes is not None:
        ex = answer_files.zip_files(zip_bytes, name=zip_name)
        repaired = ""
    else:
        repaired = strip_copy_damage(text or "", fixes)
        ex = answer_files.extract(repaired)
    files, problems = [], list(ex.problems)
    seen: set[str] = set()
    for f in ex.files:
        p = answer_files.safe_path(f.get("path", ""))
        if not p:
            problems.append(f"skipped an unsafe path: {f.get('path', '')!r}")
            continue
        if p.casefold() in seen:
            problems.append(f"{p} came twice — the last copy is used")
            files = [x for x in files if x["path"].casefold() != p.casefold()]
        seen.add(p.casefold())
        body = f.get("content", "")
        if ex.format in ("aiwb", "markdown") and body and not body.endswith("\n"):
            body += "\n"  # a fence drops the file's last newline; JSON and ZIP keep the bytes as sent
        files.append({"path": p, "content": body})
    out: dict[str, Any] = {"files": files, "format": ex.format, "label": ex.label if ex.format else "",
                           "fixes": fixes + list(ex.fixes), "problems": problems, "truncated": bool(ex.truncated),
                           "continue_prompt": ""}
    if ex.truncated and repaired:
        out["continue_prompt"] = continue_prompt(truncation_report(repaired))
    if not files and not problems:
        out["problems"].append("no file was found in the answer — paste the whole answer (or load the ZIP it gave)")
    return out


def plan(root: Path, files: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Each delivered file against the folder: ``status`` new / changed / same, ``diff`` (unified, text). Reading only."""
    root = Path(root)
    out = []
    for f in files:
        target = root / f["path"]
        new = f["content"]
        if target.is_file():
            try:
                old = target.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                old = None
            if old is not None and (old == new or old.rstrip("\n") == new.rstrip("\n")):
                status, diff = "same", ""
            else:
                status = "changed"
                diff = "".join(difflib.unified_diff((old or "").splitlines(True), new.splitlines(True),
                                                    f"a/{f['path']}", f"b/{f['path']}"))
        else:
            status = "new"
            diff = "".join(difflib.unified_diff([], new.splitlines(True), "/dev/null", f"b/{f['path']}"))
        out.append({"path": f["path"], "status": status, "diff": diff, "content": new,
                    "lines": new.count("\n") + (1 if new and not new.endswith("\n") else 0)})
    return out


def summary(items: list[dict[str, Any]]) -> str:
    """'2 new · 1 changed · 1 unchanged' for a plan."""
    n = {k: sum(1 for i in items if i["status"] == k) for k in ("new", "changed", "same")}
    parts = [f"{n['new']} new", f"{n['changed']} changed"] + ([f"{n['same']} unchanged"] if n["same"] else [])
    return " · ".join(parts)


# --------------------------------------------------------------------------- apply / restore

def apply(root: Path, items: list[dict[str, Any]], *, task: str = "") -> dict[str, Any]:
    """Write the new and changed files of a :func:`plan` (unchanged ones are skipped) after one backup.

    Returns the apply record ``{apply_id, at, files: [{path, existed, after_sha}], written}``. Raises
    :class:`QuickError` when there is nothing to write or a path is unsafe.
    """
    root = Path(root).resolve()
    todo = [i for i in items if i["status"] in ("new", "changed")]
    if not todo:
        raise QuickError("Nothing to apply: every file is already the same.")
    for i in todo:
        if answer_files.safe_path(i["path"]) != i["path"]:
            raise QuickError(f"Unsafe path refused: {i['path']}")
    data = _load(root)
    aid = f"A-{len(data['applies']) + 1:04d}"
    backup = _dir(root) / "backups" / aid
    rec_files = []
    for i in todo:  # back up everything first, write nothing before the backup is complete
        target = root / i["path"]
        existed = target.is_file()
        if existed:
            b = backup / i["path"]
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, b)
        rec_files.append({"path": i["path"], "existed": existed,
                          "after_sha": _sha(i["content"].encode("utf-8"))})
    written = []
    for i in todo:
        target = root / i["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".aiwb-tmp")
        tmp.write_bytes(i["content"].encode("utf-8"))
        os.replace(tmp, target)
        written.append(i["path"])
    rec = {"apply_id": aid, "at": _now(), "task": (task or "")[:500], "files": rec_files, "written": written,
           "restored_at": ""}
    data["applies"].append(rec)
    _save(root, data)
    return rec


def last_apply(root: Path) -> dict[str, Any] | None:
    """The latest apply that has not been restored yet (None when there is none)."""
    for rec in reversed(_load(root)["applies"]):
        if not rec.get("restored_at"):
            return rec
    return None


def restore(root: Path, apply_id: str = "") -> dict[str, Any]:
    """Undo an apply (default: the last one not restored yet). A file edited after the apply is left alone and listed.

    Returns ``{apply_id, restored: [paths], kept: [paths edited since]}``.
    """
    root = Path(root).resolve()
    data = _load(root)
    recs = [r for r in data["applies"] if not r.get("restored_at") and (not apply_id or r["apply_id"] == apply_id)]
    if not recs:
        raise QuickError("There is no apply to restore.")
    rec = recs[-1]
    backup = _dir(root) / "backups" / rec["apply_id"]
    restored, kept = [], []
    for f in rec["files"]:
        target = root / f["path"]
        current = target.read_bytes() if target.is_file() else None
        if current is not None and _sha(current) != f["after_sha"]:
            kept.append(f["path"])  # edited after the apply: never overwritten
            continue
        if f["existed"]:
            src = backup / f["path"]
            if not src.is_file():
                kept.append(f["path"])
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        elif current is not None:
            target.unlink()
        restored.append(f["path"])
    for r in data["applies"]:
        if r["apply_id"] == rec["apply_id"]:
            r["restored_at"] = _now()
            r["kept_on_restore"] = kept
    _save(root, data)
    return {"apply_id": rec["apply_id"], "restored": restored, "kept": kept}


# --------------------------------------------------------------------------- Quick → Guided

def to_guided(root: Path, goal: str, rows: list[dict[str, Any]], answer_format: str = "aiwb") -> dict[str, Any]:
    """Make this Quick folder a multi-AI project (the New Project wizard's brief + team) — no file is touched.

    The last Quick job is the default goal. Returns the wizard result ``{agents, workers}``.
    """
    from aiwb.v2 import V2Project, team_setup
    root = Path(root).resolve()
    data = _load(root)
    goal = (goal or "").strip() or (data["rounds"][-1]["task"] if data["rounds"] else "")
    if (root / ".workbench" / "v2" / "state.json").is_file():
        raise QuickError("This folder is already a multi-AI project.")
    project = V2Project(root, root.name)
    out = team_setup.apply_wizard(project, {"goal": goal, "name": root.name, "platform": "", "constraints": ""},
                                  rows, answer_format)
    data["converted"] = _now()
    _save(root, data)
    return out
