# Windows Release Checklist — AI Workbench 5.7.0 (5.x — Agents hub)

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

## 5.7.0 specific

- [x] `test_agent_hub.py` — per-AI stats from recorded facts only, idle/stuck/overloaded alerts, rebalance plan moves
      only unstarted `ready` tasks, queue order, self-contained briefing, memory note goes into "Your role"
- [x] `test_agents_cards.py` — card numbers = Mission Map lane numbers, state words, note round-trip, rebalance writes
      in one store transaction
- [x] `gui_v5_agents_smoke.py` — one card per enabled AI, alerts + suggested move under Balance, card click selects,
      Copy briefing writes nothing, Memory note… persists and reaches the next prompt, Apply suggested moves evens the
      load; Midnight and Daylight screenshots in `docs/design/screens/`
- [x] Layout smoke at 1024x640: the Agents page scrolls, nothing clipped; App Map regenerated, audit balanced
- [x] All 5.1.0 – 5.5.0 gates stay green
- [ ] NOT RUN: Agents page on real Windows 10/11 at 100/150 % scaling

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Known open items and their release-owner decisions: `RELEASE_OWNER_DECISIONS_v5.7.0.md`. Rollback: `ROLLBACK_PLAN.md`.
