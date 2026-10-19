# Contributing

1. **Pick the step from [`ROADMAP.md`](ROADMAP.md).** Work only on the active step unless a fix is required. Do not rebuild features that already exist — check the code first.
2. **Branch** from `main` (`feat/…`, `fix/…`, `docs/…`, `ci/…`). `main` is protected by CI; changes land through pull requests.
3. **Small commits** with Conventional-Commit style messages (`feat(desktop/git): …`, `fix(installer): …`, `docs: …`).
4. **Tests are required.** New behaviour needs unit tests in `apps/desktop/tests/`; UI changes need a GUI smoke in `apps/desktop/tests/gui/`.
5. **New shipped file?** Add it to `apps/desktop/installer/install.ps1` **and** `apps/desktop/release_manifest.json`. `tools/check_installer_manifest.py` fails otherwise.
6. **Update `ROADMAP.md`** (status + checklist of the step) and `CHANGELOG.md` in the same PR.
7. **Never commit secrets** — tokens, keystores (`*.p12`, `*.jks`), `.env`. Signing material lives only in GitHub secrets.

## Running checks locally

```bash
cd apps/desktop && python -m unittest discover -s tests -t .
xvfb-run -a python tests/gui/run_all.py
cd ../.. && python tools/check_installer_manifest.py && python -m unittest tools/test_build_desktop_installer.py
```

## Product rules that reviews enforce

- No direct model API / model-account login; copy-paste with ordinary chats stays the workflow.
- No model output writes files or runs commands without preview and explicit user approval.
- No force push / hard reset / auto-commit in normal flows; push to `main`/`master` from the app stays blocked.
- Anything not actually run (e.g. native Windows checks) is reported as **NOT RUN**, never PASS.
- **Language policy:** the user interface is **English-only** for now, on both Desktop (Windows) and Android. Do not add or extend Persian (or any other) translations, RTL work or Persian-specific tests until the product owner explicitly asks for it in a later version. Gates run in English.
