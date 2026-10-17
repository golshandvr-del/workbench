"""Safe metadata registry and lifecycle for GitHub PAT accounts."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping

from .api_client import GitHubApiClient, GitHubApiError, GitHubUser
from .credential_store import CredentialStore, CredentialStoreError
from .redaction import validate_pat

ACCOUNT_SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class GitHubAccount:
    account_id: str
    github_user_id: int
    login: str
    avatar_url: str | None
    html_url: str | None
    auth_method: str
    token_format: str
    credential_ref: str
    connection_status: str
    last_verified_at: str | None
    capability_snapshot: Mapping[str, str] = field(default_factory=dict)
    last_error_category: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Safe settings representation. The PAT itself is structurally impossible here."""
        return {
            "account_id": self.account_id,
            "github_user_id": self.github_user_id,
            "login": self.login,
            "avatar_url": self.avatar_url,
            "html_url": self.html_url,
            "auth_method": self.auth_method,
            "token_format": self.token_format,
            "credential_ref": self.credential_ref,
            "connection_status": self.connection_status,
            "last_verified_at": self.last_verified_at,
            "capability_snapshot": dict(self.capability_snapshot),
            "last_error_category": self.last_error_category,
        }


def _token_format(token: str) -> str:
    if token.startswith("github_pat_"):
        return "fine_grained_pat"
    if token.startswith("ghp_"):
        return "classic_pat"
    return "personal_access_token"


def _safe_account_from_data(item: object) -> GitHubAccount | None:
    if not isinstance(item, dict):
        return None
    try:
        account_id = str(item["account_id"])
        uuid.UUID(account_id)
        user_id = item["github_user_id"]
        login = item["login"]
        credential_ref = str(item["credential_ref"])
        if credential_ref.startswith("github-api:"):
            reference_uuid = credential_ref.partition(":")[2]
            if str(uuid.UUID(reference_uuid)) != reference_uuid:
                return None
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            return None
        if not isinstance(login, str) or not login.strip() or len(login) > 100:
            return None
        if not credential_ref.startswith("github-api:") or not credential_ref.partition(":")[2]:
            return None
        status = item.get("connection_status", "Not verified")
        if not isinstance(status, str) or len(status) > 80:
            status = "Not verified"
        capabilities = item.get("capability_snapshot", {})
        if not isinstance(capabilities, dict):
            capabilities = {}
        safe_capabilities: dict[str, str] = {}
        allowed = {"identity", "repository_read", "repository_write", "actions_read", "workflow_dispatch", "artifact_download", "release_write"}
        for key, value in capabilities.items():
            if key in allowed and isinstance(value, str) and value in {"available", "not_checked", "available_read_only", "not_available", "requires_approval"}:
                safe_capabilities[key] = value
        def safe_url(value: object, *, github_only: bool = False) -> str | None:
            if not isinstance(value, str) or len(value) > 2048 or not value.startswith("https://"):
                return None
            if github_only and "github.com/" not in value:
                return None
            return value
        last_verified = item.get("last_verified_at")
        if not isinstance(last_verified, str) or len(last_verified) > 64:
            last_verified = None
        last_error = item.get("last_error_category")
        if not isinstance(last_error, str) or len(last_error) > 64:
            last_error = None
        auth_method = "pat"  # Do not honor serialized providers not implemented in this release.
        token_format = item.get("token_format", "personal_access_token")
        if token_format not in {"fine_grained_pat", "classic_pat", "personal_access_token"}:
            token_format = "personal_access_token"
        return GitHubAccount(
            account_id=account_id, github_user_id=user_id, login=login.strip(),
            avatar_url=safe_url(item.get("avatar_url")), html_url=safe_url(item.get("html_url"), github_only=True),
            auth_method=auth_method, token_format=token_format, credential_ref=credential_ref,
            connection_status=status, last_verified_at=last_verified,
            capability_snapshot=safe_capabilities, last_error_category=last_error,
        )
    except (KeyError, ValueError, TypeError, AttributeError):
        return None


class GitHubAccountError(RuntimeError):
    """Safe account lifecycle error suitable for UI display."""


LoadAccounts = Callable[[], object]
SaveAccounts = Callable[[list[dict[str, object]]], bool]


