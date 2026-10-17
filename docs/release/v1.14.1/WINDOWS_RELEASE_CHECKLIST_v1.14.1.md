# AI Workbench 1.14.1 — Native Windows Release Gate

**Status at package build:** NOT RUN in this environment. Linux tests and source-level packaging checks do not constitute native Windows verification.

Record:
- Windows edition/build:
- Python version/Tkinter probe:
- Git for Windows version:
- Installer SHA-256:
- Tester/date/evidence:

| ID | Test | Result | Evidence / notes |
|---|---|---|---|
| W01 | Fresh install by Explorer double-click | NOT RUN | Use the final `.bat`, not a direct PowerShell invocation |
| W02 | Upgrade v1.14.0 → v1.14.1; retain settings/projects | NOT RUN | Confirm nested `aiwb\\git\\` modules are installed |
| W03 | Launch installed Workbench and verify version `1.14.1` | NOT RUN | Confirm no `ModuleNotFoundError` |
| W04 | Git version discovery through PATH and normal Git for Windows paths | NOT RUN | |
| W05 | Git status in project path with spaces and Persian/Unicode filenames | NOT RUN | |
| W06 | Status parser with untracked, modified, deleted and staged paths | NOT RUN | Compare Workbench display with `git status --porcelain=v1 -z` |
| W07 | Create-project option “Initialize a local Git repository” | NOT RUN | Confirm initialization now uses shared service and does not freeze UI |
| W08 | Missing Git and timed-out Git subprocess | NOT RUN | Clear user-visible messages; no false success |
| W09 | Git Credential Manager push on a work branch | NOT RUN | No credential appears in remote URL, command line, logs or errors |
| W10 | Branch creation, staged review, commit and push regression | NOT RUN | Confirm main/master direct-push guard still works |
| W11 | Installer payload integrity and nested module copying | NOT RUN | Offline byte-identity tests run separately; confirm installed files on Windows |

## Release decision

Any failure in installer launch, import of `aiwb.git`, Git status parsing, commit/push approval behavior or secret redaction blocks a production release until fixed or explicitly reviewed. Record actual target-machine results; never replace NOT RUN with PASS on the strength of Linux/mock tests.
