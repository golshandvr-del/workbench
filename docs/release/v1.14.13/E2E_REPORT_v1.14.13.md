# E2E report — 1.14.13 (real GitHub API, separate test repository)

- **Tool:** `tools/e2e_github_sandbox.py` (refuses to run against `golshandvr-del/workbench`)
- **Repository:** `golshandvr-del/aiwb-e2e-sandbox`, workflow `.github/workflows/e2e.yml` (push on `e2e/**` + `workflow_dispatch`)
- **Date:** 2026-10-18, Linux sandbox, Python 3.13, real Git over HTTPS (token supplied by a one-shot credential helper via environment, never in URL/config/argv)
- **Working paths:** contain spaces and Unicode (`aiwb e2e ü …/work tree`, `downloads ü`)

| Check | Result |
|---|---|
| operation lock | PASS |
| preflight (account, workflow, branch, remote, fetch, checkout, sync) | PASS |
| sensitive file (`secret.env`) blocked in review and refused by commit | PASS |
| commit / idempotent commit (no second commit) | PASS |
| push / idempotent push | PASS |
| run matched to the pushed SHA only (a seed push on the same branch had its own run) | PASS (run 39107092083) |
| build passed | PASS |
| artifact downloaded, SHA-256 **matched** GitHub's digest | PASS |
| artifact content (`commit.txt`) equals the pushed SHA | PASS |
| `build-metadata.v1` conversion of the stored record | PASS |
| stale plan: concurrent push after review → commit refused, HEAD unchanged | PASS |
| manual `workflow_dispatch` confirmed with run ID | PASS (run 39107108460) |
| no token in records, events, `.git/config` | PASS |
| cleanup (work branch deleted) | PASS |

Re-run: `AIWB_E2E_TOKEN=<PAT with contents+actions on the sandbox repo> python tools/e2e_github_sandbox.py`.
