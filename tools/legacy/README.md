# Legacy release tools (from the original 1.14.4 source)

Kept for provenance and as an **independent** cross-check of the current builder.

| File | Status |
|---|---|
| `build_installer.py` | Original single-step builder (`--payload ZIP --output BAT`). Superseded by `tools/build_desktop_installer.py` (builds the payload from `release_manifest.json`, byte-reproducible). Do not use for releases. |
| `test_installer_packaging.py` | Original packaging verifier, written independently of the new builder. CI runs it against every freshly built installer. Only change: the checklist file name follows the release version. |
