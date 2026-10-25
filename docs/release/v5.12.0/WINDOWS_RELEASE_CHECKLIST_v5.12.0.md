# Windows Release Checklist — AI Workbench 5.12.0 (real chat answers work — owner audit B1, B2, B8)

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

## 5.12.0 specific (real chat answers — owner audit of 5.11.0, ROADMAP §1b B1, B2, B8)

- [x] `gui_context_smoke.py` — **the gate**: the owner's real GPT answer (a context request with `required_files`, no
      `type`, a folder) put on the **real clipboard as a Windows rendered copy** (every line ends with `\`, `_`
      escaped) and pasted with `<<Paste>>` into Home's inline panel → the card turns into "<AI> asked for 4 files" →
      *Copy the files for the chat* → *I sent them* → the delivery is pasted and accepted
- [x] `test_copy_damage.py` — `strip_copy_damage` removes the line-end `\` and Markdown escapes, never inside a code
      block; the owner's answer round-trips (B1)
- [x] `test_context_forgiving.py` — a context request is read with synonyms (`required_files`, `paths`, …), plain
      paths, folders, a missing `type`; the paste preview uses the real parser (no "✓" that then does nothing) (B2)
- [x] `test_context_step.py` — request → files step → copy (text, or ZIP when big) → sent → answer; secrets never
      leave; the step is cleared by the answer (B2)
- [x] Every prompt ends with the *whole answer in one five-backtick code block* rule (B1)
- [x] Answer corpus: 60 cases incl. the owner's real answer (clean + Windows copy) and Windows-copied files and
      charter; the corpus must hold owner answers (B8)
- [x] All 5.1.0 – 5.11.0 gates stay green (unit + 47 GUI smokes)
- [ ] NOT RUN: the owner's path on real Windows 10/11 with answers from real ChatGPT / Claude / Gemini windows

## Manual checks on a real user machine — NOT RUN until ticked

- [ ] Git Credential Manager prompt flow on a fresh Windows profile (HTTPS push with GCM instead of PAT)
- [ ] Disconnect the network during push in the GUI: log says the local commit WAS created and is kept; reconnect → push completes without a second commit (covered by unit test `test_resume_after_lost_push_result_needs_no_second_commit`, not by hand)
- [ ] Real secondary-rate-limit response from GitHub shown in Build Center (covered by unit tests only)
- [ ] Close and reopen the Sync & Build window during CI: the app offers to resume
- [ ] SmartScreen / antivirus behaviour on `Setup.bat` on a consumer machine

Known open items and their release-owner decisions: `RELEASE_OWNER_DECISIONS_v5.12.0.md`. Rollback: `ROLLBACK_PLAN.md`.
