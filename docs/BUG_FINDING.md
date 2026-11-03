# BUG FINDING — AI Workbench desktop (from 5.20.0)

Living document. Updated continuously during the bug hunt (each edit is its own checkpoint commit).
Goal: find problems **before** the owner shows the app to friends — especially places where the app can
**get stuck** (dead ends, crashes, lost data, misleading steps).

## Legend

| Field | Meaning |
|---|---|
| ID | `BF-NNN` |
| Severity | **S1** crash / data loss / stuck with no way out · **S2** wrong behaviour, workaround exists · **S3** cosmetic / docs / minor |
| Status | `OPEN` · `FIXED (commit)` · `WONTFIX (reason)` · `NOT A BUG` |
| How found | static analysis · unit/GUI tests · code review · scripted scenario |

## Method (session 9)

1. Unit test suite + GUI smoke suite (xvfb) on 5.20.0.
2. Static analysis (pyflakes / compileall) of `apps/desktop/src`.
3. Code review of the main user path: open/create project → charter → PM prompt → paste answer →
   proposals → tasks → developer prompt → files on disk → release; plus Quick mode, Settings, helper AI, Git.
4. Scripted "stuck" hunts: every Next-step state must offer an action; malformed / empty / huge pastes;
   corrupt or missing state files; non-ASCII paths; read-only folders.

## Summary

| Severity | Open | Fixed |
|---|---|---|
| S1 | 0 | 0 |
| S2 | 0 | 0 |
| S3 | 0 | 0 |

## Findings

### BF-001 · S2 · OPEN — a task whose prerequisite was cancelled: the offered button always fails

**Where:** `aiwb/v2/guide.py` `steps()` (task branches `draft/proposed` and `blocked`), `aiwb/v2/tasks.py`
`readiness()` / `_transition_in()`.

**Reproduce** (script `/tmp/hunt/a_dead_dep.py`, re-creatable from this text):
1. Task A, task B with `depends_on: [A]`. Cancel A (or the PM supersedes it).
2. B (draft) → Home shows **"Approve TASK-B"** with *Approve the task* (primary) / *Cancel…*.
   *Approve* → error `TASK-B is not ready: prerequisite no longer valid: TASK-A (cancelled) — re-plan this task`.
3. B (blocked "waiting for A") → becomes `blocked: prerequisite no longer valid …`, Home shows
   **"TASK-B is blocked"** with *It can continue now* (primary) → same error.

**Why it matters:** the primary button can never succeed. In the draft variant the only other button is *Cancel…*
(the work is lost); the "ask the project manager" step does not appear because this broken step counts as "something
waiting for you". No button removes the dead dependency.

**Expected:** a dead prerequisite gets its own step: *Drop the dead prerequisite and continue* / *Ask the project
manager to re-plan* / *Cancel…* — and never a button that is known to fail.

## Checked and OK

_(areas reviewed with no problem found are listed here so they are not re-checked after a reset)_
