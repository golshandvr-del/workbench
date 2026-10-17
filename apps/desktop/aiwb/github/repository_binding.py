"""Validated project-to-GitHub repository bindings and safe local-remote checks.

This module has no Tkinter dependency. It never stores credentials or exposes a
raw remote URL in its validation errors. Remote mutation is a separate, explicit
operation chosen by the caller after user confirmation.
"""
from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlsplit

from aiwb.git.service import GitService
from .api_client import GitHubRepository

_ACCOUNT_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$|^[A-Za-z0-9]$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_SCP_REMOTE_RE = re.compile(r"^(?:[^@/:\s]+@)?github\.com:([^/\s]+)/([^/\s]+?)(?:\.git)?$", re.I)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class RepositoryBindingError(RuntimeError):
    """Safe, user-facing project binding error."""


class RemoteConfigurationRequired(RepositoryBindingError):
    """Explicit user decision is needed before changing origin."""
    def __init__(self, kind: str, existing_repository: str | None = None) -> None:
        self.kind = kind
        self.existing_repository = existing_repository
        if kind == "missing":
            message = "This local Git repository has no 'origin' remote. Confirm adding the selected GitHub repository as origin."
        elif existing_repository:
            message = f"The local 'origin' points to {existing_repository}, not the selected repository. Explicit confirmation is required to replace it."
        else:
            message = "The local 'origin' is not a recognized github.com repository. Explicit confirmation is required to replace it."
        super().__init__(message)


