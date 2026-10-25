"""The model asked for files: keep the request on its handoff and prepare what the user pastes back (roadmap 5.12.0,
owner audit B2).

Before 5.12.0 a pasted ``AIWB_CONTEXT_REQUEST`` only noted an event and pointed to a page that no longer existed —
the Next-step card never changed. Now:

* :func:`record` stores the request on the handoff it belongs to (``handoff["context_request"]``), replacing an
  earlier one; the guide turns that handoff's step into "<AI> asked for N file(s)";
* :func:`prepare` resolves the request against the project folder (same safety rules as every write:
  :func:`aiwb.v2.files.safe_path`, sensitive files refused) and builds the text the user pastes into the same chat —
  or, when it is too large for one paste, a ZIP under ``.workbench/v2/context/`` to attach;
* :func:`clear` drops the request when the real answer for that handoff arrives (kept in ``context_history``).

Nothing is ever sent: preparing is copying to the clipboard / writing a ZIP the user attaches.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from .. import context_request as cr
from .models import now_utc
from .store import emit

SENSITIVE_NAMES = {
    ".env", ".env.local", ".env.development", ".env.production", ".npmrc", ".pypirc", ".netrc", ".git-credentials",
    "credentials", "credentials.json", "secrets.json", "secrets.yaml", "secrets.yml", "id_rsa", "id_ed25519",
    "id_ecdsa", "id_dsa", "authorized_keys", "token.txt", "access_token.txt", "dockerconfigjson",
}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".secret", ".secrets")
SENSITIVE_DIRS = {".ssh", ".aws", ".azure", ".gnupg", "secrets", "credentials", ".workbench", ".git"}
SAFE_EXAMPLES = {".env.example", ".env.sample", ".env.template"}


def is_sensitive(rel_path: str) -> bool:
    """Secrets, keys and Workbench's own data are never packed without a separate decision (same rule as the app)."""
    parts = [p.casefold() for p in PurePosixPath(str(rel_path).replace("\\", "/")).parts]
    name = parts[-1] if parts else ""
    if any(p in SENSITIVE_DIRS for p in parts[:-1]) or name in (".workbench", ".git"):
        return True
    if name in SAFE_EXAMPLES:
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    return name in SENSITIVE_NAMES or name.endswith(SENSITIVE_SUFFIXES)


def _path_problem(p: str) -> str:
    from .files import safe_path
    return "" if safe_path(p) else "path must be relative and inside the project"


def to_record(req: cr.ContextRequest) -> dict[str, Any]:
    """The request as plain JSON for the state."""
    return {"attempt_id": req.attempt_id, "reason": req.reason, "questions": list(req.questions),
            "fixes": list(req.fixes), "at": now_utc(),
            "items": [{"path": i.path, "mode": i.mode, "ranges": [list(r) for r in i.ranges], "symbol": i.symbol,
                       "required": i.required, "reason": i.reason} for i in req.items],
            "base_hashes": dict(req.base_hashes)}


def from_record(rec: dict[str, Any]) -> cr.ContextRequest:
    items = [cr.RequestedItem(str(i.get("path", "")), str(i.get("mode", "full_file")),
                              [tuple(r) for r in i.get("ranges") or []], str(i.get("symbol", "")),
                              bool(i.get("required", True)), str(i.get("reason", ""))) for i in rec.get("items") or []]
    return cr.ContextRequest("1.0", str(rec.get("attempt_id", "")), "", str(rec.get("reason", "")), items,
                             list(rec.get("questions") or []), dict(rec.get("base_hashes") or {}),
                             list(rec.get("fixes") or []))


def record(store: Any, handoff_id: str, req: cr.ContextRequest) -> dict[str, Any]:
    """Keep the request on its handoff (a newer request replaces the older one)."""
    with store.transaction("context request on handoff") as s:
        h = s["handoffs"][handoff_id]
        rec = to_record(req)
        h["context_request"] = rec
        emit(s, "context_request_on_handoff", handoff_id=handoff_id, task_id=h["task_id"],
             files=len(rec["items"]), questions=len(rec["questions"]))
        return rec


