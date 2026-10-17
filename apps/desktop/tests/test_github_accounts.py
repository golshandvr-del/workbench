"""Unit and lifecycle tests for v1.14.2 GitHub PAT account management."""
from __future__ import annotations

import unittest
import uuid
from typing import Any

from aiwb.github.accounts import GitHubAccountService
from aiwb.github.api_client import GitHubApiClient, GitHubApiError, GitHubUser, HttpResponse
from aiwb.github.credential_store import (
    CredentialStoreError, MemoryCredentialStore, UnsupportedCredentialStore,
    WindowsCredentialStore, create_default_credential_store,
)
from aiwb.github.redaction import redact_github_text, validate_pat

TOKEN_A = "github_pat_" + "A" * 40
TOKEN_B = "github_pat_" + "B" * 40
TOKEN_BAD = "github_pat_" + "Z" * 40


def response(status: int = 200, *, login: str = "octocat", user_id: int = 583231, headers: dict[str, str] | None = None, body: bytes | None = None) -> HttpResponse:
    if body is None:
        import json
        body = json.dumps({"id": user_id, "login": login, "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4", "html_url": f"https://github.com/{login}"}).encode()
    return HttpResponse(status, headers or {}, body)


class QueueTransport:
    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.calls: list[tuple[str, dict[str, str], float]] = []

    def __call__(self, url: str, headers: Any, timeout: float) -> HttpResponse:
        self.calls.append((url, dict(headers), timeout))
        if not self.items:
            raise AssertionError("No fake transport response queued")
        result = self.items.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class CredentialStoreTests(unittest.TestCase):
    def test_memory_store_set_get_delete(self) -> None:
        store = MemoryCredentialStore()
        ref = "github-api:" + str(uuid.uuid4())
        store.set_secret(ref, TOKEN_A)
        self.assertEqual(store.get_secret(ref), TOKEN_A)
        store.delete_secret(ref)
        with self.assertRaisesRegex(CredentialStoreError, "missing"):
            store.get_secret(ref)

    def test_rejects_nonopaque_or_malformed_reference(self) -> None:
        store = MemoryCredentialStore()
        for bad_ref in ("token-value", "github-api:not-a-uuid", "github-api:" + str(uuid.uuid4()).upper()):
            with self.subTest(bad_ref=bad_ref), self.assertRaises(CredentialStoreError):
                store.set_secret(bad_ref, TOKEN_A)

    def test_production_factory_never_falls_back_to_memory_store(self) -> None:
        # This test runs on the build host. Native Windows operations are separately required by release checklist.
        import os
        if os.name != "nt":
            store = create_default_credential_store()
            with self.assertRaises(UnsupportedCredentialStore):
                store.set_secret("github-api:" + str(uuid.uuid4()), TOKEN_A)

    def test_windows_store_does_not_claim_native_support_on_other_os(self) -> None:
        import os
        if os.name != "nt":
            with self.assertRaises(UnsupportedCredentialStore):
                WindowsCredentialStore()


class TokenValidationTests(unittest.TestCase):
    def test_trims_outer_whitespace_but_rejects_internal_whitespace(self) -> None:
        self.assertEqual(validate_pat("  " + TOKEN_A + "  "), TOKEN_A)
        with self.assertRaisesRegex(ValueError, "whitespace"):
            validate_pat(TOKEN_A + " extra")
        with self.assertRaises(ValueError):
            validate_pat("short")

    def test_redactor_hides_known_and_structural_secrets(self) -> None:
        message = redact_github_text("request failed: " + TOKEN_A + "; Authorization: Bearer anotherlongsecretvalue123", known_secrets=(TOKEN_A,))
        self.assertNotIn(TOKEN_A, message)
        self.assertNotIn("anotherlongsecretvalue123", message)
        self.assertIn("[REDACTED_SECRET]", message)