@dataclass(frozen=True)
class RepositoryBinding:
    """Versioned link between one Workbench project and a shared Git repository.

    Paths are local to this device. Credentials must never be added to this model.
    Multiple bindings may intentionally share ``repository_id`` when they refer to
    different subdirectories of a Monorepo.
    """
    binding_id: str
    project_path: str
    local_git_root: str
    project_subpath: str
    account_id: str
    repository_id: int
    owner: str
    name: str
    full_name: str
    html_url: str
    default_branch: str
    working_branch: str
    linked_at: str
    workflow_file: str | None = None
    artifact_pattern: str = ""
    release_channel: str = "dev"
    last_known_remote_sha: str | None = None
    last_synced_at: str | None = None
    metadata_refreshed_at: str | None = None
    schema_version: int = 2

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "binding_id": self.binding_id,
            "project_path": self.project_path,
            "local_git_root": self.local_git_root,
            "project_subpath": self.project_subpath,
            "account_id": self.account_id,
            "repository_id": self.repository_id,
            "owner": self.owner,
            "name": self.name,
            "full_name": self.full_name,
            "html_url": self.html_url,
            "default_branch": self.default_branch,
            "working_branch": self.working_branch,
            "linked_at": self.linked_at,
            "workflow_file": self.workflow_file,
            "artifact_pattern": self.artifact_pattern,
            "release_channel": self.release_channel,
            "last_known_remote_sha": self.last_known_remote_sha,
            "last_synced_at": self.last_synced_at,
            "metadata_refreshed_at": self.metadata_refreshed_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "RepositoryBinding | None":
        """Validate schema v1 or v2 and normalize valid records to schema v2."""
        if not isinstance(value, dict):
            return None
        try:
            schema_version = value.get("schema_version", 1)
            if schema_version not in (1, 2):
                return None
            binding_id = value["binding_id"]
            account_id = value["account_id"]
            repository_id = value["repository_id"]
            project_path = value["project_path"]
            git_root = value["local_git_root"]
            subpath = value["project_subpath"]
            owner, name, full_name = value["owner"], value["name"], value["full_name"]
            html_url = value["html_url"]
            default_branch = value["default_branch"]
            working_branch = value["working_branch"]
            linked_at = value["linked_at"]
            if not isinstance(binding_id, str) or not _ACCOUNT_ID_RE.fullmatch(binding_id):
                return None
            if not isinstance(account_id, str) or not _ACCOUNT_ID_RE.fullmatch(account_id):
                return None
            if not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0:
                return None
            if not isinstance(project_path, str) or not Path(project_path).is_absolute():
                return None
            if not isinstance(git_root, str) or not Path(git_root).is_absolute():
                return None
            try:
                project_canonical = Path(project_path).resolve(strict=False)
                git_root_canonical = Path(git_root).resolve(strict=False)
                relative_project = project_canonical.relative_to(git_root_canonical)
            except (OSError, ValueError, RuntimeError):
                return None
            if not isinstance(subpath, str) or len(subpath) > 2048 or "\\" in subpath or "\x00" in subpath:
                return None
            parsed_subpath = PurePosixPath(subpath or ".")
            expected_subpath = relative_project.as_posix() or "."
            if (parsed_subpath.is_absolute() or any(part == ".." or part.casefold() == ".git" for part in parsed_subpath.parts)
                    or parsed_subpath.as_posix() != expected_subpath):
                return None
            if not isinstance(owner, str) or not _OWNER_RE.fullmatch(owner):
                return None
            if not isinstance(name, str) or not _REPO_RE.fullmatch(name) or name in {".", ".."}:
                return None
            if not isinstance(full_name, str) or full_name.casefold() != f"{owner}/{name}".casefold():
                return None
            parts = urlsplit(html_url if isinstance(html_url, str) else "")
            try:
                url_port = parts.port
            except ValueError:
                return None
            if (parts.scheme != "https" or parts.hostname != "github.com" or url_port not in (None, 443)
                    or parts.username or parts.password or parts.query or parts.fragment
                    or parts.path.rstrip("/").casefold() != ("/" + full_name).casefold()):
                return None
            if not _valid_branch(default_branch) or not _valid_branch(working_branch):
                return None
            if not isinstance(linked_at, str) or len(linked_at) > 64:
                return None

            # v1 has no preferences/sync metadata. Normalize it in memory; migration
            # code separately backs up settings before persisting the v2 representation.
            workflow_file = value.get("workflow_file") if schema_version == 2 else None
            artifact_pattern = value.get("artifact_pattern", "") if schema_version == 2 else ""
            release_channel = value.get("release_channel", "dev") if schema_version == 2 else "dev"
            remote_sha = value.get("last_known_remote_sha") if schema_version == 2 else None
            last_synced_at = value.get("last_synced_at") if schema_version == 2 else None
            metadata_refreshed_at = value.get("metadata_refreshed_at") if schema_version == 2 else None
            if workflow_file is not None and not _valid_workflow_file(workflow_file):
                return None
            if not _valid_artifact_pattern(artifact_pattern):
                return None
            if release_channel not in {"dev", "beta", "stable"}:
                return None
            if remote_sha is not None and (not isinstance(remote_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", remote_sha)):
                return None
            for time_value in (last_synced_at, metadata_refreshed_at):
                if time_value is not None and (not isinstance(time_value, str) or len(time_value) > 64 or any(ch in time_value for ch in "\x00\r\n")):
                    return None
            return cls(
                binding_id=binding_id, project_path=str(project_canonical),
                local_git_root=str(git_root_canonical), project_subpath=(subpath or "."),
                account_id=account_id, repository_id=repository_id, owner=owner, name=name,
                full_name=full_name, html_url=html_url, default_branch=default_branch,
                working_branch=working_branch, linked_at=linked_at,
                workflow_file=workflow_file, artifact_pattern=artifact_pattern,
                release_channel=release_channel, last_known_remote_sha=remote_sha,
                last_synced_at=last_synced_at, metadata_refreshed_at=metadata_refreshed_at,
                schema_version=2,
            )
        except (KeyError, ValueError, TypeError, OSError):
            return None


@dataclass(frozen=True)
class BindingMigrationReport:
    records: tuple[dict[str, object], ...]
    migrated_count: int
    invalid_count: int
    duplicate_count: int
    changed: bool


def _valid_workflow_file(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 512 or "\\" in value or "\x00" in value or any(ord(ch) < 32 for ch in value):
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and len(path.parts) >= 3 and path.parts[0] == ".github"
            and path.parts[1] == "workflows" and all(part not in {"", ".", ".."} for part in path.parts)
            and path.suffix.casefold() in {".yml", ".yaml"})


def _valid_artifact_pattern(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 160:
        return False
    if any(ch in value for ch in "\\/\x00\r\n") or any(ord(ch) < 32 for ch in value):
        return False
    return not any(part == ".." for part in value.split("."))


def migrate_binding_records(value: object) -> BindingMigrationReport:
    """Idempotently normalize persisted binding records to schema v2.

    Invalid and duplicate rows are excluded from the active data set, but callers
    must persist a backup of the original settings before saving this result.
    The counts allow UI/reporting to be honest about any discarded entries.
    """
    if not isinstance(value, list):
        invalid = 0 if value in (None, []) else 1
        return BindingMigrationReport((), 0, invalid, 0, bool(invalid))
    rows: list[dict[str, object]] = []
    seen_projects: set[str] = set()
    seen_ids: set[str] = set()
    migrated = invalid = duplicates = 0
    changed = False
    for item in value:
        binding = RepositoryBinding.from_dict(item)
        if binding is None:
            invalid += 1
            changed = True
            continue
        old_version = item.get("schema_version", 1) if isinstance(item, dict) else 1
        old_path = item.get("project_path") if isinstance(item, dict) else None
        if old_version != 2 or (isinstance(item, dict) and any(k not in item for k in ("workflow_file", "artifact_pattern", "release_channel", "last_known_remote_sha", "last_synced_at", "metadata_refreshed_at"))):
            migrated += 1
            changed = True
        key = os.path.normcase(os.path.normpath(binding.project_path)).casefold()
        if key in seen_projects or binding.binding_id in seen_ids:
            duplicates += 1
            changed = True
            continue
        seen_projects.add(key)
        seen_ids.add(binding.binding_id)
        normalized = binding.to_dict()
        if not isinstance(item, dict) or normalized != item:
            changed = True
        rows.append(normalized)
    return BindingMigrationReport(tuple(rows), migrated, invalid, duplicates, changed)


def _valid_branch(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 255:
        return False
    if value.startswith("-") or value.startswith("/") or value.endswith(("/", ".")) or "//" in value or ".." in value or "@{" in value:
        return False
    if any(ch in value for ch in " ~^:?*[\\\x00\r\n"):
        return False
    components = value.split("/")
    if any(not part or part.startswith(".") or part.endswith(".lock") for part in components):
        return False
    return True


def parse_github_remote(remote_url: str) -> tuple[str, str] | None:
    """Parse common GitHub HTTPS/SSH remotes without ever returning credentials."""
    if not isinstance(remote_url, str) or not remote_url or "\x00" in remote_url or "\n" in remote_url or "\r" in remote_url:
        return None
    match = _SCP_REMOTE_RE.fullmatch(remote_url.strip())
    if match:
        owner, name = match.groups()
    else:
        try:
            parts = urlsplit(remote_url.strip())
        except ValueError:
            return None
        host = (parts.hostname or "").casefold()
        if host != "github.com" or parts.query or parts.fragment or parts.scheme.casefold() not in {"https", "ssh"}:
            return None
        path = parts.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        pieces = path.split("/")
        if len(pieces) != 2 or not all(pieces):
            return None
        owner, name = pieces
    if not _OWNER_RE.fullmatch(owner) or not _REPO_RE.fullmatch(name) or name in {".", ".."}:
        return None
    return owner, name


def canonical_repository_url(repository: GitHubRepository | RepositoryBinding | Mapping[str, Any]) -> str:
    if isinstance(repository, Mapping):
        full_name = repository.get("full_name")
        owner = repository.get("owner")
        name = repository.get("name")
        if isinstance(owner, Mapping):
            owner = owner.get("login")
        full_name = full_name if isinstance(full_name, str) else f"{owner}/{name}"
    else:
        full_name = repository.full_name
    if not isinstance(full_name, str) or full_name.count("/") != 1:
        raise RepositoryBindingError("The selected GitHub repository metadata is invalid.")
    owner, name = full_name.split("/", 1)
    if not _OWNER_RE.fullmatch(owner) or not _REPO_RE.fullmatch(name):
        raise RepositoryBindingError("The selected GitHub repository name is invalid.")
    return f"https://github.com/{owner}/{name}.git"


@dataclass(frozen=True)
class RepositoryGitContext:
    project_path: Path
    local_git_root: Path
    project_subpath: str
    current_branch: str
    origin_present: bool
    origin_matches: bool
    existing_remote_repository: str | None
    target_full_name: str
    origin_remote_unrecognized: bool = False
    raw_origin_url: str | None = field(default=None, repr=False, compare=False)


def inspect_local_repository(git_service: GitService, project_path: Path, repository: GitHubRepository) -> RepositoryGitContext:
    path = Path(project_path).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise RepositoryBindingError("The active project path is not a directory.")
    root_result = git_service.run(path, ["rev-parse", "--show-toplevel"])
    if root_result.returncode != 0 or not root_result.stdout.strip():
        raise RepositoryBindingError("The active project is not inside a local Git repository. Initialize or clone a repository before linking it.")
    try:
        root = Path(root_result.stdout.strip()).resolve(strict=True)
        relative = path.relative_to(root)
    except (OSError, ValueError):
        raise RepositoryBindingError("Could not determine the active project's path inside the local Git repository.") from None
    subpath = relative.as_posix() or "."
    if any(part in {"..", ".git"} for part in PurePosixPath(subpath).parts):
        raise RepositoryBindingError("The active project subpath is not valid for a repository binding.")
    branch_result = git_service.run(root, ["branch", "--show-current"])
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    remote_result = git_service.run(root, ["remote", "get-url", "origin"])
    if remote_result.returncode != 0:
        # Distinguish no origin from another Git error without returning raw stderr.
        names_result = git_service.run(root, ["remote"])
        if names_result.returncode != 0:
            raise RepositoryBindingError("Git could not list the local repository remotes.")
        remotes = {line.strip() for line in names_result.stdout.splitlines() if line.strip()}
        if "origin" in remotes:
            raise RepositoryBindingError("Git could not read the local 'origin' remote. Check its configuration and retry.")
        origin_present = False
        remote_identity = None
        recognized = True
    else:
        origin_present = True
        remote_identity = parse_github_remote(remote_result.stdout.strip())
        recognized = remote_identity is not None
    matches = bool(remote_identity and remote_identity[0].casefold() == repository.owner.casefold() and remote_identity[1].casefold() == repository.name.casefold())
    existing_label = f"{remote_identity[0]}/{remote_identity[1]}" if remote_identity else None
    return RepositoryGitContext(
        project_path=path, local_git_root=root, project_subpath=subpath,
        current_branch=branch, origin_present=origin_present, origin_matches=matches,
        existing_remote_repository=existing_label, target_full_name=repository.full_name,
        origin_remote_unrecognized=origin_present and not recognized,
        raw_origin_url=remote_result.stdout.strip() if origin_present and remote_result.returncode == 0 else None,
    )


def configure_origin(git_service: GitService, context: RepositoryGitContext, repository: GitHubRepository, action: str) -> None:
    """Configure origin only after the UI has obtained an explicit user decision."""
    if action not in {"keep", "add", "replace"}:
        raise RepositoryBindingError("Unknown origin configuration action.")
    if context.origin_matches:
        return
    expected_url = canonical_repository_url(repository)
    if not context.origin_present:
        if action != "add":
            raise RemoteConfigurationRequired("missing")
        result = git_service.run(context.local_git_root, ["remote", "add", "origin", expected_url])
    else:
        if action != "replace":
            raise RemoteConfigurationRequired("mismatch", context.existing_remote_repository)
        result = git_service.run(context.local_git_root, ["remote", "set-url", "origin", expected_url])
    if result.returncode != 0:
        raise RepositoryBindingError("Git could not update the 'origin' remote. The project was not linked.")
    verify = git_service.run(context.local_git_root, ["remote", "get-url", "origin"])
    identity = parse_github_remote(verify.stdout.strip()) if verify.returncode == 0 else None
    if identity is None or identity[0].casefold() != repository.owner.casefold() or identity[1].casefold() != repository.name.casefold():
        restored = rollback_origin(git_service, context)
        detail = " The previous origin configuration was restored." if restored else " WARNING: origin rollback could not be confirmed; inspect Git remotes manually."
        raise RepositoryBindingError("Git did not confirm the expected GitHub 'origin'. The project was not linked." + detail)


def rollback_origin(git_service: GitService, context: RepositoryGitContext) -> bool:
    """Best-effort compensation if persisting a just-created binding fails.

    The prior URL remains in memory only for this transaction; it is never logged,
    displayed, or persisted by Workbench.
    """
    try:
        if context.origin_present:
            if not context.raw_origin_url:
                return False
            result = git_service.run(context.local_git_root, ["remote", "set-url", "origin", context.raw_origin_url])
        else:
            result = git_service.run(context.local_git_root, ["remote", "remove", "origin"])
        return result.returncode == 0
    except Exception:
        return False


def make_binding(
    context: RepositoryGitContext,
    account_id: str,
    repository: GitHubRepository,
    *,
    workflow_file: str | None = None,
    artifact_pattern: str = "",
    release_channel: str = "dev",
) -> RepositoryBinding:
    if not _ACCOUNT_ID_RE.fullmatch(account_id):
        raise RepositoryBindingError("The selected GitHub account reference is invalid.")
    branch = context.current_branch if _valid_branch(context.current_branch) else repository.default_branch
    binding = RepositoryBinding(
        binding_id=str(uuid.uuid4()), project_path=str(context.project_path),
        local_git_root=str(context.local_git_root), project_subpath=context.project_subpath,
        account_id=account_id, repository_id=repository.repository_id, owner=repository.owner,
        name=repository.name, full_name=repository.full_name, html_url=repository.html_url,
        default_branch=repository.default_branch, working_branch=branch, linked_at=utc_now_iso(),
        workflow_file=workflow_file, artifact_pattern=artifact_pattern, release_channel=release_channel,
        metadata_refreshed_at=utc_now_iso(),
    )
    if RepositoryBinding.from_dict(binding.to_dict()) is None:
        raise RepositoryBindingError("The project-to-repository binding failed validation and was not saved.")
    return binding


def load_bindings(value: object) -> list[RepositoryBinding]:
    report = migrate_binding_records(value)
    return [binding for row in report.records if (binding := RepositoryBinding.from_dict(row)) is not None]


def update_binding_preferences(
    binding: RepositoryBinding,
    *,
    working_branch: str,
    workflow_file: str | None,
    artifact_pattern: str,
    release_channel: str,
) -> RepositoryBinding:
    if not _valid_branch(working_branch):
        raise RepositoryBindingError("The working branch name is invalid according to Git reference-name rules.")
    if workflow_file == "":
        workflow_file = None
    if workflow_file is not None and not _valid_workflow_file(workflow_file):
        raise RepositoryBindingError("Workflow file must be a repository-relative path under .github/workflows ending in .yml or .yaml.")
    if not _valid_artifact_pattern(artifact_pattern):
        raise RepositoryBindingError("Artifact pattern must be a short name/pattern, not a path or multiline value.")
    if release_channel not in {"dev", "beta", "stable"}:
        raise RepositoryBindingError("Release channel must be dev, beta, or stable.")
    updated = replace(binding, working_branch=working_branch.strip(), workflow_file=workflow_file,
                      artifact_pattern=artifact_pattern.strip(), release_channel=release_channel,
                      schema_version=2)
    if RepositoryBinding.from_dict(updated.to_dict()) is None:
        raise RepositoryBindingError("Updated project binding failed validation.")
    return updated


def refresh_binding_repository_metadata(
    binding: RepositoryBinding, repository: GitHubRepository, *, account_id: str
) -> RepositoryBinding:
    """Refresh mutable owner/name/default-branch metadata by stable numeric ID."""
    if binding.account_id != account_id or binding.repository_id != repository.repository_id:
        raise RepositoryBindingError("Repository metadata does not match this binding's account and numeric repository ID.")
    old_default = binding.default_branch
    working_branch = repository.default_branch if binding.working_branch == old_default else binding.working_branch
    updated = replace(
        binding, owner=repository.owner, name=repository.name, full_name=repository.full_name,
        html_url=repository.html_url, default_branch=repository.default_branch,
        working_branch=working_branch, metadata_refreshed_at=utc_now_iso(), schema_version=2,
    )
    if RepositoryBinding.from_dict(updated.to_dict()) is None:
        raise RepositoryBindingError("Refreshed GitHub repository metadata failed validation.")
    return updated


def classify_scoped_paths(project_subpath: str, paths: list[str] | tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split root-relative Git paths into project scope and outside-scope paths."""
    scope = PurePosixPath(project_subpath or ".")
    if scope.is_absolute() or any(part == ".." or part.casefold() == ".git" for part in scope.parts):
        raise RepositoryBindingError("Project subpath is invalid.")
    scope_text = scope.as_posix()
    inside: list[str] = []
    outside: list[str] = []
    for raw in paths:
        if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
            outside.append(str(raw))
            continue
        path = PurePosixPath(raw)
        if path.is_absolute() or any(part in {"..", ".git"} for part in path.parts):
            outside.append(raw)
        elif scope_text == "." or raw == scope_text or raw.startswith(scope_text.rstrip("/") + "/"):
            inside.append(raw)
        else:
            outside.append(raw)
    return tuple(inside), tuple(outside)


@dataclass(frozen=True)
class InitialPushFile:
    path: str
    status: str
    size_bytes: int | None
    in_project_scope: bool
    sensitive_path: bool
    large_file: bool
    secret_signature: bool


@dataclass(frozen=True)
class InitialPushReview:
    git_root: str
    project_subpath: str
    branch: str
    files: tuple[InitialPushFile, ...]
    proposed_gitignore_entries: tuple[str, ...]
    gitignore_path: str
    gitignore_exists: bool
    warning_count: int


def _path_looks_sensitive(path: str) -> bool:
    parts = [part.casefold() for part in PurePosixPath(path).parts]
    basename = parts[-1] if parts else ""
    if basename in {".env", ".env.local", ".env.production", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}:
        return True
    if basename.endswith((".pem", ".p12", ".pfx", ".key", ".keystore")):
        return True
    if any(part in {"secrets", "credentials", "private_keys"} for part in parts):
        return True
    return bool(re.search(r"(?i)(^|[._-])(secret|token|credential|password)([._-]|$)", basename))


def _file_contains_secret_signature(path: Path, *, scan_limit_bytes: int = 1024 * 1024) -> bool:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > scan_limit_bytes:
            return False
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return False
    patterns = (
        r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[^\s'\"]{12,}",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def build_initial_push_review(
    git_service: GitService, git_root: Path, project_subpath: str, *, large_file_bytes: int = 10 * 1024 * 1024
) -> InitialPushReview:
    """Audit files likely to be included in an initial push; this is advice, not a guarantee."""
    root = Path(git_root).expanduser().resolve(strict=True)
    inside = git_service.run(root, ["rev-parse", "--show-toplevel"])
    if inside.returncode != 0 or Path(inside.stdout.strip()).resolve(strict=True) != root:
        raise RepositoryBindingError("The configured Git root no longer points to the root of this local repository.")
    branch_result = git_service.run(root, ["branch", "--show-current"])
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "(unknown)"
    status = git_service.status_snapshot(root)
    if not status.is_repo:
        raise RepositoryBindingError("The configured Git root is not a Git repository.")
    status_by_path = {entry.path: entry.status for entry in status.entries}
    listed = git_service.run(root, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    if listed.returncode != 0:
        raise RepositoryBindingError("Git could not enumerate files for the initial-push review.")
    candidates = sorted({part for part in listed.stdout.split("\x00") if part})
    inside_paths, outside_paths = classify_scoped_paths(project_subpath, candidates)
    outside_set = set(outside_paths)
    files: list[InitialPushFile] = []
    proposed: set[str] = set()
    for name in candidates:
        path = root.joinpath(*PurePosixPath(name).parts)
        try:
            size = path.stat().st_size if path.exists() and path.is_file() and not path.is_symlink() else None
        except OSError:
            size = None
        sensitive = _path_looks_sensitive(name)
        large = size is not None and size >= large_file_bytes
        secret = _file_contains_secret_signature(path) if size is not None and size <= 1024 * 1024 else False
        files.append(InitialPushFile(name, status_by_path.get(name, "tracked/committed"), size,
                                     name not in outside_set, sensitive, large, secret))
        if sensitive:
            base = PurePosixPath(name).name.casefold()
            if base.startswith(".env"):
                proposed.add(".env*")
            elif base.endswith((".pem", ".p12", ".pfx", ".key", ".keystore")) or base in {"id_rsa", "id_ed25519"}:
                proposed.add("*." + base.rsplit(".", 1)[-1] if "." in base else base)
            elif "secret" in base or "credential" in base or "token" in base or "password" in base:
                proposed.add("*" + base + "*")
    common_candidates = (".env", ".env.*", "*.pem", "*.p12", "*.pfx", "*.key", ".venv/", "venv/", "__pycache__/", "node_modules/", "dist/", "build/")
    proposed.update(common_candidates)
    ignore_path = Path(root.joinpath(*PurePosixPath(project_subpath or ".").parts)) / ".gitignore"
    if project_subpath == ".":
        ignore_path = root / ".gitignore"
    warnings = sum(1 for item in files if item.sensitive_path or item.large_file or item.secret_signature)
    return InitialPushReview(str(root), project_subpath or ".", branch, tuple(files), tuple(sorted(proposed)),
                             str(ignore_path), ignore_path.exists(), warnings)


def upsert_binding(value: object, binding: RepositoryBinding) -> list[dict[str, object]]:
    records = load_bindings(value)
    key = os.path.normcase(os.path.normpath(binding.project_path)).casefold()
    out = [item for item in records if os.path.normcase(os.path.normpath(item.project_path)).casefold() != key]
    out.append(binding)
    return [item.to_dict() for item in out]


def remove_binding(value: object, project_path: Path) -> list[dict[str, object]]:
    key = os.path.normcase(os.path.normpath(str(Path(project_path).resolve()))).casefold()
    return [item.to_dict() for item in load_bindings(value) if os.path.normcase(os.path.normpath(item.project_path)).casefold() != key]


def find_binding(value: object, project_path: Path) -> RepositoryBinding | None:
    key = os.path.normcase(os.path.normpath(str(Path(project_path).resolve()))).casefold()
    return next((item for item in load_bindings(value) if os.path.normcase(os.path.normpath(item.project_path)).casefold() == key), None)
