"""GitHub Actions read model for the Build Center (roadmap v1.14.6).

UI-independent services over :class:`GitHubApiClient`:

* discover workflows (``GET /repos/{o}/{r}/actions/workflows``) and read each
  workflow file to learn its triggers, so ``workflow_dispatch`` is only reported
  when the file really declares it;
* list runs with branch/ref, commit SHA, run ID, attempt, times and link, and
  correlate a run with a specific commit (an older run is never presented as
  the result of a newer push);
* list jobs and their failed steps;
* cancel a run (only with explicit confirmation by the caller; 1.14.6 never
  dispatches or downloads anything);
* a polling policy with cache, exponential backoff and rate-limit awareness;
* an in-process guard against two conflicting Sync/Build operations on the same
  repository/ref.

Nothing here stores credentials; tokens are passed per call and never logged.
"""
from __future__ import annotations

import base64
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping
from urllib.parse import quote, urlencode, urlsplit

from .api_client import GitHubApiClient, GitHubApiError

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_WORKFLOW_PATH_RE = re.compile(r"^\.github/workflows/[^/\\\x00]+\.ya?ml$")

RUNNING_STATUSES = frozenset({"queued", "in_progress", "waiting", "requested", "pending"})
KNOWN_CONCLUSIONS = frozenset({
    "success", "failure", "cancelled", "skipped", "timed_out", "action_required",
    "neutral", "stale", "startup_failure",
})
MAX_RUNS_PER_PAGE = 100


def _check_repo(owner: str, repo: str) -> tuple[str, str]:
    if not isinstance(owner, str) or not isinstance(repo, str) or not _NAME_RE.match(owner) or not _NAME_RE.match(repo) or repo in {".", ".."}:
        raise GitHubApiError("request", "Repository owner/name is invalid.")
    return owner, repo


def _str(value: object, limit: int = 300) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _github_html(value: object) -> str:
    """Only https://github.com links are kept for display/opening."""
    if not isinstance(value, str):
        return ""
    parts = urlsplit(value)
    if parts.scheme != "https" or (parts.hostname or "").casefold() != "github.com" or parts.username or parts.password:
        return ""
    return value


# ---------------------------------------------------------------- triggers


def parse_workflow_triggers(text: str) -> tuple[str, ...] | None:
    """Return the event names under the top-level ``on:`` key, or ``None``.

    Deliberately small and dependency-free (no PyYAML at runtime). Handles the
    forms GitHub documents: scalar (``on: push``), flow list (``on: [push, pull_request]``),
    flow mapping (``on: {push: ..., workflow_dispatch: {}}``) and block mapping/list.
    ``None`` means "could not determine" — callers must then treat manual
    dispatch as *unknown*, never as available.
    """
    if not isinstance(text, str):
        return None
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    key_re = re.compile(r"""^(?:on|"on"|'on'|true|True)\s*:(.*)$""")
    for index, line in enumerate(lines):
        match = key_re.match(line)
        if not match:
            continue
        rest = _strip_comment(match.group(1)).strip()
        if rest:
            return _parse_flow(rest)
        events: list[str] = []
        child_indent: int | None = None
        for child in lines[index + 1:]:
            stripped = _strip_comment(child)
            if not stripped.strip():
                continue
            indent = len(child) - len(child.lstrip(" "))
            if indent == 0:
                break
            if child_indent is None:
                child_indent = indent
            if indent != child_indent:
                continue
            body = stripped.strip()
            item = re.match(r"^-\s*(.+)$", body)
            if item:
                events.append(_unquote(item.group(1).strip()))
                continue
            key = re.match(r"""^("[^"]+"|'[^']+'|[A-Za-z_][A-Za-z0-9_-]*)\s*:""", body)
            if key:
                events.append(_unquote(key.group(1)))
        return tuple(e for e in events if e) or None
    return None


