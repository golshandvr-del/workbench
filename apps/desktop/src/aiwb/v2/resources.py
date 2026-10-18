"""Account Profiles and manual Chat Bindings (roadmap 2.3.0 stage 2 / 2.4.0, ADR-008, spec §8).

An Account Profile is a *local label* the user gives to a model account they own
("GPT paid — work"). The plan (free/paid/…) is self-declared and never verified.
No credential field exists, and values that look like secrets are refused.

A Chat Binding links one agent (role) to one account profile and, optionally, a
chat name/link the user typed. Workbench never opens, reads or monitors the chat.
Changing a binding never changes the agent ID or rewrites earlier attempts.
"""
from __future__ import annotations

import re
from typing import Any

from .models import SCHEMA_VERSION, ModelError, now_utc
from .store import ProjectStore, emit, next_id, require

PLANS = ("free", "paid", "team", "unknown")
PROVIDERS = ("GPT", "Gemini", "Claude", "Other")
USAGE_TAGS = ("planning", "architecture", "coding", "review", "research", "tests")
SECRET_RE = re.compile(r"(ghp_|github_pat_|gho_|sk-[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}|xox[abp]-|"
                       r"(?:password|passwd|token|cookie|session|api[_ -]?key)\s*[:=]|[A-Za-z0-9+/]{40,}={0,2}|[0-9a-f]{40,})",
                       re.I)
FORBIDDEN_KEYS = ("password", "token", "cookie", "session", "api_key", "apikey", "secret", "credential")


def _clean(v: Any, name: str, limit: int, required: bool = False) -> str:
    if v is None or v == "":
        if required:
            raise ModelError(f"{name} is required")
        return ""
    if not isinstance(v, str):
        raise ModelError(f"{name} must be text")
    v = v.strip()[:limit]
    if SECRET_RE.search(v):
        raise ModelError(f"{name} looks like a password, token or key. Workbench never stores model credentials; "
                         "use a plain label instead.")
    return v


def _no_secret_keys(data: dict[str, Any]) -> None:
    bad = [k for k in data if any(f in k.lower() for f in FORBIDDEN_KEYS)]
    if bad:
        raise ModelError(f"field(s) {', '.join(bad)} are not allowed: Workbench never stores model credentials")


def _link(v: Any) -> str:
    link = _clean(v, "link", 500)
    if link and not re.match(r"^https?://[^\s]+$", link):
        raise ModelError("link must be an http(s) address (it is only a note for you; Workbench never opens it)")
    if re.search(r"[?&](token|key|auth|sig|session)=", link, re.I):
        raise ModelError("link contains an access parameter; remove it (Workbench never needs access to the chat)")
    return link


