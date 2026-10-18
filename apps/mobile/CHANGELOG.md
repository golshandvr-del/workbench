# AI Workbench Mobile — Changelog

## [0.2.2] - 2026-10-18

### Release pipeline fix
- The signed release build ran `testReleaseUnitTest`, which AGP 9 no longer creates by default (unit tests are generated for the tested build type only), so the `mobile-v0.2.1` release job failed before publishing anything. The release workflow now runs `testDebugUnitTest` together with `assembleRelease bundleRelease`. 0.2.2 is the first published build with AGP 9.4.1 + Gradle 9.8.1 + built-in Kotlin.

## [0.2.1] - 2026-10-18
### Tooling migration (roadmap mobile 0.2.x-tooling)
- Android Gradle Plugin 8.7.3 → **9.4.1** together with Gradle **9.8.1** in one change (AGP 8.x does not
  run on Gradle 9.8, which is why Dependabot PRs #2, #5 and #8 broke the build).
- Kotlin now comes from AGP 9 **built-in Kotlin** (bundled KGP); the separate
  `org.jetbrains.kotlin.android` plugin and the removed `kotlinOptions` block are gone; JVM target follows
  `compileOptions` (Java 17).
- No functional app change; unit tests, lint and the debug/release builds run unchanged in CI.

## [0.1.0] - 2026-10-17
### Proof-of-build (roadmap v1.14.11 step)
- First Android app in the monorepo (`apps/mobile/android`, Kotlin, no third-party runtime dependencies).
- Shows exact build provenance: versionName/versionCode, channel, commit SHA and ref baked in by CI.
- "Check latest releases": reads this repository's GitHub Releases, shows latest Desktop (Windows) and Mobile versions, offers the Setup.bat / APK download and detects a newer mobile version.
- Only `https://github.com/` links are opened; INTERNET is the only permission; no cleartext, no backup.
- English and Persian UI.
- Companion features (pairing with desktop, tasks, prompts) are **not** included yet.
