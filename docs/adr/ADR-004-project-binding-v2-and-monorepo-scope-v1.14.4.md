# ADR-004: Project Binding v2 and Monorepo Scope

- **Status:** Accepted for AI Workbench 1.14.4
- **Date:** 2026-10-17
- **Context:** v1.14.3 linked a Workbench project path to a GitHub repository ID and recorded the actual Git root/subpath, but the binding omitted build preferences and Git actions could still need stronger scope guarantees for Monorepo projects.

## Decision

1. Upgrade `RepositoryBinding` to schema v2, retaining schema-v1 normalization. Persist non-secret configuration only: workflow file, artifact pattern, release channel and optional synchronization metadata. Credential material stays in the operating-system credential service; raw remote URLs are not persisted in binding records.
2. Treat the project path, canonical Git root and repository-relative subpath as separate concepts. Before branch, commit or push operations, resolve the actual root and ensure it still matches the saved binding.
3. Repository status is computed from the actual Git root and explicitly partitioned into active-project paths and outside-scope paths. Workbench Commit stages only active-scope paths using literal pathspecs. If the index already contains staged changes, it stops rather than guessing which project staged them. The user must resolve existing staged changes separately.
4. Initial Push Review is read-only. It lists candidate files, marks outside-scope paths, flags path signatures and likely secrets, flags oversized files and offers `.gitignore` suggestions. Applying those suggestions requires a separate confirmation and never overwrites existing `.gitignore` content.
5. Clone requires a new destination. Initialize & Link creates local repository state on a non-main branch and configures the remote only after approval. Neither path commits or pushes on behalf of the user.
6. `.workbench/` is added to the private `info/exclude` file of the actual Git directory (not a wrongly calculated subdirectory path); already tracked files are not hidden by exclude rules.

## Consequences

- Different Workbench projects can share one numeric GitHub repository ID with distinct subpaths and preferences.
- Git branch and push semantics remain repository-wide, while Commit path selection is constrained to the active project's scope. A commit in a Monorepo still creates one repository commit; it cannot be isolated as a separate repository history without a different repository architecture.
- Pre-staged user changes block Workbench Commit in this release. A dedicated file-level staged/unstaged review and Sync Plan are deferred to v1.14.5.
- Sensitive-file scanning is heuristic; it reduces risk but is not a security boundary. Initial Push Review never stages, commits or pushes.
- Native Windows verification and real GitHub credentials must be tested separately. Linux/Xvfb/local-Git tests are evidence for logic paths only.

## Verification

The v1.14.4 unit suite covers binding migration/idempotence, shared repository ID with multiple subpaths, validation, repository rename by numeric ID, component-aware path classification, read-only initial review and invalid roots. The GUI smoke uses a real local Git repository to check migration backup, outside-scope visibility, non-mutating review and a commit containing only a file in the active Monorepo project.
