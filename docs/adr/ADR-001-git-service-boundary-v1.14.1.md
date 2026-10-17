# ADR-001: Local Git service boundary

- **Status:** Accepted for v1.14.1
- **Date:** 2026-10-17
- **Decision owners:** AI Workbench maintainers

## Context

The desktop GUI had local Git discovery, subprocess invocation, status parsing and changed-path logic in `AI_Workbench.py`. That coupled process mechanics to the GUI module and made these operations harder to test independently. The GitHub/Monorepo roadmap requires a stable local Git layer before adding authenticated GitHub API services.

## Decision

Create a Tkinter-independent `aiwb.git` package with:

- `GitCommandRunner`: one argv-based `subprocess.run` boundary, `shell=False`, bounded timeout, disabled terminal prompting, and injectable providers for tests.
- `GitService`: executable/version, command, status snapshot and changed-path operations.
- `GitStatusEntry` and `GitStatusSnapshot`: immutable typed status models.
- Thin top-level compatibility adapters so the current GUI does not need a broad refactor in this release.

The service does not own GitHub REST API credentials. Git-over-HTTPS authentication continues to use the user's configured Git credential helper. PAT storage and API authentication will be separate future services.

## Consequences

### Positive

- Command construction and error behavior are unit-testable without a GUI or network.
- GUI and future application workflows can share one local Git boundary.
- Legacy status payloads remain stable while new code can consume typed data.
- The installer must include nested modules, so packaging tests now assert their presence.

### Trade-offs

- Some orchestration (user confirmation, Branch policy, sensitive-file review, commit/push handlers) still lives in `AI_Workbench.py` and is not declared fully modular.
- This release does not solve remote divergence, selective staging, Repository bindings or GitHub API management; those remain separate roadmap milestones.

## Guardrails

- Never pass a token through argv, a remote URL, project JSON or logs.
- Do not invoke the shell for ordinary Git commands.
- Preserve NUL-delimited path semantics and avoid trimming filename data.
- Do not change existing direct-push policy or automatically discard local changes during this extraction.
- Treat Linux/mock tests and native Windows install/credential tests as different evidence categories.

## Acceptance evidence

See `test_git_service.py` and `AI_Workbench_Test_Report_v1.14.1.txt`. This ADR does not claim the native Windows installer has been executed in the current environment.
