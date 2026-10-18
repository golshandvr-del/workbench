"""Append-only Event Ledger (roadmap 2.3.0 stage 2, ADR-008).

``.workbench/v2/events.jsonl`` is a *derived* history: :class:`ProjectStore`
appends the events of every committed transaction after the atomic state write.
The ledger never feeds the current state. Event IDs are deterministic
(``LE-<state_revision>-<index>``), so syncing twice adds nothing.

Only an allow-list of fields is copied (IDs, statuses, counts, short reasons);
prompt/response text and anything that looks like a secret is dropped.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Iterable

LEDGER_SCHEMA = "event-ledger.v1"
PAGE_SIZE = 200
TEXT_LIMIT = 300
STATUS_KEYS = ("old", "new", "status", "outcome", "kind", "verified", "active", "stale", "mode", "result")
COUNT_KEYS = ("operations", "artifacts", "revision", "task_revision", "count")
TEXT_KEYS = ("why", "label", "title", "name")
SENSITIVE = re.compile(r"(prompt|text|response_text|body|content|token|secret|password|cookie|api_?key|credential)", re.I)
SECRETISH = re.compile(r"(ghp_|github_pat_|sk-[A-Za-z0-9]|xox[abp]-|AKIA[0-9A-Z]{8})")
USER_CONFIRMED = ("user_confirmed_sent", "context_marked_sent")
USER_ACTIONS = {"proposal_reviewed", "handoff_accepted", "handoff_rejected", "decision_accepted", "decision_rejected",
                "account_profile_added", "account_profile_updated", "chat_binding_updated", "chat_binding_added",
                "milestone_created", "milestone_accepted", "version_proposed", "version_created", "release_published",
                "prompt_copied", "user_confirmed_sent", "context_marked_sent", "task_assigned"}

# Event families for the timeline filter (§5.3)
FAMILIES = {
    "task": ("task_", "agents_installed", "agent_"),
    "attempt": ("attempt_", "prompt_", "user_confirmed_sent", "response_"),
    "handoff": ("handoff_",),
    "decision": ("decision_", "proposal_"),
    "evidence": ("evidence_", "validation_"),
    "team": ("account_profile_", "chat_binding_", "team_"),
    "version": ("milestone_", "version_", "release_"),
    "publish": ("project_state_publish", "publish_"),
    "context": ("context_",),
}


def family(event_type: str) -> str:
    for fam, prefixes in FAMILIES.items():
        if any(event_type == p or event_type.startswith(p) for p in prefixes):
            return fam
    return "other"


def _clean_text(v: Any) -> str:
    s = str(v)[:TEXT_LIMIT]
    return "[redacted]" if SECRETISH.search(s) else s


def to_record(project_id: str, e: dict[str, Any], index: int, *, legacy_import: bool = False) -> dict[str, Any]:
    """Map an in-state event to a ledger record using the allow-list."""
    etype = str(e.get("type", "change"))[:60]
    rev = int(e.get("state_revision", 0) or 0)
    refs, after, payload = {}, {}, {}
    for k, v in e.items():
        if k in ("type", "at", "state_revision", "reason") or SENSITIVE.search(k):
            continue
        if k.endswith("_id") and isinstance(v, (str, int)):
            refs[k] = _clean_text(v)
        elif k.endswith("_ids") and isinstance(v, list):
            refs[k] = [_clean_text(x) for x in v[:50]]
        elif k in STATUS_KEYS and isinstance(v, (str, bool, int)):
            after[k] = v if isinstance(v, (bool, int)) else _clean_text(v)
        elif k in COUNT_KEYS and isinstance(v, int):
            payload[k] = v
        elif k in TEXT_KEYS and isinstance(v, str):
            payload[k] = _clean_text(v)
        elif k == "applied" and isinstance(v, list):
            payload["applied_count"] = len(v)
    at = e.get("at")
    time_source = "user_confirmed" if etype in USER_CONFIRMED else ("workbench_clock" if at else "unknown")
    source = "user" if etype in USER_ACTIONS else ("model" if after.get("kind") == "model_report" else "workbench")
    if etype == "evidence_recorded":
        level = "verified" if after.get("verified") is True else "reported"
    else:
        level = ""
    rec = {"schema": LEDGER_SCHEMA, "event_id": f"LE-{rev:06d}-{index:02d}", "project_id": project_id,
           "state_revision": rev, "timestamp_utc": at or "", "time_source": time_source, "event_type": etype,
           "family": family(etype), "source": source, "refs": refs, "after": after, "payload": payload,
           "reason": _clean_text(e.get("reason", "")) if e.get("reason") else ""}
    if "old" in after:
        rec["before"] = {"status": after.pop("old")}
    if level:
        rec["evidence_level"] = level
    if legacy_import:
        rec["legacy_import"] = True
    return rec


class EventLedger:
    def __init__(self, directory: Path, project_id: str) -> None:
        self.path = Path(directory) / "events.jsonl"
        self.project_id = project_id
        self._lock = threading.RLock()

    # -- write
    def last_revision(self) -> int:
        last = 0
        for rec in self._iter():
            last = max(last, int(rec.get("state_revision", 0)))
        return last

    def append_events(self, events: Iterable[dict[str, Any]], *, legacy_import: bool = False) -> int:
        """Append events whose state_revision is newer than the ledger's last one. Returns count written."""
        with self._lock:
            last = self.last_revision()
            per_rev: dict[int, int] = {}
            lines = []
            for e in events:
                rev = int(e.get("state_revision", 0) or 0)
                if rev <= last:
                    continue
                idx = per_rev.get(rev, 0)
                per_rev[rev] = idx + 1
                lines.append(json.dumps(to_record(self.project_id, e, idx, legacy_import=legacy_import),
                                        ensure_ascii=False, sort_keys=True))
            if not lines:
                return 0
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(lines) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return len(lines)

    # -- read
    def _iter(self) -> Iterable[dict[str, Any]]:
        try:
            fh = open(self.path, encoding="utf-8")
        except FileNotFoundError:
            return
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue  # a torn last line after a crash is skipped, never fatal
                if isinstance(rec, dict) and rec.get("schema") == LEDGER_SCHEMA:
                    yield rec

    def all(self) -> list[dict[str, Any]]:
        return list(self._iter())

    def count(self) -> int:
        return sum(1 for _ in self._iter())

    def query(self, *, families: Iterable[str] = (), task_id: str = "", agent_id: str = "", since: str = "",
              until: str = "", text: str = "", milestone_id: str = "", version_id: str = "", evidence: str = "",
              page: int = 0, page_size: int = PAGE_SIZE) -> dict[str, Any]:
        """Newest first, paginated. Filters never write anything."""
        fams = set(families)
        out = []
        needle = text.lower().strip()
        for rec in self._iter():
            refs = rec.get("refs", {})
            if fams and rec.get("family") not in fams:
                continue
            if task_id and refs.get("task_id") != task_id and task_id not in refs.get("task_ids", []):
                continue
            if agent_id and agent_id not in (refs.get("agent_id"), refs.get("to_agent_id"), refs.get("from_agent_id")) \
                    and agent_id not in refs.get("agent_ids", []):
                continue
            if milestone_id and refs.get("milestone_id") != milestone_id:
                continue
            if version_id and refs.get("version_id") != version_id:
                continue
            if evidence and rec.get("evidence_level") != evidence:
                continue
            ts = rec.get("timestamp_utc", "")
            if since and (not ts or ts < since):
                continue
            if until and (not ts or ts > until):
                continue
            if needle and needle not in json.dumps(rec, ensure_ascii=False).lower():
                continue
            out.append(rec)
        out.reverse()
        total = len(out)
        start = max(page, 0) * page_size
        return {"total": total, "page": page, "page_size": page_size, "items": out[start:start + page_size],
                "pages": (total + page_size - 1) // page_size}
