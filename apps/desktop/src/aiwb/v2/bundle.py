"""Project bundle ``aiwb-bundle.v1`` (roadmap 3.8.0 / mobile 1.0.0): move a whole project between Desktop and phone.

A bundle is one small JSON file::

    {"schema_version": "1.0", "bundle_type": "aiwb-bundle", "bundle_version": 1, "created_at": "...Z",
     "producer": {"app": "ai-workbench-desktop", "version": "3.8.0"},
     "project": {"project_id": "todo", "name": "Todo", "state_revision": 12},
     "state_json": "<the V2 state document, as a string>", "state_sha256": "<hex sha256 of state_json UTF-8>"}

The state travels as a *string* so both apps check integrity over the exact bytes (no canonical-JSON rules shared
between Python and Kotlin). Both apps work on the same V2 state document, so unknown fields survive a round trip.

Import never merges. :func:`plan_import` compares the bundle with the local project:

* ``new``         – no local project yet;
* ``same``        – identical state;
* ``newer``       – the bundle *descends* from the local state (its event history contains the local last event) and
                    has a higher revision: safe to replace (a backup is written first);
* ``older``       – the local state descends from the bundle: importing would lose local work;
* ``diverged``    – both sides changed since they last matched: refused unless the user forces it (backup first);
* ``other_project`` – a different project_id.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .models import ModelError, now_utc
from .store import DB_VERSION, ProjectStore, StoreError, migrate_state

BUNDLE_TYPE = "aiwb-bundle"
BUNDLE_VERSION = 1
MAX_BUNDLE_BYTES = 8 * 1024 * 1024
PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
DESKTOP_APP = "ai-workbench-desktop"
MOBILE_APP = "ai-workbench-mobile"
SAFE = ("new", "same", "newer")


class BundleError(ModelError):
    """Invalid or unsafe bundle. Message is user-presentable."""


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def export_bundle(state: dict[str, Any], *, name: str = "", app: str = DESKTOP_APP, version: str = "") -> dict[str, Any]:
    """Build a bundle from a V2 state document (nothing is removed; the state is the source of truth)."""
    st = {k: v for k, v in state.items() if not k.startswith("_pending")}
    pid = str(st.get("project_id") or "project")
    text = json.dumps(st, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"schema_version": "1.0", "bundle_type": BUNDLE_TYPE, "bundle_version": BUNDLE_VERSION,
            "created_at": now_utc(), "producer": {"app": app, "version": version or "0"},
            "project": {"project_id": pid, "name": (name or pid)[:120],
                        "state_revision": int(st.get("state_revision", 0) or 0)},
            "state_json": text, "state_sha256": sha256_hex(text)}


def dumps(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, ensure_ascii=False, indent=1) + "\n"


def read_bundle(data: str | bytes | dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a bundle and return ``(bundle, state)``. Raises :class:`BundleError` with a precise reason."""
    if isinstance(data, (bytes, bytearray)):
        if len(data) > MAX_BUNDLE_BYTES:
            raise BundleError("the bundle is larger than 8 MB")
        data = data.decode("utf-8-sig", errors="strict")
    if isinstance(data, str):
        if len(data.encode("utf-8")) > MAX_BUNDLE_BYTES:
            raise BundleError("the bundle is larger than 8 MB")
        try:
            data = json.loads(data.lstrip("\ufeff"))
        except ValueError as exc:
            raise BundleError(f"the bundle is not valid JSON ({exc})") from None
    b = data
    if not isinstance(b, dict):
        raise BundleError("the bundle must be a JSON object")
    if b.get("bundle_type") != BUNDLE_TYPE:
        raise BundleError("this file is not an AI Workbench project bundle (bundle_type)")
    if b.get("bundle_version") != BUNDLE_VERSION:
        raise BundleError(f"unsupported bundle_version {b.get('bundle_version')!r}; update AI Workbench")
    text = b.get("state_json")
    if not isinstance(text, str) or not text:
        raise BundleError("state_json is missing")
    if b.get("state_sha256") != sha256_hex(text):
        raise BundleError("the bundle is damaged: state_sha256 does not match state_json")
    try:
        state = json.loads(text)
    except ValueError as exc:
        raise BundleError(f"state_json is not valid JSON ({exc})") from None
    if not isinstance(state, dict):
        raise BundleError("state_json must hold a JSON object")
    pid = state.get("project_id")
    if not isinstance(pid, str) or not PROJECT_ID.match(pid):
        raise BundleError("the project_id in the bundle is not valid")
    proj = b.get("project") or {}
    if proj.get("project_id") != pid:
        raise BundleError("project.project_id does not match the state")
    if int(state.get("db_version", 0) or 0) > DB_VERSION:
        raise BundleError("the bundle was written by a newer AI Workbench; update this app")
    try:
        state = migrate_state(state, pid)[0]
    except StoreError as exc:
        raise BundleError(str(exc)) from None
    return b, state


