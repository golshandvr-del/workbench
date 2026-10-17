# AI Workbench Mobile — Changelog

## [0.1.0] - 2026-10-17
### Proof-of-build (roadmap v1.14.11 step)
- First Android app in the monorepo (`apps/mobile/android`, Kotlin, no third-party runtime dependencies).
- Shows exact build provenance: versionName/versionCode, channel, commit SHA and ref baked in by CI.
- "Check latest releases": reads this repository's GitHub Releases, shows latest Desktop (Windows) and Mobile versions, offers the Setup.bat / APK download and detects a newer mobile version.
- Only `https://github.com/` links are opened; INTERNET is the only permission; no cleartext, no backup.
- English and Persian UI.
- Companion features (pairing with desktop, tasks, prompts) are **not** included yet.
