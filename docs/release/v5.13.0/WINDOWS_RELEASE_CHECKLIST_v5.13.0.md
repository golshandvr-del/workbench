# Windows Release Checklist — AI Workbench 5.13.0 (one project, one screen — owner audits B3–B5 and C1–C7)

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

## 5.13.0 specific (one project, one screen — ROADMAP §1b B3, B4, B5 and §1c C1–C7)

- [x] **Update really updates (C1)**: `test_stale_bytecode.py` reproduces the 5.12 bug (same size + same mtime, old
      `.pyc` keeps running) and checks both fixes — `install.ps1` deletes every `__pycache__`/`*.pyc` before copying
      and runs `compileall -f`; `launch_aiwb.clear_stale_bytecode` clears caches once when the version stamp changes
- [x] `gui_owner_path_smoke.py` — **the gate**: New Project → Charter → context request → files → answer → Accept →
      Tests passed → Milestone accepted, only from Home, **14 clicks + 3 pastes**; screenshots
      `docs/audit/screens/v5.13-one-screen/`
- [x] Rail of four (Home · Agents · History · Settings); project switcher in the toolbar; Settings › Project
- [x] Mission Map columns carry milestones/versions (`test_column_menu.py`); History is one filtered list
      (`test_history_feed.py`); every command has one home (`test_commands.py`); guide/status say AI names, never ids
      (`test_user_words.py`)
- [x] C2 no blank button on the Next-step card · C3 no "Charter start prompts" in Project settings · C4 timeline lanes
      named and readable · C5 card role in user words, Edit team… on the title row · C6 Balance button only with moves,
      stuck alerts say what to do · C7 App Map out of Settings (Ctrl+Shift+F12)
- [x] All 5.1.0 – 5.12.0 gates stay green (unit 840 + 47 GUI smokes)
- [ ] NOT RUN: install 5.13.0 over 5.12.0 on real Windows and check the title says 5.13.0

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Known open items and their release-owner decisions: `RELEASE_OWNER_DECISIONS_v5.13.0.md`. Rollback: `ROLLBACK_PLAN.md`.