def _strip_comment(value: str) -> str:
    # A '#' starts a comment only at line start or after whitespace (outside quotes: good enough here).
    out = re.split(r"(?:^|\s)#", value, maxsplit=1)
    return out[0]


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_flow(rest: str) -> tuple[str, ...] | None:
    if rest.startswith("["):
        if not rest.endswith("]"):
            return None
        items = [_unquote(x) for x in rest[1:-1].split(",")]
        return tuple(i for i in items if i) or None
    if rest.startswith("{"):
        if not rest.endswith("}"):
            return None
        depth, current, keys = 0, "", []
        for ch in rest[1:-1] + ",":
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
            if ch == "," and depth == 0:
                key = current.split(":", 1)[0].strip()
                if key:
                    keys.append(_unquote(key))
                current = ""
            else:
                current += ch
        return tuple(keys) or None
    value = _unquote(rest)
    return (value,) if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", value) else None


# ---------------------------------------------------------------- models


@dataclass(frozen=True)
class WorkflowInfo:
    workflow_id: int
    name: str
    path: str
    state: str
    html_url: str
    triggers: tuple[str, ...] | None = None  # None = not read / undeterminable

    @property
    def manual_dispatch(self) -> str:
        """``available`` / ``not_available`` / ``unknown`` — never guessed."""
        if self.triggers is None:
            return "unknown"
        return "available" if "workflow_dispatch" in self.triggers else "not_available"

    @property
    def is_active(self) -> bool:
        return self.state == "active"


@dataclass(frozen=True)
class WorkflowRun:
    run_id: int
    workflow_id: int | None
    name: str
    event: str
    status: str
    conclusion: str | None
    head_branch: str
    head_sha: str
    run_number: int | None
    run_attempt: int | None
    created_at: str
    updated_at: str
    run_started_at: str
    html_url: str
    actor: str = ""

    @property
    def outcome(self) -> str:
        """Single display category, distinguishing every terminal conclusion."""
        if self.status in RUNNING_STATUSES:
            return "running" if self.status == "in_progress" else self.status
        if self.status == "completed":
            if self.conclusion in KNOWN_CONCLUSIONS:
                return str(self.conclusion)
            return "completed_unknown"
        return "unknown"

    @property
    def is_finished(self) -> bool:
        return self.status == "completed"


@dataclass(frozen=True)
class JobStep:
    number: int | None
    name: str
    status: str
    conclusion: str | None


@dataclass(frozen=True)
class WorkflowJob:
    job_id: int
    name: str
    status: str
    conclusion: str | None
    started_at: str
    completed_at: str
    html_url: str
    steps: tuple[JobStep, ...] = ()

    @property
    def failed_steps(self) -> tuple[JobStep, ...]:
        return tuple(s for s in self.steps if s.conclusion in {"failure", "timed_out", "cancelled", "startup_failure"})

    @property
    def log_url(self) -> str:
        # The browsable log is the job page; the raw-log API endpoint is a
        # short-lived redirect that must not be copied into logs/clipboard.
        return self.html_url


@dataclass(frozen=True)
class RunCorrelation:
    """Which run (if any) is the evidence for a specific commit."""
    commit_sha: str
    state: str  # matched | no_run_for_commit | only_older_runs
    run: WorkflowRun | None = None
    newest_other: WorkflowRun | None = None


def correlate_runs_with_commit(runs: Iterable[WorkflowRun], commit_sha: str, *, branch: str | None = None) -> RunCorrelation:
    """Pick the newest run whose ``head_sha`` equals the commit exactly.

    A run for another SHA is *never* returned as the result; it is only
    reported as ``newest_other`` so the UI can say "latest run is for an
    older/different commit".
    """
    sha = (commit_sha or "").strip().lower()
    if not _SHA_RE.match(sha) or len(sha) != 40:
        raise ValueError("A full 40-character commit SHA is required for run correlation.")
    candidates = [r for r in runs if branch is None or r.head_branch == branch]
    candidates.sort(key=lambda r: (r.created_at, r.run_id), reverse=True)
    matched = [r for r in candidates if r.head_sha.lower() == sha]
    if matched:
        best = sorted(matched, key=lambda r: (r.created_at, r.run_id, r.run_attempt or 0), reverse=True)[0]
        return RunCorrelation(sha, "matched", best, None)
    other = candidates[0] if candidates else None
    return RunCorrelation(sha, "only_older_runs" if other else "no_run_for_commit", None, other)


