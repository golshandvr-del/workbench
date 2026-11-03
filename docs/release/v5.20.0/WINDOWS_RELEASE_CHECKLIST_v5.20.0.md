# Windows Release Checklist — AI Workbench 5.20.0 (clear forms: the question, the options, the recommendation)

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

## 5.20.0 specific (clear forms — roadmap R5)

- [x] `v2/choices.py`: options and a recommendation read from a decision record, the latest handoff's `decision_requests` or the question text (bullets, "Options:", (a)(b), "A or B?"); never invents options (`test_choices.py`, 14 tests)
- [x] Guide steps that need a `choice` carry `choices` = question + options + recommended (names as the user named the AIs)
- [x] `ui/action_form.py`: ONE window for all inputs of a step — title, full question, radio options ("(recommended)" pre-selected; nothing pre-selected without a recommendation), "Other answer…" box, passed/failed radios, reason with its default; Enter = OK, Esc = Cancel; a missing answer is named and the window stays open
- [x] Used by Home's card and the Workbench (`guide_action`), the Mission Map task menu and column menu; no `simpledialog.askstring` for step inputs (`gui_v517_forms_smoke.py` patches it to fail)
- [x] All 5.1.0 – 5.16.0 gates stay green (unit 890 + all GUI smokes incl. S1–S9 and 5.16 light smoke)
- [ ] NOT RUN: the decision form on real Windows (fonts, DPI 125/150 %, keyboard Tab order)

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Rollback: `ROLLBACK_PLAN.md`.
