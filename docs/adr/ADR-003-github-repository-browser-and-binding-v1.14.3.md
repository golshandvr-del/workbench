# ADR-003 — GitHub Repository Browser and Project Binding

- **Status:** Accepted for v1.14.3
- **Date:** 2026-10-17

## Context

v1.14.2 provides a secure account/PAT boundary and an injectable REST client but has no repository browsing or persistent link from a Workbench project to a GitHub repository. The UI must not contain API authentication or remote parsing policy.

## Decisions

1. `GitHubApiClient.list_repositories()` calls `GET /user/repos` with explicit `visibility=all`, `affiliation=owner,collaborator,organization_member`, `per_page<=100`, and sequential page traversal. Results are immutable validated records; duplicate numeric repository IDs are removed. The ceiling is 100 pages / 10,000 repositories and is visible to the UI.
2. The UI performs search and All/Private/Public/Forks/Archived filters over the loaded list. This avoids first-page-only search behavior and avoids undocumented assumptions about search API visibility.
3. `RepositoryBinding` is a non-secret, versioned record containing numeric GitHub repository ID, account ID, local Git root, Workbench project path, Monorepo subpath, repository identity, branch metadata, and timestamp. Raw token and raw Git remote URL are excluded.
4. Git root and subpath are discovered from the active local project using `git rev-parse --show-toplevel`; binding is refused when the project is not inside a Git repository.
5. Existing `origin` is inspected without printing the raw URL. A missing/mismatched origin is only configured after explicit confirmation. A credential-free HTTPS URL is used. A post-change verification is required.
6. If persisting the binding fails after origin configuration, the app attempts to restore the old remote URL or remove the newly added remote. If restoration fails, the UI receives a clear warning and the release checklist calls for manual inspection.
7. Unlink removes only Workbench metadata. It never deletes or mutates the local repository.
8. The API client updates only the `repository_read` capability based on the `/user/repos` result; account identity does not imply Git write, Actions, dispatch, artifact, or release permissions.

## Consequences

The UI has a working repository list and can link multiple Workbench subprojects to different subpaths of one Monorepo. The feature does not clone or initialize a repository, stage/commit/push files, or run CI. These operations remain separate roadmap stages. API/local Git tests run with synthetic tokens, injected transport and disposable local repositories; native Windows Credential Manager and live GitHub API verification remain separate release gates.

## Acceptance

- Pagination, deduplication, API error categories and malformed repository responses are tested.
- HTTPS, SSH and scp-style GitHub remotes are parsed; other hosts do not match.
- Missing and mismatched remotes require explicit action; Link never stages, commits or pushes.
- Monorepo subpath binding round-trips and survives settings reload.
- A failed metadata save triggers best-effort origin rollback; logs/UI never expose the old raw URL.
