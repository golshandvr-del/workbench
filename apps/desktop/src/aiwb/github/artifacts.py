"""Workflow dispatch and safe Artifact download (roadmap v1.14.7).

UI-independent. Builds on :mod:`aiwb.github.actions`.

* ``parse_dispatch_inputs`` reads the ``workflow_dispatch.inputs`` block of a
  workflow file (small YAML subset, no PyYAML) and ``validate_dispatch_values``
  checks user values against type/required/options.
* ``GitHubDispatchService.dispatch`` sends ``POST .../dispatches`` for an
  explicit ref. A run is only reported as *the* dispatched run when GitHub
  returned its ID, or when strict matching (workflow, event, branch, creation
  time, not seen before) finds exactly one candidate. HTTP 204 alone is
  ``unconfirmed`` — never success.
* Artifacts are listed with ID/name/size/expiry/digest/run/commit; an artifact
  of another run or commit is rejected as output of a task.
* Download asks GitHub for the official ``/zip`` endpoint **without following
  the redirect**, then fetches the short-lived URL *without* the token, into a
  ``.part`` file with size/time caps, hashing SHA-256 on the fly. The temporary
  URL is never returned, logged or raised. Partial files are removed.
* ``safe_extract_zip`` refuses traversal, absolute/drive paths, duplicates and
  case collisions, Windows reserved names, symlinks/special files, encrypted
  entries, too many entries and zip bombs (declared and actual sizes).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Iterator, Mapping
from urllib.parse import urlsplit

from .actions import GitHubActionsService, WorkflowInfo, WorkflowRun, _check_repo, _int, _str
from .api_client import GitHubApiError, HttpResponse
from .redaction import validate_pat

# ---------------------------------------------------------------- tiny YAML subset


def _strip_comment(line: str) -> str:
    out, quote = [], ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(value: str) -> object:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return [_scalar(x) for x in _split_flow(value[1:-1])]
    if value.startswith("{") and value.endswith("}"):
        result: dict[str, object] = {}
        for part in _split_flow(value[1:-1]):
            if ":" in part:
                k, v = part.split(":", 1)
                result[str(_scalar(k))] = _scalar(v) if v.strip() else None
            elif part.strip():
                result[str(_scalar(part))] = None
        return result
    return value


def _split_flow(text: str) -> list[str]:
    parts, depth, cur, quote = [], 0, "", ""
    for ch in text:
        if quote:
            cur += ch
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


_KEY_RE = re.compile(r"""^("[^"]*"|'[^']*'|[^:#\s][^:#]*?)\s*:(?:\s+(.*))?$""")


def parse_yaml_subset(text: str) -> object:
    """Parse block mappings/lists with scalar and flow values.

    Enough for workflow ``on:`` sections. Raises ``ValueError`` on anything it
    does not understand (anchors, multi-docs, block scalars inside inputs are
    tolerated as strings by skipping their body).
    """
    lines: list[tuple[int, str]] = []
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    skip_indent: int | None = None
    for raw in raw_lines:
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ValueError("tabs in indentation")
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        if skip_indent is not None:
            if indent > skip_indent:
                continue
            skip_indent = None
        body = stripped.strip()
        if body in {"---", "..."}:
            continue
        if re.search(r":\s*[|>][+-]?\d*$", body):  # block scalar: keep key, drop body
            skip_indent = indent
            body = re.sub(r":\s*[|>][+-]?\d*$", ': ""', body)
        lines.append((indent, body))
    pos = 0

    def parse_block(indent: int) -> object:
        nonlocal pos
        if pos >= len(lines):
            return None
        is_list = lines[pos][1].startswith("- ") or lines[pos][1] == "-"
        container: object = [] if is_list else {}
        while pos < len(lines):
            ind, body = lines[pos]
            if ind < indent:
                break
            if ind > indent:
                raise ValueError("unexpected indentation")
            if is_list:
                if not (body.startswith("- ") or body == "-"):
                    break
                item = body[1:].strip()
                pos += 1
                if not item:
                    container.append(parse_block(lines[pos][0]) if pos < len(lines) and lines[pos][0] > ind else None)  # type: ignore[union-attr]
                elif _KEY_RE.match(item) and not item.startswith(("'", '"', "[", "{")):
                    # "- key: value" -> mapping item; continuation lines are indented deeper
                    lines.insert(pos, (ind + 2, item))
                    container.append(parse_block(ind + 2))  # type: ignore[union-attr]
                else:
                    container.append(_scalar(item))  # type: ignore[union-attr]
            else:
                m = _KEY_RE.match(body)
                if not m:
                    raise ValueError(f"cannot parse line: {body[:40]}")
                key = str(_scalar(m.group(1)))
                value = m.group(2)
                pos += 1
                if value is None or value == "":
                    if pos < len(lines) and lines[pos][0] > ind:
                        container[key] = parse_block(lines[pos][0])  # type: ignore[index]
                    elif pos < len(lines) and lines[pos][0] == ind and lines[pos][1].startswith("- "):
                        container[key] = parse_block(ind)  # type: ignore[index]
                    else:
                        container[key] = None  # type: ignore[index]
                else:
                    container[key] = _scalar(value)  # type: ignore[index]
        return container

    return parse_block(lines[0][0]) if lines else {}


