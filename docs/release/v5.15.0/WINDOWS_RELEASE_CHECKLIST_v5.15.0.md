# Windows Release Checklist — AI Workbench 5.15.0 (gate of real scenarios S1–S9)

## Automated in GitHub Actions (`ci.yml` / `release-desktop.yml`, `windows-latest`)

- [x] Full unit/regression suite natively on Windows (Python 3.13) and Linux (3.10/3.13), incl. `test_rc_hardening.py`
- [x] Native Windows Credential Manager round-trip
- [x] `install.ps1` ⇄ `release_manifest.json` consistency gate; undefined-name gate (pyflakes); shared contracts gate
- [x] Reproducible `Setup.bat`; tag version must equal `APP_VERSION` and manifest
- [x] **Upgrade:** previous published `desktop-v*` installed first, sentinels written to `settings.json` and app data, then this build installed over it — sentinels must survive
- [x] Installed files and Desktop shortcut verified
- [x] GUI smoke of the installed copy, and of a copy under a **Unicode path with spaces** (`AI Wörkbench تست ü`)
- [x] All GUI smoke scripts against the installed copy
- [x] SHA-256 sums + contract `release-manifest.json` published with the release

## Automated against the real GitHub API (separate test repository `golshandvr-del/aiwb-e2e-sandbox`)

`tools/e2e_github_sandbox.py` — run 2026-10-18, all PASS (see `E2E_REPORT_v5.5.0.md (unchanged GitHub code paths)`):
preflight · sensitive file blocked · commit · idempotent commit · push · idempotent push · exact run of the pushed SHA (not the seed push) · build passed · artifact SHA-256 matched GitHub's digest · artifact content = pushed SHA · build-metadata contract · stale plan refused after a concurrent push · manual dispatch confirmed with run ID · no token in records/events/`.git/config` · branch cleanup. Paths contain spaces and Unicode.

## 5.15.0 specific (gate of real scenarios — the app driven like a person, REAL widgets and the real clipboard)

Shared driver `apps/desktop/tests/gui/scenario_driver.py` (counts clicks and pastes; any unexpected window, error box
or callback error fails the scenario). One script per scenario, run by `run_all.py` on Linux (xvfb) and against the
installed copy on Windows; screenshots `docs/audit/screens/v5.15-scenarios/`.

- [x] S1 `gui_scenario_s1_quick_smoke.py` — Quick, one AI chat, three files → Apply 3 files → round 2 → Restore
- [x] S2 `gui_scenario_s2_guided_smoke.py` — guided project, three AIs named by the user → charter → task → file on
      disk → Tests/build passed → first milestone accepted, never leaving Home
- [x] S3 `gui_scenario_s3_broken_smoke.py` — broken charter → fix prompt copied, nothing imported; sloppy charter
      (comments, trailing commas, smart quotes, bold markers) → auto-fixed; Markdown files → converted → on disk
- [x] S4 `gui_scenario_s4_continue_smoke.py` — cut-off answer → Copy the continue prompt → the rest → **both** files
      on disk (bug found and fixed: the files that arrived complete before the cut were lost; `guide.merge_partial`,
      `test_guide_continue.py`, 8 tests)
- [x] S5 `gui_scenario_s5_reopen_smoke.py` — close the app mid-work, open it again → same project, same step, same
      attempt → the answer lands
- [x] S6 `gui_scenario_s6_old_project_smoke.py` — a half-done project written by the REAL 5.7.0 code
      (`tests/fixtures/projects/v5.7.0_todo.zip`, `build_v570_project.py`) opens untouched and the work goes on
- [x] S7 `gui_scenario_s7_gpt_zip_smoke.py` — a ChatGPT ZIP (top folder, `AIWB_HANDOFF.json`, Mac noise) through the
      real Load ZIP… button → files on disk
- [x] S8 `gui_scenario_s8_context_smoke.py` — the owner's real GPT context request → files copied (folder expanded,
      `.env` refused) → delivery → on disk
- [x] S9 `gui_scenario_s9_windows_copy_smoke.py` — answers copied from the rendered Windows chat (line-end `\`,
      escaped `_`, CRLF): charter, task answer and Quick answer all land byte for byte
- [x] All 5.1.0 – 5.14.0 gates stay green (unit 863 + all GUI smokes)
- [ ] NOT RUN: install 5.15.0 over 5.14.0 on real Windows; S1–S9 by hand with real chats (GPT / Claude / Gemini)

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Known open items and their release-owner decisions: `RELEASE_OWNER_DECISIONS_v5.15.0.md`. Rollback: `ROLLBACK_PLAN.md`.