# ---------------------------------------------------------------- service


WriteTransport = Callable[[str, str, Mapping[str, str], float], int]


def _urllib_post(url: str, method: str, headers: Mapping[str, str], timeout: float) -> int:
    import urllib.error
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
            return None

    request = urllib.request.Request(url, data=b"", headers=dict(headers), method=method)
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


class GitHubActionsService:
    """Read GitHub Actions state for one repository; cancel with confirmation only."""

    def __init__(self, client: GitHubApiClient, *, write_transport: WriteTransport | None = None) -> None:
        self.client = client
        self._write = write_transport or _urllib_post

    # -- workflows
    def list_workflows(self, token: str, owner: str, repo: str, *, ref: str | None = None, read_triggers: bool = True) -> tuple[WorkflowInfo, ...]:
        owner, repo = _check_repo(owner, repo)
        response = self.client._request_response(token, f"/repos/{owner}/{repo}/actions/workflows?per_page=100", endpoint_label="workflows")
        payload = self.client._decode_json(response, expected_type=dict, resource_label="workflow list")
        items = payload.get("workflows")
        if not isinstance(items, list):
            raise GitHubApiError("invalid_response", "GitHub returned an unexpected workflow list.", status_code=response.status)
        result: list[WorkflowInfo] = []
        for raw in items[:200]:
            if not isinstance(raw, dict):
                continue
            wid = _int(raw.get("id"))
            path = _str(raw.get("path"))
            # GitHub also lists dynamic workflows (e.g. "dynamic/dependabot/...") — not files in the repo.
            if wid is None or not _WORKFLOW_PATH_RE.match(path):
                continue
            triggers = None
            if read_triggers:
                try:
                    triggers = parse_workflow_triggers(self.read_file(token, owner, repo, path, ref=ref))
                except GitHubApiError as exc:
                    if exc.category in {"authentication", "rate_limit"}:
                        raise
                    triggers = None
            result.append(WorkflowInfo(wid, _str(raw.get("name")) or path, path, _str(raw.get("state"), 40), _github_html(raw.get("html_url")), triggers))
        return tuple(sorted(result, key=lambda w: w.path))

    def read_file(self, token: str, owner: str, repo: str, path: str, *, ref: str | None = None) -> str:
        owner, repo = _check_repo(owner, repo)
        if not _WORKFLOW_PATH_RE.match(path or ""):
            raise GitHubApiError("request", "Only workflow files under .github/workflows can be read here.")
        query = "?" + urlencode({"ref": ref}) if ref else ""
        response = self.client._request_response(token, f"/repos/{owner}/{repo}/contents/{quote(path)}{query}", endpoint_label="workflow-file")
        payload = self.client._decode_json(response, expected_type=dict, resource_label="workflow file")
        if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
            raise GitHubApiError("invalid_response", "GitHub returned the workflow file in an unexpected encoding.", status_code=response.status)
        try:
            return base64.b64decode(payload["content"], validate=False).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            raise GitHubApiError("invalid_response", "The workflow file could not be decoded.", status_code=response.status) from None

    # -- runs
    def list_runs(
        self, token: str, owner: str, repo: str, *, workflow_id: int | None = None,
        branch: str | None = None, head_sha: str | None = None, per_page: int = 20,
    ) -> tuple[WorkflowRun, ...]:
        owner, repo = _check_repo(owner, repo)
        if not isinstance(per_page, int) or isinstance(per_page, bool) or not 1 <= per_page <= MAX_RUNS_PER_PAGE:
            raise ValueError("per_page must be between 1 and 100.")
        params: dict[str, object] = {"per_page": per_page}
        if branch:
            params["branch"] = branch
        if head_sha:
            if not _SHA_RE.match(head_sha.lower()) or len(head_sha) != 40:
                raise ValueError("head_sha must be a full commit SHA.")
            params["head_sha"] = head_sha.lower()
        base = f"/repos/{owner}/{repo}/actions/workflows/{int(workflow_id)}/runs" if workflow_id is not None else f"/repos/{owner}/{repo}/actions/runs"
        response = self.client._request_response(token, base + "?" + urlencode(params), endpoint_label="workflow-runs")
        payload = self.client._decode_json(response, expected_type=dict, resource_label="workflow runs")
        items = payload.get("workflow_runs")
        if not isinstance(items, list):
            raise GitHubApiError("invalid_response", "GitHub returned an unexpected run list.", status_code=response.status)
        runs = [r for r in (self._parse_run(raw) for raw in items[:per_page]) if r is not None]
        return tuple(sorted(runs, key=lambda r: (r.created_at, r.run_id), reverse=True))

    @staticmethod
    def _parse_run(raw: object) -> WorkflowRun | None:
        if not isinstance(raw, dict):
            return None
        run_id = _int(raw.get("id"))
        sha = _str(raw.get("head_sha"), 64).lower()
        if run_id is None or not _SHA_RE.match(sha):
            return None
        conclusion = raw.get("conclusion")
        actor = raw.get("actor") if isinstance(raw.get("actor"), dict) else {}
        return WorkflowRun(
            run_id=run_id, workflow_id=_int(raw.get("workflow_id")), name=_str(raw.get("name")) or _str(raw.get("display_title")),
            event=_str(raw.get("event"), 40), status=_str(raw.get("status"), 40),
            conclusion=conclusion if isinstance(conclusion, str) else None,
            head_branch=_str(raw.get("head_branch"), 255), head_sha=sha,
            run_number=_int(raw.get("run_number")), run_attempt=_int(raw.get("run_attempt")),
            created_at=_str(raw.get("created_at"), 40), updated_at=_str(raw.get("updated_at"), 40),
            run_started_at=_str(raw.get("run_started_at"), 40), html_url=_github_html(raw.get("html_url")),
            actor=_str(actor.get("login"), 100),
        )

    def list_jobs(self, token: str, owner: str, repo: str, run_id: int) -> tuple[WorkflowJob, ...]:
        owner, repo = _check_repo(owner, repo)
        response = self.client._request_response(token, f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}/jobs?per_page=100", endpoint_label="workflow-jobs")
        payload = self.client._decode_json(response, expected_type=dict, resource_label="workflow jobs")
        items = payload.get("jobs")
        if not isinstance(items, list):
            raise GitHubApiError("invalid_response", "GitHub returned an unexpected job list.", status_code=response.status)
        jobs: list[WorkflowJob] = []
        for raw in items[:100]:
            if not isinstance(raw, dict) or _int(raw.get("id")) is None:
                continue
            steps = tuple(
                JobStep(_int(s.get("number")), _str(s.get("name")), _str(s.get("status"), 40), s.get("conclusion") if isinstance(s.get("conclusion"), str) else None)
                for s in (raw.get("steps") or [])[:300] if isinstance(s, dict)
            )
            jobs.append(WorkflowJob(
                int(raw["id"]), _str(raw.get("name")), _str(raw.get("status"), 40),
                raw.get("conclusion") if isinstance(raw.get("conclusion"), str) else None,
                _str(raw.get("started_at"), 40), _str(raw.get("completed_at"), 40), _github_html(raw.get("html_url")), steps,
            ))
        return tuple(jobs)

    def cancel_run(self, token: str, owner: str, repo: str, run: WorkflowRun, *, confirmed: bool) -> str:
        """Request cancellation. Returns ``requested`` or raises a categorized error.

        The caller must have asked the user (``confirmed=True``). A finished run
        is never "cancelled". 409 means GitHub refused (already finishing).
        """
        if not confirmed:
            raise GitHubApiError("request", "Cancelling a run requires explicit confirmation.")
        if run.is_finished:
            raise GitHubApiError("request", "This run has already finished; there is nothing to cancel.")
        owner, repo = _check_repo(owner, repo)
        from .redaction import validate_pat
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {validate_pat(token)}",
            "X-GitHub-Api-Version": self.client.api_version,
            "User-Agent": self.client.user_agent,
        }
        url = f"{self.client.base_url}/repos/{owner}/{repo}/actions/runs/{int(run.run_id)}/cancel"
        try:
            status = self._write(url, "POST", headers, self.client.timeout_seconds)
        except (TimeoutError, OSError):
            raise GitHubApiError("network", "Could not reach GitHub to cancel the run.") from None
        if status == 202:
            return "requested"
        if status in (401,):
            raise GitHubApiError("authentication", "GitHub rejected this token (HTTP 401).", status_code=status)
        if status in (403, 404):
            raise GitHubApiError("permission_or_policy", "This token is not allowed to cancel runs in this repository (needs Actions: write).", status_code=status)
        if status == 409:
            raise GitHubApiError("conflict", "GitHub refused the cancel request (HTTP 409); the run may already be finishing.", status_code=status)
        raise GitHubApiError("request", f"GitHub did not accept the cancel request (HTTP {status}).", status_code=status)


