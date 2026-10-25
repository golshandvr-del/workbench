# Windows Release Checklist — AI Workbench 5.11.0 (core-path repair: one clear work page — Home is the cockpit)

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

## 5.11.0 specific (core-path repair, step 4: Home = cockpit, audit A7)

- [x] `gui_owner_path_smoke.py` — **the gate**: New Project → first file on disk driven **only from Home** with real
      widgets (toolbar menu, wizard, the Next-step card's button / More menu and its **inline** paste panel); no modal
      dialog may open on the way; **11 clicks + 2 pastes** (≤ 12 required): New Project ▾ · Guided project · Next ·
      Next · Create project · Copy the charter prompt · Use this answer · Accept all valid changes · Prepare the prompt
      (also copies it) · Use this answer · Accept the delivery
- [x] `gui_v5_map_smoke.py` / `test_ui_balance.py` — App Map audit with the new rule **at most 8 controls visible at
      once per page** (was 10): Home 6, Projects 8, Run & Report 8, Agents 8, History 8, Settings 7; no command with two
      homes (the Workbench's next-step strip is a *link* to Home; the card's own buttons are *dynamic* controls)
- [x] `test_next_card.py` — the card model: AI names instead of ids, primary + More, the paste action as the inline
      panel, focus on one AI's queue (Mission Map click), "Back to the next step"
- [x] `test_workspace.py` — the Project Workbench has 3 sections (Plan & Tasks · Timeline · Project settings); the old
      section keys (`overview`, `tasks`, `team`, `files`, `versions`, `settings`) still open the section that holds
      them, also from an old `ui.json`
- [x] `gui_paste_box_smoke.py` — live diagnosis, *Load ZIP…* and Markdown answers to files, now in Home's inline panel
- [x] `gui_guide_smoke.py`, `gui_wizard_smoke.py`, `gui_team_editor_smoke.py`, `gui_charter_smoke.py`,
      `gui_team_planner_smoke.py` — driven from Home's card; removed duplicates (*Design the whole project…*,
      *Plan project…*, *Plan team & tasks…*, the Workbench's parallel-chats box) stay gone
- [x] After *Create project* the app shows **Home** (not the Workbench, not the 1.x Profile)
- [x] All 5.1.0 – 5.10.0 gates stay green
- [ ] NOT RUN: the owner's path on real Windows 10/11 with answers from real ChatGPT / Claude / Gemini windows

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Known open items and their release-owner decisions: `RELEASE_OWNER_DECISIONS_v5.11.0.md`. Rollback: `ROLLBACK_PLAN.md`.
