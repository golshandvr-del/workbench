"""Safe Git Review & Sync Plan (roadmap v1.14.5).

UI-independent services that turn local/remote Git state into an explicit,
reviewable plan. Design rules:

* Read-only operations (status, fetch, ls-remote) never change the working tree.
* Only a fast-forward merge (``merge --ff-only``) is ever performed automatically,
  and only when the remote is strictly ahead and the working tree is clean.
* Diverged / conflicted / dirty states stop with manual options; nothing is
  overwritten silently. There is no force push anywhere in this module.
* Before push the remote branch SHA is re-read; if it moved since the plan was
  built the push is refused and a new plan is required.
* A selected-file commit refuses to run if the index already contains staged
  paths that were not selected (pre-existing staged changes are never mixed in).
* Results distinguish "commit failed" from "commit created but push failed".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .service import GitCommandError, GitService

PROTECTED_BRANCHES = frozenset({"main", "master"})

# Sync states
CLEAN = "clean"
LOCAL_AHEAD = "local_ahead"
REMOTE_AHEAD = "remote_ahead"
DIVERGED = "diverged"
DIRTY = "dirty"
CONFLICT = "conflict"
NO_UPSTREAM = "no_upstream"
DETACHED = "detached"
NOT_A_REPO = "not_a_repo"

_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_TRAILER_VALUE_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,80}$")


@dataclass(frozen=True, slots=True)
class ReviewEntry:
    """One path from ``git status --porcelain=v2``, classified for review."""

    path: str
    index: str          # X column ('.' = unchanged)
    worktree: str       # Y column ('.' = unchanged); for untracked both are '?'
    kind: str           # 'changed' | 'renamed' | 'untracked' | 'conflict' | 'ignored'
    orig_path: str = ""

    @property
    def staged(self) -> bool:
        return self.kind in ("changed", "renamed") and self.index not in (".", " ")

    @property
    def unstaged(self) -> bool:
        return self.kind in ("changed", "renamed") and self.worktree not in (".", " ")

    @property
    def untracked(self) -> bool:
        return self.kind == "untracked"

    @property
    def deleted(self) -> bool:
        return "D" in (self.index, self.worktree) and self.kind != "conflict"

    @property
    def renamed(self) -> bool:
        return self.kind == "renamed"

    @property
    def conflicted(self) -> bool:
        return self.kind == "conflict"

    def labels(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.conflicted:
            out.append("conflict")
        if self.untracked:
            out.append("untracked")
        if self.staged:
            out.append("staged")
        if self.unstaged:
            out.append("unstaged")
        if self.deleted:
            out.append("deleted")
        if self.renamed:
            out.append("renamed")
        return tuple(out)


@dataclass(frozen=True, slots=True)
class BranchInfo:
    head_sha: str = ""          # '' for an unborn branch
    branch: str = ""            # '' when detached
    upstream: str = ""          # e.g. 'origin/feature'
    ahead: int = 0
    behind: int = 0
    has_upstream_counts: bool = False


@dataclass(frozen=True, slots=True)
class ReviewSnapshot:
    root: Path
    branch: BranchInfo
    entries: tuple[ReviewEntry, ...]

    def by_label(self, label: str) -> tuple[ReviewEntry, ...]:
        return tuple(e for e in self.entries if label in e.labels())

    @property
    def staged_paths(self) -> tuple[str, ...]:
        return tuple(e.path for e in self.entries if e.staged)

    @property
    def has_conflicts(self) -> bool:
        return any(e.conflicted for e in self.entries)

    @property
    def is_dirty(self) -> bool:
        return any(e.kind != "ignored" for e in self.entries)

    def counts(self) -> dict[str, int]:
        keys = ("staged", "unstaged", "untracked", "deleted", "renamed", "conflict")
        return {k: len(self.by_label(k)) for k in keys}


@dataclass(frozen=True, slots=True)
class SyncPlan:
    state: str
    branch: str
    upstream: str
    local_sha: str
    remote_sha: str
    ahead: int
    behind: int
    allowed_actions: tuple[str, ...]
    summary: str
    manual_options: tuple[str, ...] = ()
    fetched: bool = False
    fetch_error: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def can_fast_forward(self) -> bool:
        return "fast_forward" in self.allowed_actions

    @property
    def can_push(self) -> bool:
        return "push" in self.allowed_actions


@dataclass(slots=True)
class OperationResult:
    ok: bool
    stage: str                       # 'commit' | 'push' | 'fast_forward' | 'fetch'
    message: str
    commit_created: bool = False
    commit_sha: str = ""
    details: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- parsing

def parse_porcelain_v2(raw: str) -> tuple[BranchInfo, tuple[ReviewEntry, ...]]:
    """Parse ``git status --porcelain=v2 --branch -z --untracked-files=all``.

    Paths are kept exactly (no stripping). Rename records carry the original
    path as the following NUL-separated field.
    """
    head_sha = branch = upstream = ""
    ahead = behind = 0
    counts = False
    entries: list[ReviewEntry] = []
    parts = raw.split("\0")
    i = 0
    while i < len(parts):
        rec = parts[i]
        i += 1
        if not rec:
            continue
        if rec.startswith("# "):
            key, _, value = rec[2:].partition(" ")
            if key == "branch.oid":
                head_sha = "" if value == "(initial)" else value
            elif key == "branch.head":
                branch = "" if value == "(detached)" else value
            elif key == "branch.upstream":
                upstream = value
            elif key == "branch.ab":
                m = re.match(r"^\+(\d+) -(\d+)$", value)
                if m:
                    ahead, behind, counts = int(m.group(1)), int(m.group(2)), True
            continue
        tag = rec[:2]
        if tag == "1 ":
            fields = rec.split(" ", 8)
            if len(fields) == 9:
                xy = fields[1]
                entries.append(ReviewEntry(fields[8], xy[0], xy[1], "changed"))
        elif tag == "2 ":
            fields = rec.split(" ", 9)
            if len(fields) == 10:
                xy = fields[1]
                orig = parts[i] if i < len(parts) else ""
                i += 1
                entries.append(ReviewEntry(fields[9], xy[0], xy[1], "renamed", orig))
        elif tag == "u ":
            fields = rec.split(" ", 10)
            if len(fields) == 11:
                xy = fields[1]
                entries.append(ReviewEntry(fields[10], xy[0], xy[1], "conflict"))
        elif tag == "? ":
            entries.append(ReviewEntry(rec[2:], "?", "?", "untracked"))
        elif tag == "! ":
            entries.append(ReviewEntry(rec[2:], "!", "!", "ignored"))
    return BranchInfo(head_sha, branch, upstream, ahead, behind, counts), tuple(entries)


def classify_sync_state(snapshot: ReviewSnapshot, remote_sha: str = "") -> SyncPlan:
    """Pure decision table: state, allowed actions and manual options."""
    b = snapshot.branch
    warnings: list[str] = []
    protected = b.branch.casefold() in PROTECTED_BRANCHES
    if protected:
        warnings.append(f"Direct push to '{b.branch}' is blocked; create a work branch to publish changes.")
    staged_note = snapshot.staged_paths
    if staged_note:
        warnings.append(f"{len(staged_note)} path(s) are already staged in the index; they are never mixed into a Workbench commit.")

    def plan(state: str, actions: Iterable[str], summary: str, manual: Iterable[str] = ()) -> SyncPlan:
        acts = tuple(a for a in actions if not (a == "push" and protected))
        return SyncPlan(state, b.branch, b.upstream, b.head_sha, remote_sha, b.ahead, b.behind,
                        acts, summary, tuple(manual), warnings=tuple(warnings))

    if not b.branch:
        return plan(DETACHED, (), "HEAD is detached; sync is disabled.",
                    ("Check out a branch (git switch <branch>) or create one from this commit.",))
    if snapshot.has_conflicts:
        return plan(CONFLICT, (), f"{len(snapshot.by_label('conflict'))} conflicted path(s); resolve them first.",
                    ("Resolve conflicts in an editor, then stage the resolved files.",
                     "Or abort the in-progress merge/rebase (git merge --abort / git rebase --abort)."))
    if not b.upstream or not b.has_upstream_counts:
        actions = ["commit_selected"] if snapshot.is_dirty else []
        actions.append("push")
        return plan(NO_UPSTREAM, actions,
                    "Branch has no upstream; the first push will create it (git push -u origin HEAD).")
    dirty = snapshot.is_dirty
    if b.ahead and b.behind:
        return plan(DIVERGED, ("commit_selected",) if dirty else (),
                    f"Local and remote have diverged (ahead {b.ahead}, behind {b.behind}). Workbench will not merge, rebase or force-push.",
                    ("Rebase manually: git rebase {0} (then review and push).".format(b.upstream),
                     "Or merge manually: git merge {0}.".format(b.upstream),
                     "Or push your commits to a new branch and open a Pull Request."))
    if b.behind:
        if dirty:
            return plan(DIRTY, ("commit_selected",),
                        f"Remote is ahead by {b.behind} commit(s) but the working tree has local changes; fast-forward is blocked.",
                        ("Commit or stash local changes, refresh the plan, then fast-forward.",))
        return plan(REMOTE_AHEAD, ("fast_forward",),
                    f"Remote is ahead by {b.behind} commit(s); a fast-forward-only update is safe.")
    if b.ahead:
        return plan(LOCAL_AHEAD, ("push", "commit_selected") if dirty else ("push",),
                    f"Local branch is ahead by {b.ahead} commit(s)." + (" Working tree also has uncommitted changes." if dirty else ""))
    if dirty:
        return plan(DIRTY, ("commit_selected",), "Up to date with remote; working tree has uncommitted changes.")
    return plan(CLEAN, (), "Clean and up to date with the remote.")


def build_commit_message(summary: str, *, task_id: str = "", run_id: str = "", apply_id: str = "") -> str:
    """Editable commit message with Workbench trailers. Never contains prompts."""
    text = (summary or "").strip()
    if not text:
        raise GitCommandError("Commit message summary is empty.")
    if len(text) > 5000:
        raise GitCommandError("Commit message is too long (max 5000 characters).")
    trailers = []
    for key, value in (("Workbench-Task", task_id), ("Workbench-Run", run_id), ("Workbench-Apply", apply_id)):
        value = (value or "").strip()
        if value:
            if not _TRAILER_VALUE_RE.match(value):
                raise GitCommandError(f"{key} value contains unsupported characters.")
            trailers.append(f"{key}: {value}")
    return text + ("\n\n" + "\n".join(trailers) if trailers else "")


# ---------------------------------------------------------------- service

class GitSyncService:
    """Fetch, plan, fast-forward, selected commit and guarded push."""

    def __init__(self, git: GitService | None = None, *,
                 secret_check: Callable[[Path, Sequence[str]], list[str]] | None = None) -> None:
        self.git = git or GitService()
        self._secret_check = secret_check

    # -- read-only
    def review_snapshot(self, root: Path) -> ReviewSnapshot:
        root = Path(root).resolve()
        inside = self.git.run(root, ["rev-parse", "--is-inside-work-tree"])
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            raise GitCommandError("The folder is not inside a Git repository.")
        result = self.git.run(root, ["status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all"])
        if result.returncode != 0:
            raise GitCommandError((result.stderr or "Failed to read Git status.").strip())
        branch, entries = parse_porcelain_v2(result.stdout)
        return ReviewSnapshot(root, branch, entries)

    def file_diff(self, root: Path, entry: ReviewEntry, *, max_chars: int = 200_000) -> str:
        root = Path(root).resolve()
        if entry.untracked:
            target = (root / entry.path)
            try:
                resolved = target.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                return "(path is outside the repository)"
            if not resolved.is_file():
                return "(untracked directory or special file)"
            data = resolved.read_bytes()[:max_chars]
            if b"\0" in data:
                return "(new binary file)"
            return "new file: " + entry.path + "\n" + data.decode("utf-8", "replace")
        chunks = []
        for label, args in (("staged", ["diff", "--cached"]), ("unstaged", ["diff"])):
            r = self.git.run(root, ["--literal-pathspecs", *args, "--", entry.path])
            if r.returncode == 0 and r.stdout.strip():
                chunks.append(f"=== {label} ===\n{r.stdout}")
        text = "\n".join(chunks) or "(no textual diff)"
        return text[:max_chars] + ("\n… (truncated)" if len(text) > max_chars else "")

    def fetch(self, root: Path, *, remote: str = "origin", timeout: int = 120) -> OperationResult:
        r = self.git.run(Path(root).resolve(), ["fetch", "--prune", "--no-tags", remote], timeout=timeout)
        if r.returncode != 0:
            return OperationResult(False, "fetch", (r.stderr or r.stdout or "Fetch failed.").strip())
        return OperationResult(True, "fetch", "Fetched " + remote)

    def remote_branch_sha(self, root: Path, upstream: str, *, timeout: int = 60) -> str:
        """Live remote SHA via ls-remote (not the possibly stale tracking ref)."""
        remote, _, branch = upstream.partition("/")
        if not remote or not branch:
            return ""
        r = self.git.run(Path(root).resolve(), ["ls-remote", "--heads", remote, "refs/heads/" + branch], timeout=timeout)
        if r.returncode != 0:
            raise GitCommandError((r.stderr or "ls-remote failed.").strip())
        for line in r.stdout.splitlines():
            sha, _, ref = line.partition("\t")
            if ref.strip() == "refs/heads/" + branch and _SHA_RE.match(sha.strip()):
                return sha.strip()
        return ""

    def build_plan(self, root: Path, *, fetch: bool = True) -> SyncPlan:
        fetched, fetch_error = False, ""
        if fetch:
            res = self.fetch(root)
            fetched, fetch_error = res.ok, ("" if res.ok else res.message)
        snap = self.review_snapshot(root)
        remote_sha = ""
        if snap.branch.upstream:
            r = self.git.run(snap.root, ["rev-parse", "--verify", "--quiet", snap.branch.upstream + "^{commit}"])
            remote_sha = r.stdout.strip() if r.returncode == 0 else ""
        plan = classify_sync_state(snap, remote_sha)
        if fetch_error:
            plan = SyncPlan(**{**_plan_dict(plan), "fetch_error": fetch_error,
                               "warnings": plan.warnings + ("Fetch failed; the plan uses the last known remote state.",)})
        else:
            plan = SyncPlan(**{**_plan_dict(plan), "fetched": fetched})
        return plan

    # -- mutating
    def fast_forward(self, root: Path, plan: SyncPlan) -> OperationResult:
        if not plan.can_fast_forward:
            return OperationResult(False, "fast_forward", "Fast-forward is not allowed for the current plan.")
        snap = self.review_snapshot(root)
        if snap.is_dirty or snap.branch.head_sha != plan.local_sha or snap.branch.branch != plan.branch:
            return OperationResult(False, "fast_forward", "Repository state changed since the plan was built; refresh the plan.")
        r = self.git.run(snap.root, ["merge", "--ff-only", plan.upstream], timeout=120)
        if r.returncode != 0:
            return OperationResult(False, "fast_forward", (r.stderr or r.stdout or "Fast-forward failed.").strip())
        return OperationResult(True, "fast_forward", f"Fast-forwarded {plan.branch} to {plan.upstream}.")

    def commit_selected(self, root: Path, paths: Sequence[str], message: str, *,
                        expected_staged: Sequence[str] = ()) -> OperationResult:
        """Stage exactly ``paths`` and commit. Refuses when unrelated paths are staged."""
        if not paths:
            return OperationResult(False, "commit", "No files were selected.")
        if any(not p or "\0" in p for p in paths):
            return OperationResult(False, "commit", "Invalid path in selection.")
        snap = self.review_snapshot(root)
        selected = set(paths)
        foreign = sorted(set(snap.staged_paths) - selected - set(expected_staged))
        if foreign:
            return OperationResult(False, "commit",
                                   "The index already contains staged changes that were not selected; nothing was committed.",
                                   details=foreign[:50])
        known = {e.path for e in snap.entries} | {e.orig_path for e in snap.entries if e.orig_path}
        missing = sorted(selected - known)
        if missing:
            return OperationResult(False, "commit", "Some selected files no longer have changes; refresh the review.",
                                   details=missing[:50])
        if self._secret_check is not None:
            problems = self._secret_check(snap.root, sorted(selected))
            if problems:
                return OperationResult(False, "commit", "Commit blocked by security checks (best-effort scan, not a guarantee).",
                                       details=problems[:50])
        add = self.git.run(snap.root, ["--literal-pathspecs", "add", "-A", "--", *sorted(selected)], timeout=60)
        if add.returncode != 0:
            return OperationResult(False, "commit", (add.stderr or "Failed to stage selected files.").strip())
        staged = self.git.run(snap.root, ["diff", "--cached", "--name-only", "-z"])
        staged_paths = {p for p in staged.stdout.split("\0") if p}
        extra = sorted(staged_paths - selected - set(expected_staged))
        if extra:
            return OperationResult(False, "commit", "Unexpected paths appeared in the index; nothing was committed. Review and unstage them.",
                                   details=extra[:50])
        if not staged_paths:
            return OperationResult(False, "commit", "Nothing is staged after adding the selection.")
        c = self.git.run(snap.root, ["commit", "-F", "-"], timeout=90, input_text=message)
        if c.returncode != 0:
            return OperationResult(False, "commit", "Commit failed: " + (c.stderr or c.stdout or "").strip())
        sha = self.git.run(snap.root, ["rev-parse", "HEAD"]).stdout.strip()
        return OperationResult(True, "commit", f"Commit {sha[:12]} created with {len(staged_paths)} file(s).",
                               commit_created=True, commit_sha=sha)

    def safe_push(self, root: Path, plan: SyncPlan, *, remote: str = "origin") -> OperationResult:
        """Push HEAD after re-verifying the remote branch SHA. Never forces."""
        if not plan.can_push:
            return OperationResult(False, "push", "Push is not allowed for the current plan.")
        if plan.branch.casefold() in PROTECTED_BRANCHES:
            return OperationResult(False, "push", f"Direct push to '{plan.branch}' is blocked.")
        snap = self.review_snapshot(root)
        if snap.branch.branch != plan.branch:
            return OperationResult(False, "push", "The checked-out branch changed since the plan was built; refresh the plan.")
        upstream = plan.upstream or f"{remote}/{plan.branch}"
        try:
            live = self.remote_branch_sha(snap.root, upstream)
        except GitCommandError as exc:
            return OperationResult(False, "push", f"Could not verify the remote before push: {exc}")
        if live != plan.remote_sha:
            return OperationResult(False, "push",
                                   "The remote branch changed since the plan was built (expected "
                                   f"{plan.remote_sha[:12] or 'none'}, found {live[:12] or 'none'}). Fetch and build a new plan.")
        args = ["push", "--porcelain"]
        if not plan.upstream:
            args.append("-u")
        # --force-with-lease is deliberately NOT used: a normal push is rejected
        # by the server for any non-fast-forward, which is the desired behaviour.
        args += [remote, "HEAD:refs/heads/" + plan.branch]
        r = self.git.run(snap.root, args, timeout=180)
        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip()
            hint = " (rejected: remote has new commits — fetch and re-plan)" if "rejected" in detail or "non-fast-forward" in detail else ""
            return OperationResult(False, "push", "Push failed" + hint + ": " + detail)
        return OperationResult(True, "push", f"Pushed {plan.branch} to {remote}.")

    def commit_and_push(self, root: Path, paths: Sequence[str], message: str, plan: SyncPlan) -> OperationResult:
        """Commit then push; result states clearly which stage failed."""
        c = self.commit_selected(root, paths, message)
        if not c.ok:
            return c
        snap = self.review_snapshot(root)
        fresh = classify_sync_state(snap, plan.remote_sha)
        p = self.safe_push(root, fresh)
        if p.ok:
            return OperationResult(True, "push", c.message + " " + p.message, True, c.commit_sha)
        return OperationResult(False, "push", f"Local commit {c.commit_sha[:12]} WAS created, but push failed: {p.message}",
                               True, c.commit_sha, p.details)


def _plan_dict(plan: SyncPlan) -> dict:
    return {k: getattr(plan, k) for k in SyncPlan.__dataclass_fields__}