# ---------------------------------------------------------------- dispatch inputs

INPUT_TYPES = frozenset({"string", "boolean", "choice", "number", "environment"})
MAX_INPUTS = 25  # GitHub limit for workflow_dispatch inputs


@dataclass(frozen=True)
class DispatchInput:
    name: str
    type: str = "string"
    required: bool = False
    default: str | None = None
    description: str = ""
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class DispatchForm:
    """Result of reading a workflow file for manual dispatch."""
    dispatchable: bool
    inputs: tuple[DispatchInput, ...] = ()
    error: str = ""


def _bool_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "on"}:
        return "true"
    if text in {"false", "no", "off"}:
        return "false"
    return text


def parse_dispatch_inputs(text: str) -> DispatchForm:
    try:
        doc = parse_yaml_subset(text)
    except (ValueError, IndexError, RecursionError) as exc:
        return DispatchForm(False, (), f"Workflow file could not be read reliably ({exc}).")
    if not isinstance(doc, dict):
        return DispatchForm(False, (), "Workflow file has no top-level mapping.")
    on = None
    for key in ("on", "true", "True"):
        if key in doc:
            on = doc[key]
            break
    if isinstance(on, str):
        return DispatchForm(on == "workflow_dispatch")
    if isinstance(on, list):
        return DispatchForm("workflow_dispatch" in on)
    if not isinstance(on, dict) or "workflow_dispatch" not in on:
        return DispatchForm(False)
    wd = on.get("workflow_dispatch")
    if wd is None or wd == "" or wd == {}:
        return DispatchForm(True)
    if not isinstance(wd, dict):
        return DispatchForm(False, (), "workflow_dispatch has an unexpected shape.")
    raw_inputs = wd.get("inputs") or {}
    if not isinstance(raw_inputs, dict):
        return DispatchForm(False, (), "workflow_dispatch.inputs has an unexpected shape.")
    if len(raw_inputs) > MAX_INPUTS:
        return DispatchForm(False, (), f"More than {MAX_INPUTS} inputs are not supported by GitHub.")
    result: list[DispatchInput] = []
    for name, spec in raw_inputs.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,99}", name):
            return DispatchForm(False, (), f"Input name '{name[:40]}' is not valid.")
        spec = spec if isinstance(spec, dict) else {}
        typ = str(spec.get("type") or "string").strip()
        if typ not in INPUT_TYPES:
            return DispatchForm(False, (), f"Input '{name}' has unsupported type '{typ[:20]}'.")
        options = spec.get("options") or []
        if typ == "choice" and (not isinstance(options, list) or not options):
            return DispatchForm(False, (), f"Choice input '{name}' has no options.")
        default = spec.get("default")
        default_text = _bool_text(default) if typ == "boolean" else (None if default is None else str(default))
        result.append(DispatchInput(
            name=name, type=typ, required=_bool_text(spec.get("required")) == "true",
            default=default_text, description=str(spec.get("description") or "")[:300],
            options=tuple(str(o) for o in options) if isinstance(options, list) else (),
        ))
    return DispatchForm(True, tuple(result))


