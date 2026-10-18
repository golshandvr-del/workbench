# V2 State Publisher — real GitHub API check (2026-10-18)

Repository: `golshandvr-del/aiwb-e2e-sandbox`, branch `aiwb-state-e2e` (deleted afterwards).

| Case | Result |
|---|---|
| First publish: one atomic commit (blob → tree → commit → ref) with `.aiwb/project-state.json` + `.aiwb/PROJECT_STATUS.md` | PASS (`published`) |
| Same state again | PASS (`noop`, no commit) |
| Changed state | PASS (`published`) |
| Remote snapshot is this project (project_id) with both tasks | PASS |
| Write to default branch `main` | PASS (refused: `protected`) |
| Invalid token | PASS (`auth`, queue paused, local state intact) |
| No token / local path in published files | PASS |

Offline, rate limit (`Retry-After`), remote branch moved (conflict, no overwrite), foreign project on the state
branch and queue survival across restarts are covered by `tests/test_v2_flow.py::PublisherTests` with a
GitHub Git-Data fake.
