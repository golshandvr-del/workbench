# Windows release checklist — AI Workbench 1.14.2

## Automated in the available build environment
- [x] `python -m compileall -q .` — PASS
- [x] `python test_github_accounts.py` — 23 tests PASS: API transport, account lifecycle, redaction, and test-store behavior
- [x] `python -m unittest discover -v` — 205 tests PASS
- [x] GUI smoke flows under Xvfb — 12/12 PASS, including GitHub Accounts panel, background-thread settings persistence and settings redaction
- [x] `python test_installer_packaging.py AI_Workbench_1.14.2_Setup.bat AI_Workbench_v1.14.2_Windows_Payload.zip` — PASS
- [x] Payload contains all `aiwb/github/` runtime modules and the native storage test
- [x] Embedded payload bytes match the source ZIP byte-for-byte
- [x] Synthetic-token tests verified settings metadata does not contain the token. No live PAT was provided. Test/source archives intentionally contain fake token-shaped fixtures; a real Windows install must still be inspected for leakage.

## Must run on a real Windows 10/11 target before declaring the release Windows-verified
- [ ] Install/upgrade with the actual one-click `.bat` installer and start Workbench twice
- [ ] Run `python test_windows_credential_store.py`; verify set/read/replace/delete succeeds and the test entry is removed from Windows Credential Manager
- [ ] Start with a valid fine-grained PAT and confirm the GitHub login/numeric user ID shown by `GET /user`
- [ ] Use an intentionally invalid dummy token and verify `401` is distinct, safe, and does not persist it
- [ ] Test a revoked PAT; confirm status changes to `Needs re-authentication`
- [ ] Simulate/observe `403`, `429`, network unavailable and timeout without freezing Tkinter
- [ ] Replace a credential for the same GitHub account; verify previous entry is removed
- [ ] Attempt to replace with a token for a different account; verify no credential change occurs
- [ ] Disconnect an account; verify only the Workbench account and associated API credential are removed. Confirm project folders, local Git history, remotes, and Git Credential Manager entries remain unchanged
- [ ] Search `%LOCALAPPDATA%\AIWorkbench\settings.json`, app logs, installed files, and Git remote URLs for the test PAT; no match must exist
- [ ] Check GitHub organization/PAT policy behavior; do not interpret successful identity verification as proof of repository, Actions, or write permission

## Release status for this build
Native Windows execution is not available in the current build environment. All automated Linux/Xvfb and package-level checks above are recorded as PASS; native Windows items below remain **NOT RUN**, not PASS.
