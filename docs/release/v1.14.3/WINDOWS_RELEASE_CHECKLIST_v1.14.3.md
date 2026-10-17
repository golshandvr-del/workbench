# Windows Release Checklist — AI Workbench 1.14.3

Status at packaging: **NOT RUN on native Windows**. Linux/Xvfb and local-Git tests are not a substitute.

## Install / update
- [ ] Install over a clean Windows 10/11 user profile using `AI_Workbench_1.14.3_Setup.bat`.
- [ ] Update over the prior 1.14.2 installation and confirm launch shortcut, `pythonw`, and application version.
- [ ] Confirm the installer copies `aiwb/github/repository_binding.py` and `test_github_repository_browser.py`.
- [ ] Launch the installed app and confirm the Git / GitHub tab lays out correctly at 1280x860 and at a smaller supported window.

## Credential and live API
- [ ] On a test account, connect a least-privilege Fine-grained PAT in Windows Credential Manager.
- [ ] Confirm `settings.json`, app logs and the project folder do not contain the PAT.
- [ ] Refresh repositories and confirm all pages load. For an account with multiple pages, confirm search works for repositories from later pages.
- [ ] Test an inaccessible/private repository and confirm a permission error is distinct from a network error.
- [ ] Revoke/replace the test PAT and confirm 401 updates the account status without printing the token.

## Repository binding
- [ ] Link an active project whose existing origin already matches; confirm no remote mutation.
- [ ] Link a project below a Monorepo root; confirm `local_git_root` is the root and `project_subpath` is the relative path.
- [ ] When origin is missing, cancel the prompt and confirm no origin is added; accept it and confirm the credential-free canonical URL is set.
- [ ] When origin points to a different repository, cancel and confirm it remains unchanged; accept replacement and confirm the URL is updated.
- [ ] Test a non-GitHub/SSH remote with embedded user information; ensure it is never shown or stored in binding settings.
- [ ] Confirm no Commit or Push is performed by Link.
- [ ] Close/reopen Workbench and confirm the binding is reloaded and displayed for the same project.
- [ ] Unlink the project and confirm binding metadata disappears but origin, working tree, commits and remote repository remain unchanged.
- [ ] Force binding-settings persistence failure in a disposable test project after changing origin; confirm the previous origin is restored or an explicit rollback warning is shown.

## Final gates
- [ ] `python -m compileall -q .`
- [ ] `python -m unittest discover -v`
- [ ] Run `gui_v1143_smoke.py` from the source archive under a real Windows desktop session (with mocked API transport).
- [ ] Run `test_windows_credential_store.py` on the intended Windows/Python architecture.
- [ ] Run `test_installer_packaging.py` against the generated installer and exact payload ZIP.
- [ ] Review `settings.json`, application log, and installed folder before declaring release-ready.
