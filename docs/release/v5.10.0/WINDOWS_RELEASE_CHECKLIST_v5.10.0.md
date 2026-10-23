# Windows Release Checklist — AI Workbench 5.10.0 (core-path repair: whatever the model returns, it works)

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

## 5.10.0 specific (core-path repair, step 3: robust intake)

- [x] `test_answer_corpus.py` — **the gate**: 54 stored chat answers in `apps/desktop/tests/fixtures/answers/`
      (30 charters, 24 file answers; GPT, Claude, Gemini, DeepSeek and Copilot shapes, chat copy damage, rendered
      Markdown, CRLF/NBSP/zero-width, ZIPs, cut-off answers) replayed into a fresh project: 49/49 usable answers
      accepted (≥ 95 % required), the other 5 refused with a precise fix prompt or a continue prompt; the corpus is
      rebuilt byte-for-byte by `build_corpus.py`
- [x] `test_v2_charter.py` — lenient charter: unmarked / fenced / unclosed blocks, numeric schema, text revision,
      role and id synonyms, short versions, strings for lists, dictionaries for lists, comments, missing
      coordination and overlapping ownership are warnings; only ambiguous answers are refused, every fix is listed
- [x] `test_answer_files.py` — files from AIWB blocks, Markdown (`**path**`, `### path`, `` `path` ``, `File:`,
      `title="…"`, first-line comment), Strict JSON and ZIP; ZIP limits (size, count, unsafe paths, binaries); the
      guided loop from each format to files on disk
- [x] `test_answer_preview.py` — the live diagnosis of the paste box is read-only and never raises
- [x] `gui_paste_box_smoke.py` — the **real** paste box: live diagnosis while typing, *Load ZIP…*, a Markdown answer
      to files on disk
- [x] `gui_wizard_smoke.py` — all three answer formats can be chosen and are kept
- [x] All 5.1.0 – 5.9.0 gates stay green
- [ ] NOT RUN: answers pasted by the owner from real ChatGPT / Claude / Gemini / DeepSeek / Copilot windows on real
      Windows 10/11 (the corpus answers are reconstructed shapes; owner answers that fail are added to the corpus)

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Known open items and their release-owner decisions: `RELEASE_OWNER_DECISIONS_v5.10.0.md`. Rollback: `ROLLBACK_PLAN.md`.
