# Windows Release Checklist — AI Workbench 1.14.9

Automated in GitHub Actions (`ci.yml` / `release-desktop.yml`, `windows-latest`):

- [x] Full unit/regression suite natively on Windows (Python 3.13)
- [x] Native Windows Credential Manager round-trip
- [x] `install.ps1` ⇄ `release_manifest.json` consistency gate
- [x] Reproducible `Setup.bat`; tag version must equal `APP_VERSION` and manifest
- [x] Install from `Setup.bat` on a clean runner; installed files and Desktop shortcut verified
- [x] All GUI smoke scripts against the **installed** copy, including Build Center and the Run workflow / Artifacts dialogs and the Sync & Build window (real Git + local bare remote, fake GitHub)
- [x] SHA-256 sums published with the release

Manual checks recommended on a real user machine (not automatable in CI) — NOT RUN until ticked:

- [ ] GitHub tab → *Sync & Build…* on a linked test repository with a work branch and a selected Build workflow: *Check* lists preflight results and changes; sensitive files are not selectable
- [ ] Commit + Push + Build: the commit appears on the work branch; the window shows the run of **this** commit only, then Build Passed/Failed
- [ ] Disconnect the network during push: the log says the local commit WAS created and is kept; reconnect, press the button again → push completes without a second commit
- [ ] Download & verify artifacts: files saved, SHA-256 shown as matched/computed
- [ ] Cancel at each stage: before commit nothing changes; after push the run is cancelled on GitHub and the commit stays
- [ ] Close and reopen the window during CI: the app offers to resume the operation
- [ ] Upgrade over 1.14.7 keeps settings, accounts and bindings
