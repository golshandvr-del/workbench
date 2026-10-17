# AI Workbench — monorepo

AI Workbench is a desktop "project studio" for AI-assisted development: it builds
prompts from your real project, validates and applies AI responses safely
(transactions, restore, semantic diff), runs/validates the result, and manages
Git/GitHub for the project. A companion Android app is starting in `apps/mobile`.

| App | Path | Current | Download |
|---|---|---|---|
| Desktop (Windows 10/11, Python + Tk) | `apps/desktop` | **1.14.5** | [Releases → `desktop-v*`](https://github.com/golshandvr-del/workbench/releases) |
| Mobile (Android 7.0+) | `apps/mobile` | **0.1.0** proof-of-build | [Releases → `mobile-v*`](https://github.com/golshandvr-del/workbench/releases) |

## Repository layout

```
apps/desktop/        Desktop app source (AI_Workbench.py + aiwb/ package), installer scripts, tests
apps/mobile/         Android app (Kotlin, Gradle) + version.properties (single version source)
packages/contracts/  (planned) shared JSON schemas between desktop and mobile
tools/               Reproducible installer builder, installer/manifest gate, GUI smoke tests
docs/handoff/        Original product specs and roadmaps (FA)
docs/audit/          Implementation audit: which specs are done and how far
docs/adr/            Architecture decision records
docs/release/        Historical release evidence (hashes, test reports)
.github/workflows/   CI and release pipelines
```

## Releasing

Both apps are released by **pushing a tag**; GitHub Actions builds, tests and publishes.

### Desktop (Windows)
1. Bump `APP_VERSION` in `apps/desktop/AI_Workbench.py` and `version` in `apps/desktop/release_manifest.json`; add a `## [X.Y.Z]` section to `apps/desktop/CHANGELOG.md`.
2. If you add a file, list it in `install.ps1` **and** `release_manifest.json` (CI gate enforces this).
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
cd apps/desktop && python -m unittest discover -p "test_*.py"   # desktop tests
python tools/build_desktop_installer.py --out dist                # build Setup.bat
xvfb-run -a python tools/gui_smoke.py                             # GUI smoke (Linux)
cd apps/mobile/android && ./gradlew testDebugUnitTest assembleDebug
```

## Status / roadmap

See [`docs/audit/IMPLEMENTATION_AUDIT_FA.md`](docs/audit/IMPLEMENTATION_AUDIT_FA.md).
Done: roadmap 1.14.1–1.14.5, mobile proof-of-build (1.14.11), monorepo + CI/CD.
Next: 1.14.6 Build Center → 1.14.7 Sync & Build → 1.14.8 Artifact Manager → 1.14.12 shared contracts.
