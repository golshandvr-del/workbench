"""Companion pairing + request service (Integration Spec §11.2, P3.1–P3.3).

* Pairing: the desktop creates a one-time code (pairing id + 32-byte secret, 10 minutes). The phone sends
  its own random device key sealed with that secret; the desktop user must approve the device. The code is
  consumed by the first request; GitHub tokens never leave the desktop.
* Every later request is sealed with the device key (kid = device id), checked for replay (nonce + time
  window) and permission, then forwarded to the central ProjectsController - there is no separate write
  path. Preview/Apply/Run are not exposed at all.
* Devices can be listed, have permissions changed and be revoked; a revoked device is refused at once.
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from . import crypto
from .crypto import EnvelopeError, b64d, b64e

PAIRING_TTL_SECONDS = 600
PERMISSIONS = ("view_project", "create_task", "submit_response")
DEFAULT_PERMISSIONS = ("view_project",)
MAX_TEXT = 300_000


class CompanionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DeviceRegistry:
    """devices.json (atomic replace) in the per-user app-data directory, never inside a project."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def _load(self) -> dict[str, Any]:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("devices"), dict):
                return d
        except (OSError, ValueError):
            pass
        return {"schema_version": 1, "devices": {}}

    def _save(self, d: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".devices-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{k: v for k, v in dev.items() if k != "key"} for dev in self._load()["devices"].values()]

    def get(self, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._load()["devices"].get(device_id)

    def add(self, name: str, key: bytes, permissions: tuple[str, ...]) -> dict[str, Any]:
        with self._lock:
            d = self._load()
            dev = {"device_id": "dev-" + uuid.uuid4().hex[:12], "name": name, "key": b64e(key),
                   "permissions": list(permissions), "status": "active", "paired_at": int(time.time()),
                   "last_seen": 0}
            d["devices"][dev["device_id"]] = dev
            self._save(d)
            return dev

    def update(self, device_id: str, **kw: Any) -> None:
        with self._lock:
            d = self._load()
            if device_id not in d["devices"]:
                raise CompanionError("unknown_device", "unknown device")
            d["devices"][device_id].update(kw)
            self._save(d)

    def revoke(self, device_id: str) -> None:
        self.update(device_id, status="revoked", key="", permissions=[])

    def set_permissions(self, device_id: str, permissions: list[str]) -> None:
        bad = [p for p in permissions if p not in PERMISSIONS]
        if bad:
            raise CompanionError("bad_permission", "unknown permission: " + ", ".join(bad))
        self.update(device_id, permissions=list(dict.fromkeys(permissions)))


class CompanionService:
    def __init__(self, registry: DeviceRegistry, *, controller: Callable[[], Any],
                 builds: Callable[[], list[dict[str, Any]]] = list, clock: Callable[[], float] = time.time,
                 on_change: Callable[[], None] = lambda: None) -> None:
        self.registry = registry
        self.controller = controller
        self.builds = builds
        self.clock = clock
        self._on_change = on_change
        self._lock = threading.RLock()
        self.pairing: dict[str, Any] | None = None
        self.pending: dict[str, dict[str, Any]] = {}   # pairing_id -> request awaiting desktop approval
        self._seen: dict[str, float] = {}               # nonce -> ts (replay protection)

    @property
    def on_change(self) -> Callable[[], None]:
        def safe() -> None:
            try:
                self._on_change()
            except Exception:  # noqa: BLE001 - a UI notification never breaks a request
                pass
        return safe

    @on_change.setter
    def on_change(self, fn: Callable[[], None]) -> None:
        self._on_change = fn

    # -- pairing (desktop side)
    def start_pairing(self, host: str, port: int) -> str:
        with self._lock:
            pid = "pair-" + secrets.token_hex(6)
            secret = secrets.token_bytes(32)
            self.pairing = {"pairing_id": pid, "secret": secret, "expires": self.clock() + PAIRING_TTL_SECONDS,
                            "used": False, "result": None}
            return f"aiwb1:{host}:{port}:{pid}:{b64e(secret)}"

    def cancel_pairing(self) -> None:
        with self._lock:
            self.pairing = None
            self.pending.clear()

    def pending_requests(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self.pending.values()]

    def decide(self, pairing_id: str, approve: bool, permissions: tuple[str, ...] = DEFAULT_PERMISSIONS) -> dict[str, Any] | None:
        with self._lock:
            req = self.pending.pop(pairing_id, None)
            if req is None or not self.pairing or self.pairing["pairing_id"] != pairing_id:
                raise CompanionError("no_request", "no pairing request is waiting")
            if not approve:
                self.pairing["result"] = {"status": "denied"}
                return None
            dev = self.registry.add(req["device_name"], b64d(req["device_key"]), permissions)
            self.pairing["result"] = {"status": "approved", "device_id": dev["device_id"],
                                      "permissions": dev["permissions"]}
            self.on_change()
            return {k: v for k, v in dev.items() if k != "key"}

    # -- request handling (network side)
    def _replay(self, env: dict[str, Any]) -> None:
        now = self.clock()
        for n, ts in list(self._seen.items()):
            if now - ts > 2 * crypto.MAX_SKEW_SECONDS:
                del self._seen[n]
        key = env["kid"] + "|" + env["nonce"]
        if key in self._seen:
            raise EnvelopeError("replayed message")
        self._seen[key] = now

    def handle(self, body: bytes) -> tuple[int, dict[str, Any]]:
        """Returns (http_status, json). Authenticated replies are sealed; failures are plain codes only."""
        try:
            env = crypto.check_shape(json.loads(body.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            return 400, {"error": "bad_request"}
        with self._lock:
            try:
                kid = env["kid"]
                if kid.startswith("pair-"):
                    p = self.pairing
                    if not p or p["pairing_id"] != kid or self.clock() > p["expires"]:
                        return 403, {"error": "pairing_expired"}
                    key = p["secret"]
                else:
                    dev = self.registry.get(kid)
                    if not dev or dev.get("status") != "active" or not dev.get("key"):
                        return 403, {"error": "device_not_paired"}
                    key = b64d(dev["key"])
                req = crypto.open_json(key, env, now=self.clock())
                self._replay(env)
            except EnvelopeError:
                return 401, {"error": "unauthenticated"}
            try:
                out = self._dispatch(kid, req)
            except CompanionError as exc:
                out = {"ok": False, "error": exc.code, "message": str(exc)}
            except Exception as exc:  # noqa: BLE001 - central-service errors are reported, never crash the server
                out = {"ok": False, "error": "service_error", "message": str(exc)[:500]}
            return 200, crypto.seal(key, kid, out, ts=int(self.clock()), reply_to=env["nonce"])

    def _dispatch(self, kid: str, req: dict[str, Any]) -> dict[str, Any]:
        op = req.get("op")
        if kid.startswith("pair-"):
            p = self.pairing
            assert p is not None
            if op == "pair_request":
                if p["used"]:
                    raise CompanionError("pairing_used", "this pairing code was already used")
                name = str(req.get("device_name") or "").strip()[:60] or "Android device"
                dk = b64d(str(req.get("device_key") or ""))
                if len(dk) != 32:
                    raise CompanionError("bad_request", "device key must be 32 bytes")
                p["used"] = True
                self.pending[p["pairing_id"]] = {"pairing_id": p["pairing_id"], "device_name": name,
                                                 "device_key": b64e(dk)}
                self.on_change()
                return {"ok": True, "status": "pending"}
            if op == "pair_status":
                return {"ok": True, **(p["result"] or {"status": "pending"})}
            raise CompanionError("bad_op", "unknown operation")
        dev = self.registry.get(kid) or {}
        self.registry.update(kid, last_seen=int(self.clock()))
        perms = set(dev.get("permissions", []))

        def need(p: str) -> None:
            if p not in perms:
                raise CompanionError("forbidden", f"this device is not allowed to {p.replace('_', ' ')}")

        ctl = self.controller()
        if op == "hello":
            return {"ok": True, "device_id": kid, "permissions": sorted(perms), "project": bool(ctl)}
        if ctl is None:
            raise CompanionError("no_project", "no project is open in Workbench on the desktop")
        if op == "get_state":
            need("view_project")
            return {"ok": True, **project_view(ctl, self.builds())}
        if op == "create_task":
            need("create_task")
            t = ctl.project.tasks.create({"title": req.get("title"), "objective": req.get("objective"),
                                          "origin": "companion"})
            ctl._dirty("task from companion")
            self.on_change()
            return {"ok": True, "task_id": t["task_id"], "status": t["status"]}
        if op == "submit_response":
            need("submit_response")
            text = str(req.get("text") or "")
            if len(text) > MAX_TEXT:
                raise CompanionError("too_large", "answer is too large for the companion channel")
            r = ctl.route_answer(text)
            self.on_change()
            return {"ok": r.kind != "rejected", "kind": r.kind, "message": r.message, "reference": r.reference_id}
        raise CompanionError("bad_op", "unknown or not allowed operation")


def project_view(ctl: Any, builds: list[dict[str, Any]]) -> dict[str, Any]:
    """Read-only projection for the phone: the published snapshot shape + plain texts; no prompts/paths."""
    from ..v2 import build_snapshot
    st = ctl.state()
    snap = build_snapshot(st, goal=str(st["settings"].get("goal", "")))
    rows = [{"task_id": r["task_id"], "title": r["title"], "status": r["status"], "status_text": r["status_text"]}
            for r in ctl.task_rows()]
    return {"snapshot": snap, "next_action": ctl.next_action_text(), "warnings": ctl.warnings()[:10],
            "tasks": rows, "builds": builds[-5:], "lang": ctl.lang}
