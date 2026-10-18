# 1.15.0 — Definition of Done (evidence)

| Requirement | Evidence |
|---|---|
| Secure GitHub accounts / credentials | `aiwb/github/accounts.py`, `credential_store.py`; native Windows Credential Manager round-trip in CI |
| Repository browser and binding (full repo or monorepo subpath) | `aiwb/github/repository_binding.py`, `test_github_repository_binding_v144.py` |
| Git review, selective commit, sync plan, controlled push | `aiwb/git/sync.py`, `review_dialog.py`; never pushes to `main`/`master`, no force push |
| Build Center with exact run/job/artifacts | `aiwb/github/actions.py`, `build_center.py` (full-SHA attribution) |
| Sync & Build end to end with hash verification | `aiwb/github/orchestrator.py`; real E2E `docs/release/v1.14.13/E2E_REPORT_v1.14.13.md` |
| Monorepo, desktop CI, Android proof build, contracts/capabilities | `ci.yml` (Linux + Windows + Android + contracts), `packages/contracts`, `capabilities.yml` |
| Separate desktop/mobile release workflows, protected signing | `release-desktop.yml`, `release-mobile.yml`; `release` Environment with required reviewer |
| Regression tests, real Windows install, release docs, SHA-256 manifest | 306+ unit tests, GUI smokes, upgrade test, Unicode path smoke, `release-manifest.json` + `SHA256SUMS` |

Out of scope (unchanged): GitHub App/OAuth, iOS, Mobile Companion, Auto Commit & Push, Force Push/Hard Reset, unapproved mobile releases.
Open manual checks and their decisions: `docs/release/v1.14.13/RELEASE_OWNER_DECISIONS_v1.14.13.md`.
