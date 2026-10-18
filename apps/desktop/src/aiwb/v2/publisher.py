"""GitHub State Publisher (roadmap 1.19.0 / slice 2E, spec 12.6–12.10).

The single writer of published state. One snapshot = one atomic commit made
with the Git Data API (blobs → tree → commit → fast-forward ref update) on a
dedicated branch (default ``aiwb-state``). Never touches code branches, never
force-pushes. Persistent queue in ``.workbench/v2/publish_queue.json`` survives
restarts; unchanged content is a no-op; transient failures back off
(respecting Retry-After); 401/403 stop until the user acts; a moved remote is a
conflict that is reported (local snapshot kept), never overwritten.

Code Auto-Sync is a different feature: this publisher never commits source.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .models import now_utc
from .snapshot import build_snapshot, render_status_md
from .store import ProjectStore

PROTECTED_BRANCHES = {"main", "master", "develop", "development", "trunk"}
BACKOFF = (30, 60, 120, 300, 900, 1800)


@dataclass
class ApiResult:
    status: int
    body: Any
    headers: Mapping[str, str]


Transport = Callable[[str, str, Mapping[str, str], bytes | None], ApiResult]


def urllib_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> ApiResult:
    req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (https only, checked by caller)
            raw = r.read(4 * 1024 * 1024)
            return ApiResult(r.status, json.loads(raw) if raw else None, dict(r.headers))
    except urllib.error.HTTPError as e:
        raw = e.read(65536) if e.fp else b""
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        return ApiResult(e.code, parsed, dict(e.headers or {}))


class PublishError(RuntimeError):
    def __init__(self, kind: str, message: str, retry_after: float = 0) -> None:
        super().__init__(message)
        self.kind = kind            # auth | rate_limit | conflict | network | invalid | protected
        self.retry_after = retry_after


class GitHubStateClient:
    """Minimal Git Data API client for the state branch."""

    def __init__(self, token: str, owner: str, repo: str, *, transport: Transport | None = None,
                 api: str = "https://api.github.com") -> None:
        if not api.startswith("https://") and not api.startswith("http://127.0.0.1"):
            raise PublishError("invalid", "GitHub API URL must use https")
        self._token = token
        self.owner, self.repo, self.api = owner, repo, api.rstrip("/")
        self.transport = transport or urllib_transport

    def _call(self, method: str, path: str, payload: Any = None) -> Any:
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "AI-Workbench-State-Publisher"}
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            r = self.transport(method, f"{self.api}/repos/{self.owner}/{self.repo}{path}", headers, body)
        except (OSError, urllib.error.URLError) as exc:
            raise PublishError("network", f"GitHub is not reachable ({type(exc).__name__})") from None
        if r.status in (401,):
            raise PublishError("auth", "GitHub rejected the token (401). Update the account token; publishing is paused.")
        if r.status == 403 or r.status == 429:
            remaining = str(r.headers.get("X-RateLimit-Remaining", r.headers.get("x-ratelimit-remaining", "")))
            retry = r.headers.get("Retry-After") or r.headers.get("retry-after")
            if r.status == 429 or remaining == "0" or retry:
                wait = float(retry) if retry else max(0.0, float(r.headers.get("X-RateLimit-Reset", time.time() + 60)) - time.time())
                raise PublishError("rate_limit", f"GitHub rate limit; retry after {int(wait)} s", retry_after=wait)
            raise PublishError("auth", "GitHub refused access (403): the token needs Contents write permission on this repository.")
        if r.status in (409, 422) and path.startswith("/git/refs"):
            raise PublishError("conflict", "the state branch moved on GitHub since the last read (not fast-forward)")
        if r.status >= 500:
            raise PublishError("network", f"GitHub server error {r.status}")
        if r.status >= 400:
            msg = (r.body or {}).get("message", "") if isinstance(r.body, dict) else ""
            raise PublishError("invalid", f"GitHub API {method} {path.split('?')[0]} failed: {r.status} {msg[:120]}")
        return r.body

    def branch_head(self, branch: str) -> str | None:
        try:
            body = self._call("GET", f"/git/ref/heads/{branch}")
        except PublishError as exc:
            if "404" in str(exc):
                return None
            raise
        return body["object"]["sha"]

    def default_head(self) -> str:
        repo = self._call("GET", "")
        return self._call("GET", f"/git/ref/heads/{repo['default_branch']}")["object"]["sha"]

    def commit_tree(self, sha: str) -> str:
        return self._call("GET", f"/git/commits/{sha}")["tree"]["sha"]

    def read_file(self, branch: str, path: str) -> str | None:
        try:
            body = self._call("GET", f"/contents/{path}?ref={branch}")
        except PublishError as exc:
            if "404" in str(exc):
                return None
            raise
        return base64.b64decode(body.get("content", "")).decode("utf-8") if isinstance(body, dict) else None

    def commit_files(self, branch: str, files: dict[str, str], message: str, *, expected_head: str | None) -> str:
        """Atomic multi-file commit; fast-forward only. Returns the new commit SHA."""
        if branch in PROTECTED_BRANCHES:
            raise PublishError("protected", f"refusing to publish state to code branch '{branch}'")
        head = self.branch_head(branch)
        if head != expected_head:
            raise PublishError("conflict", f"state branch head is {str(head)[:10]}, expected {str(expected_head)[:10]}")
        parent = head or self.default_head()
        base_tree = self.commit_tree(parent)
        tree = [{"path": p, "mode": "100644", "type": "blob",
                 "sha": self._call("POST", "/git/blobs", {"content": c, "encoding": "utf-8"})["sha"]}
                for p, c in sorted(files.items())]
        new_tree = self._call("POST", "/git/trees", {"base_tree": base_tree, "tree": tree})["sha"]
        commit = self._call("POST", "/git/commits", {"message": message, "tree": new_tree, "parents": [parent]})["sha"]
        if head is None:
            self._call("POST", "/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit})
        else:
            self._call("PATCH", f"/git/refs/heads/{branch}", {"sha": commit, "force": False})
        return commit


class StatePublisher:
    def __init__(self, store: ProjectStore, *, client_factory: Callable[[], GitHubStateClient | None],
                 source_info: Callable[[], dict[str, Any]] = dict, clock: Callable[[], float] = time.time,
                 goal: Callable[[], str] = str) -> None:
        self.store = store
        self.client_factory = client_factory
        self.source_info = source_info
        self.clock = clock
        self.goal = goal
        self.qpath = store.dir / "publish_queue.json"
        self._lock = threading.RLock()

    # -- persistent queue
    def queue(self) -> dict[str, Any]:
        try:
            q = json.loads(self.qpath.read_text(encoding="utf-8"))
            if isinstance(q, dict):
                return {**self._empty(), **q}
        except (OSError, ValueError):
            pass
        return self._empty()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"pending_revision": 0, "last_published_revision": 0, "last_published_hash": "", "last_commit": "",
                "remote_head": None, "attempts": 0, "next_try_at": 0.0, "paused": "", "last_error": "",
                "last_try_at": "", "history": [], "dirty_since": 0.0}

    def _save(self, q: dict[str, Any]) -> None:
        self.store.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.store.dir), prefix=".queue-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(q, fh, indent=1, sort_keys=True)
        os.replace(tmp, self.qpath)

    def mark_dirty(self, reason: str = "") -> None:
        """Event trigger: something important changed. Coalesced; publish happens on the next tick."""
        with self._lock:
            q = self.queue()
            rev = self.store.revision
            if rev > q["pending_revision"]:
                q["pending_revision"] = rev
                q["dirty_since"] = q["dirty_since"] or self.clock()
                self._save(q)

    @property
    def pending(self) -> bool:
        q = self.queue()
        return self.store.revision > q["last_published_revision"] and q["last_published_hash"] != self.preview()[0]["content_hash"]

    def settings(self) -> dict[str, Any]:
        return self.store.load()["settings"]["publish"]

    def preview(self) -> tuple[dict[str, Any], dict[str, str]]:
        """Exactly what would be published (snapshot + files)."""
        state = self.store.load()
        q = self.queue()
        st = state["settings"]["publish"]
        snap = build_snapshot(state, source=self.source_info(), goal=self.goal(), phase="multi_agent_v2",
                              previous_hash=q["last_published_hash"], last_published_revision=q["last_published_revision"],
                              include_task_details=bool(st.get("include_task_details", True)))
        base = st.get("path", ".aiwb").strip("/") or ".aiwb"
        files = {f"{base}/project-state.json": json.dumps(snap, ensure_ascii=False, indent=2) + "\n",
                 f"{base}/PROJECT_STATUS.md": render_status_md(snap, state)}
        return snap, files

    def tick(self, *, force: bool = False, debounce_seconds: float = 5.0) -> dict[str, Any]:
        """Run one publish step if due (event-driven + periodic). Returns a status dict; never raises."""
        with self._lock:
            q = self.queue()
            st = self.settings()
            now = self.clock()
            if not st.get("enabled") and not force:
                return {"status": "disabled"}
            if q["paused"] and not force:
                return {"status": "paused", "reason": q["paused"]}
            if not force and now < q["next_try_at"]:
                return {"status": "waiting", "retry_in": int(q["next_try_at"] - now)}
            if not force and q["dirty_since"] and now - q["dirty_since"] < debounce_seconds:
                return {"status": "debouncing"}
            snap, files = self.preview()
            if snap["content_hash"] == q["last_published_hash"]:
                q.update(last_published_revision=max(q["last_published_revision"], snap["state_revision"]),
                         pending_revision=0, dirty_since=0.0, attempts=0)
                self._save(q)
                return {"status": "noop", "state_revision": snap["state_revision"]}
            client = self.client_factory()
            if client is None:
                q["last_error"] = "no GitHub account/repository bound to this project"
                self._save(q)
                return {"status": "unbound"}
            publish_id = "pub-" + uuid.uuid4().hex[:12]
            branch = st.get("branch") or "aiwb-state"
            q["last_try_at"] = now_utc()
            try:
                expected = q["remote_head"]
                if expected is None:
                    expected = client.branch_head(branch)
                    if expected is not None:
                        remote = client.read_file(branch, f"{(st.get('path') or '.aiwb').strip('/')}/project-state.json")
                        if remote and json.loads(remote).get("project_id") != snap["project_id"]:
                            raise PublishError("conflict", f"branch '{branch}' holds state of another project")
                msg = (f"aiwb-state: {snap['project_id']} revision {snap['state_revision']}\n\n"
                       f"publish_id: {publish_id}\nsnapshot: {snap['content_hash']}\n"
                       f"source_commit: {snap['source']['commit_sha'] or '-'} (state commit, not a source change)")
                commit = client.commit_files(branch, files, msg, expected_head=expected)
            except PublishError as exc:
                q["last_error"] = str(exc)
                if exc.kind == "auth" or exc.kind == "protected" or exc.kind == "invalid":
                    q["paused"] = str(exc)
                elif exc.kind == "conflict":
                    q["paused"] = "conflict: " + str(exc) + " — review the remote state branch, then 'Resolve conflict'"
                    q["remote_head"] = None
                else:
                    wait = exc.retry_after or BACKOFF[min(q["attempts"], len(BACKOFF) - 1)]
                    q["attempts"] += 1
                    q["next_try_at"] = now + wait
                self._save(q)
                return {"status": "error", "kind": exc.kind, "message": str(exc)}
            q.update(last_published_revision=snap["state_revision"], last_published_hash=snap["content_hash"],
                     last_commit=commit, remote_head=commit, attempts=0, next_try_at=0.0, last_error="",
                     pending_revision=0, dirty_since=0.0)
            q["history"] = (q["history"] + [{"publish_id": publish_id, "state_revision": snap["state_revision"],
                                             "commit": commit, "hash": snap["content_hash"], "at": now_utc()}])[-50:]
            self._save(q)  # publish history lives in the queue file: recording it must not bump state_revision
            return {"status": "published", "commit": commit, "state_revision": snap["state_revision"],
                    "publish_id": publish_id}

    def resume(self) -> None:
        """User fixed the token/conflict: clear pause, re-read the remote head on next tick."""
        with self._lock:
            q = self.queue()
            q.update(paused="", next_try_at=0.0, attempts=0, remote_head=None)
            self._save(q)
