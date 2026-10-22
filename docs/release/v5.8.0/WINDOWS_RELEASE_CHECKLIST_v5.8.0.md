# Windows Release Checklist — AI Workbench 5.8.0 (5.x — one job per page)

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

## 5.8.0 specific (core-path repair, step 1: stop the bleeding)

- [x] `test_ui_call_signatures.py` — every `ui_layout.*` call matches the helper's real signature (catches the 5.7.0
      `place_dialog() missing 1 required positional argument: 'height'` crash; verified red on the old code)
- [x] `test_profile_to_charter.py` — the saved Project Profile (platform, language, framework …) is in the charter
      prompt; defaults such as "Let AI recommend" are left out; a missing or broken `project.json` is harmless
- [x] `gui_owner_path_smoke.py` — the owner's path with **real widgets**: New Project › Guided → Workbench (not the
      old Profile) → the five start questions in their real dialogs → Copy the charter prompt → More › Paste the
      charter in the **real paste box** → Accept → task prompt → I sent it → real paste box → Accept → the file is
      on disk; status bar never says "No project open"; no callback error (verified red with the 5.7.0 call)
- [x] All 5.1.0 – 5.7.0 gates stay green
- [ ] NOT RUN: the same path on real Windows 10/11 with a real GPT / Claude answer pasted from the chat window

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Known open items and their release-owner decisions: `RELEASE_OWNER_DECISIONS_v5.8.0.md`. Rollback: `ROLLBACK_PLAN.md`.
