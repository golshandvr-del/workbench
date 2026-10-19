# Product Release Gate — desktop 3.9.0 · mobile 1.0.0 (Master Roadmap 3.x, step 3.9.0)

Date: 2026-10-19. Branch `feat/release-gate-3.9.0`. Every result below is produced by CI (GitHub Actions)
or by the commands listed; nothing that was not run is reported as passed.

## 1. Gates of every 3.x step

| Step | Gate evidence (automated) | Result |
|---|---|---|
| 3.0.0 single shell, Fluent theme | `gui_single_shell_smoke` (Linux Xvfb + installed copy on Windows CI) | PASS |
| 3.1.0 robust layout | `gui_layout_smoke` at 1024×640, 1280×720, 1920×1080 | PASS |
| 3.2.0 reliable intake | `test_intake_normalize` (36-case shared corpus), `gui_intake_smoke`, Kotlin `IntakeCorpusTest` | PASS |
| 3.3.0 information architecture | `gui_ia_smoke`, `test_ui_actions`, `docs/specs/UI_TREE.md` | PASS |
| 3.4.0 Project Charter | `test_v2_charter`, `gui_charter_smoke`, `validate_contracts` | PASS |
| 3.5.0 guided loop | `test_v2_guide` (invariant + idea→release E2E with 3 parallel AIs), `gui_guide_smoke` | PASS |
| 3.6.0 visual timeline | `test_timeline_canvas` (2000 events < 300 ms), `gui_timeline_smoke` | PASS |
| 3.7.0 / mobile 0.4.0 QR pairing | `test_qr_pairing` (zbar reference decoder), `PairingContractTest` (ZXing) | PASS |
| 3.8.0 / mobile 1.0.0 standalone | `test_bundle`, `BundleContractTest`, `StandaloneLoopTest`, shared `fixtures/bundle/` | PASS |
| **3.9.0 product E2E** | `test_release_gate` (below) | PASS |

Repository gates on every PR: compile-all, pyflakes undefined-name gate, installer/manifest consistency
(`check_installer_manifest`: 139 payload files), shared contracts (9 schemas, 20 fixtures), Windows
upgrade install from the previous published release, run from a Unicode path with spaces, Android lint +
unit tests + debug APK.

## 2. End-to-end (`apps/desktop/tests/test_release_gate.py`)

1. Idea → charter prompt → a **dirty chat copy** of the charter (smart apostrophe, NBSP, markdown-escaped
   `\<\<\<AIWB\_…` markers, outer code fence, chatter before/after) is normalised and imported.
2. The **guided loop alone** drives 3 AIs from the charter to 2 released versions; every reached state
   has at least one step with an action (no dead end); validation counts only when recorded by the user.
3. **Desktop → phone → desktop:** the finished project is exported as `aiwb-bundle.v1`, imported into an
   empty project (plan `new`), and both sides then report `same`; versions survive unchanged. The bundle
   produced by the Kotlin core (`todo.mobile.aiwb-bundle.json`) is accepted and has a next step.
4. Performance budgets (see §3).

On the phone side the same loop is covered by `StandaloneLoopTest` (charter → released version, no dead end).

## 3. Performance (Linux, 2 vCPU, Python 3.13, Xvfb — `tools/measure_baseline.py`, `test_release_gate`)

| Measure | Result | Budget |
|---|---|---|
| Import of the app module | 187 ms | — |
| Main window construction until idle | 545 ms | — |
| Open a project with 200 tasks / 2000 events (580 KB state), median | 155 ms | < 1500 ms |
| Workspace read models (overview / tasks / timeline / team) | 100 / 54 / 16 / 27 ms | — |
| Open finished E2E project · guide steps · bundle export | 8 · 5 · 4 ms | 1500 · 500 · 500 ms |
| Timeline canvas, 2000 events | < 300 ms (gate 3.6.0) | 300 ms |
| Max RSS | 60 MiB | — |
| Installer payload | 2.51 MB, 139 files | < 4 MB |

## 4. Screenshots before / after

* Before (2.6.0 Workspace, separate window): `docs/audit/screens/v2.6.0/` (`tools/gui_screenshots.py`).
* After (3.9.0 single window, Fluent light/dark, every rail page and every Workbench view, 1280×720):
  `docs/audit/screens/v3.9.0/` (`tools/gui_screenshots_3x.py`, `manifest.json` records the conditions).
* Both sets are Linux/Xvfb captures, not physical Windows.

## 5. User documentation

`docs/USER_GUIDE.md` (English): install, main window, first project through the guided loop, timeline,
phone standalone mode, bundles, Companion pairing, Git/GitHub, troubleshooting, privacy.

## 6. NOT RUN (only the product owner can run these)

* Physical Windows at DPI 100 / 125 / 150 / 200 % (CI runs Windows Server without a scaled display).
* A full scenario with real ChatGPT / Gemini / Claude chats (3 parallel AIs) — CI uses scripted answers and
  a corpus of real breakage patterns.
* A physical phone: QR scan, pairing over Wi-Fi, standalone mode, bundle transfer PC ↔ phone.
* SmartScreen / antivirus behaviour of `Setup.bat` on a consumer machine.

These are listed, not passed. The release is published with them open, as decided for every 3.x step.
