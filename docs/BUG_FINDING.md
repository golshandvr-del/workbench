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

### BF-002 · S1 · OPEN — an emergency task can deadlock the whole project silently

**Where:** `aiwb/v2/report.py` `apply_decision()` (emergency `blocks`), `aiwb/v2/proposals.py` `review()`.

**Reproduce** (script `/tmp/hunt/b_emergency_cycle.py`):
1. Task X (ready), task Y depends on X (blocked "waiting for X").
2. The PM sends a proposal: `create_task E1` (a hotfix) with `depends_on: [X]` and
   `emergency_tasks: [{"ref": "E1", "blocks": ["X"]}]` (a natural thing to write: "fix X first").
3. Accept the plan → message *"Emergency: TASK-E1 goes first; paused until it is done: TASK-X"*.
   Result: X depends on E1 and E1 depends on X → **cycle**. X, Y, E1 are all `blocked: waiting for …`.
   `waves()` reports `cycle: [X, Y, E1]`, no task can start.

**Why it matters:** `apply_decision` adds `blocks` edges to `depends_on` **after** `validate_graph()` ran, without a
cycle check. "waiting for …" tasks are hidden from Home **and** from the PM's "Stuck tasks" report section, so Home
only says *"Ask the project manager for the next step"* and the PM is told nothing is stuck → endless PM rounds,
no code. Exactly the kind of "stuck" the friends hit on 5.15.

**Expected:** a `blocks` edge that would make a cycle is skipped (with a note), and any dependency cycle among open
tasks is shown as a step (and reported to the PM as stuck).

### BF-003 · S1 · OPEN — when the task graph is already invalid, a plan cannot even be rejected

**Where:** `aiwb/v2/proposals.py` `review()` → `_apply()` runs `validate_graph(s["tasks"])` on the **whole** graph
even when `accept == []` (reject / *Ask for changes…*), and raises.

**Reproduce:** continue BF-002 (cycle exists). The PM sends any new plan. *Reject the plan* → error
`proposal not applied: resulting task graph is invalid: dependency cycle: TASK-X → TASK-E1 → TASK-X`.
*Ask for changes…* → same error, and the change-request prompt is not handed out. Only *Accept* works, and only if
the plan happens to break the cycle. A random-walk fuzz (30 projects) hit this 178 times.

**Why it matters:** a plan step that cannot be removed sits at the top of Home forever (rank 5) unless the user
accepts something they did not want.

**Expected:** reject never validates or changes the graph; accepting only fails for problems the plan **adds**.

### BF-004 · S1 · OPEN — removing a task's last prerequisite leaves it "blocked: waiting for …" forever (invisible)

**Where:** `aiwb/v2/tasks.py` `_refresh_readiness()` skips every task with an empty `depends_on`
(`... or not t.get("depends_on"): continue`); `aiwb/v2/proposals.py` `_apply()` (`remove_dependency`) never
re-derives readiness; `guide.steps()` hides blocked tasks whose reason starts with "waiting for".

**Reproduce** (script `/tmp/hunt/c_remove_dep.py`):
1. X ready, Y depends on X (blocked "waiting for X").
2. The PM sends `remove_dependency Y → X`, the user accepts.
3. Y: `blocked`, `depends_on: []`, reason still `waiting for TASK-X`. Even after X is **done**, Y never becomes
   ready (nothing re-checks a task with no prerequisites). Home never shows Y; the PM report does not list Y as stuck.

Same root cause after BF-002's cycle is broken with `remove_dependency`: the emergency-paused task stays
`blocked [] "waiting for E1 (emergency)"` forever.

**Why it matters:** a task silently disappears from the flow; the project ends with Home asking the PM "for the next
step" while a planned task never runs. The PM sees nothing stuck.

**Expected:** a blocked "waiting for/prerequisite" task with no open prerequisite becomes ready again
(`_refresh_readiness` must not skip `depends_on == []`; `_apply` must refresh readiness for every task).

## Checked and OK

_(areas reviewed with no problem found are listed here so they are not re-checked after a reset)_
