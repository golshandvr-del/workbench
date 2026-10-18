"""One-click Sync & Build orchestrator (roadmap v1.14.8).

Connects the earlier services into one visible, stoppable flow::

    Checking -> Review Required -> Ready to Commit -> Committed -> Pushing
    -> CI Queued -> CI Running -> Build Passed / Build Failed
    -> Artifact Verified / Artifact Downloaded

Rules (from the roadmap acceptance criteria):

* Never commit/push on ``main``/``master``; only the bound work branch.
* Sensitive files can never be committed; out-of-scope and workflow-file
  changes need explicit confirmation.
* The remote is fetched again before commit and verified live before push; if
  it moved, nothing is done and a new plan is required.
* A run belongs to this flow only if workflow + branch + the pushed commit's
  full SHA match exactly; artifacts must match repository + run + head SHA.
* Cancel never deletes or undoes a commit. After push it cancels the run.
* Every flow has an operation ID; commit / push / download are idempotent and
  are reused from the record when repeated (also after reopening the app).
* One flow per repository/branch at a time (``OPERATION_GUARD``).

No Tk here. Records hold no credentials and no prompt text.
"""
from __future__ import annotations

import fnmatch
import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from ..git.service import GitCommandError
from ..git.sync import PROTECTED_BRANCHES, GitSyncService, ReviewEntry, SyncPlan, build_commit_message, classify_sync_state
from .actions import OPERATION_GUARD, GitHubActionsService, RepositoryOperationGuard, WorkflowRun
from .api_client import GitHubApiError
from .artifacts import ArtifactInfo, GitHubDispatchService, artifact_matches

# ------------------------------------------------------------------ states
CHECKING = "checking"
PREFLIGHT_FAILED = "preflight_failed"
REVIEW_REQUIRED = "review_required"
READY_TO_COMMIT = "ready_to_commit"
COMMITTED = "committed"
PUSHING = "pushing"
PUSHED = "pushed"
CI_QUEUED = "ci_queued"
CI_RUNNING = "ci_running"
BUILD_PASSED = "build_passed"
BUILD_FAILED = "build_failed"
ARTIFACT_VERIFIED = "artifact_verified"
ARTIFACT_DOWNLOADED = "artifact_downloaded"
CANCELLED = "cancelled"
STALE_PLAN = "stale_plan"
FAILED = "failed"

STATE_LABELS = {
    CHECKING: "Checking", PREFLIGHT_FAILED: "Preflight failed", REVIEW_REQUIRED: "Review Required",
    READY_TO_COMMIT: "Ready to Commit", COMMITTED: "Committed", PUSHING: "Pushing", PUSHED: "Pushed",
    CI_QUEUED: "CI Queued", CI_RUNNING: "CI Running", BUILD_PASSED: "Build Passed", BUILD_FAILED: "Build Failed",
    ARTIFACT_VERIFIED: "Artifact Verified", ARTIFACT_DOWNLOADED: "Artifact Downloaded", CANCELLED: "Cancelled",
    STALE_PLAN: "Stale plan", FAILED: "Failed",
}
CHAIN = (CHECKING, REVIEW_REQUIRED, READY_TO_COMMIT, COMMITTED, PUSHING, CI_QUEUED, CI_RUNNING, BUILD_PASSED, ARTIFACT_VERIFIED)
TERMINAL = frozenset({CANCELLED, BUILD_FAILED, ARTIFACT_VERIFIED, ARTIFACT_DOWNLOADED})

WORKFLOW_DIR = ".github/workflows/"


