# Windows Release Checklist — AI Workbench 1.14.6

Automated in GitHub Actions (`ci.yml` / `release-desktop.yml`, `windows-latest`):

- [x] Full unit/regression suite natively on Windows (Python 3.13)
- [x] Native Windows Credential Manager round-trip
- [x] `install.ps1` ⇄ `release_manifest.json` consistency gate
- [x] Reproducible `Setup.bat`; tag version must equal `APP_VERSION` and manifest
- [x] Install from `Setup.bat` on a clean runner; installed files and Desktop shortcut verified
- [x] All GUI smoke scripts against the **installed** copy, including the Build Center window (fake GitHub transport)
- [x] SHA-256 sums published with the release

Manual checks recommended on a real user machine (not automatable in CI):

- [ ] GitHub tab → *Build Center…* on a linked real repository: workflows listed, "Manual run" column matches the files
- [ ] Select the main Build workflow; rename the file on GitHub → stale warning appears
- [ ] Push a commit → Build Center says "No run yet for local HEAD" until the new run appears, then shows its result
- [ ] Cancel an in-progress run with a token that has Actions: write; a read-only token shows a permission error
- [ ] Upgrade over 1.14.5 keeps settings, accounts and bindings
