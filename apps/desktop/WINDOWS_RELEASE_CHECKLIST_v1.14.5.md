# Windows Release Checklist — AI Workbench 1.14.5

Automated in GitHub Actions (`ci.yml` / `release-desktop.yml`, `windows-latest`):

- [x] Full unit/regression suite natively on Windows (Python 3.13) — 242 tests
- [x] Native Windows Credential Manager round-trip (`test_windows_credential_store.py`)
- [x] `install.ps1` ⇄ `release_manifest.json` consistency gate
- [x] Build `Setup.bat` reproducibly; tag version must equal `APP_VERSION` and manifest
- [x] Install from `Setup.bat` on a clean runner; installed files and Desktop shortcut verified
- [x] GUI startup smoke of the **installed** copy (7 main tabs)
- [x] Git Review & Sync window smoke (real repo + local bare remote)
- [x] SHA-256 sums published with the release

Manual checks recommended on a real user machine (not automatable in CI):

- [ ] Double-click `AI_Workbench_1.14.5_Setup.bat` on a PC **without** Python (winget install path)
- [ ] Git tab → *Review & Sync…* against a real GitHub repository: Fetch, commit selected, push to a work branch
- [ ] Push with Git Credential Manager interactive login
- [ ] Upgrade over an existing 1.14.4 install keeps settings and projects
