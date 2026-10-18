# AI Workbench Mobile — Changelog

## [0.3.0] - 2026-10-18

### Mobile Companion (Integration Spec §11, P3.1–P3.3)
- New **Mobile Companion** screen: pair with AI Workbench Desktop 2.2.0 on the same local network using the
  one-time code shown on the desktop; the desktop user approves the phone.
- View project summary, next action, warnings, tasks and recent builds; create a task and submit a model
  answer to the desktop Inbox when the desktop granted that permission. Preview/Apply/Run stay on the desktop.
- `CompanionCrypto` implements envelope v1 byte-for-byte like the desktop (shared vectors); the client only
  connects to private-LAN/loopback IPv4 addresses; the device key stays in app-private storage.
- Network security config: system CAs only; local cleartext transport carries only sealed envelopes.

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