def validate_dispatch_values(inputs: Iterable[DispatchInput], values: Mapping[str, object]) -> dict[str, str]:
    """Return the JSON ``inputs`` payload or raise ``ValueError`` with a clear message."""
    known = {i.name: i for i in inputs}
    unknown = [k for k in values if k not in known]
    if unknown:
        raise ValueError(f"Unknown input(s): {', '.join(sorted(unknown))}.")
    payload: dict[str, str] = {}
    for spec in known.values():
        raw = values.get(spec.name)
        text = "" if raw is None else (("true" if raw else "false") if isinstance(raw, bool) else str(raw))
        if text == "" and spec.default is not None:
            text = spec.default
        if text == "":
            if spec.required:
                raise ValueError(f"Input '{spec.name}' is required.")
            continue
        if len(text) > 65535:
            raise ValueError(f"Input '{spec.name}' is too long.")
        if spec.type == "boolean":
            norm = _bool_text(text)
            if norm not in {"true", "false"}:
                raise ValueError(f"Input '{spec.name}' must be true or false.")
            text = norm
        elif spec.type == "number":
            try:
                float(text)
            except ValueError:
                raise ValueError(f"Input '{spec.name}' must be a number.") from None
            if text.strip().lower() in {"nan", "inf", "-inf", "infinity", "-infinity"}:
                raise ValueError(f"Input '{spec.name}' must be a finite number.")
        elif spec.type == "choice" and text not in spec.options:
            raise ValueError(f"Input '{spec.name}' must be one of: {', '.join(spec.options)}.")
        payload[spec.name] = text
    return payload


_REF_RE = re.compile(r"^(?!/)(?!.*//)(?!.*\.\.)(?!.*@\{)[^\x00-\x20~^:?*\[\\]{1,255}(?<!/)(?<!\.lock)(?<!\.)$")


def validate_ref(ref: str) -> str:
    ref = (ref or "").strip()
    if not _REF_RE.match(ref):
        raise ValueError("Enter a valid branch or tag name to run the workflow on.")
    return ref


# ---------------------------------------------------------------- artifacts model


@dataclass(frozen=True)
class ArtifactInfo:
    artifact_id: int
    name: str
    size_in_bytes: int
    expired: bool
    expires_at: str
    created_at: str
    digest: str  # "sha256:<hex>" or ""
    run_id: int | None
    head_sha: str
    head_branch: str
    repository_id: int | None

    @property
    def sha256_reference(self) -> str | None:
        if self.digest.lower().startswith("sha256:"):
            value = self.digest[7:].lower()
            if re.fullmatch(r"[0-9a-f]{64}", value):
                return value
        return None

    @property
    def downloadable(self) -> bool:
        return not self.expired


def artifact_matches(artifact: ArtifactInfo, *, run_id: int, head_sha: str, repository_id: int | None = None) -> bool:
    """True only if the artifact provably belongs to this run *and* commit."""
    if artifact.run_id != run_id:
        return False
    if not head_sha or artifact.head_sha.lower() != head_sha.lower():
        return False
    if repository_id is not None and artifact.repository_id is not None and artifact.repository_id != repository_id:
        return False
    return True


# ---------------------------------------------------------------- dispatch result


@dataclass(frozen=True)
class DispatchResult:
    state: str  # confirmed | unconfirmed
    workflow_id: int
    ref: str
    requested_at: float
    run_id: int | None = None
    html_url: str = ""
    message: str = ""


# ---------------------------------------------------------------- transports

# (url, method, headers, body, timeout) -> HttpResponse ; MUST NOT follow redirects.
RequestTransport = Callable[[str, str, Mapping[str, str], bytes | None, float], HttpResponse]
# (url, timeout) -> iterator of byte chunks ; NO credentials are sent.
StreamTransport = Callable[[str, float], Iterator[bytes]]


def _urllib_request(url: str, method: str, headers: Mapping[str, str], body: bytes | None, timeout: float) -> HttpResponse:
    import urllib.error
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
            return None

    req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as resp:
            return HttpResponse(int(resp.status), dict(resp.headers.items()), resp.read(1024 * 1024))
    except urllib.error.HTTPError as exc:
        try:
            data = exc.read(1024 * 1024)
        except Exception:
            data = b""
        return HttpResponse(int(exc.code), dict(exc.headers.items()) if exc.headers else {}, data)


def _urllib_stream(url: str, timeout: float) -> Iterator[bytes]:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "AI-Workbench"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # no Authorization header, by design
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                return
            yield chunk


