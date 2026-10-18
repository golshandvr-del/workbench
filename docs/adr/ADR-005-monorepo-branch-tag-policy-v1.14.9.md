# ADR-005 — Monorepo, branch and tag policy (v1.14.9)

- **Status:** Accepted (2026-10-18)
- **Context:** The repository `golshandvr-del/workbench` hosts the Windows desktop app, the Android app and shared contracts. Releases, CI and the in-app Sync & Build flow (1.14.8) all depend on predictable branch and tag names.

## Decision

### Layout
| Path | Owner | Notes |
|---|---|---|
| `apps/desktop/{src,tests,tests/gui,installer,examples}` | Desktop | `release_manifest.json` v2 maps source → installed path |
| `apps/mobile/android` | Mobile | version in `apps/mobile/version.properties` |
| `packages/contracts/` | Shared | JSON Schema + fixtures; only for entities consumed by **both** apps |
| `docs/{specs,adr,release,audit}` | Docs | `ROADMAP.md` is the only execution order |
| `tools/` | Build/CI | builders, gates, release helpers |

### Branches
- `main` is protected: required check **CI summary**, no force push, no deletion. Nothing is pushed directly; every change lands through a PR.
- Work branches: `feat/<version>-<slug>`, `fix/<slug>`, `docs/<slug>`, `chore/<slug>`, `dependabot/*`. Branches are deleted after merge.
- The app never pushes to `main`/`master` (enforced in `aiwb/git/sync.py` and the 1.14.8 orchestrator); users bind a work branch.

### Tags and versions
- Independent version lines: `desktop-vX.Y.Z` and `mobile-vX.Y.Z` (SemVer). No bare `vX.Y.Z` tags.
- A tag is created **only on the merge commit on `main`** after CI is green, and must equal `APP_VERSION` / `release_manifest.json` (desktop) or `version.properties` (mobile); release workflows refuse a mismatch.
- Tags are never moved. A wrong tag is deleted immediately (before its release publishes) and the release workflow run is cancelled; a published release is fixed by a new patch version.
- Pre-releases use the workflow's `prerelease` input; the channel (`stable`/`beta`) is written into the release manifest.

### Contracts
- A change under `packages/contracts/` triggers desktop, mobile and contracts jobs (see `ci.yml` change detection).
- Schemas are versioned by `schema_version` inside each document; a breaking change adds a new schema file (`*.v2.schema.json`) and keeps the old one until both apps migrate.

## Consequences
- Release automation (`tools/bump_desktop_release.py`, `tools/mark_roadmap_step.py`) can rely on these names.
- Dependabot major-toolchain bumps for Android are excluded and handled as a planned migration (`0.2.x-tooling`).