def clear(store: Any, handoff_id: str, why: str = "answer received") -> bool:
    """The real answer arrived: the request is done (moved to ``context_history``)."""
    with store.transaction("context request done") as s:
        h = s["handoffs"].get(handoff_id)
        if not h or not h.get("context_request"):
            return False
        old = h.pop("context_request")
        h.setdefault("context_history", []).append({**old, "closed_at": now_utc(), "closed_because": why})
        return True


def summary_line(rec: dict[str, Any], limit: int = 6) -> str:
    """"src/a.py, src/pkg/ (folder) …" for the card."""
    names = [i["path"] + (" (folder)" if i.get("mode") == cr.FOLDER_MODE else "") for i in rec.get("items") or []]
    out = ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")
    if rec.get("questions"):
        out += ("; " if out else "") + f"{len(rec['questions'])} question(s): " + " · ".join(rec["questions"][:2])
    return out


def prepare(store: Any, root: Path, handoff_id: str) -> dict[str, Any]:
    """Resolve the handoff's request and build what the user pastes (``text``) or attaches (``zip_path``).

    Keys: ``text`` (always: the files inline, or — for a ZIP — a short note to send with it), ``zip_path`` ("" when
    inline), ``kind`` (``text`` | ``zip``), ``ready`` / ``missing`` (paths), ``items`` (resolved, for the record).
    """
    st = store.load()
    h = st["handoffs"][handoff_id]
    rec = h.get("context_request")
    if not rec:
        raise ValueError(f"{handoff_id} has no open context request")
    req = from_record(rec)
    root = Path(root)
    items = cr.resolve(req, root, path_problem=_path_problem, is_sensitive=is_sensitive)
    attempt_line = f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n(Repeat the line above as the first line of your answer.)"
    text = cr.pack_inline(req, items, attempt_line=attempt_line)
    kind, zip_path = "text", ""
    if cr.suggest_delivery(items) == "zip" and len(text) > cr.INLINE_LIMIT_CHARS:
        kind = "zip"
        out_dir = root / ".workbench" / "v2" / "context"
        out_dir.mkdir(parents=True, exist_ok=True)
        zp = out_dir / f"{handoff_id}-context.zip"
        zp.write_bytes(cr.pack_zip(req, items, root))
        zip_path = str(zp)
        ready = [r for r in items if r.deliverable]
        missing = [r for r in items if not r.deliverable]
        text = "\n".join([attempt_line, "", "# Context requested by you (prepared by AI Workbench)",
                          f"The attached ZIP ({zp.name}) has the {len(ready)} file(s) you asked for under context/ and "
                          "AIWB_CONTEXT_MANIFEST.json."]
                         + ([f"- not provided: {r.path} — {r.status}: {r.detail}" for r in missing])
                         + (["", "## Your questions"] + [f"- {q}" for q in req.questions] if req.questions else [])
                         + ["", "Continue the task using only this context. If something essential is still missing, "
                            "send another AIWB_CONTEXT_REQUEST. Do not claim anything was run or tested."])
    with store.transaction("context prepared on handoff") as s:
        hh = s["handoffs"][handoff_id]
        if hh.get("context_request"):
            hh["context_request"]["prepared_at"] = now_utc()
            hh["context_request"]["kind"] = kind
    return {"text": text, "zip_path": zip_path, "kind": kind,
            "ready": [r.path for r in items if r.deliverable],
            "missing": [f"{r.path} ({r.status})" for r in items if not r.deliverable], "items": items}


def mark_sent(store: Any, handoff_id: str) -> None:
    with store.transaction("context sent on handoff") as s:
        hh = s["handoffs"][handoff_id]
        if hh.get("context_request"):
            hh["context_request"]["sent_at"] = now_utc()
