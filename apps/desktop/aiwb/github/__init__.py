"""GitHub account and REST API services for AI Workbench.

The package deliberately separates API credentials from Git transport credentials.
It has no Tkinter dependency and makes no assumptions about project directories.
"""
from .accounts import GitHubAccount, GitHubAccountService, GitHubAccountError
from .api_client import GitHubApiClient, GitHubApiError, GitHubUser, GitHubRepository, RepositoryListing
from .credential_store import (
    CredentialStore,
    CredentialStoreError,
    MemoryCredentialStore,
    UnsupportedCredentialStore,
    WindowsCredentialStore,
    create_default_credential_store,
)
from .redaction import redact_github_text, validate_pat

__all__ = [
    "GitHubAccount", "GitHubAccountService", "GitHubAccountError",
    "GitHubApiClient", "GitHubApiError", "GitHubUser", "GitHubRepository", "RepositoryListing",
    "CredentialStore", "CredentialStoreError", "MemoryCredentialStore",
    "UnsupportedCredentialStore", "WindowsCredentialStore", "create_default_credential_store",
    "redact_github_text", "validate_pat",
]