def _last_event(state: dict[str, Any]) -> dict[str, Any] | None:
    ev = state.get("events") or []
    return ev[-1] if ev else None


def _contains(history: list[dict[str, Any]], e: dict[str, Any]) -> bool:
    key = (e.get("state_revision"), e.get("type"), e.get("at"))
    return any((x.get("state_revision"), x.get("type"), x.get("at")) == key for x in history)


def descends(child: dict[str, Any], parent: dict[str, Any]) -> bool:
    """True if *child* was derived from *parent* (or parent is empty)."""
    if int(parent.get("state_revision", 0) or 0) == 0:
        return True
    last = _last_event(parent)
    return bool(last) and int(child.get("state_revision", 0) or 0) >= int(parent["state_revision"]) \
        and _contains(child.get("events") or [], last)


def plan_import(local: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    """Decide what importing *incoming* over *local* means. Pure; never writes."""
    rev_in = int(incoming.get("state_revision", 0) or 0)
    if local is None or (int(local.get("state_revision", 0) or 0) == 0 and not local.get("tasks")):
        return {"kind": "new", "safe": True, "local_revision": 0, "bundle_revision": rev_in,
                "message": f"Import the project (revision {rev_in})."}
    rev_local = int(local.get("state_revision", 0) or 0)
    base = {"local_revision": rev_local, "bundle_revision": rev_in}
    if local.get("project_id") != incoming.get("project_id"):
        return {**base, "kind": "other_project", "safe": False,
                "message": f"This bundle is project '{incoming.get('project_id')}', not '{local.get('project_id')}'. "
                           "Import it into an empty project folder instead."}
    strip = ("settings",)
    same = {k: v for k, v in local.items() if k not in strip} == {k: v for k, v in incoming.items() if k not in strip}
    if same and local.get("settings", {}).get("goal") == incoming.get("settings", {}).get("goal"):
        return {**base, "kind": "same", "safe": True, "message": "The project is already up to date."}
    if rev_in > rev_local and descends(incoming, local):
        return {**base, "kind": "newer", "safe": True,
                "message": f"Update the project from revision {rev_local} to {rev_in} (a backup is kept)."}
    if descends(local, incoming):
        return {**base, "kind": "older", "safe": False,
                "message": f"The bundle (revision {rev_in}) is older than this project (revision {rev_local}); "
                           "importing it would lose local work."}
    return {**base, "kind": "diverged", "safe": False,
            "message": f"Both copies changed since they last matched (here revision {rev_local}, bundle {rev_in}). "
                       "Workbench does not merge: importing replaces this copy (a backup is kept)."}


def import_into(store: ProjectStore, data: str | bytes | dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    """Import a bundle into a project store. Unsafe kinds need ``force``; a backup is written before replacing."""
    _b, incoming = read_bundle(data)
    try:
        local = store.load() if store.path.exists() else None
    except StoreError:
        local = None
    plan = plan_import(local, incoming)
    if plan["kind"] == "same":
        return {**plan, "imported": False}
    if not plan["safe"] and not (force and plan["kind"] in ("older", "diverged")):
        raise BundleError(plan["message"])
    with store._lock:  # noqa: SLF001 — the store owns the lock; import is a whole-document replace
        if store.path.exists():
            store.backup("pre-bundle-import")
        sync = dict(incoming["settings"].get("sync") or {})
        sync.update(last_import_at=now_utc(), last_import_revision=int(incoming.get("state_revision", 0) or 0),
                    last_import_from=str((_b.get("producer") or {}).get("app", ""))[:40])
        incoming["settings"]["sync"] = sync
        store._write(incoming)  # noqa: SLF001
        store.sync_ledger(incoming)
    return {**plan, "imported": True}