class GitHubAccountService:
    """Manages non-secret account metadata and references to OS credentials."""
    def __init__(
        self,
        credential_store: CredentialStore,
        api_client: GitHubApiClient,
        load_accounts: LoadAccounts,
        save_accounts: SaveAccounts,
    ) -> None:
        self.credential_store = credential_store
        self.api_client = api_client
        self._load = load_accounts
        self._save = save_accounts

    def list_accounts(self) -> list[GitHubAccount]:
        raw = self._load()
        if not isinstance(raw, list):
            return []
        seen_ids: set[str] = set()
        seen_refs: set[str] = set()
        accounts: list[GitHubAccount] = []
        for item in raw:
            account = _safe_account_from_data(item)
            if account is None or account.account_id in seen_ids or account.credential_ref in seen_refs:
                continue
            seen_ids.add(account.account_id)
            seen_refs.add(account.credential_ref)
            accounts.append(account)
        return accounts

    def _save_list(self, accounts: Iterable[GitHubAccount]) -> None:
        data = [account.to_dict() for account in accounts]
        # Defensive assertion: this serialization path must never contain a known credential field.
        forbidden = {"token", "pat", "secret", "access_token", "password", "authorization"}
        if any(forbidden.intersection({str(k).casefold() for k in row}) for row in data):
            raise GitHubAccountError("Internal account metadata contained a forbidden secret field; nothing was saved.")
        try:
            ok = self._save(data)
        except Exception:
            ok = False
        if not ok:
            raise GitHubAccountError("Could not persist GitHub account metadata. No project files were changed.")

    @staticmethod
    def _verified_account(
        *, account_id: str, user: GitHubUser, credential_ref: str, token: str, capability_snapshot: Mapping[str, str],
        prior: GitHubAccount | None = None,
    ) -> GitHubAccount:
        return GitHubAccount(
            account_id=account_id, github_user_id=user.github_user_id, login=user.login,
            avatar_url=user.avatar_url, html_url=user.html_url, auth_method="pat", token_format=_token_format(token),
            credential_ref=credential_ref, connection_status="Connected", last_verified_at=utc_now_iso(),
            capability_snapshot=dict(capability_snapshot), last_error_category=None,
        )

    def add_pat(self, token: str) -> GitHubAccount:
        try:
            pat = validate_pat(token)
        except ValueError as exc:
            raise GitHubAccountError(str(exc)) from None
        try:
            user, capability = self.api_client.get_authenticated_user(pat)
        except GitHubApiError:
            raise
        accounts = self.list_accounts()
        if any(account.github_user_id == user.github_user_id for account in accounts):
            raise GitHubAccountError(f"The GitHub account @{user.login} is already connected. Use Test Connection or Replace Credential instead.")
        account_id = str(uuid.uuid4())
        credential_ref = "github-api:" + str(uuid.uuid4())
        try:
            self.credential_store.set_secret(credential_ref, pat)
        except CredentialStoreError as exc:
            raise GitHubAccountError(str(exc)) from None
        account = self._verified_account(account_id=account_id, user=user, credential_ref=credential_ref, token=pat, capability_snapshot=capability)
        try:
            self._save_list([*accounts, account])
        except Exception:
            try:
                self.credential_store.delete_secret(credential_ref)
            except CredentialStoreError:
                pass
            raise
        return account

    def replace_pat(self, account_id: str, token: str) -> GitHubAccount:
        try:
            pat = validate_pat(token)
        except ValueError as exc:
            raise GitHubAccountError(str(exc)) from None
        accounts = self.list_accounts()
        prior = next((item for item in accounts if item.account_id == account_id), None)
        if prior is None:
            raise GitHubAccountError("The selected GitHub account no longer exists. Refresh the account list.")
        try:
            user, capability = self.api_client.get_authenticated_user(pat)
        except GitHubApiError:
            raise
        if user.github_user_id != prior.github_user_id:
            raise GitHubAccountError("The new token belongs to a different GitHub account. Disconnect that account separately or use its own account entry.")
        new_ref = "github-api:" + str(uuid.uuid4())
        try:
            self.credential_store.set_secret(new_ref, pat)
        except CredentialStoreError as exc:
            raise GitHubAccountError(str(exc)) from None
        updated = self._verified_account(account_id=prior.account_id, user=user, credential_ref=new_ref, token=pat, capability_snapshot=capability, prior=prior)
        replacement = [updated if item.account_id == account_id else item for item in accounts]
        try:
            self._save_list(replacement)
        except Exception:
            try:
                self.credential_store.delete_secret(new_ref)
            except CredentialStoreError:
                pass
            raise
        cleanup_warning = False
        try:
            self.credential_store.delete_secret(prior.credential_ref)
        except CredentialStoreError:
            cleanup_warning = True
        if cleanup_warning:
            # The old unreferenced entry is inaccessible to Workbench, but tell the user to check Windows Credential Manager.
            updated = GitHubAccount(**{**updated.__dict__, "last_error_category": "old_credential_cleanup_failed"})
            try:
                self._save_list([updated if item.account_id == account_id else item for item in replacement])
            except Exception:
                pass
        return updated

    def record_capability(self, account_id: str, capability: str, status: str) -> GitHubAccount:
        """Persist a narrowly evidenced capability result from a successful/denied API call."""
        allowed_capabilities = {"identity", "repository_read", "repository_write", "actions_read", "workflow_dispatch", "artifact_download", "release_write"}
        allowed_statuses = {"available", "not_checked", "available_read_only", "not_available", "requires_approval"}
        if capability not in allowed_capabilities or status not in allowed_statuses:
            raise GitHubAccountError("The capability result is not recognized and was not saved.")
        accounts = self.list_accounts()
        prior = next((item for item in accounts if item.account_id == account_id), None)
        if prior is None:
            raise GitHubAccountError("The selected GitHub account no longer exists. Refresh the account list.")
        snapshot = dict(prior.capability_snapshot)
        snapshot[capability] = status
        updated = GitHubAccount(**{**prior.__dict__, "capability_snapshot": snapshot})
        self._save_list([updated if item.account_id == account_id else item for item in accounts])
        return updated

    def get_api_token(self, account_id: str) -> str:
        """Retrieve an account's API token for an immediate service call.

        The token is returned only to the caller and must never be placed in UI
        state, settings, a URL, a Git command, or a diagnostic message.
        """
        account = next((item for item in self.list_accounts() if item.account_id == account_id), None)
        if account is None:
            raise GitHubAccountError("The selected GitHub account no longer exists. Refresh the account list.")
        try:
            return self.credential_store.get_secret(account.credential_ref)
        except CredentialStoreError as exc:
            self._update_status(self.list_accounts(), account, "Needs re-authentication", "credential_missing")
            raise GitHubAccountError(str(exc)) from None

    def test_connection(self, account_id: str) -> GitHubAccount:
        accounts = self.list_accounts()
        account = next((item for item in accounts if item.account_id == account_id), None)
        if account is None:
            raise GitHubAccountError("The selected GitHub account no longer exists. Refresh the account list.")
        try:
            token = self.credential_store.get_secret(account.credential_ref)
        except CredentialStoreError as exc:
            self._update_status(accounts, account, "Needs re-authentication", "credential_missing")
            raise GitHubAccountError(str(exc)) from None
        try:
            user, capability = self.api_client.get_authenticated_user(token)
        except GitHubApiError as exc:
            self._update_status(accounts, account, exc.account_status, exc.category)
            raise
        if user.github_user_id != account.github_user_id:
            self._update_status(accounts, account, "Identity mismatch", "identity_mismatch")
            raise GitHubAccountError("The credential now resolves to a different GitHub account ID. Replace the credential only after verifying the selected account.")
        updated = self._verified_account(
            account_id=account.account_id, user=user, credential_ref=account.credential_ref,
            token=token, capability_snapshot=capability, prior=account,
        )
        self._save_list([updated if item.account_id == account_id else item for item in accounts])
        return updated

    def _update_status(self, accounts: list[GitHubAccount], account: GitHubAccount, status: str, category: str) -> None:
        updated = GitHubAccount(**{**account.__dict__, "connection_status": status, "last_error_category": category})
        try:
            self._save_list([updated if item.account_id == account.account_id else item for item in accounts])
        except GitHubAccountError:
            # Do not mask the actual authentication/network failure with a secondary settings-save failure.
            pass

    def refresh_all(self) -> list[tuple[GitHubAccount, str | None]]:
        results: list[tuple[GitHubAccount, str | None]] = []
        for account in self.list_accounts():
            try:
                updated = self.test_connection(account.account_id)
                results.append((updated, None))
            except (GitHubApiError, GitHubAccountError) as exc:
                refreshed = next((a for a in self.list_accounts() if a.account_id == account.account_id), account)
                results.append((refreshed, str(exc)))
        return results

    def disconnect(self, account_id: str) -> bool:
        accounts = self.list_accounts()
        account = next((item for item in accounts if item.account_id == account_id), None)
        if account is None:
            return False
        # Remove the reference from durable app settings first. Never touch local Git repositories or project files.
        self._save_list([item for item in accounts if item.account_id != account_id])
        try:
            self.credential_store.delete_secret(account.credential_ref)
            return True
        except CredentialStoreError:
            # Metadata is disconnected. True would falsely claim secret cleanup succeeded.
            return False
