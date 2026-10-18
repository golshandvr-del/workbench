# Rollback plan (desktop and mobile)

Applies from 1.14.13 onward. Tags are never moved (ADR-005).

## Desktop (Windows)
1. **Bad release detected** → mark the GitHub Release as *pre-release* (removes it from "Latest") and add a warning line at the top of its notes.
2. Users reinstall the previous good version: download `AI_Workbench_<prev>_Setup.bat` from its release and run it. The installer only replaces files under `%LOCALAPPDATA%\Programs\AIWorkbench`; user data in `%LOCALAPPDATA%\AIWorkbench` (settings, accounts metadata, bindings, `.workbench/` project records) is **not** touched. Tokens stay in Windows Credential Manager.
3. Settings written by a newer version are tolerated by older versions (unknown keys ignored; binding schema v2 since 1.14.4). If a future schema bump is not backward-compatible, its release notes must say so and the app keeps a `*.bak` copy before migrating.
4. Fix forward with a new patch tag (`desktop-vX.Y.Z+1`) from `main` after CI is green.

## Mobile (Android)
1. Mark the release as pre-release; do not delete it (APK hashes are referenced by the release manifest).
2. Android cannot downgrade `versionCode`; the fix is always a new release with a higher `versionCode`. Users may uninstall/reinstall an older APK (data loss limited to app-local caches).

## Repository
- A wrong tag that has **not** published yet: delete the tag and cancel the release run immediately.
- A broken merge on `main`: revert PR (`git revert -m 1 <merge>`) through a normal PR; never force-push `main`.