def _is_trusted_download_host(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").casefold()
    if parts.scheme != "https" or parts.username or parts.password:
        return False
    return host.endswith(".githubusercontent.com") or host.endswith(".blob.core.windows.net") or host.endswith(".github.com") or host == "github.com"


# ---------------------------------------------------------------- service

DEFAULT_MAX_DOWNLOAD_BYTES = 2 * 1024 ** 3
DEFAULT_DOWNLOAD_SECONDS = 15 * 60
DISPATCH_CLOCK_SKEW_SECONDS = 120


@dataclass(frozen=True)
class DownloadResult:
    artifact_id: int
    path: Path
    size: int
    sha256: str
    verification: str  # matched | mismatch | computed_only
    reference_sha256: str | None = None

    @property
    def verified(self) -> bool:
        return self.verification == "matched"


def _iso_to_epoch(value: str) -> float | None:
    import calendar
    try:
        return float(calendar.timegm(time.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, TypeError):
        return None


class GitHubDispatchService:
    def __init__(
        self, actions: GitHubActionsService, *, request: RequestTransport | None = None,
        stream: StreamTransport | None = None, clock: Callable[[], float] = time.time,
    ) -> None:
        self.actions = actions
        self.client = actions.client
        self._request = request or _urllib_request
        self._stream = stream or _urllib_stream
        self.clock = clock

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {validate_pat(token)}",
            "X-GitHub-Api-Version": self.client.api_version,
            "User-Agent": self.client.user_agent,
        }

    def _send(self, token: str, method: str, path: str, body: object | None = None) -> HttpResponse:
        headers = self._headers(token)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            return self._request(self.client.base_url + path, method, headers, data, self.client.timeout_seconds)
        except (TimeoutError,) :
            raise GitHubApiError("timeout", "The GitHub request timed out.") from None
        except OSError:
            raise GitHubApiError("network", "Could not reach GitHub. Check the network/proxy and retry.") from None

    # -- dispatch form
    def dispatch_form(self, token: str, owner: str, repo: str, workflow: WorkflowInfo, *, ref: str) -> DispatchForm:
        text = self.actions.read_file(token, owner, repo, workflow.path, ref=ref)
        return parse_dispatch_inputs(text)

    def dispatch(
        self, token: str, owner: str, repo: str, workflow: WorkflowInfo, *, ref: str,
        inputs: Mapping[str, str], form: DispatchForm,
    ) -> DispatchResult:
        owner, repo = _check_repo(owner, repo)
        ref = validate_ref(ref)
        if not form.dispatchable:
            raise GitHubApiError("request", "This workflow does not declare workflow_dispatch; it cannot be run manually.")
        if not workflow.is_active:
            raise GitHubApiError("request", "This workflow is disabled on GitHub.")
        payload = validate_dispatch_values(form.inputs, inputs)
        requested_at = self.clock()
        resp = self._send(token, "POST", f"/repos/{owner}/{repo}/actions/workflows/{int(workflow.workflow_id)}/dispatches",
                          {"ref": ref, "inputs": payload, "return_run_details": True})
        status = resp.status
        if status == 200:
            try:
                data = json.loads(resp.body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                data = {}
            run_id = _int(data.get("workflow_run_id")) if isinstance(data, dict) else None
            if run_id:
                html = data.get("html_url") if isinstance(data.get("html_url"), str) else ""
                return DispatchResult("confirmed", workflow.workflow_id, ref, requested_at, run_id,
                                      html if html.startswith("https://github.com/") else "", "GitHub returned the run ID.")
            return DispatchResult("unconfirmed", workflow.workflow_id, ref, requested_at, None, "", "GitHub accepted the request but returned no run ID.")
        if status == 204:
            return DispatchResult("unconfirmed", workflow.workflow_id, ref, requested_at, None, "",
                                  "GitHub accepted the request (HTTP 204) without a run ID; the run is not confirmed yet.")
        self._raise_for(status, action="run this workflow", write_scope="Actions: write")
        raise AssertionError("unreachable")

    @staticmethod
    def _raise_for(status: int, *, action: str, write_scope: str = "") -> None:
        if status == 401:
            raise GitHubApiError("authentication", "GitHub rejected this token (HTTP 401).", status_code=status)
        if status in (403, 404):
            raise GitHubApiError("permission_or_policy", f"This token is not allowed to {action} (needs {write_scope or 'access'}), or the resource is not visible.", status_code=status)
        if status == 410:
            raise GitHubApiError("expired", "The artifact has expired on GitHub and can no longer be downloaded (HTTP 410).", status_code=status)
        if status == 422:
            raise GitHubApiError("request", f"GitHub rejected the request (HTTP 422): the ref or inputs are not valid for this workflow.", status_code=status)
        if status == 429:
            raise GitHubApiError("rate_limit", "GitHub rate-limited this request (HTTP 429).", status_code=status)
        if status >= 500:
            raise GitHubApiError("server", f"GitHub returned a server error (HTTP {status}).", status_code=status)
        raise GitHubApiError("request", f"GitHub did not accept the request (HTTP {status}).", status_code=status)

    def find_dispatched_run(
        self, token: str, owner: str, repo: str, result: DispatchResult, *, known_run_ids: Iterable[int] = (),
    ) -> DispatchResult:
        """Strict lookup for a 204 dispatch. Exactly one new candidate → confirmed."""
        if result.state == "confirmed":
            return result
        runs = self.actions.list_runs(token, owner, repo, workflow_id=result.workflow_id, branch=result.ref, per_page=20)
        known = set(known_run_ids)
        floor = result.requested_at - DISPATCH_CLOCK_SKEW_SECONDS
        candidates = [
            r for r in runs
            if r.event == "workflow_dispatch" and r.head_branch == result.ref and r.run_id not in known
            and (r.workflow_id in (None, result.workflow_id))
            and (_iso_to_epoch(r.created_at) or 0) >= floor
        ]
        if len(candidates) == 1:
            r = candidates[0]
            return DispatchResult("confirmed", result.workflow_id, result.ref, result.requested_at, r.run_id, r.html_url,
                                  "Matched exactly one new workflow_dispatch run on this ref.")
        if len(candidates) > 1:
            return DispatchResult("unconfirmed", result.workflow_id, result.ref, result.requested_at, None, "",
                                  f"{len(candidates)} new manual runs match; cannot tell which one is yours. Pick it in the run list.")
        return DispatchResult("unconfirmed", result.workflow_id, result.ref, result.requested_at, None, "", "No matching run has appeared yet.")

    # -- artifacts
    def list_artifacts(self, token: str, owner: str, repo: str, run_id: int) -> tuple[ArtifactInfo, ...]:
        owner, repo = _check_repo(owner, repo)
        response = self.client._request_response(token, f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}/artifacts?per_page=100", endpoint_label="artifacts")
        payload = self.client._decode_json(response, expected_type=dict, resource_label="artifact list")
        items = payload.get("artifacts")
        if not isinstance(items, list):
            raise GitHubApiError("invalid_response", "GitHub returned an unexpected artifact list.", status_code=response.status)
        out: list[ArtifactInfo] = []
        for raw in items[:200]:
            if not isinstance(raw, dict) or _int(raw.get("id")) is None:
                continue
            wr = raw.get("workflow_run") if isinstance(raw.get("workflow_run"), dict) else {}
            out.append(ArtifactInfo(
                artifact_id=int(raw["id"]), name=_str(raw.get("name"), 256), size_in_bytes=_int(raw.get("size_in_bytes")) or 0,
                expired=raw.get("expired") is True, expires_at=_str(raw.get("expires_at"), 40), created_at=_str(raw.get("created_at"), 40),
                digest=_str(raw.get("digest"), 100), run_id=_int(wr.get("id")), head_sha=_str(wr.get("head_sha"), 64).lower(),
                head_branch=_str(wr.get("head_branch"), 255), repository_id=_int(wr.get("repository_id")),
            ))
        return tuple(out)

    def download_artifact(
        self, token: str, owner: str, repo: str, artifact: ArtifactInfo, dest_dir: Path, *,
        run: WorkflowRun | None = None, max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
        max_seconds: float = DEFAULT_DOWNLOAD_SECONDS, cancel: Callable[[], bool] = lambda: False,
    ) -> DownloadResult:
        owner, repo = _check_repo(owner, repo)
        if artifact.expired:
            raise GitHubApiError("expired", "This artifact has expired and can no longer be downloaded.")
        if run is not None and not artifact_matches(artifact, run_id=run.run_id, head_sha=run.head_sha):
            raise GitHubApiError("request", "This artifact does not belong to the selected run/commit; refusing to deliver it as its output.")
        if artifact.size_in_bytes and artifact.size_in_bytes > max_bytes:
            raise GitHubApiError("too_large", f"The artifact ({artifact.size_in_bytes} bytes) exceeds the download limit ({max_bytes} bytes).")
        dest_dir = Path(dest_dir)
        if not dest_dir.is_dir():
            raise GitHubApiError("request", "The destination folder does not exist.")
        resp = self._send(token, "GET", f"/repos/{owner}/{repo}/actions/artifacts/{int(artifact.artifact_id)}/zip")
        if resp.status not in (301, 302, 303, 307, 308):
            self._raise_for(resp.status, action="download this artifact", write_scope="Actions: read")
        location = next((str(v) for k, v in resp.headers.items() if str(k).casefold() == "location"), "")
        if not _is_trusted_download_host(location):
            raise GitHubApiError("invalid_response", "GitHub returned an unexpected download location; refusing to follow it.")
        safe_name = sanitize_filename(f"{artifact.name or 'artifact'}-{artifact.artifact_id}.zip")
        final = dest_dir / safe_name
        part = dest_dir / (safe_name + ".part")
        digest = hashlib.sha256()
        size = 0
        started = time.monotonic()
        try:
            with open(part, "wb") as fh:
                try:
                    for chunk in self._stream(location, self.client.timeout_seconds):
                        if cancel():
                            raise GitHubApiError("cancelled", "Download cancelled.")
                        if time.monotonic() - started > max_seconds:
                            raise GitHubApiError("timeout", "The download took longer than the allowed time.")
                        size += len(chunk)
                        if size > max_bytes:
                            raise GitHubApiError("too_large", "The download exceeded the size limit.")
                        digest.update(chunk)
                        fh.write(chunk)
                except GitHubApiError:
                    raise
                except Exception as exc:
                    # Never surface the temporary URL (it may be inside the exception text).
                    if "timed out" in type(exc).__name__.lower() or isinstance(exc, TimeoutError):
                        raise GitHubApiError("timeout", "The download timed out.") from None
                    code = getattr(exc, "code", None)
                    if code == 410:
                        raise GitHubApiError("expired", "The download link expired (HTTP 410). Retry the download.", status_code=410) from None
                    raise GitHubApiError("network", "The download failed (network error).") from None
            if artifact.size_in_bytes and size != artifact.size_in_bytes:
                raise GitHubApiError("invalid_response", f"Downloaded size ({size}) differs from the size GitHub reported ({artifact.size_in_bytes}).")
            if not zipfile.is_zipfile(part):
                raise GitHubApiError("invalid_response", "The downloaded file is not a valid ZIP archive.")
            os.replace(part, final)
        except BaseException:
            try:
                part.unlink()
            except OSError:
                pass
            raise
        sha = digest.hexdigest()
        ref = artifact.sha256_reference
        verification = "computed_only" if ref is None else ("matched" if ref == sha else "mismatch")
        if verification == "mismatch":
            try:
                final.unlink()
            except OSError:
                pass
            raise GitHubApiError("integrity", "SHA-256 of the download does not match the digest GitHub reported; the file was removed.")
        return DownloadResult(artifact.artifact_id, final, size, sha, verification, ref)


# ---------------------------------------------------------------- safe extraction

_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "artifact.zip"
    if cleaned.split(".")[0].casefold() in _WINDOWS_RESERVED:
        cleaned = "_" + cleaned
    return cleaned[:180]


@dataclass(frozen=True)
class ExtractLimits:
    max_entries: int = 10000
    max_total_bytes: int = 4 * 1024 ** 3
    max_file_bytes: int = 2 * 1024 ** 3
    max_ratio: float = 200.0  # uncompressed / compressed per entry (only when big)
    ratio_min_bytes: int = 1024 * 1024


class UnsafeArchiveError(ValueError):
    pass


def _check_member_name(name: str) -> PurePosixPath:
    if not name or "\x00" in name:
        raise UnsafeArchiveError("An entry has an empty or invalid name.")
    if "\\" in name:
        raise UnsafeArchiveError(f"Entry '{name[:80]}' uses backslashes in its path.")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise UnsafeArchiveError(f"Entry '{name[:80]}' has an absolute path.")
    path = PurePosixPath(name)
    for part in path.parts:
        if part in {"..", "."}:
            raise UnsafeArchiveError(f"Entry '{name[:80]}' escapes the destination folder.")
        if part != part.rstrip(" .") or re.search(r'[<>:"|?*\x00-\x1f]', part):
            raise UnsafeArchiveError(f"Entry '{name[:80]}' has a name that is invalid on Windows.")
        if part.split(".")[0].casefold() in _WINDOWS_RESERVED:
            raise UnsafeArchiveError(f"Entry '{name[:80]}' uses a reserved Windows device name.")
    return path


def inspect_zip(zip_path: Path, limits: ExtractLimits = ExtractLimits()) -> list[zipfile.ZipInfo]:
    """Validate every entry before anything is written. Returns file entries."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise UnsafeArchiveError("Not a valid ZIP archive.") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > limits.max_entries:
            raise UnsafeArchiveError(f"The archive has too many entries ({len(infos)}).")
        seen: dict[str, str] = {}
        total = 0
        files: list[zipfile.ZipInfo] = []
        for info in infos:
            path = _check_member_name(info.filename.rstrip("/") if info.is_dir() else info.filename)
            key = str(path).casefold()
            if key in seen:
                raise UnsafeArchiveError(f"Duplicate or case-colliding entries: '{seen[key][:60]}' and '{info.filename[:60]}'.")
            seen[key] = info.filename
            if info.flag_bits & 0x1:
                raise UnsafeArchiveError(f"Entry '{info.filename[:80]}' is encrypted.")
            mode = (info.external_attr >> 16) & 0xFFFF
            ftype = stat.S_IFMT(mode)
            if ftype and ftype not in (stat.S_IFREG, stat.S_IFDIR):
                raise UnsafeArchiveError(f"Entry '{info.filename[:80]}' is a link or special file.")
            if info.is_dir():
                continue
            if info.file_size > limits.max_file_bytes:
                raise UnsafeArchiveError(f"Entry '{info.filename[:80]}' is too large.")
            total += info.file_size
            if total > limits.max_total_bytes:
                raise UnsafeArchiveError("The archive expands beyond the allowed size.")
            if info.file_size >= limits.ratio_min_bytes and info.file_size > limits.max_ratio * max(1, info.compress_size):
                raise UnsafeArchiveError(f"Entry '{info.filename[:80]}' has a suspicious compression ratio (possible zip bomb).")
            files.append(info)
        # file vs directory prefix collisions (a/b as file and a/b/c)
        names = {str(PurePosixPath(i.filename)).casefold() for i in files}
        for n in names:
            parent = PurePosixPath(n).parent
            while str(parent) not in {".", ""}:
                if str(parent) in names:
                    raise UnsafeArchiveError(f"Entry '{parent}' is both a file and a folder.")
                parent = parent.parent
        return files


def safe_extract_zip(zip_path: Path, dest_dir: Path, limits: ExtractLimits = ExtractLimits()) -> list[Path]:
    """Extract into a new empty folder ``dest_dir`` (created). Atomic: staging then rename."""
    dest_dir = Path(dest_dir)
    if dest_dir.exists():
        raise UnsafeArchiveError("The extraction folder already exists; choose a new folder.")
    files = inspect_zip(zip_path, limits)
    staging = Path(tempfile.mkdtemp(prefix=".aiwb-extract-", dir=str(dest_dir.parent)))
    written: list[Path] = []
    try:
        total = 0
        with zipfile.ZipFile(zip_path) as zf:
            root = staging.resolve()
            for info in files:
                target = (staging / Path(*PurePosixPath(info.filename).parts)).resolve()
                if root not in target.parents:
                    raise UnsafeArchiveError(f"Entry '{info.filename[:80]}' escapes the destination folder.")
                target.parent.mkdir(parents=True, exist_ok=True)
                size = 0
                with zf.open(info) as src, open(target, "xb") as out:
                    while True:
                        chunk = src.read(256 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        total += len(chunk)
                        # Actual bytes, not the (forgeable) header values.
                        if size > max(info.file_size, 0) or size > limits.max_file_bytes or total > limits.max_total_bytes:
                            raise UnsafeArchiveError(f"Entry '{info.filename[:80]}' expands beyond its declared size (possible zip bomb).")
                        out.write(chunk)
                written.append(target.relative_to(root))
        os.replace(staging, dest_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return [dest_dir / p for p in written]
