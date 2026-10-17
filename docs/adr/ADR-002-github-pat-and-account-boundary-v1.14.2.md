# ADR-002 — GitHub PAT and account boundary

- **Status:** Accepted for v1.14.2
- **Date:** 2026-10-17
- **Scope:** GitHub REST API account connection and PAT lifecycle

## Context

AI Workbench already has a local Git service. Git transport authentication and GitHub REST API authentication are different responsibilities and should not share storage implicitly. The application must support adding, checking, replacing, refreshing, and disconnecting multiple GitHub accounts without persisting PATs in JSON settings, project files, remote URLs, command-line arguments, or logs.

## Decisions

1. **Windows Credential Manager is the production credential store.** Each secret is stored as a generic credential under a Workbench-specific opaque reference. A plaintext file fallback and an automatic fallback to the in-memory test store are prohibited.
2. **Settings store metadata only.** Each account record includes account ID, GitHub numeric user ID, login, display URLs, PAT format label, connection status, verification timestamp, a reference such as `github-api:<uuid>`, and a conservative capability snapshot. It never contains the PAT.
3. **Verify before save.** Add and replace operations call the authenticated-user endpoint before writing the credential. Replacements must resolve to the same immutable GitHub user ID. On metadata-save failure, a newly written credential is removed and the old credential remains active.
4. **Conservative permission semantics.** A successful `GET /user` means identity verification only. Repository, Actions, dispatch, artifact, and release capabilities remain `not_checked` until their own endpoints are tested in later releases.
5. **API transport is injectable.** The production standard-library HTTPS transport only accepts `https://api.github.com`; arbitrary hosts/path prefixes are rejected before any bearer token is sent. Custom HTTPS bases can be used only with an explicitly injected transport for tests. Requests set an explicit API-version header, User-Agent and Accept header, with bounded timeout/response size. Redirects are not followed for credential-bearing requests. No raw response body or transport exception is shown to the user.
6. **Error categories remain separate.** Authentication (`401`), permission/policy (`403`), rate limit (`403`/`429` with headers/body signals), network, timeout, not found, server, and invalid response are represented distinctly.
7. **Disconnect is not repository deletion.** The account reference is removed from Workbench settings and its OS credential is deleted. Local projects, Git history, remotes, and Git Credential Manager entries are untouched. If OS credential cleanup fails, the UI reports the partial cleanup instead of claiming full success.
8. **UI never handles Git transport tokens.** Existing local fetch/push remains delegated to Git's configured credential helper, such as Git Credential Manager.

## Consequences

- Unit tests use an injectable HTTP transport and an explicitly test-only in-memory credential store. Background account operations persist metadata without calling Tk and share a lock with regular settings updates.
- A native Windows Credential Manager round-trip script is supplied for the target-machine release gate. A Linux/Xvfb or mock-only pass does not establish native Windows support.
- GitHub App/OAuth, repository enumeration, endpoint-specific permission probes, and Build Center remain future releases.
