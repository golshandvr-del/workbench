# Windows Release Checklist — AI Workbench 5.14.0 (one project, one screen — owner audits B3–B5 and C1–C7)

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

## 5.14.0 specific (Quick mode — one AI chat, replaces the classic 1.x Prompt / AI Response pages)

- [x] `gui_quick_smoke.py` — **the gate**: New Project ▾ › Quick — one AI chat… → form → Quick window → Copy the
      prompt → **AIWB file blocks** pasted from the real clipboard → file list + diff → Apply → Restore last apply
      (folder back to before) → **Strict JSON** → Apply → **GPT ZIP** via Load ZIP… → Apply → cut-off answer → Copy
      the continue prompt → Home shows the Quick card (no template lanes on the map) → Make it a multi-AI project… →
      files untouched, Home shows the Project Charter step; screenshots `docs/audit/screens/v5.14-quick/`
- [x] Engine `aiwb/v2/quick.py` (`test_quick.py`, 15 tests): prompt per format, answers of the three formats + copy
      damage + cut-off + unsafe paths, plan/diff, apply with backup, hash-guarded restore, Quick → Guided
- [x] Quick paste check shows no multi-AI warnings ("no AIWB_HANDOFF manifest"); charters / context requests are
      explained as "not a Quick answer"
- [x] Settings › Classic tools (1.x) is gone: Settings › Tools = Project Profile, Run & Report; the Workbench has no
      "Classic prompt & response…" link; `test_commands.py` registers `project.new_quick`; `docs/UI_MAP.md` regenerated
- [x] All 5.1.0 – 5.13.0 gates stay green (unit 855 + 48 GUI smokes)
- [ ] NOT RUN: install 5.14.0 over 5.13.0 on real Windows; a Quick round with a real chat answer (GPT / Claude)

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Known open items and their release-owner decisions: `RELEASE_OWNER_DECISIONS_v5.14.0.md`. Rollback: `ROLLBACK_PLAN.md`.
