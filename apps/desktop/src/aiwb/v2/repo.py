"""GitHub integration of the owner's algorithm — the blue nodes (roadmap 4.5.0, flowchart F3, F22–F24).

Every GitHub *write* is a two-step handshake: ``prepare`` records a pending action (what will be written, where)
in ``settings.flow.github_pending``; only ``confirm`` with that action's id executes it. A write without a
confirmed pending action is refused. With no token the same step is shown as manual instructions plus
"record the result" (never a dead end).

* F3  ``connect`` — bind an existing repository (or ``create`` a new private one) and the project branch
  ``aiwb/<project>``; the default branch is never written.
* F22 ``save`` — one atomic commit of the files integrated since the last save onto the project branch
  (fast-forward only, never force, never a protected branch such as ``main``).
* F23 ``release_needed`` — a roadmap version whose milestones are all accepted and that is not released yet.
* F24 ``release`` — tag + GitHub Release on the saved commit, then the version is recorded as released.

The HTTP layer is the existing Git Data client (``publisher.GitHubStateClient``) with an injectable transport,
so the tests run against a fake GitHub without network. The phone has the same rules in ``core/Repo.kt``.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Callable

from .models import ModelError, now_utc
from .publisher import PROTECTED_BRANCHES, GitHubStateClient, PublishError
from .store import emit

KINDS = ("create", "connect", "save", "release")
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def project_branch(state: dict[str, Any]) -> str:
    raw = str((state.get("settings", {}).get("brief") or {}).get("name") or state.get("project_id") or "project")
    slug = re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")[:40] or "project"
    return f"aiwb/{slug}"


def repo_info(state: dict[str, Any]) -> dict[str, Any]:
    return dict((state.get("settings", {}).get("flow") or {}).get("repo") or {})


def release_needed(state: dict[str, Any]) -> list[dict[str, Any]]:
    """F23: versions whose milestones are all accepted and that are not released / withdrawn."""
    ms = state.get("milestones", {})
    out = []
    for v in sorted(state.get("versions", {}).values(), key=lambda v: v.get("version_id", "")):
        ids = v.get("milestone_ids") or []
        if v.get("status") not in ("released", "withdrawn") and ids and all(
                (ms.get(m) or {}).get("status") == "accepted" for m in ids):
            out.append(v)
    return out


def unsaved_files(state: dict[str, Any]) -> list[str]:
    """Integrated paths not yet committed to the project branch (F22)."""
    saved = set((repo_info(state).get("saved_handoffs") or []))
    out: list[str] = []
    for h in sorted(state.get("handoffs", {}).values(), key=lambda h: h.get("handoff_id", "")):
        if h.get("integrated_at") and h["handoff_id"] not in saved:
            out += [p for p in h.get("integrated_files") or [] if p not in out]
    return out


def manual_steps(kind: str, state: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    """What the user does by hand when no token is set (then records the result)."""
    br = repo_info(state).get("branch") or project_branch(state)
    if kind in ("create", "connect"):
        return ["Create (or open) the repository on github.com.", f"Create the branch {br} from the default branch.",
                "Record owner/name and the branch here."]
    if kind == "save":
        return [f"Commit these files to the branch {br} (no force push, never to main): "
                + ", ".join(unsaved_files(state)[:20]), "Record the commit SHA here."]
    return [f"On github.com → Releases → Draft a new release: tag {payload.get('tag', '')} on branch {br}.",
            "Record the tag, the commit SHA and (optional) the build run here."]


class RepoService:
    """Prepare / confirm GitHub writes for one project."""

    def __init__(self, store: Any, root: Path, client_factory: Callable[[str, str], GitHubStateClient | None] | None = None):
        self.store, self.root, self.client_factory = store, Path(root), client_factory

    # -- handshake
    def pending(self) -> dict[str, Any] | None:
        return (self.store.load()["settings"].get("flow") or {}).get("github_pending")

    def prepare(self, kind: str, **payload: Any) -> dict[str, Any]:
        """Record what will be written; nothing is sent to GitHub."""
        if kind not in KINDS:
            raise ModelError(f"unknown GitHub action {kind!r}")
        st = self.store.load()
        repo = repo_info(st)
        if kind in ("create", "connect"):
            owner, name = str(payload.get("owner", "")).strip(), str(payload.get("name", "")).strip()
            if not (_NAME.match(owner) and _NAME.match(name)):
                raise ModelError("owner and repository name may only use letters, digits, '-', '_' and '.'")
            branch = str(payload.get("branch") or project_branch(st)).strip()
            if branch in PROTECTED_BRANCHES:
                raise ModelError(f"the project branch cannot be '{branch}'; Workbench never writes the default branch")
            payload = {"owner": owner, "name": name, "branch": branch}
        else:
            if not repo.get("full_name"):
                raise ModelError("connect a repository first (F3)")
            if kind == "save":
                files = unsaved_files(st)
                if not files:
                    raise ModelError("no integrated file is waiting to be saved")
                payload = {"files": files, "message": str(payload.get("message") or f"AI Workbench: {len(files)} file(s)")[:200]}
            else:
                vs = {v["version_id"]: v for v in release_needed(st)}
                vid = str(payload.get("version_id") or next(iter(vs), ""))
                if vid not in vs:
                    raise ModelError("no roadmap version is ready to release (all its milestones must be accepted)")
                payload = {"version_id": vid, "tag": str(payload.get("tag") or "v" + vs[vid]["label"]).strip()[:60],
                           "label": vs[vid]["label"]}
        action = {"action_id": "gh-" + uuid.uuid4().hex[:10], "kind": kind, "payload": payload, "prepared_at": now_utc(),
                  "manual": self.client_factory is None, "steps": manual_steps(kind, st, payload)}
        with self.store.transaction("prepare GitHub action") as s:
            s["settings"].setdefault("flow", {})["github_pending"] = action
            emit(s, "github_prepared", kind=kind, action_id=action["action_id"])
        return action

    def cancel(self) -> None:
        with self.store.transaction("cancel GitHub action") as s:
            (s["settings"].get("flow") or {}).pop("github_pending", None)

    def confirm(self, action_id: str, token_owner_repo: tuple[str, str] | None = None) -> dict[str, Any]:
        """Execute the pending action — only with its id (the user's explicit approval)."""
        act = self.pending()
        if not act or act["action_id"] != action_id:
            raise ModelError("this GitHub write was not prepared or was already done; nothing was sent")
        if self.client_factory is None:
            raise ModelError("no GitHub token: do it by hand and record the result")
        kind, pl = act["kind"], act["payload"]
        owner, name = (pl["owner"], pl["name"]) if kind in ("create", "connect") else repo_info(self.store.load())["full_name"].split("/", 1)
        client = self.client_factory(owner, name)
        if client is None:
            raise ModelError("no GitHub token: do it by hand and record the result")
        try:
            result = getattr(self, "_do_" + kind)(client, pl)
        except PublishError as exc:
            with self.store.transaction("GitHub action failed") as s:
                emit(s, "github_failed", kind=kind, error=str(exc)[:300])
            raise ModelError(f"GitHub: {exc}") from None
        self._record(kind, pl, result)
        return result

    # -- results (also used by manual mode)
    def record(self, kind: str, **result: Any) -> dict[str, Any]:
        """Manual mode: the user did it by hand and records the outcome."""
        act = self.pending()
        if not act or act["kind"] != kind:
            raise ModelError("prepare the action first so Workbench knows what was done")
        pl = act["payload"]
        if kind == "save" and not str(result.get("commit_sha", "")).strip():
            raise ModelError("the commit SHA is required")
        if kind == "release" and not str(result.get("tag", pl.get("tag", ""))).strip():
            raise ModelError("the tag is required")
        self._record(kind, pl, {k: str(v).strip() for k, v in result.items()} | {"manual": True})
        return result

    def _record(self, kind: str, pl: dict[str, Any], result: dict[str, Any]) -> None:
        with self.store.transaction(f"GitHub {kind}") as s:
            fs = s["settings"].setdefault("flow", {})
            repo = fs.setdefault("repo", {})
            if kind in ("create", "connect"):
                repo.update(full_name=f"{pl['owner']}/{pl['name']}", branch=pl["branch"], connected_at=now_utc(),
                            url=result.get("url") or f"https://github.com/{pl['owner']}/{pl['name']}",
                            default_branch=result.get("default_branch", ""))
            elif kind == "save":
                repo["head"] = result.get("commit_sha", "")
                saved = repo.setdefault("saved_handoffs", [])
                for h in s["handoffs"].values():
                    if h.get("integrated_at") and h["handoff_id"] not in saved:
                        saved.append(h["handoff_id"])
                repo["saved_at"] = now_utc()
            else:
                v = s["versions"][pl["version_id"]]
                rel = {"tag": result.get("tag") or pl["tag"], "commit_sha": result.get("commit_sha") or repo.get("head", ""),
                       "run_id": result.get("run_id", ""), "url": result.get("url", ""), "at": now_utc()}
                # same facts as Timeline.advance_version: a release is never assumed, it carries a tag + run/URL
                v.update(tag=rel["tag"], commit_sha=rel["commit_sha"] or v.get("commit_sha", ""),
                         run_id=rel["run_id"] or v.get("run_id", ""),
                         artifact=rel["url"] or v.get("artifact", "") or f"github-release:{rel['tag']}", release=rel)
                v.setdefault("history", []).append({"from": v["status"], "to": "released", "at": now_utc()})
                old = v["status"]
                v.update(status="released", updated_at=now_utc())
                emit(s, "release_published", version_id=v["version_id"], label=v["label"], old=old, new="released",
                     commit_sha=v["commit_sha"], run_id=v["run_id"])
            fs.pop("github_pending", None)
            emit(s, f"github_{kind}", importance="major", **{k: v for k, v in result.items() if k in ("commit_sha", "tag", "url")})

    # -- GitHub calls (fake-able transport)
    def _do_create(self, client: GitHubStateClient, pl: dict[str, Any]) -> dict[str, Any]:
        body = client.raw("POST", "/user/repos", {"name": pl["name"], "private": True, "auto_init": True})
        return {"url": body.get("html_url", ""), "default_branch": body.get("default_branch", "main"), **self._ensure_branch(client, pl)}

    def _do_connect(self, client: GitHubStateClient, pl: dict[str, Any]) -> dict[str, Any]:
        body = client.raw("GET", f"/repos/{pl['owner']}/{pl['name']}")
        return {"url": body.get("html_url", ""), "default_branch": body.get("default_branch", ""), **self._ensure_branch(client, pl)}

    @staticmethod
    def _ensure_branch(client: GitHubStateClient, pl: dict[str, Any]) -> dict[str, Any]:
        head = client.branch_head(pl["branch"])
        if head is None:
            head = client.default_head()
            client.raw("POST", f"/repos/{pl['owner']}/{pl['name']}/git/refs", {"ref": f"refs/heads/{pl['branch']}", "sha": head})
        return {"commit_sha": head}

    def _do_save(self, client: GitHubStateClient, pl: dict[str, Any]) -> dict[str, Any]:
        repo = repo_info(self.store.load())
        branch = repo["branch"]
        files = {}
        for p in pl["files"]:
            f = (self.root / p)
            if f.is_file():
                files[p] = f.read_text(encoding="utf-8", errors="replace")
        if not files:
            raise ModelError("the integrated files are no longer in the project folder")
        sha = client.commit_files(branch, files, pl["message"], expected_head=client.branch_head(branch))
        return {"commit_sha": sha, "count": len(files)}

    def _do_release(self, client: GitHubStateClient, pl: dict[str, Any]) -> dict[str, Any]:
        repo = repo_info(self.store.load())
        sha = client.branch_head(repo["branch"]) or repo.get("head", "")
        o, n = repo["full_name"].split("/", 1)
        client.raw("POST", f"/repos/{o}/{n}/git/refs", {"ref": f"refs/tags/{pl['tag']}", "sha": sha})
        body = client.raw("POST", f"/repos/{o}/{n}/releases", {"tag_name": pl["tag"], "name": f"{pl['label']}",
                                                               "target_commitish": repo["branch"],
                                                               "body": "Released with AI Workbench."})
        return {"tag": pl["tag"], "commit_sha": sha, "url": (body or {}).get("html_url", "")}
