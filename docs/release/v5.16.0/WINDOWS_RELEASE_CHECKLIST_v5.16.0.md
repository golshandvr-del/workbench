# Windows Release Checklist — AI Workbench 5.16.0 (light and smooth: state cache, bounded animation, fast closable menu)

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

## 5.16.0 specific (light and smooth — roadmap R2 R3 R4)

- [x] State cache (`v2/store.py`): migrated state kept per file stat signature (mtime_ns, size, inode) as pickle
      bytes; every `load()` is an independent copy; a file changed by another process is re-read. 600 KB project:
      load 20 → 3.5 ms, `Guide.steps` 20 → 2.5 ms, write transaction 64 → 38 ms (`test_store_cache.py`, 10 tests)
- [x] Mission Map live loops (`mission:pulse`, `mission:particles`) play 6 s after a change, then stand still; they stop
      when the map is hidden. Idle app: 42 → 0 frames/s (`gui_v516_light_smoke.py`)
- [x] Menu panel sprite drawn small and 9-sliced: pixel-identical (`test_raster_9slice.py`), menu first open
      ~700 ms → ~110 ms (Linux xvfb), later opens ~20 ms
- [x] Floating menus close on page switch, a click anywhere else, main window moved/resized/minimised
      (`menu5.close_all`, `install_auto_close`; `gui_v516_light_smoke.py`)
- [x] Status poll: `state.json` unchanged → no read, no redraw, no listener (`AppShell._poll_once`, `status_state` cache)
- [x] All 5.1.0 – 5.15.0 gates stay green (unit 876 + all GUI smokes incl. S1–S9)
- [ ] NOT RUN: install 5.16.0 over 5.15.0 on real Windows; right-click menu feel and idle CPU checked by hand

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Rollback: `ROLLBACK_PLAN.md`.
