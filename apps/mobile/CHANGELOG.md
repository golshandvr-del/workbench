# AI Workbench Mobile — Changelog

## [1.0.1] - 2026-10-20

### Fixes from the first phone test (standalone mode stuck after step 1)
- **Verify step no longer traps the user.** It showed one action with an unlabelled `result` field, so the only
  outcome was "Error: result is required". Now: *Tests/build passed…*, *Tests/build failed…* and
  *I can't run tests — accept on review…* buttons. The last one never fakes evidence: the task is accepted on
  review alone, its policy becomes `manual_review`, a `validation_waiver` with `result: not_run` and a
  "validation NOT RUN" flag are kept, and the timeline shows a `validation_waived` event.
- Every input field has a hint (what to type, and whether it is optional); `record_validation` accepts
  ok/yes/pass/fail words.
- **Project settings**: goal and *how many AI chats you will follow at the same time* (1–12). This number goes
  into the Project Charter prompt; the project manager sizes the team inside it.
- **Project overview**: AI team, tasks with status and owner, versions, and the charter's questions for you.
- Errors are shown in red at the top and the page scrolls to them.
- Timeline: version labels at the same time are stacked instead of drawn over each other (the "0.1.0" knot).
- Prompts ask the AI to wrap every file in a four-backtick fence: chat apps strip indentation and backticks
  from text outside code blocks when it is copied (seen in a real Gemini answer).

### Validation
- `VerifyStepTest` (JVM): one-tap verify, honest waiver, team-size setting, four-backtick fence parsing.
- NOT RUN: on a physical phone.

## [1.0.0] - 2026-10-19

### Standalone mode (roadmap mobile 1.0.0 + 3.8.0)
- The phone no longer needs the desktop: **Standalone mode** keeps projects in app-private storage, in the same V2
  project document as the desktop.
- Kotlin core (`core/`): `StrictJson` (RFC 8259, output byte-identical to Python `json.dumps`), `Normalize` and
  `Intake` (same normalizer and AIWB blocks as the desktop, shared corpus), `State`/`ProjectStore` (transactions,
  backups), `Charter` (prompt, validation, fix prompt, reviewed import), `Project` (proposals, tasks, handoffs,
  evidence policy, decisions, milestones, versions), `Prompts`, `Guide` (guided loop: a next step for every state)
  and `Timeline` (lanes per AI, importance, version lines).
- UI: project list, *next step* card with its actions, paste-an-answer box (charter, manager proposal or task
  answer is recognised automatically), visual timeline with pinch zoom/pan/tap, and project bundle
  import/export (`aiwb-bundle.v1`) through the system file picker. Bundles are never merged; a backup is kept.
- Mobile Companion (pairing with the desktop) is unchanged.

### Validation
- JVM tests on the shared fixtures: `IntakeCorpusTest`, `BundleContractTest` (desktop bundle read, byte-identical
  re-export, newer/older/diverged, damage) and `StandaloneLoopTest` (from charter to a released version without a
  dead end; model claims never count as validation).
- NOT RUN: the standalone loop on a physical phone.

## [0.4.0] - 2026-10-19

### Pairing with QR (roadmap 3.7.0 + mobile 0.4.0)
- **Built-in QR scanner** (Camera2 + ZXing core): Mobile Companion → *Scan QR code* reads the code shown in
  Workbench Desktop 3.7.0 → Mobile Companion and pairs at once. The camera permission is optional.
- **Deep link** `aiwb://pair?h=<ipv4>&p=<port>&k=<code>`: scanning the desktop QR with the system camera opens
  the app directly on the pairing step.
- **Short manual code**: desktop address + 16 Base32 characters (`ABCD-EFGH-IJKL-MNOP`, 80 bits; case, spaces and
  dashes are ignored; 0/1/8 are read as O/I/B). Valid 10 minutes, single use; the desktop cancels it after 5 wrong
  attempts.
- The raw code never travels over the network: the envelope key and the pairing id are derived from it with
  HMAC-SHA256 (`companion-pairing.v2`). The old `aiwb1:` codes are no longer accepted (desktop 3.7.0 required).

### Validation
- `PairingContractTest`: the shared `packages/contracts/vectors/companion-pairing.v2.json` vectors (same as the
  desktop's `test_qr_pairing`), invalid codes/links, and ZXing decoding of the QR matrix produced by the desktop's
  pure-Python encoder (several scales and a padded camera row stride).
- NOT RUN: scanning on a physical phone.

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
