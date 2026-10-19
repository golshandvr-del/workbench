"""Small, injectable GitHub REST API client with safe failure categories.

Only a caller-supplied PAT is used; this module does not persist credentials or
perform Git transport. Response bodies and headers are never included verbatim in
exceptions, logs, or UI messages.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.parse import urlencode, urlsplit

from .redaction import validate_pat

GITHUB_API_VERSION = "2026-03-10"
MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class GitHubUser:
    github_user_id: int
    login: str
    avatar_url: str | None
    html_url: str | None


@dataclass(frozen=True)
class GitHubRepository:
    """Validated, credential-free metadata for a repository visible to the account."""
    repository_id: int
    owner: str
    name: str
    full_name: str
    private: bool
    fork: bool
    archived: bool
    default_branch: str
    updated_at: str | None
    description: str | None
    html_url: str
    can_push: bool | None = None

    @property
    def visibility(self) -> str:
        return "Private" if self.private else "Public"


@dataclass(frozen=True)
class RepositoryListing:
    repositories: tuple[GitHubRepository, ...]
    pages_loaded: int
    truncated: bool = False


class GitHubApiError(RuntimeError):
    """Categorized, secret-safe GitHub API failure."""
    def __init__(
        self,
        category: str,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds

    @property
    def account_status(self) -> str:
        return {
            "authentication": "Needs re-authentication",
            "permission_or_policy": "Permission / policy issue",
            "rate_limit": "Rate limited",
            "network": "Connection error",
            "timeout": "Connection error",
            "not_found": "Connection error",
            "server": "Connection error",
            "invalid_response": "Connection error",
            "credential_missing": "Needs re-authentication",
        }.get(self.category, "Connection error")


Transport = Callable[[str, Mapping[str, str], float], HttpResponse]


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward a credential-bearing API request to a redirect target."""
    def redirect_request(self, req: object, fp: object, code: int, msg: str, headers: object, newurl: str) -> None:  # type: ignore[override]
        return None


