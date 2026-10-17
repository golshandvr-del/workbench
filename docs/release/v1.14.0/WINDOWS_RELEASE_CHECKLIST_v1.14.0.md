# AI Workbench 1.14.0 — Native Windows Release Gate

**Status at package build:** NOT RUN in this environment. Linux/Xvfb and source-level checks do not substitute for native Windows verification. Do not mark this checklist passed without recording actual results from a Windows 10/11 machine.

Record for each run:
- Windows edition/build:
- Python executable/version and Tkinter probe result:
- Git version (or unavailable):
- Workbench release / installer SHA-256:
- Tester, date, and machine notes:

| ID | Test | Result (PASS/FAIL/BLOCKED/NOT RUN) | Evidence / notes |
|---|---|---|---|
| W01 | Clean install by double-clicking the final `.bat` | NOT RUN | Must be a real Explorer double-click, not direct `install.ps1` invocation |
| W02 | Upgrade from the prior release; confirm user settings and project data are preserved | NOT RUN | Record exactly what was retained/replaced |
| W03 | Reinstall and cancel/deny permissions; verify clear failure and no false success | NOT RUN | Include diagnostic location if produced |
| W04 | Launch through installed `pythonw` / VBS with no unwanted console; verify errors remain logged | NOT RUN | |
| W05 | Project path with spaces, Persian/Unicode characters, and ordinary long path | NOT RUN | Create → prompt → import → preview → selective apply → history |
| W06 | Apply two of five files; other three remain byte-identical | NOT RUN | Verify transaction manifest lists only selected files |
| W07 | Restore an overwritten file and remove an unchanged newly created file | NOT RUN | Verify restore event and new version-ledger record |
| W08 | Modify a file externally after Apply; restore must show conflict and refuse overwrite | NOT RUN | |
| W09 | Run `.bat`, `.cmd`, PowerShell and Python with spaces in executable/script/arguments | NOT RUN | Verify argv semantics and output evidence |
| W10 | Timeout, huge stdout/stderr, missing executable, child process, close UI during run | NOT RUN | Check process termination and bounded output |
| W11 | Validation profile: pass, nonzero exit, missing executable, timeout, stale/missing expected log, manual step | NOT RUN | Unknown/Blocked/Not run must not be reported Passed |
| W12 | Import mixed text + PNG/PDF ZIP; exact binary SHA-256 survives Apply and Restore | NOT RUN | No binary execution or direct ZIP extraction |
| W13 | Invalid/traversal/duplicate/case-colliding/symlink ZIP and oversized expansion | NOT RUN | No project files changed |
| W14 | Import, Preview, cancel, stale-preview invalidation, partial Apply, command dependency warning | NOT RUN | Import/Preview alone must have no side effects |
| W15 | Restore Manager: corrupted/missing backup, conflict, partial selection, undo Restore | NOT RUN | No forced overwrite path |
| W16 | Diagnostics export preview; confirm no source/prompt/response/full path/process output | NOT RUN | File stays local; no network upload |
| W17 | LTspice integration if installed | NOT RUN | Report real simulator result separately from mock/runner tests |
| W18 | Typed `workbench-v3` write/delete/rename/move; reject duplicate IDs, unsafe paths and existing destinations | NOT RUN | Verify preflight rejects before any mutation; manually inspect operation preview |
| W19 | Apply Delete then Restore; Apply Move then Restore both source and destination | NOT RUN | Confirm hash-guarded transaction manifest contains every endpoint and no force-overwrite path |
| W20 | Architecture-plan import → validate → edit → save → reload → export from Wizard and Project Profile | NOT RUN | Confirm plan does not modify source files and appears as reference context in next prompt |
| W21 | Save multiple model candidates, compare each destination, select Skip/one candidate, preview merged result | NOT RUN | Confirm defaults are Skip, merged result is revalidated, actions are omitted, and no change occurs before approval |
| W22 | Task Playbook selection persists and is visible in generated prompt | NOT RUN | Cover feature, bugfix, security, refactor and engineering/simulation playbooks |
| W23 | Static dependency graph and semantic diff UI | NOT RUN | Include unresolved imports, multi-language heuristic warning, scan-limit behavior and responsiveness on large repositories |
| W24 | Upgrade an existing install with populated older version; verify the new `aiwb\` package and all module files are installed | NOT RUN | Ensure app launches without `ModuleNotFoundError` and user settings/projects remain intact |

## Release decision

- Any failure in installation, path safety, stale-preview checks, transactional rollback, Restore hash checks, or binary integrity blocks release unless the release owner documents an explicit, reviewed exception.
- Every result must be based on observed evidence. Mock/Linux results must be labeled as such.
- This file is a checklist, not evidence that the Windows tests were executed.