class GitHubApiClientTests(unittest.TestCase):
    def test_authenticated_user_headers_and_capability_limits(self) -> None:
        transport = QueueTransport(response())
        client = GitHubApiClient(transport=transport)
        user, capabilities = client.get_authenticated_user(TOKEN_A)
        self.assertEqual(user.login, "octocat")
        self.assertEqual(user.github_user_id, 583231)
        url, headers, timeout = transport.calls[0]
        self.assertEqual(url, "https://api.github.com/user")
        self.assertEqual(headers["Accept"], "application/vnd.github+json")
        self.assertEqual(headers["X-GitHub-Api-Version"], "2026-03-10")
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN_A)
        self.assertGreater(timeout, 0)
        self.assertEqual(capabilities["identity"], "available")
        for key in ("repository_read", "repository_write", "actions_read", "workflow_dispatch", "artifact_download", "release_write"):
            self.assertEqual(capabilities[key], "not_checked")

    def test_401_is_authentication_failure_and_does_not_echo_response(self) -> None:
        transport = QueueTransport(HttpResponse(401, {}, ("bad " + TOKEN_A).encode()))
        with self.assertRaises(GitHubApiError) as caught:
            GitHubApiClient(transport=transport).get_authenticated_user(TOKEN_A)
        self.assertEqual(caught.exception.category, "authentication")
        self.assertNotIn(TOKEN_A, str(caught.exception))
        self.assertEqual(caught.exception.status_code, 401)

    def test_403_permission_and_rate_limit_are_distinguished(self) -> None:
        permission = QueueTransport(HttpResponse(403, {}, b'{"message":"Resource not accessible by integration"}'))
        with self.assertRaises(GitHubApiError) as caught:
            GitHubApiClient(transport=permission).get_authenticated_user(TOKEN_A)
        self.assertEqual(caught.exception.category, "permission_or_policy")
        rate = QueueTransport(HttpResponse(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "2000000000"}, b'{"message":"API rate limit exceeded"}'))
        with self.assertRaises(GitHubApiError) as caught_rate:
            GitHubApiClient(transport=rate).get_authenticated_user(TOKEN_A)
        self.assertEqual(caught_rate.exception.category, "rate_limit")
        self.assertIsNotNone(caught_rate.exception.retry_after_seconds)

    def test_429_404_server_and_unexpected_json(self) -> None:
        cases = [
            (HttpResponse(429, {"Retry-After": "30"}, b"{}"), "rate_limit"),
            (response(404), "not_found"),
            (response(503), "server"),
            (HttpResponse(200, {}, b"not json"), "invalid_response"),
            (HttpResponse(200, {}, b"[]"), "invalid_response"),
        ]
        for item, category in cases:
            with self.subTest(category=category), self.assertRaises(GitHubApiError) as caught:
                GitHubApiClient(transport=QueueTransport(item)).get_authenticated_user(TOKEN_A)
            self.assertEqual(caught.exception.category, category)

    def test_network_and_timeout_are_distinct_and_sanitized(self) -> None:
        with self.assertRaises(GitHubApiError) as timeout:
            GitHubApiClient(transport=QueueTransport(TimeoutError("token " + TOKEN_A))).get_authenticated_user(TOKEN_A)
        self.assertEqual(timeout.exception.category, "timeout")
        self.assertNotIn(TOKEN_A, str(timeout.exception))
        with self.assertRaises(GitHubApiError) as network:
            GitHubApiClient(transport=QueueTransport(OSError("network failure " + TOKEN_A))).get_authenticated_user(TOKEN_A)
        self.assertEqual(network.exception.category, "network")
        self.assertNotIn(TOKEN_A, str(network.exception))

    def test_rejects_non_https_api_base_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            GitHubApiClient(base_url="http://api.github.com")
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            GitHubApiClient(base_url="https://user:password@api.github.com")

    def test_live_transport_rejects_non_github_hosts_and_paths(self) -> None:
        # In production, a typo or malicious HTTPS host must never receive a PAT.
        for url in (
            "https://attacker.example",
            "https://api.github.com.attacker.example",
            "https://api.github.com:8443",
            "https://api.github.com/proxy-prefix",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "api.github.com only"):
                GitHubApiClient(base_url=url)
        # Custom HTTPS endpoints remain usable with an explicitly injected test transport.
        GitHubApiClient(base_url="https://test.example/api", transport=QueueTransport(response()))

    def test_response_size_is_bounded(self) -> None:
        transport = QueueTransport(HttpResponse(200, {}, b"x" * (1024 * 1024 + 1)))
        with self.assertRaisesRegex(GitHubApiError, "size") as caught:
            GitHubApiClient(transport=transport).get_authenticated_user(TOKEN_A)
        self.assertEqual(caught.exception.category, "invalid_response")