def _urllib_get(url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        opener = urllib.request.build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            return HttpResponse(int(response.status), dict(response.headers.items()), body)
    except urllib.error.HTTPError as exc:
        # HTTP errors are responses and should be classified by status/headers.
        try:
            body = exc.read(MAX_RESPONSE_BYTES + 1)
        except Exception:
            body = b""
        return HttpResponse(int(exc.code), dict(exc.headers.items()) if exc.headers else {}, body)


def _safe_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        parsed = int(str(value).strip())
        return parsed if parsed >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


class GitHubApiClient:
    def __init__(
        self,
        *,
        transport: Transport | None = None,
        base_url: str = "https://api.github.com",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = "AI-Workbench/2.7.0",
        api_version: str = GITHUB_API_VERSION,
    ) -> None:
        parts = urlsplit(base_url)
        try:
            port = parts.port
        except ValueError:
            raise ValueError("GitHub API base URL contains an invalid port.") from None
        if parts.scheme.lower() != "https" or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("GitHub API base URL must be an HTTPS URL without credentials, query, or fragment.")
        # Production requests carry a bearer token. In this release they may only go
        # to GitHub.com; a custom HTTPS URL is accepted solely with an explicitly
        # injected transport (used by tests), never by the real network transport.
        # This prevents accidental PAT disclosure to a typo, hostile host, or proxy URL.
        if transport is None and (
            (parts.hostname or "").casefold() != "api.github.com"
            or port not in (None, 443)
            or parts.path not in ("", "/")
        ):
            raise ValueError("Production PAT requests must target https://api.github.com only.")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not (1 <= timeout_seconds <= 60):
            raise ValueError("GitHub API timeout must be between 1 and 60 seconds.")
        if not user_agent.strip() or len(user_agent) > 120:
            raise ValueError("A short User-Agent is required for GitHub API requests.")
        if not api_version or len(api_version) > 32:
            raise ValueError("A valid GitHub REST API version is required.")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.user_agent = user_agent
        self.api_version = api_version
        self._transport = transport or _urllib_get

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str | None:
        wanted = name.casefold()
        for key, value in headers.items():
            if str(key).casefold() == wanted:
                return str(value)
        return None

    def _request_response(self, token: str, path_and_query: str, *, endpoint_label: str) -> HttpResponse:
        """Issue one authenticated GET with centralized safe transport/error handling.

        Callers may construct the path/query, but not the host. Production URLs are
        always rooted at the constructor-validated api.github.com origin.
        """
        pat = validate_pat(token)
        if not path_and_query.startswith("/") or path_and_query.startswith("//") or "\\" in path_and_query or "\x00" in path_and_query:
            raise GitHubApiError("request", "The GitHub API request path is invalid.")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {pat}",
            "X-GitHub-Api-Version": self.api_version,
            "User-Agent": self.user_agent,
        }
        try:
            response = self._transport(self.base_url + path_and_query, headers, self.timeout_seconds)
        except (TimeoutError, socket.timeout):
            raise GitHubApiError("timeout", "The GitHub API request timed out. Check your connection and retry.") from None
        except urllib.error.URLError as exc:
            reason_name = type(getattr(exc, "reason", None)).__name__.casefold()
            if "timeout" in reason_name:
                raise GitHubApiError("timeout", "The GitHub API request timed out. Check your connection and retry.") from None
            raise GitHubApiError("network", "Could not reach GitHub. Check the network/proxy and retry.") from None
        except OSError:
            raise GitHubApiError("network", "Could not reach GitHub. Check the network/proxy and retry.") from None
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            name = type(exc).__name__.casefold()
            category = "timeout" if "timeout" in name else "network"
            message = "The GitHub API request timed out. Check your connection and retry." if category == "timeout" else "Could not reach GitHub. Check the network/proxy and retry."
            raise GitHubApiError(category, message) from None

        if not isinstance(response, HttpResponse):
            raise GitHubApiError("invalid_response", "The GitHub API returned an invalid transport response.")
        if len(response.body) > MAX_RESPONSE_BYTES:
            raise GitHubApiError("invalid_response", "The GitHub API response exceeded the permitted size.", status_code=response.status)
        normalized_headers = {str(k).casefold(): str(v) for k, v in response.headers.items()}
        status = response.status
        if status == 401:
            raise GitHubApiError("authentication", "GitHub rejected this token (HTTP 401). Replace the credential with a valid PAT.", status_code=status)
        if status == 403:
            retry_after = _safe_int(normalized_headers.get("retry-after"))
            remaining = normalized_headers.get("x-ratelimit-remaining")
            body_text = response.body[:8192].decode("utf-8", errors="replace").casefold()
            rate_limited = remaining == "0" or retry_after is not None or "rate limit" in body_text
            if rate_limited:
                reset_epoch = _safe_int(normalized_headers.get("x-ratelimit-reset"))
                if retry_after is None and reset_epoch is not None:
                    retry_after = max(0, reset_epoch - int(time.time()))
                wait_text = f" Try again in about {retry_after} second(s)." if retry_after is not None else " Wait for the rate-limit reset, then retry."
                raise GitHubApiError("rate_limit", "GitHub rate-limited this request." + wait_text, status_code=status, retry_after_seconds=retry_after)
            raise GitHubApiError("permission_or_policy", "GitHub denied this request (HTTP 403). Check token access and organization policy.", status_code=status)
        if status == 404:
            message = "GitHub did not return the requested resource (HTTP 404). It may not be visible to this account." if endpoint_label != "authenticated-user" else "GitHub did not return the authenticated-user endpoint (HTTP 404). Check network/proxy configuration."
            raise GitHubApiError("not_found", message, status_code=status)
        if status == 429:
            retry_after = _safe_int(normalized_headers.get("retry-after"))
            wait_text = f" Try again in about {retry_after} second(s)." if retry_after is not None else " Wait, then retry."
            raise GitHubApiError("rate_limit", "GitHub rate-limited this request (HTTP 429)." + wait_text, status_code=status, retry_after_seconds=retry_after)
        if status >= 500:
            raise GitHubApiError("server", f"GitHub returned a server error (HTTP {status}). Retry later.", status_code=status)
        if status < 200 or status >= 300:
            raise GitHubApiError("request", f"GitHub rejected the request (HTTP {status}). Check the token and try again.", status_code=status)
        return response

    @staticmethod
    def _decode_json(response: HttpResponse, *, expected_type: type, resource_label: str) -> object:
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GitHubApiError("invalid_response", f"GitHub returned a response that was not valid JSON for {resource_label}.", status_code=response.status) from None
        if not isinstance(payload, expected_type):
            raise GitHubApiError("invalid_response", f"GitHub returned an unexpected {resource_label} response format.", status_code=response.status)
        return payload

    def list_repositories(
        self, token: str, *, per_page: int = 100, max_pages: int = 100,
    ) -> RepositoryListing:
        """Load all repositories visible through GET /user/repos, following pages.

        Repository filtering/search is local so a search does not silently omit a
        match merely because it resides on a later API page. A 10,000-repository
        safety ceiling prevents unbounded API requests; ``truncated`` flags that cap.
        """
        pat = validate_pat(token)
        if not isinstance(per_page, int) or isinstance(per_page, bool) or not 1 <= per_page <= 100:
            raise ValueError("per_page must be an integer between 1 and 100.")
        if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= 100:
            raise ValueError("max_pages must be an integer between 1 and 100.")
        repositories: list[GitHubRepository] = []
        seen_ids: set[int] = set()
        pages_loaded = 0
        truncated = False
        for page in range(1, max_pages + 1):
            query = urlencode({
                "visibility": "all",
                "affiliation": "owner,collaborator,organization_member",
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
            })
            response = self._request_response(pat, "/user/repos?" + query, endpoint_label="repositories")
            payload = self._decode_json(response, expected_type=list, resource_label="repository list")
            if len(payload) > per_page:
                raise GitHubApiError("invalid_response", "GitHub returned more repositories than the requested page size.", status_code=response.status)
            pages_loaded += 1
            for raw in payload:
                repository = self._parse_repository(raw, status_code=response.status)
                if repository.repository_id not in seen_ids:
                    seen_ids.add(repository.repository_id)
                    repositories.append(repository)
            if len(payload) < per_page:
                break
            if page == max_pages:
                truncated = True
        return RepositoryListing(tuple(repositories), pages_loaded, truncated)

    @staticmethod
    def _parse_repository(raw: object, *, status_code: int | None = None) -> GitHubRepository:
        if not isinstance(raw, dict):
            raise GitHubApiError("invalid_response", "GitHub returned a repository entry with an invalid structure.", status_code=status_code)
        repository_id = raw.get("id")
        full_name = raw.get("full_name")
        name = raw.get("name")
        archived, fork, private = raw.get("archived"), raw.get("fork"), raw.get("private")
        owner_data = raw.get("owner")
        owner = owner_data.get("login") if isinstance(owner_data, dict) else None
        default_branch = raw.get("default_branch")
        html_url = raw.get("html_url")
        if (not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0
                or not isinstance(owner, str) or not owner.strip() or len(owner) > 100
                or not isinstance(name, str) or not name.strip() or len(name) > 100
                or not isinstance(full_name, str) or full_name.casefold() != f"{owner}/{name}".casefold()
                or not isinstance(private, bool) or not isinstance(fork, bool) or not isinstance(archived, bool)
                or not isinstance(default_branch, str) or not default_branch.strip() or len(default_branch) > 255
                or any(ch in default_branch for ch in "\x00\r\n")
                or not isinstance(html_url, str)):
            raise GitHubApiError("invalid_response", "GitHub returned repository metadata that failed validation.", status_code=status_code)
        parts = urlsplit(html_url)
        if parts.scheme != "https" or (parts.hostname or "").casefold() not in {"github.com", "www.github.com"} or parts.username or parts.password or parts.query or parts.fragment or parts.path.rstrip("/").casefold() != ("/" + full_name).casefold():
            raise GitHubApiError("invalid_response", "GitHub returned an unexpected repository URL.", status_code=status_code)
        description = raw.get("description")
        if not isinstance(description, str):
            description = None
        if description is not None:
            description = description[:2000]
        updated = raw.get("updated_at")
        if not isinstance(updated, str) or len(updated) > 64:
            updated = None
        permissions = raw.get("permissions")
        can_push: bool | None = None
        if isinstance(permissions, dict) and isinstance(permissions.get("push"), bool):
            can_push = permissions["push"]
        return GitHubRepository(
            repository_id=repository_id, owner=owner.strip(), name=name.strip(), full_name=full_name.strip(),
            private=private, fork=fork, archived=archived, default_branch=default_branch.strip(),
            updated_at=updated, description=description, html_url=html_url, can_push=can_push,
        )

    def get_authenticated_user(self, token: str) -> tuple[GitHubUser, dict[str, str]]:
        pat = validate_pat(token)
        response = self._request_response(pat, "/user", endpoint_label="authenticated-user")
        status = response.status

        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GitHubApiError("invalid_response", "GitHub returned a response that was not valid JSON.", status_code=status) from None
        if not isinstance(payload, dict):
            raise GitHubApiError("invalid_response", "GitHub returned an unexpected user response format.", status_code=status)
        user_id = payload.get("id")
        login = payload.get("login")
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0 or not isinstance(login, str) or not login.strip() or len(login) > 100:
            raise GitHubApiError("invalid_response", "GitHub's response did not contain a valid account ID and login.", status_code=status)
        avatar_url = payload.get("avatar_url") if isinstance(payload.get("avatar_url"), str) else None
        html_url = payload.get("html_url") if isinstance(payload.get("html_url"), str) else None
        # Keep metadata URLs constrained to HTTPS before persisting them for display.
        if avatar_url:
            avatar_parts = urlsplit(avatar_url)
            if avatar_parts.scheme != "https" or not avatar_parts.hostname or avatar_parts.username or avatar_parts.password or not (avatar_parts.hostname.casefold() == "github.com" or avatar_parts.hostname.casefold().endswith(".githubusercontent.com")):
                avatar_url = None
        if html_url:
            html_parts = urlsplit(html_url)
            if html_parts.scheme != "https" or html_parts.hostname is None or html_parts.hostname.casefold() not in {"github.com", "www.github.com"} or html_parts.username or html_parts.password:
                html_url = None
        user = GitHubUser(user_id, login.strip(), avatar_url, html_url)
        # An authenticated identity is not evidence of access to repos, Actions, or releases.
        capabilities = {
            "identity": "available",
            "repository_read": "not_checked",
            "repository_write": "not_checked",
            "actions_read": "not_checked",
            "workflow_dispatch": "not_checked",
            "artifact_download": "not_checked",
            "release_write": "not_checked",
        }
        return user, capabilities