class OrchestratorError(RuntimeError):
    """Flow refused at a stage; ``stage`` names where."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


# ------------------------------------------------------------------ records
@dataclass
class GitOperationRecord:
    operation_id: str
    repository: str
    branch: str
    state: str = CHECKING
    task_id: str = ""
    approved_paths: list[str] = field(default_factory=list)
    base_remote_sha: str = ""
    commit_sha: str = ""
    pushed: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BuildRunRecord:
    operation_id: str
    workflow_file: str = ""
    workflow_id: int | None = None
    run_id: int | None = None
    run_url: str = ""
    head_sha: str = ""
    outcome: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)  # {artifact_id,name,path,sha256,verification}


class RecordStore:
    """Small JSON store (atomic replace) for operation history, newest last."""

    MAX_ITEMS = 50

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def history(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("operations") if isinstance(data, dict) else None
        return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []

    def get(self, operation_id: str) -> dict[str, Any] | None:
        for item in self.history():
            if (item.get("git") or {}).get("operation_id") == operation_id:
                return item
        return None

    def save(self, git: GitOperationRecord, build: BuildRunRecord) -> None:
        with self._lock:
            items = [i for i in self.history() if (i.get("git") or {}).get("operation_id") != git.operation_id]
            items.append({"git": asdict(git), "build": asdict(build)})
            items = items[-self.MAX_ITEMS:]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".sync_build.", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump({"schema_version": 1, "operations": items}, fh, indent=2)
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise


# ------------------------------------------------------------------ review model
@dataclass(frozen=True)
class ReviewItem:
    path: str
    labels: tuple[str, ...]
    flags: tuple[str, ...]  # sensitive | outside_scope | workflow_change

    @property
    def blocked(self) -> bool:
        return "sensitive" in self.flags

    @property
    def needs_confirmation(self) -> bool:
        return "outside_scope" in self.flags or "workflow_change" in self.flags


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class CheckResult:
    checks: tuple[PreflightCheck, ...]
    plan: SyncPlan | None
    items: tuple[ReviewItem, ...]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


# ------------------------------------------------------------------ orchestrator
class SyncBuildOrchestrator:
    def __init__(
        self, *, sync: GitSyncService, actions: GitHubActionsService, dispatch: GitHubDispatchService,
        git_root: Path, project_subpath: str, owner: str, repo: str, repository_id: int | None,
        branch: str, workflow_file: str, artifact_pattern: str, get_token: Callable[[], str],
        store: RecordStore, in_scope: Callable[[str], bool] = lambda _p: True,
        is_sensitive: Callable[[str], bool] = lambda _p: False, operation_id: str | None = None,
        task_id: str = "", guard: RepositoryOperationGuard = OPERATION_GUARD,
        clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not workflow_file:
            raise OrchestratorError("preflight", "No main Build workflow is selected for this binding.")
        self.sync, self.actions, self.dispatch = sync, actions, dispatch
        self.git_root = Path(git_root)
        self.project_subpath = project_subpath or ""
        self.owner, self.repo, self.repository_id = owner, repo, repository_id
        self.full_name = f"{owner}/{repo}"
        self.branch, self.workflow_file, self.artifact_pattern = branch, workflow_file, artifact_pattern or ""
        self.get_token, self.store = get_token, store
        self.in_scope, self.is_sensitive = in_scope, is_sensitive
        self.guard, self.clock, self.sleep = guard, clock, sleep
        self.cancel_requested = False
        self._listeners: list[Callable[[str, str], None]] = []
        self.last_check: CheckResult | None = None
        self._held = False
        existing = store.get(operation_id) if operation_id else None
        if existing:
            g, b = existing.get("git") or {}, existing.get("build") or {}
            self.git = GitOperationRecord(**{k: g[k] for k in GitOperationRecord.__dataclass_fields__ if k in g})
            self.build = BuildRunRecord(**{k: b[k] for k in BuildRunRecord.__dataclass_fields__ if k in b})
            if self.git.repository != self.full_name or self.git.branch != branch:
                raise OrchestratorError("resume", "The recorded operation belongs to another repository/branch.")
            self.resumed = True
        else:
            oid = "sb-" + uuid.uuid4().hex[:12]
            now = clock()
            self.git = GitOperationRecord(oid, self.full_name, branch, task_id=task_id, created_at=now, updated_at=now)
            self.build = BuildRunRecord(oid, workflow_file=workflow_file)
            self.resumed = False

    # -- events / persistence
    @property
    def operation_id(self) -> str:
        return self.git.operation_id

    @property
    def state(self) -> str:
        return self.git.state

    def subscribe(self, fn: Callable[[str, str], None]) -> None:
        self._listeners.append(fn)

    def _event(self, state: str, message: str) -> None:
        self.git.state = state
        self.git.updated_at = self.clock()
        self.git.events.append({"t": round(self.git.updated_at, 3), "state": state, "message": message[:500]})
        self.git.events = self.git.events[-200:]
        self.store.save(self.git, self.build)
        for fn in list(self._listeners):
            try:
                fn(state, message)
            except Exception:
                pass

    def last_successful_step(self) -> str:
        best = ""
        for ev in self.git.events:
            st = ev.get("state")
            if st in CHAIN:
                best = st
        return STATE_LABELS.get(best, "")

    def git_effect(self) -> str:
        if self.git.pushed:
            return f"Commit {self.git.commit_sha[:12]} is on origin/{self.branch}."
        if self.git.commit_sha:
            return f"Local commit {self.git.commit_sha[:12]} exists (not pushed)."
        return "Nothing changed in Git."

    # -- lock
    def acquire(self) -> bool:
        if self._held:
            return True
        self._held = self.guard.acquire(self.full_name, self.branch, "sync-build:" + self.operation_id)
        return self._held

    def release(self) -> None:
        if self._held:
            self.guard.release(self.full_name, self.branch)
            self._held = False

    def _require_lock(self) -> None:
        if not self.acquire():
            holder = self.guard.holder(self.full_name, self.branch) or "another operation"
            raise OrchestratorError("lock", f"{holder} is already running on {self.full_name}@{self.branch}.")

    def _check_cancel(self, stage: str) -> None:
        if self.cancel_requested:
            raise OrchestratorError(stage, "Cancelled by user.")

    # -- 1. preflight + review
    def check(self) -> CheckResult:
        self._require_lock()
        self._event(CHECKING, "Running preflight checks.")
        checks: list[PreflightCheck] = []
        try:
            token = self.get_token()
            checks.append(PreflightCheck("account", bool(token), "GitHub token available." if token else "No token."))
        except Exception:
            checks.append(PreflightCheck("account", False, "The GitHub token could not be read from the credential store."))
        checks.append(PreflightCheck("workflow", bool(self.workflow_file), self.workflow_file or "No Build workflow selected."))
        protected = self.branch.casefold() in PROTECTED_BRANCHES
        checks.append(PreflightCheck("branch", bool(self.branch) and not protected,
                                     f"Work branch '{self.branch}'." if not protected else f"'{self.branch}' is protected; bind a work branch."))
        plan = None
        items: tuple[ReviewItem, ...] = ()
        try:
            remote = self.sync.git.run(self.git_root, ["remote", "get-url", "origin"])
            checks.append(PreflightCheck("remote", remote.returncode == 0, "origin configured." if remote.returncode == 0 else "No 'origin' remote."))
            plan = self.sync.build_plan(self.git_root, fetch=True)
            checks.append(PreflightCheck("fetch", not plan.fetch_error, "Fetched origin." if not plan.fetch_error else plan.fetch_error[:200]))
            checks.append(PreflightCheck("checkout", plan.branch == self.branch,
                                         f"Checked out '{plan.branch or '(detached)'}'" + ("" if plan.branch == self.branch else f"; expected '{self.branch}'.")))
            sync_ok = plan.state not in ("diverged", "conflict", "detached", "not_a_repo") and not (plan.state == "dirty" and plan.behind)
            checks.append(PreflightCheck("sync", sync_ok and plan.state != "remote_ahead", plan.summary))
            snap = self.sync.review_snapshot(self.git_root)
            items = tuple(self._review_item(e) for e in snap.entries if e.kind != "ignored")
        except GitCommandError as exc:
            checks.append(PreflightCheck("git", False, str(exc)[:300]))
        result = CheckResult(tuple(checks), plan, items)
        self.last_check = result
        if not result.ok:
            self._event(PREFLIGHT_FAILED, "; ".join(c.detail for c in checks if not c.ok)[:500])
        elif self.git.commit_sha:
            self._event(COMMITTED if not self.git.pushed else PUSHED, "Resuming: " + self.git_effect())
        elif not items:
            self._event(READY_TO_COMMIT, "No local changes; the current HEAD can be pushed/built.")
        else:
            self._event(REVIEW_REQUIRED, f"{len(items)} changed path(s) to review.")
        return result

    def _review_item(self, entry: ReviewEntry) -> ReviewItem:
        flags = []
        if self.is_sensitive(entry.path):
            flags.append("sensitive")
        if not self.in_scope(entry.path):
            flags.append("outside_scope")
        if entry.path.startswith(WORKFLOW_DIR) or entry.orig_path.startswith(WORKFLOW_DIR):
            flags.append("workflow_change")
        return ReviewItem(entry.path, entry.labels(), tuple(flags))

    # -- 2. commit
    def commit(self, paths: Sequence[str], summary: str, *, confirmed_paths: Iterable[str] = ()) -> str:
        """Commit exactly ``paths``. Idempotent: returns the recorded SHA if already committed."""
        self._require_lock()
        if self.git.commit_sha:
            return self.git.commit_sha
        self._check_cancel("commit")
        if self.last_check is None or not self.last_check.ok:
            raise OrchestratorError("commit", "Run the preflight check first.")
        items = {i.path: i for i in self.last_check.items}
        confirmed = set(confirmed_paths)
        for p in paths:
            item = items.get(p)
            if item is None:
                raise OrchestratorError("commit", f"'{p}' is not in the reviewed change list; check again.")
            if item.blocked:
                raise OrchestratorError("commit", f"'{p}' looks sensitive and cannot be committed.")
            if item.needs_confirmation and p not in confirmed:
                raise OrchestratorError("commit", f"'{p}' needs explicit confirmation ({', '.join(item.flags)}).")
        before = self.last_check.plan
        fresh = self.sync.build_plan(self.git_root, fetch=True)
        if before is None or fresh.remote_sha != before.remote_sha or fresh.branch != self.branch:
            self._event(STALE_PLAN, "The remote changed since the review; nothing was committed. Check again.")
            raise OrchestratorError("commit", "The remote changed since the review; nothing was committed.")
        if fresh.behind:
            self._event(STALE_PLAN, "The remote is ahead; nothing was committed.")
            raise OrchestratorError("commit", "The remote is ahead of the local branch; nothing was committed.")
        self._event(READY_TO_COMMIT, f"Committing {len(paths)} file(s).")
        message = build_commit_message(summary, task_id=self.git.task_id, run_id=self.operation_id)
        res = self.sync.commit_selected(self.git_root, list(paths), message)
        if not res.ok:
            self._event(FAILED, "Commit failed: " + res.message)
            raise OrchestratorError("commit", res.message + (" " + ", ".join(res.details[:5]) if res.details else ""))
        self.git.commit_sha = res.commit_sha
        self.git.approved_paths = sorted(paths)
        self.git.base_remote_sha = fresh.remote_sha
        self._event(COMMITTED, res.message)
        return res.commit_sha

    def adopt_head(self) -> str:
        """No changes to commit: build the current local HEAD (must be ahead of or equal to the remote)."""
        self._require_lock()
        if self.git.commit_sha:
            return self.git.commit_sha
        head = self.sync.git.run(self.git_root, ["rev-parse", "HEAD"]).stdout.strip()
        if len(head) != 40:
            raise OrchestratorError("commit", "The repository has no commit yet.")
        plan = self.last_check.plan if self.last_check else None
        self.git.commit_sha = head
        self.git.base_remote_sha = plan.remote_sha if plan else ""
        self._event(COMMITTED, f"Using existing HEAD {head[:12]} (no new commit).")
        return head

    # -- 3. push
    def push(self) -> None:
        self._require_lock()
        if self.git.pushed:
            return
        if not self.git.commit_sha:
            raise OrchestratorError("push", "Nothing is committed yet.")
        self._check_cancel("push")
        if self.branch.casefold() in PROTECTED_BRANCHES:
            raise OrchestratorError("push", f"Direct push to '{self.branch}' is blocked.")
        snap = self.sync.review_snapshot(self.git_root)
        upstream = snap.branch.upstream or f"origin/{self.branch}"
        try:
            live = self.sync.remote_branch_sha(self.git_root, upstream)
        except GitCommandError as exc:
            self._event(COMMITTED, f"Could not verify the remote (commit kept): {exc}")
            raise OrchestratorError("push", f"Could not verify the remote; local commit {self.git.commit_sha[:12]} is kept.") from None
        if live == self.git.commit_sha:
            # The previous push succeeded but its result was lost.
            self.git.pushed = True
            self._event(PUSHED, f"Remote already has {self.git.commit_sha[:12]} (earlier push completed).")
            return
        if snap.branch.head_sha != self.git.commit_sha:
            raise OrchestratorError("push", "HEAD moved since the commit was recorded; check again.")
        if live != self.git.base_remote_sha:
            self._event(STALE_PLAN, f"The remote moved (expected {self.git.base_remote_sha[:12] or 'none'}, found {live[:12] or 'none'}); local commit kept, nothing pushed.")
            raise OrchestratorError("push", "The remote branch moved; nothing was pushed. The local commit is kept.")
        self._event(PUSHING, f"Pushing {self.git.commit_sha[:12]} to origin/{self.branch}.")
        plan = classify_sync_state(snap, live)
        res = self.sync.safe_push(self.git_root, plan)
        if not res.ok:
            self._event(COMMITTED, f"Local commit {self.git.commit_sha[:12]} WAS created and is kept, but push failed: {res.message}")
            raise OrchestratorError("push", f"Push failed; local commit {self.git.commit_sha[:12]} is kept. {res.message}")
        self.git.pushed = True
        self._event(PUSHED, res.message)

    # -- 4. CI tracking
    def _workflow_id(self, token: str) -> int:
        if self.build.workflow_id:
            return self.build.workflow_id
        wfs = self.actions.list_workflows(token, self.owner, self.repo, read_triggers=False)
        wf = next((w for w in wfs if w.path == self.workflow_file), None)
        if wf is None:
            raise OrchestratorError("ci", f"Build workflow '{self.workflow_file}' no longer exists on GitHub (stale binding).")
        self.build.workflow_id = wf.workflow_id
        return wf.workflow_id

    def poll_run(self) -> WorkflowRun | None:
        """One lookup for the run of exactly the pushed commit. Updates state."""
        if not self.git.pushed:
            raise OrchestratorError("ci", "The commit is not pushed yet.")
        token = self.get_token()
        wid = self._workflow_id(token)
        runs = self.actions.list_runs(token, self.owner, self.repo, workflow_id=wid, branch=self.branch,
                                      head_sha=self.git.commit_sha, per_page=20)
        mine = [r for r in runs if r.head_sha.lower() == self.git.commit_sha.lower() and r.head_branch == self.branch
                and r.workflow_id in (None, wid)]
        if self.build.run_id:
            mine = [r for r in mine if r.run_id == self.build.run_id] or mine
        if not mine:
            if self.state not in (CI_QUEUED,):
                self._event(CI_QUEUED, f"Waiting for a run of {self.git.commit_sha[:12]}.")
            return None
        run = mine[0]
        self.build.run_id, self.build.run_url, self.build.head_sha = run.run_id, run.html_url, run.head_sha
        self.build.outcome = run.outcome
        if not run.is_finished:
            st = CI_QUEUED if run.status in ("queued", "waiting", "requested", "pending") else CI_RUNNING
            if self.state != st:
                self._event(st, f"Run {run.run_id}: {run.status}.")
            else:
                self.store.save(self.git, self.build)
        elif run.conclusion == "success":
            self._event(BUILD_PASSED, f"Run {run.run_id} succeeded.")
        else:
            self._event(BUILD_FAILED, f"Run {run.run_id} finished: {run.outcome}.")
        return run

    def wait_for_build(self, *, timeout: float = 3600, interval: float = 10) -> WorkflowRun | None:
        deadline = self.clock() + timeout
        while True:
            self._check_cancel("ci")
            try:
                run = self.poll_run()
            except GitHubApiError as exc:
                if exc.category == "authentication":
                    raise OrchestratorError("ci", "GitHub rejected the token (401); stopped.") from None
                run = None
            if run is not None and run.is_finished:
                return run
            if self.clock() >= deadline:
                return run
            self.sleep(interval)

    # -- 5. artifacts
    def matching_artifacts(self) -> list[ArtifactInfo]:
        if self.state not in (BUILD_PASSED, ARTIFACT_VERIFIED, ARTIFACT_DOWNLOADED) or not self.build.run_id:
            raise OrchestratorError("artifacts", "The build has not passed.")
        arts = self.dispatch.list_artifacts(self.get_token(), self.owner, self.repo, self.build.run_id)
        out = [a for a in arts if artifact_matches(a, run_id=self.build.run_id, head_sha=self.git.commit_sha, repository_id=self.repository_id)
               and not a.expired]
        if self.artifact_pattern:
            out = [a for a in out if fnmatch.fnmatchcase(a.name, self.artifact_pattern)]
        return out

    def download_artifacts(self, dest_dir: Path) -> list[dict[str, Any]]:
        self._require_lock()
        done = {a["artifact_id"]: a for a in self.build.artifacts if Path(a.get("path", "")).is_file()}
        run = WorkflowRun(self.build.run_id or 0, self.build.workflow_id, "", "", "completed", "success", self.branch,
                          self.git.commit_sha, None, None, "", "", "", "")
        arts = self.matching_artifacts()
        if not arts:
            raise OrchestratorError("artifacts", "No artifact of this run/commit matches the binding pattern.")
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for a in arts:
            self._check_cancel("artifacts")
            if a.artifact_id in done:
                results.append(done[a.artifact_id])
                continue
            res = self.dispatch.download_artifact(self.get_token(), self.owner, self.repo, a, dest_dir, run=run,
                                                  cancel=lambda: self.cancel_requested)
            rec = {"artifact_id": a.artifact_id, "name": a.name, "path": str(res.path), "sha256": res.sha256,
                   "verification": res.verification, "size": res.size}
            self.build.artifacts = [x for x in self.build.artifacts if x.get("artifact_id") != a.artifact_id] + [rec]
            results.append(rec)
            self.store.save(self.git, self.build)
        verified = all(r["verification"] == "matched" for r in results)
        self._event(ARTIFACT_VERIFIED if verified else ARTIFACT_DOWNLOADED,
                    f"{len(results)} artifact(s) saved in {dest_dir}; " + ("SHA-256 matches GitHub's digest." if verified else "SHA-256 computed (no reference for some)."))
        return results

    # -- cancel
    def cancel(self) -> str:
        """Stop the flow. Never deletes or undoes a commit."""
        self.cancel_requested = True
        try:
            if not self.git.commit_sha:
                self._event(CANCELLED, "Stopped before commit; nothing changed.")
                return "nothing_changed"
            if not self.git.pushed:
                self._event(CANCELLED, f"Stopped; local commit {self.git.commit_sha[:12]} is kept (not pushed).")
                return "commit_kept"
            b = self.build
            if b.run_id and b.outcome not in ("success", "failure", "cancelled", "skipped", "timed_out", "neutral", "action_required", "stale", "startup_failure"):
                run = WorkflowRun(b.run_id, b.workflow_id, "", "", "in_progress", None, self.branch, self.git.commit_sha,
                                  None, None, "", "", "", b.run_url)
                try:
                    self.actions.cancel_run(self.get_token(), self.owner, self.repo, run, confirmed=True)
                except GitHubApiError as exc:
                    self._event(CANCELLED, f"Stopped tracking; cancelling run {b.run_id} failed ({exc}). The pushed commit stays on the remote.")
                    return "run_cancel_failed"
                self._event(CANCELLED, f"Requested cancellation of run {b.run_id}; the pushed commit stays on the remote.")
                return "run_cancel_requested"
            self._event(CANCELLED, "Stopped tracking; the pushed commit stays on the remote.")
            return "stopped_tracking"
        finally:
            self.release()
