# Windows Release Checklist — AI Workbench 1.14.4

**Release gate:** do not mark Windows-native verified until this checklist is completed on a real Windows 10/11 machine.

## Installation and upgrade
- [ ] Run `AI_Workbench_1.14.4_Setup.bat` by double-click from a standard user account.
- [ ] Confirm Python/Tkinter detection or installation completes and diagnostics are useful if it fails.
- [ ] Install over 1.14.3 and confirm project list, settings, account references, PAT credentials and history are retained.
- [ ] Confirm an original `settings.json` backup is created when schema-v1 repository bindings migrate to schema v2.
- [ ] Confirm migration can be repeated without changing already-migrated records.
- [ ] Confirm invalid/duplicate binding records are reported and original settings remain in the backup.
- [ ] Launch from Desktop and Start Menu shortcuts; close and relaunch without a console window.

## GitHub binding and Monorepo scope
- [ ] Open a Workbench project under a Git repository root and confirm Git root differs from project subpath when appropriate.
- [ ] Link one Repository and then link a second Workbench project under a different subpath to the same numeric Repository ID.
- [ ] Confirm Repository ID, account ID, owner/name, default branch, working branch, workflow, artifact pattern and channel persist.
- [ ] Rename repository owner/name or default branch on a test repository, refresh metadata by numeric ID and confirm binding remains linked.
- [ ] Confirm refreshing metadata does not rewrite `origin`; a mismatch is visibly reported.
- [ ] Create changes both inside and outside the active project subpath. Confirm both are visible and outside-scope entries are warned.
- [ ] Confirm Commit from the active subproject cannot stage sibling project changes implicitly.
- [ ] Run Initial Push Review with `.env`, a private key name, a test token-like fixture and a large file. Confirm warnings appear and no file is staged or committed.
- [ ] Confirm `.gitignore` suggestions do not alter existing content unless explicitly approved; if approved, only missing patterns are appended.
- [ ] Initialize an unversioned project. Confirm the branch is a non-main `workbench/initial-sync-*` branch and no file is staged/committed/pushed.
- [ ] Clone a test repository to a new destination; confirm existing destination folders are never overwritten.
- [ ] Configure binding preferences and confirm invalid workflow paths, branch names and release channels are rejected.
- [ ] Confirm multiple project bindings sharing the same `repository_id` are retained, while duplicate bindings for one project are not.

## Credential, privacy and error handling
- [ ] Check settings, backup and application logs contain no PAT or credential-bearing remote URL.
- [ ] Confirm Clone uses a credential-free `https://github.com/owner/repo.git` URL and configured Git Credential Manager handles private repositories.
- [ ] Confirm canceling each confirmation leaves the original `origin`, project files and stage/index unchanged.
- [ ] Confirm an origin replacement failure or metadata persistence failure reports whether rollback succeeded.

## Required evidence
- [ ] Record Windows edition/build, Git version and Python version.
- [ ] Attach a sanitized install log and results for the checks above.
- [ ] Mark only tests actually run; Linux/Xvfb and simulated payload-layout tests are not native Windows evidence.
