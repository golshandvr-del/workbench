# AI Workbench — monorepo

AI Workbench is a desktop "project studio" for AI-assisted development: it builds
prompts from your real project, validates and applies AI responses safely
(transactions, restore, semantic diff), runs/validates the result, and manages
Git/GitHub for the project. The Android companion app in `apps/mobile` pairs with the desktop over the local network.

| App | Path | Current | Download |
|---|---|---|---|
| Desktop (Windows 10/11, Python + Tk) | `apps/desktop` | **4.5.0** (single window, Fluent theme, robust layout, reliable chat-copy intake, calm pages, Project Charter, guided loop, visual timeline, QR pairing, project bundles; product release gate) | [Releases → `desktop-v*`](https://github.com/golshandvr-del/workbench/releases) |
| Mobile (Android 7.0+) | `apps/mobile` | **1.6.0** (Standalone mode: full guided loop on the phone, team size and overview; Companion; QR pairing) | [Releases → `mobile-v*`](https://github.com/golshandvr-del/workbench/releases) |

New here? Read the **[User Guide](docs/USER_GUIDE.md)**.

## Repository layout

```
ROADMAP.md                  Master roadmap — single source of truth for order, status and gates
apps/desktop/
  src/                      Application: AI_Workbench.py, *_store/service modules, aiwb/ package
  tests/                    Unit/regression tests (python -m unittest discover -s tests -t .)
  tests/gui/                GUI smoke scripts + run_all.py (needs a display / Xvfb)
  installer/                install.ps1, uninstall.bat, bootstrap.ps1 (self-extracting Setup.bat)
  examples/                 Sample model responses for manual testing
  release_manifest.json     Version + payload map (repo source -> installed flat path)
  CHANGELOG.md, README*.md, ARCHITECTURE.md
apps/mobile/                Android app (Kotlin, Gradle) + version.properties
packages/contracts/         shared JSON schemas + fixtures (ADR-005)
tools/                      Reproducible installer builder, manifest gate, installed-app smoke
tools/legacy/               Original 1.14.4 builder + independent packaging verifier
docs/specs/                 Product specs and roadmaps (FA) — detail behind ROADMAP.md
docs/adr/                   Architecture decision records (ADR-001 … ADR-004)
docs/audit/                 Implementation audit of the specs
docs/release/vX.Y.Z/        Per-release evidence: test reports, Windows checklists, hashes
.github/workflows/          CI and tag-driven release pipelines
```

The installed program folder is **flat** (unchanged since 1.14.4); `release_manifest.json`
maps every repository file to its installed path, so the repo layout can evolve without
breaking upgrades.

## Releasing

Both apps are released by **pushing a tag**; GitHub Actions builds, tests and publishes.

### Desktop (Windows)
1. Bump `APP_VERSION` in `apps/desktop/src/AI_Workbench.py` and `version` in `apps/desktop/release_manifest.json`; add a `## [X.Y.Z]` section to `apps/desktop/CHANGELOG.md`.
2. If you add a file, list it in `apps/desktop/installer/install.ps1` **and** `release_manifest.json` (CI gate enforces this). Put the release checklist in `docs/release/vX.Y.Z/`.
3. `git tag desktop-vX.Y.Z && git push origin desktop-vX.Y.Z`
4. `release-desktop.yml` runs tests on Windows, builds `AI_Workbench_X.Y.Z_Setup.bat`, installs it on a clean runner, GUI-smokes the installed copy and publishes the release with SHA-256 sums.

### Mobile (Android)
1. Bump `versionName` **and** `versionCode` in `apps/mobile/version.properties`; add a section to `apps/mobile/CHANGELOG.md`.
2. `git tag mobile-vX.Y.Z && git push origin mobile-vX.Y.Z`
3. `release-mobile.yml` builds a **signed** APK + AAB (keystore from repository secrets), verifies the signature and publishes the release (desktop stays "Latest").

Re-publish an existing tag: *Actions → Release … → Run workflow*.

## CI

`ci.yml` runs only the areas that changed:
- **Desktop:** tests on Linux (Python 3.10, 3.13) and natively on Windows, Credential Manager round-trip, installer build, real install from `Setup.bat`, GUI smokes.
- **Mobile:** JVM unit tests, lint, debug APK artifact.

## Local development

```bash
cd apps/desktop && python -m unittest discover -s tests -t .      # unit/regression tests
python src/AI_Workbench.py                                         # run the app
xvfb-run -a python tests/gui/run_all.py                            # all GUI smokes (Linux)
cd ../.. && python tools/check_installer_manifest.py               # installer/manifest gate
python tools/build_desktop_installer.py --out dist                 # build Setup.bat
cd apps/mobile/android && ./gradlew testDebugUnitTest assembleDebug
```

## Status / roadmap

> **Language policy:** the app UI is **English-only** for now (Desktop and Android). Persian will be added only when the product owner explicitly requests it in a later version.

**[`ROADMAP.md`](ROADMAP.md)** is the master plan (3.x product rebuild: single shell, reliable intake, project charter, guided loop, visual timeline, QR pairing, standalone mobile). Previous roadmaps are in `docs/roadmap/archive/`.
Previous roadmap (desktop 1.14.1–2.2.0, mobile 0.1.0–0.3.0) is archived in `docs/roadmap/archive/`. Audit: [`docs/audit/IMPLEMENTATION_AUDIT_FA.md`](docs/audit/IMPLEMENTATION_AUDIT_FA.md).

See also [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`SECURITY.md`](SECURITY.md).
