# AI Workbench — monorepo

AI Workbench is a desktop "project studio" for AI-assisted development: it builds
prompts from your real project, validates and applies AI responses safely
(transactions, restore, semantic diff), runs/validates the result, and manages
Git/GitHub for the project. The Android companion app in `apps/mobile` pairs with the desktop over the local network.

| App | Path | Current | Download |
|---|---|---|---|
| Desktop (Windows 10/11, Python + Tk) | `apps/desktop` | **5.20.0** (gate of real scenarios: nine scenarios S1–S9 drive the app like a person — real buttons, real menus, the real clipboard — Quick with three files, a guided project with three named AIs to the first accepted milestone, broken answers (fix prompt / auto-fix / Markdown), a cut-off answer → Continue (a lost-files bug found and fixed), close and reopen mid-work, a project made by 5.7.0, a real ChatGPT ZIP, a real context request, and answers copied from the rendered Windows chat; Quick mode: New Project ▾ › Quick — one AI chat… does the whole one-chat loop in one window — the job, the prompt, the answer in AIWB blocks / Strict JSON / GPT ZIP, every file with its diff, Apply with a backup, Restore, the continue prompt for a cut-off answer, and Make it a multi-AI project… with your files untouched; the classic 1.x Prompt / AI Response pages are gone; one project, one screen: four places — Home · Agents · History · Settings — with the project switcher in the toolbar, milestones and versions on the Mission Map columns, History as one filtered list, every command in one home, AI names instead of ids, the whole owner path from Home in 14 clicks; an installed update really runs the new version; real chat answers work: a rendered answer copied on Windows is repaired, every prompt asks for the whole answer in one code block, "the AI asks for files" is a step on Home's card — copy the files, send, paste the answer; Home is the cockpit: the Next-step card does each step with its own buttons and an inline paste panel, click an AI on the map for its own step, New Project → first file in 11 clicks, Workbench in 3 sections, no page with more than 8 controls in view; whatever the model returns, it works: lenient charter reading with every auto-fix listed, files from AIWB blocks, Markdown, Strict JSON or ZIP, one paste box with live diagnosis and Load ZIP…, an answer corpus of 60 chat answers (incl. the owner's real ones) as the gate; you decide the AI team: one-window 3-step New Project wizard — project, team with your own names, answer format — no template AIs, named Mission Map lanes, Edit team at any time; core-path repair begun: the paste boxes work again, Guided project goes straight to the guided start, the Project Profile reaches the charter prompt, an owner-path gate with real widgets; "Mission Map", one job per page: Home = the active project with Map view, History timeline; Agents hub: one card per AI with live state, load, record, briefing, memory note and load balancing; App Map: every page, section and command mapped from the live app and balanced; parallel timelines on Home, one lane per AI, right-click task menu, smooth motion with Reduce motion; shell: toolbar, icon rail, live status bar; design foundation: anti-aliased rasteriser, Midnight/Daylight tokens, UI tree contract, splash launcher; single window, robust layout, reliable chat-copy intake, calm pages, Project Charter, guided loop, visual timeline, QR pairing, project bundles; product release gate) | [Releases → `desktop-v*`](https://github.com/golshandvr-del/workbench/releases) |
| Mobile (Android 7.0+) | `apps/mobile` | **3.1.0** (Mission Map on the phone: parallel timelines with pinch/pan and long-press task menu; Midnight/Daylight shared with the desktop, 5-destination bottom bar; Standalone guided loop; Companion; QR pairing) | [Releases → `mobile-v*`](https://github.com/golshandvr-del/workbench/releases) |

New here? Read the **[User Guide](docs/USER_GUIDE.md)**.

## Repair checkpoint — 2026-11-05 (unreleased)

The active plan is [V5.21–V5.30](ROADMAP.md), replacing the completed V5.16–V5.20 plan
preserved verbatim in `docs/roadmap/archive/ROADMAP_v5.16-v5.20_Light_Clear_Short_FA.md`.
These are repair-stage targets, **not released application versions**; Desktop remains 5.20.0.

- Repaired and regression-tested findings (Desktop and/or Mobile, as catalogued): **
  BF-001, BF-002, BF-003, BF-004, BF-007, BF-009, BF-010, BF-011,
  BF-012, BF-013, BF-014, BF-015, BF-016, BF-017, BF-024, BF-026,
  BF-027, BF-028, BF-031, BF-032, BF-033, BF-035, BF-039, BF-042,
  BF-043, BF-044, BF-047, BF-048, BF-051, BF-052, BF-053, BF-054,
  BF-055, BF-057, BF-061, BF-063, BF-064, BF-065, BF-066, BF-076,
  BF-078, BF-079, BF-081, BF-089, BF-091, BF-092, BF-093, BF-094,
  BF-095, BF-104, BF-105, BF-106, BF-108, BF-109**.
  This is **54/106 (50.94%)** by finding count, not effort or release readiness.
- Quick and guided deliveries share full-set filesystem preflight, immutable flushed backups,
  exact preview hashes and reverse rollback on file or state-save exceptions. Guided acceptance
  commits with integration; Restore is retryable and preserves later user edits. Empty files are
  retained; staging limits and path collisions are reported and block incomplete acceptance.
- Journals/backups are retained for recovery after interrupted operations. This is exception-atomic,
  **not** a power-loss transaction across the filesystem and application state; hostile concurrent
  path replacement is not claimed solved. New source module is `aiwb/v2/file_transaction.py`.
- S5 GUI harness cancels timers through their registering widgets, with permanent ownership tests.
- All Desktop answer routes now share staging and smart checks (including Companion and classic import).
  Partial repair publishes complete files before excluding them from the next request; troubleshooting
  retains good payloads and detects missing code. Mobile now uses the same lifecycle contracts: standalone
  and guided intake stage/check once, keep cut-off continuation prompts, preserve partial/retained files,
  refuse stale preview hashes and roll back file publication if acceptance/state publication fails.
- Desktop settings recovery now preserves undecodable input byte-for-byte in unique flushed backups
  and starts with defaults instead of raising UnicodeDecodeError; repeated failures do not clobber backups.
- Build Center preferences stay with the originating project/binding. Sync & Build captures project,
  repository, task revision and attempt, independently checks local HEAD/branch/origin on completion,
  and never applies A's CI evidence to active project B or to every task. Legacy operations or operations
  without an explicitly identifiable V2 task intentionally create no automatic task evidence.
- Terminal-task change requests now suggest a follow-up task rather than silently revising finished work.
  Cancellation/supersession closes open prompts and unfinished attempts in the same state transaction on
  Desktop and Mobile, releases chat slots and preserves history. Late unwanted deliveries cannot be accepted
  or written, even with an override reason; create a new task if that work is wanted after all.
- Dropping/rejecting prompts closes their attempts and detaches only their own active pointer. Home,
  Desktop workflow/dashboard and restart warnings agree on preparing a fresh prompt, including legacy states.
- Completion decisions accept unambiguous completion wording and empty lists; unknown decisions get
  recovery guidance that explicitly permits an empty completed plan, never fabricated work. Open tasks
  still prevent completion. Shared Desktop/Mobile fixtures reject ambiguous negative phrases.
- Orphaned task owners fall back only to enabled workers, preferring the least-busy developer, never the PM.
  Home and direct task starts share dispatch's policy; no worker gives actionable assignment guidance.
  Removing an owner with open work requires explicit reassignment first; terminal history is preserved.
- Continuation cards belong only to live active handoffs. Dropped, closed, missing or replaced prompts
  cannot keep stale Paste-the-rest actions alive; old partial answers remain stored for inspection.
- Settings persistence failures report their cause and lost-on-close risk once per failure period;
  Toolbar never confirms a failed save. Helper setup/removal failures restore prior configuration
  and credentials and preserve the form for retry. Credential rollback failure is explicitly reported;
  this is exception recovery, not power-loss atomicity across secure storage and JSON.
- Fresh Desktop/Mobile task prompts include recorded current-task/revision validation feedback with
  its full stored note, separate run ID and attempt identity. Failed validation contradicts the prior
  delivery's model claims. Rejected delivery lineage and user reason survive project restart and reach
  the next self-contained prompt rather than being called the first handoff.
- Session 36 protects raw file fences and Unicode payloads, refuses unsupported file operations, isolates
  missing block boundaries, repairs JSON without corrupting literal quotes, accepts safe ZIP/path aliases,
  preserves readable source context (including empty/UTF-16 files), and refuses lossy helper-prefix rewrites.
  Manager rescue preserves decision choices and Persian title identity; old-chat metadata edits do not
  change current chat. Architecture status/severity validation and Unicode Git display have regressions.
- **23 additional findings were closed this session, not 50.** BF-045/046/098 are partial repairs and
  remain OPEN: new-task prerequisite resolution, role/comment handling and the project-creation service
  boundary still need work. The latest owner request ended new subtasks for this checkpoint.
- Final-source suites: **1009 Desktop tests OK, 10 skipped**; **120 Mobile Kotlin/JVM tests OK**;
  static gate: **0 undefined names**. Run `python3 tools/test_mobile_jvm.py` (Python 3.11+, JDK 17+)
  for the SDK-independent JVM gate; Maven dependencies are checksum-pinned and compiler output is temporary.
  This is NOT Android lint, APK compilation, instrumentation, Activity rendering or an on-device gate.
  Historical session 35 real Tk helper smoke passed under Xvfb with injected Save/Remove failures, unchanged
  disk state, successful retries and normal helper workflow against a local fake API. This is only
  the helper scenario, not the full frozen-source GUI release gate. Session 36 ran no new GUI gate. Native Windows was not tested.
- **52 independent findings remain OPEN** (0 S1 / 18 S2 / 34 S3). Zero catalogued open S1 does not
  guarantee no undiscovered data-loss defects or platform issues. BF-008 actual Windows/Android validation,
  full frozen-source GUI, remaining lifecycle/intake/persistence/UI repairs and integrated release gates
  remain. The roadmap is not complete and the program is not claimed bug-free.
- No tag, release or deployment was performed. Existing installed releases do not receive these
  source repairs until a later release passes its gates. Use the local test commands below;
  real GitHub dispatch/create/release endpoints were not used for reproductions.
- Details, original reproductions, repair commits and limitations: [bug catalog](docs/BUG_FINDING.md).
  Resume after reset: [persistent checkpoint notes](docs/roadmap/SESSION_NOTES.md).

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

**[`ROADMAP.md`](ROADMAP.md)** is the active V5.21–V5.30 root-cause repair plan for all 106 independent findings from the discovery phase. Its per-stage acceptance gates remain mandatory; partial source repairs are not a release. Previous roadmaps are in `docs/roadmap/archive/`.
Previous roadmap (desktop 1.14.1–2.2.0, mobile 0.1.0–0.3.0) is archived in `docs/roadmap/archive/`. Audit: [`docs/audit/IMPLEMENTATION_AUDIT_FA.md`](docs/audit/IMPLEMENTATION_AUDIT_FA.md).

See also [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`SECURITY.md`](SECURITY.md).
