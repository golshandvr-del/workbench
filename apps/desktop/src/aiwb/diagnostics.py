"""Redacted, local-only Diagnostics Bundle (roadmap 1.16.2, spec v1.11 §7.4).

Default content: app/OS/Python versions, a report ID, the redacted tail of the app
log, recent execution events with large text fields removed, task workflow
state without task text, and Inbox *parse results* (codes/stages only).

Never included by default: project source, prompt or response text, raw Inbox
bytes, credentials, the user's full home/project paths. Optional sections
(task text, full execution history) are separate opt-ins. The user sees the exact
file list and content before anything is written; nothing is ever uploaded.
"""
from __future__ import annotations

import json
import platform
import os
import re
import sys
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

TEXT_FIELDS_DROPPED = {"output", "last_output", "prompt", "prompt_text", "model_output", "raw_response",
                       "content", "task_text", "summary", "stdout", "stderr", "normalized_output"}
MAX_LOG_CHARS = 40_000
MAX_EVENTS = 60


@dataclass(frozen=True)
class BundleEntry:
    name: str
    content: str
    optional: bool = False


def path_variants(path: str | Path) -> set[str]:
    """Spellings of one path that may appear in logs/JSON: as given, resolved (long form on
    Windows, e.g. RUNNER~1 → runneradmin), forward/back slashes and JSON-escaped backslashes."""
    raw = {str(path)}
    try:
        raw.add(str(Path(path).resolve()))
    except OSError:
        pass
    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(32768)
            for p in list(raw):
                if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 32768):  # type: ignore[attr-defined]
                    raw.add(buf.value)
                if ctypes.windll.kernel32.GetLongPathNameW(p, buf, 32768):  # type: ignore[attr-defined]
                    raw.add(buf.value)
        except Exception:  # noqa: BLE001 - best effort
            pass
    out: set[str] = set()
    for p in raw:
        for v in (p, p.replace("\\", "/"), p.replace("/", "\\")):
            out.add(v)
            out.add(v.replace("\\", "\\\\"))
    return {v for v in out if len(v) > 3}


def _scrub_paths(text: str, replacements: dict[str, str]) -> str:
    variants = [(v, label) for real, label in replacements.items() if real for v in path_variants(real)]
    for real, label in sorted(variants, key=lambda kv: -len(kv[0])):
        text = text.replace(real, label)
        if os.name == "nt":
            text = re.sub(re.escape(real), label.replace("\\", "\\\\"), text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\b[A-Z]:(?:\\{1,2})Users(?:\\{1,2})[^\\\s\"']+", r"<USER_HOME>", text)
    text = re.sub(r"/(?:home|Users)/[^/\s\"']+", "<USER_HOME>", text)
    return text


def _strip_event(event: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in event.items():
        if k in TEXT_FIELDS_DROPPED:
            out[k] = f"<removed {len(str(v))} chars>" if v else ""
        elif isinstance(v, str) and len(v) > 500:
            out[k] = v[:500] + f"… <truncated {len(v) - 500} chars>"
        else:
            out[k] = v
    return out


def collect_bundle(project_root: Path | None, *, app_version: str, app_log: Path | None,
                   redact: Callable[[str], str], read_json: Callable[[Path, str, Any], Any] | None = None,
                   include_task_text: bool = False, include_full_history: bool = False) -> list[BundleEntry]:
    report_id = "diag-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    repl = {str(Path.home()): "<USER_HOME>"}
    if project_root is not None:
        repl[str(project_root)] = "<PROJECT>"

    def clean(text: str) -> str:
        return _scrub_paths(redact(text), repl)

    def rj(name: str, default: Any) -> Any:
        if project_root is None:
            return default
        if read_json is not None:
            return read_json(project_root, name, default)
        try:
            return json.loads((project_root / ".workbench" / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    entries: list[BundleEntry] = []
    info = {"report_id": report_id, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "workbench_version": app_version, "python": sys.version.split()[0], "platform": platform.platform(),
            "project_selected": project_root is not None,
            "contents_policy": "no source, no prompt/response text, no raw Inbox bytes, no credentials, paths scrubbed"}
    entries.append(BundleEntry("report.json", json.dumps(info, indent=2)))

    if app_log is not None:
        try:
            log = app_log.read_text(encoding="utf-8", errors="replace")[-MAX_LOG_CHARS:]
        except OSError:
            log = "(app log not available)"
        entries.append(BundleEntry("app_log_tail.txt", clean(log)))

    history = rj("execution_history.json", [])
    history = [e for e in history if isinstance(e, dict)] if isinstance(history, list) else []
    recent = [_strip_event(e) for e in history[-MAX_EVENTS:]]
    entries.append(BundleEntry("execution_events_recent.json", clean(json.dumps(recent, ensure_ascii=False, indent=2))))

    state = rj("task_state.json", {})
    if project_root is not None and isinstance(state, dict):
        keep = {k: state.get(k) for k in ("task_id", "workflow_stage", "workflow_stage_updated_at", "completion_status",
                                           "last_prompt_stage", "last_output_format", "last_response_rejected_at")}
        keep["workflow_history"] = [{k: h.get(k) for k in ("from", "to", "at")}
                                    for h in state.get("workflow_history", [])[-30:] if isinstance(h, dict)]
        keep["last_response_error"] = str(state.get("last_response_error", ""))[:800]
        entries.append(BundleEntry("task_state.json", clean(json.dumps(keep, ensure_ascii=False, indent=2))))
        if include_task_text:
            entries.append(BundleEntry("task_text.txt", clean(str(state.get("task_text", ""))), optional=True))

    if project_root is not None:
        idx = rj("inbox/index.json", {})
        rows = []
        for r in idx.get("responses", []) if isinstance(idx, dict) else []:
            if not isinstance(r, dict):
                continue
            last = (r.get("parse_results") or [{}])[-1]
            rows.append({"response_id": r.get("response_id"), "size": r.get("size"), "status": r.get("status"),
                         "attempt_id": r.get("declared_attempt_id") or r.get("attempt_id"),
                         "stages": last.get("stages"), "format": last.get("format"),
                         "issue_codes": [i.get("code") for i in last.get("issues", []) if isinstance(i, dict)],
                         "file_count": len(last.get("file_paths", []) or [])})
        entries.append(BundleEntry("inbox_parse_results.json", clean(json.dumps(rows[-50:], ensure_ascii=False, indent=2))))

    if include_full_history:
        entries.append(BundleEntry("execution_history_full.json",
                                   clean(json.dumps([_strip_event(e) for e in history], ensure_ascii=False, indent=2)),
                                   optional=True))
    return entries


def write_bundle(entries: list[BundleEntry], dest: Path) -> Path:
    """Write the reviewed entries to a new ZIP (refuses to overwrite)."""
    dest = Path(dest)
    if dest.exists():
        raise FileExistsError("Choose a new file name; the diagnostics bundle never overwrites a file.")
    with zipfile.ZipFile(dest, "x", compression=zipfile.ZIP_DEFLATED) as zf:
        for e in entries:
            zf.writestr(e.name, e.content)
    return dest


def preview_text(entries: list[BundleEntry]) -> str:
    parts = ["Files in this bundle (exact content below; review before saving — redaction cannot guarantee every secret is removed):"]
    parts += [f"- {e.name} ({len(e.content):,} chars){' [opt-in]' if e.optional else ''}" for e in entries]
    for e in entries:
        parts += ["", "=" * 70, e.name, "=" * 70, e.content]
    return "\n".join(parts)
