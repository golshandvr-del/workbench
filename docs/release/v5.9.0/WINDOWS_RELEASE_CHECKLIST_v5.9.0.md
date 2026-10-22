# Windows Release Checklist — AI Workbench 5.9.0 (core-path repair: the user decides the AI team)

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

## 5.9.0 specific (core-path repair, step 2: the user decides the team)

- [x] `test_team_setup.py` — agent ids from the user's names (`agent-<slug>`, Persian names, duplicates), the wizard
      writes brief + team with **no template agent**, sizes 1 / 3 / 5 / 12, bad input rejected before writing, the
      charter prompt binds the user's team, Edit team (rename / add / remove; an AI with work is disabled, not
      deleted; nothing changed = nothing written), older projects untouched + unused templates offered, every AI
      of the user's team keeps its Mission Map lane
- [x] `gui_wizard_smoke.py` — New Project wizard with **real widgets** for 1, 3, 5 and 12 AIs, Persian and English
      names: no "Architecture plan…" in creation, lanes named in the user's order on the real canvas, the next step
      is the charter prompt (no question repeated) and the prompt names every AI
- [x] `gui_team_editor_smoke.py` — *Add existing folder* → *Start the project…* is the same window (no chained
      question dialogs); *Agents › Team › Edit team…* rename / add / remove with the lanes following; an older
      project opens untouched and *Remove unused template AIs* removes only AIs without work
- [x] `gui_owner_path_smoke.py` — the owner's path now goes through the 3-step wizard (3 named AIs) to a file on disk
- [x] `gui_v114_smoke.py` — the architecture plan round-trip from *Tools › Architecture plan…*
- [x] App Map regenerated (`docs/UI_MAP.md`, `ui_map.png`); all 5.1.0 – 5.8.0 gates stay green
- [ ] NOT RUN: the wizard on real Windows 10/11 at 100–200 % DPI, with Persian names typed through a Persian
      keyboard layout, and a real project-manager answer pasted from the chat window

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Known open items and their release-owner decisions: `RELEASE_OWNER_DECISIONS_v5.9.0.md`. Rollback: `ROLLBACK_PLAN.md`.