class GitHubAccountServiceTests(unittest.TestCase):
    def make_service(self, *responses: Any):
        data: list[dict[str, object]] = []
        store = MemoryCredentialStore()
        client = GitHubApiClient(transport=QueueTransport(*responses))
        def load() -> object:
            return data
        def save(items: list[dict[str, object]]) -> bool:
            nonlocal data
            data = items
            return True
        service = GitHubAccountService(store, client, load, save)
        return service, store, load

    def test_add_pat_stores_only_credential_reference_in_metadata(self) -> None:
        service, store, load = self.make_service(response())
        account = service.add_pat(TOKEN_A)
        metadata = load()
        self.assertEqual(account.login, "octocat")
        self.assertEqual(store.get_secret(account.credential_ref), TOKEN_A)
        self.assertEqual(len(metadata), 1)  # type: ignore[arg-type]
        serialized = str(metadata)
        self.assertNotIn(TOKEN_A, serialized)
        self.assertNotIn('"token"', serialized)
        self.assertIn(account.credential_ref, serialized)

    def test_bad_token_is_never_saved(self) -> None:
        service, store, load = self.make_service(HttpResponse(401, {}, b"{}"))
        with self.assertRaises(GitHubApiError):
            service.add_pat(TOKEN_BAD)
        self.assertEqual(load(), [])
        self.assertEqual(store._values, {})

    def test_duplicate_identity_requires_replace_instead(self) -> None:
        service, _, _ = self.make_service(response(), response())
        service.add_pat(TOKEN_A)
        with self.assertRaisesRegex(Exception, "already connected"):
            service.add_pat(TOKEN_B)

    def test_replace_is_verified_before_old_credential_is_removed(self) -> None:
        service, store, _ = self.make_service(response(), response(login="octocat", user_id=583231), response(login="octocat", user_id=583231))
        account = service.add_pat(TOKEN_A)
        changed = service.replace_pat(account.account_id, TOKEN_B)
        self.assertEqual(store.get_secret(changed.credential_ref), TOKEN_B)
        with self.assertRaises(CredentialStoreError):
            store.get_secret(account.credential_ref)

    def test_replace_refuses_different_github_identity(self) -> None:
        service, store, _ = self.make_service(response(), response(login="someone-else", user_id=991))
        account = service.add_pat(TOKEN_A)
        with self.assertRaisesRegex(Exception, "different GitHub account"):
            service.replace_pat(account.account_id, TOKEN_B)
        self.assertEqual(store.get_secret(account.credential_ref), TOKEN_A)

    def test_repository_capability_update_is_scoped_and_validated(self) -> None:
        service, _, _ = self.make_service(response())
        account = service.add_pat(TOKEN_A)
        updated = service.record_capability(account.account_id, "repository_read", "available")
        self.assertEqual(updated.capability_snapshot["repository_read"], "available")
        self.assertEqual(updated.capability_snapshot["actions_read"], "not_checked")
        with self.assertRaisesRegex(Exception, "capability result"):
            service.record_capability(account.account_id, "secret_exfiltration", "available")
        with self.assertRaisesRegex(Exception, "capability result"):
            service.record_capability(account.account_id, "repository_read", "approved_without_check")

    def test_test_connection_records_reauth_status_on_401(self) -> None:
        service, _, load = self.make_service(response(), HttpResponse(401, {}, b"{}"))
        account = service.add_pat(TOKEN_A)
        with self.assertRaises(GitHubApiError):
            service.test_connection(account.account_id)
        refreshed = service.list_accounts()[0]
        self.assertEqual(refreshed.connection_status, "Needs re-authentication")
        self.assertEqual(refreshed.last_error_category, "authentication")
        self.assertEqual(len(load()), 1)  # type: ignore[arg-type]

    def test_disconnect_removes_metadata_and_credential_only(self) -> None:
        service, store, load = self.make_service(response())
        account = service.add_pat(TOKEN_A)
        self.assertTrue(service.disconnect(account.account_id))
        self.assertEqual(load(), [])
        with self.assertRaises(CredentialStoreError):
            store.get_secret(account.credential_ref)

    def test_disconnect_does_not_report_cleanup_success_if_store_fails(self) -> None:
        service, store, load = self.make_service(response())
        account = service.add_pat(TOKEN_A)
        original = store.delete_secret
        def fail(ref: str) -> None:
            raise CredentialStoreError("cleanup failed")
        store.delete_secret = fail  # type: ignore[method-assign]
        self.assertFalse(service.disconnect(account.account_id))
        self.assertEqual(load(), [])
        store.delete_secret = original  # type: ignore[method-assign]

    def test_metadata_loader_ignores_unknown_fields_and_duplicates(self) -> None:
        service, _, load = self.make_service(response())
        account = service.add_pat(TOKEN_A)
        account_data = account.to_dict()
        account_data["token"] = TOKEN_A
        # Directly mutate the mocked metadata to model old/corrupt settings.
        raw = load()
        raw.append(account_data)  # type: ignore[union-attr]
        listed = service.list_accounts()
        self.assertEqual(len(listed), 1)
        self.assertNotIn("token", listed[0].to_dict())


if __name__ == "__main__":
    unittest.main(verbosity=2)