def check_workflow_binding(workflow_file: str | None, workflows: Iterable[WorkflowInfo]) -> str:
    """``unset`` / ``ok`` / ``disabled`` / ``stale`` (file renamed or removed)."""
    if not workflow_file:
        return "unset"
    for wf in workflows:
        if wf.path == workflow_file:
            return "ok" if wf.is_active else "disabled"
    return "stale"


# ---------------------------------------------------------------- polling


@dataclass
class PollPolicy:
    """Non-blocking polling schedule with cache, backoff and rate-limit respect.

    ``next_delay()`` is consulted by the UI timer; ``record_*`` feed it outcomes.
    """
    active_interval: float = 10.0   # while a run is queued/in progress
    idle_interval: float = 60.0     # nothing running
    max_backoff: float = 300.0
    min_interval: float = 5.0       # cache: never hit the API faster than this
    _failures: int = 0
    _not_before: float = 0.0
    _last_fetch: float = 0.0
    _active: bool = False
    clock: Callable[[], float] = field(default=time.monotonic)

    def may_fetch_now(self) -> bool:
        now = self.clock()
        return now >= self._not_before and now - self._last_fetch >= self.min_interval

    def record_success(self, *, any_running: bool) -> None:
        self._failures = 0
        self._active = any_running
        self._last_fetch = self.clock()
        self._not_before = self._last_fetch

    def record_error(self, error: BaseException) -> None:
        self._failures += 1
        self._last_fetch = self.clock()
        base = self.active_interval if self._active else self.idle_interval
        wait = min(self.max_backoff, base * (2 ** min(self._failures, 6)))
        retry_after = getattr(error, "retry_after_seconds", None)
        if getattr(error, "category", "") == "rate_limit" and isinstance(retry_after, int):
            wait = max(wait, float(retry_after))
        if getattr(error, "category", "") == "authentication":
            wait = float("inf")  # stop polling until the user fixes the credential
        self._not_before = self._last_fetch + wait

    def next_delay(self) -> float:
        now = self.clock()
        base = self.active_interval if self._active else self.idle_interval
        return max(self.min_interval, self._not_before - now, self._last_fetch + base - now)

    @property
    def stopped(self) -> bool:
        return self._not_before == float("inf")


# ---------------------------------------------------------------- conflicts


class RepositoryOperationGuard:
    """Prevents two Sync/Build operations on the same repository + ref at once."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._held: dict[tuple[str, str], str] = {}

    @staticmethod
    def _key(full_name: str, ref: str) -> tuple[str, str]:
        return (full_name.casefold(), ref)

    def acquire(self, full_name: str, ref: str, label: str) -> bool:
        with self._lock:
            key = self._key(full_name, ref)
            if key in self._held:
                return False
            self._held[key] = label
            return True

    def holder(self, full_name: str, ref: str) -> str | None:
        with self._lock:
            return self._held.get(self._key(full_name, ref))

    def release(self, full_name: str, ref: str) -> None:
        with self._lock:
            self._held.pop(self._key(full_name, ref), None)


OPERATION_GUARD = RepositoryOperationGuard()