class ResourceRegistry:
    """Account profiles and chat bindings stored in the V2 project state (never published)."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    # -- account profiles
    def accounts(self, include_disabled: bool = True) -> list[dict[str, Any]]:
        items = self.store.load()["account_profiles"].values()
        return sorted([a for a in items if include_disabled or a.get("enabled", True)],
                      key=lambda a: a["account_profile_id"])

    def account(self, account_id: str) -> dict[str, Any] | None:
        return self.store.load()["account_profiles"].get(account_id)

    @staticmethod
    def _normalize_account(data: dict[str, Any], cur: dict[str, Any] | None = None) -> dict[str, Any]:
        _no_secret_keys(data)
        base = dict(cur or {})
        base.update(data)
        plan = base.get("plan") or "unknown"
        if plan not in PLANS:
            raise ModelError(f"plan must be one of {', '.join(PLANS)} (self-declared, never verified)")
        provider = _clean(base.get("provider") or "Other", "provider", 40)
        tags = base.get("usage_tags") or []
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ModelError("usage_tags must be a list of words")
        return {"display_name": _clean(base.get("display_name"), "display_name", 80, True), "provider": provider,
                "plan": plan, "note": _clean(base.get("note"), "note", 500),
                "usage_tags": [t.strip()[:30] for t in tags if t.strip()][:10],
                "enabled": bool(base.get("enabled", True))}

    def add_account(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = self._normalize_account(data)
        with self.store.transaction("add account profile") as s:
            names = {a["display_name"].lower() for a in s["account_profiles"].values()}
            if fields["display_name"].lower() in names:
                raise ModelError(f"an account profile named {fields['display_name']!r} already exists")
            aid = next_id(s, "account_profile")
            acc = {"schema_version": SCHEMA_VERSION, "account_profile_id": aid, **fields, "self_declared": True,
                   "created_at": now_utc(), "updated_at": now_utc()}
            s["account_profiles"][aid] = acc
            emit(s, "account_profile_added", account_profile_id=aid, label=fields["display_name"])
        return acc

    def update_account(self, account_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self.store.transaction("update account profile") as s:
            cur = require(s, "account_profiles", account_id)
            fields = self._normalize_account(changes, {k: cur.get(k) for k in
                                                       ("display_name", "provider", "plan", "note", "usage_tags", "enabled")})
            if all(cur.get(k) == v for k, v in fields.items()):
                return cur
            cur.update(fields, updated_at=now_utc())
            emit(s, "account_profile_updated", account_profile_id=account_id,
                 status="enabled" if fields["enabled"] else "disabled")
            return cur

    def set_account_enabled(self, account_id: str, enabled: bool) -> dict[str, Any]:
        return self.update_account(account_id, {"enabled": enabled})

    # -- chat bindings
    def bindings(self, agent_id: str = "", include_disabled: bool = True) -> list[dict[str, Any]]:
        items = self.store.load()["chat_bindings"].values()
        return sorted([b for b in items if (not agent_id or b["agent_id"] == agent_id)
                       and (include_disabled or b.get("enabled", True))], key=lambda b: b["chat_binding_id"])

    def binding(self, binding_id: str) -> dict[str, Any] | None:
        return self.store.load()["chat_bindings"].get(binding_id)

    def bind_chat(self, agent_id: str, account_id: str, *, chat_name: str = "", link: str = "", note: str = "") -> dict[str, Any]:
        _no_secret_keys({"chat_name": chat_name, "link": link, "note": note})
        fields = {"chat_name": _clean(chat_name, "chat_name", 120), "link": _link(link), "note": _clean(note, "note", 500)}
        with self.store.transaction("bind chat") as s:
            agent = require(s, "agents", agent_id)
            acc = require(s, "account_profiles", account_id)
            if not acc.get("enabled", True):
                raise ModelError(f"account profile {account_id} is disabled; enable it or choose another one")
            bid = next_id(s, "chat_binding")
            b = {"schema_version": SCHEMA_VERSION, "chat_binding_id": bid, "agent_id": agent["agent_id"],
                 "account_profile_id": account_id, **fields, "enabled": True, "confirmed_at": now_utc(),
                 "created_at": now_utc(), "updated_at": now_utc()}
            s["chat_bindings"][bid] = b
            emit(s, "chat_binding_added", chat_binding_id=bid, agent_id=agent_id, account_profile_id=account_id)
        return b

    def update_binding(self, binding_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        _no_secret_keys(changes)
        if "agent_id" in changes:
            raise ModelError("a chat binding cannot move to another agent; create a new binding instead")
        with self.store.transaction("update chat binding") as s:
            b = require(s, "chat_bindings", binding_id)
            if "account_profile_id" in changes:
                acc = require(s, "account_profiles", changes["account_profile_id"])
                if not acc.get("enabled", True):
                    raise ModelError(f"account profile {acc['account_profile_id']} is disabled")
                b["account_profile_id"] = acc["account_profile_id"]
            if "chat_name" in changes:
                b["chat_name"] = _clean(changes["chat_name"], "chat_name", 120)
            if "link" in changes:
                b["link"] = _link(changes["link"])
            if "note" in changes:
                b["note"] = _clean(changes["note"], "note", 500)
            if "enabled" in changes:
                b["enabled"] = bool(changes["enabled"])
            b["updated_at"] = now_utc()
            emit(s, "chat_binding_updated", chat_binding_id=binding_id, agent_id=b["agent_id"],
                 account_profile_id=b["account_profile_id"], status="enabled" if b["enabled"] else "disabled")
            return b

    def confirm_binding(self, binding_id: str) -> dict[str, Any]:
        """The user confirms this is still the chat they use for the agent (self-declared)."""
        with self.store.transaction("confirm chat binding") as s:
            b = require(s, "chat_bindings", binding_id)
            b["confirmed_at"] = now_utc()
            b["updated_at"] = now_utc()
            emit(s, "chat_binding_updated", chat_binding_id=binding_id, agent_id=b["agent_id"], status="confirmed")
            return b

    def current_binding(self, agent_id: str, state: dict[str, Any] | None = None) -> dict[str, Any] | None:
        st = state if state is not None else self.store.load()
        return current_binding(st, agent_id)

    def readiness(self, agent_id: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
        """What the user must do before preparing a prompt for this agent (spec §8.4, §11.2)."""
        st = state if state is not None else self.store.load()
        return binding_readiness(st, agent_id)


def current_binding(st: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    accs = st.get("account_profiles", {})
    live = [b for b in st.get("chat_bindings", {}).values()
            if b["agent_id"] == agent_id and b.get("enabled", True)
            and accs.get(b["account_profile_id"], {}).get("enabled", True) and b["account_profile_id"] in accs]
    return max(live, key=lambda b: (b.get("updated_at", ""), b["chat_binding_id"])) if live else None


def binding_readiness(st: dict[str, Any], agent_id: str) -> dict[str, Any]:
    agent = st["agents"].get(agent_id)
    if agent is None:
        return {"ok": False, "code": "agent_missing", "message": f"agent {agent_id} does not exist"}
    if not agent.get("enabled", True):
        return {"ok": False, "code": "agent_disabled", "message": f"{agent['name']} is disabled; assign another agent"}
    b = current_binding(st, agent_id)
    if b is None:
        stale = [x for x in st.get("chat_bindings", {}).values() if x["agent_id"] == agent_id]
        code = "account_disabled" if stale else "no_binding"
        msg = (f"the account/chat for {agent['name']} is disabled; choose a new one" if stale
               else f"choose which account and chat you use for {agent['name']} (optional, but recommended)")
        return {"ok": not stale, "code": code, "message": msg, "binding": None}
    acc = st["account_profiles"][b["account_profile_id"]]
    return {"ok": True, "code": "bound", "binding": b, "account": acc,
            "message": f"{agent['name']} → {acc['display_name']}" + (f" · chat {b['chat_name']}" if b.get("chat_name") else "")}
