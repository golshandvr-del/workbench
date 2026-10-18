# Windows Release Checklist — AI Workbench 1.14.7

Automated in GitHub Actions (`ci.yml` / `release-desktop.yml`, `windows-latest`):

- [x] Full unit/regression suite natively on Windows (Python 3.13)
- [x] Native Windows Credential Manager round-trip
- [x] `install.ps1` ⇄ `release_manifest.json` consistency gate
- [x] Reproducible `Setup.bat`; tag version must equal `APP_VERSION` and manifest
- [x] Install from `Setup.bat` on a clean runner; installed files and Desktop shortcut verified
- [x] All GUI smoke scripts against the **installed** copy, including Build Center and the Run workflow / Artifacts dialogs (fake GitHub transport)
- [x] SHA-256 sums published with the release

Manual checks recommended on a real user machine (not automatable in CI) — NOT RUN until ticked:

- [ ] Build Center → select a workflow with `workflow_dispatch` → *Run workflow…*: the form shows the file's real inputs (choice/boolean/number/string), required inputs are enforced
- [ ] Run it on a test branch: the dialog reports the run ID (or explicitly "Not confirmed"); a workflow without `workflow_dispatch` has the button disabled
- [ ] *Artifacts…* on a finished run: size/expiry/digest shown; expired artifacts cannot be downloaded
- [ ] Download to a folder with spaces/Unicode in its path: SHA-256 is shown with "matches GitHub digest" or "computed (no reference)"; no `.part` file is left after a cancelled download
- [ ] *Extract safely…* creates a new folder; extracting twice refuses (folder exists)
- [ ] Upgrade over 1.14.6 keeps settings, accounts and bindings
