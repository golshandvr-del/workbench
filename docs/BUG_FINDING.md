# BUG FINDING — AI Workbench desktop (from 5.20.0)

Living document. Discovery baseline and repair evidence (each edit is its own checkpoint commit). Session 29 entered root-cause repair under ROADMAP V5.21–V5.30.
Goal: find problems **before** the owner shows the app to friends — especially places where the app can
**get stuck** (dead ends, crashes, lost data, misleading steps).

## Legend

| Field | Meaning |
|---|---|
| ID | `BF-NNN` |
| Severity | **S1** crash / data loss / stuck with no way out · **S2** wrong behaviour, workaround exists · **S3** cosmetic / docs / minor |
| Status | `OPEN` · `FIXED (commit)` · `WONTFIX (reason)` · `NOT A BUG` · `DUPLICATE (of BF-NNN)` |
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
| S1 | 0 | 11 (BF-002, BF-003, BF-004, BF-007, BF-009, BF-010, BF-016, BF-043, BF-076, BF-078, BF-079) |
| S2 | 1 (BF-008) | 40 (BF-001, BF-005, BF-011, BF-013, BF-014, BF-017, BF-019, BF-021, BF-023, BF-025, BF-026, BF-029, BF-030, BF-032, BF-033, BF-035, BF-039, BF-041, BF-042, BF-045, BF-046, BF-048, BF-051, BF-053, BF-054, BF-055, BF-072, BF-074, BF-077, BF-080, BF-081, BF-091, BF-092, BF-096, BF-101, BF-103, BF-105, BF-106, BF-108, BF-109) |
| S3 | 0 | 54 (BF-006, BF-012, BF-015, BF-018, BF-020, BF-022, BF-024, BF-027, BF-028, BF-031, BF-034, BF-036, BF-037, BF-038, BF-040, BF-044, BF-047, BF-052, BF-056, BF-057, BF-058, BF-059, BF-060, BF-061, BF-062, BF-063, BF-064, BF-065, BF-066, BF-067, BF-068, BF-069, BF-070, BF-071, BF-073, BF-075, BF-082, BF-083, BF-084, BF-085, BF-086, BF-087, BF-088, BF-089, BF-093, BF-094, BF-095, BF-097, BF-098, BF-099, BF-100, BF-102, BF-104, BF-107) |
| — | Duplicates (not counted): BF-049 → BF-023, BF-050 → BF-021, BF-090 → BF-069 | |

**Session 41 checkpoint:** 105/106 FIXED (99.06% count-based), 1 OPEN (BF-008: Windows-invalid path names, needs a real Windows/Android gate). Session 41 repaired BF-045 (title/short-id assessments never create duplicates, title prerequisites resolve against existing and same-answer tasks, ambiguity is reported), BF-046 (assessment comments become the operation reason, never the objective; owner_role normalised through role_of in rescue and review), BF-060 (Persian Overview/Project labels via tr(), `why_text()` for queue explanations, regression scan of shell.py literals) and the BF-083 phone port (`decisionList`/`blockedReason` in core/Project.kt; needs_decision card text is the question on Desktop and phone). Desktop suite 1101 tests OK, 0 undefined names; Kotlin JVM suite 128 tests OK (standalone kotlinc). No GUI-on-real-Windows/APK/lint/device gate.

**Session 40 checkpoint:** 102/106 FIXED (96.23% count-based), 4 OPEN (BF-008, BF-045, BF-046, BF-060). Session 40 repaired BF-068/069/070/071/072/073/074/075/077/082/099/100/102 (Desktop + Mobile Kotlin where applicable). BF-083 Mobile port (core/Project.kt) still missing. Desktop suite 1097 tests OK; Kotlin JVM suite 125 tests OK (+3 new) compiled with standalone kotlinc and the whole Android tree type-checks against android.jar. No GUI-on-real-Windows/APK/lint/device gate.

**Session 39 checkpoint:** 89/106 FIXED (83.96% count-based), 17 OPEN (0 S1 / 6 S2 / 11 S3). Catalog statuses now include the sessions 37-38 repairs (BF-006/040/056/062/067/083/084/086/098, BF-085/080/005/021/023/019/030) and 19 findings repaired in session 39 (BF-096/097/101/103/107/036/037/038/041/058/059/018/020/034/022/025/029/087/088). BF-083's Mobile port (core/Project.kt) and BF-045/046 (partial) remain open. Full Desktop suite 1070 tests OK, 0 undefined names; no Mobile JVM run, no GUI/native Windows/Android gate this session.

**Session 36 checkpoint:** 23 additional catalogued findings repaired; 54/106 FIXED (50.94% count-based), 52 OPEN (0 S1 / 18 S2 / 34 S3). BF-045/046/098 have partial work and remain OPEN. This is not 50 bugs fixed in this session. Final source 66ccc8a3: 1009 Desktop tests OK (10 skipped), 120 Mobile JVM tests OK, zero undefined names. No GUI/native Windows/Android APK/device gate or release was run this session.

**Remaining top risks:** BF-008 actual Windows/Android gates; remaining lifecycle, intake, persistence and UI findings. Session-34 fixes have Desktop unit and real Kotlin/JVM regression evidence, NOT an Android APK/device/instrumentation or frozen full GUI pass. File exception rollback is not a database/filesystem power-loss transaction; backups/journals remain for manual recovery.

## Findings

### BF-001 · S2 · FIXED (8e322986) — a task whose prerequisite was cancelled: the offered button always fails

**Repair evidence — session 29 / V5.22–V5.23:** Desktop repair: dead prerequisites now offer a manager re-plan and explicit dependency removal, not a known-failing Approve/Unblock. Guide regression covers draft and blocked variants, the generated prompt, and successful removal without reviving cancelled work. Original reproduction below is retained as historical evidence. Linux regression validated; Windows release gate is still pending.

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

### BF-002 · S1 · FIXED (d10a0538, c7935b2c, 8e322986) — an emergency task can deadlock the whole project silently

**Repair evidence — session 29 / V5.22–V5.23:** Desktop repair: emergency edges are checked against the cumulative graph before retention; unsafe edges are skipped with a user-visible note. Preview and review share emergency application and final validation. Existing corrupt graphs are visible on Home and in the manager report. Tests cover cycle refusal, preview non-mutation and legacy-cycle recovery. Original reproduction below is retained as historical evidence. Linux regression validated; Windows release gate is still pending.

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

### BF-003 · S1 · FIXED (c7935b2c) — when the task graph is already invalid, a plan cannot even be rejected

**Repair evidence — session 29 / V5.22–V5.23:** Desktop repair: rejecting a nonempty proposal exits before graph validation/readiness/emergency mutation. Tests check unchanged task records in cyclic state, stored rejection note and real guided Ask for changes. Accepting a plan still requires a valid resulting graph; this does not silently permit unrelated graph corruption. Original reproduction below is retained as historical evidence. Linux regression validated; Windows release gate is still pending.

**Where:** `aiwb/v2/proposals.py` `review()` → `_apply()` runs `validate_graph(s["tasks"])` on the **whole** graph
even when `accept == []` (reject / *Ask for changes…*), and raises.

**Reproduce:** continue BF-002 (cycle exists). The PM sends any new plan. *Reject the plan* → error
`proposal not applied: resulting task graph is invalid: dependency cycle: TASK-X → TASK-E1 → TASK-X`.
*Ask for changes…* → same error, and the change-request prompt is not handed out. Only *Accept* works, and only if
the plan happens to break the cycle. A random-walk fuzz (30 projects) hit this 178 times.

**Why it matters:** a plan step that cannot be removed sits at the top of Home forever (rank 5) unless the user
accepts something they did not want.

**Expected:** reject never validates or changes the graph; accepting only fails for problems the plan **adds**.

### BF-004 · S1 · FIXED (a2f3dcc3, c7935b2c) — removing a task's last prerequisite leaves it "blocked: waiting for …" forever (invisible)

**Repair evidence — session 29 / V5.22–V5.23:** Desktop repair: readiness no longer skips empty dependency lists; proposal application uses the shared TaskService refresh for existing tasks. Regression covers proposal removal, direct update and preservation of manual blocks. Original reproduction below is retained as historical evidence. Linux regression validated; Windows release gate is still pending.

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

### BF-005 · S2 · FIXED (session 38) — a damaged `state.json` blocks the project, and the error points to a backup that does not exist

**Where:** `aiwb/v2/store.py` `_read_raw()` message; `backup()` is only called before a migration
(`store.py`) and before a bundle import (`bundle.py`).

**Reproduce** (script `/tmp/hunt/d_corrupt.py`): start a project, then cut `.workbench/v2/state.json` short
(or empty it — e.g. a OneDrive/Dropbox sync conflict, disk full, a crash of another tool).
Opening the project → *"V2 state file is corrupt (…); a backup is kept next to it. Restore a backup from
.workbench/v2/backups or move the file away."* — but `.workbench/v2/backups/` **does not exist** in a normal project.

**Why it matters:** the project cannot be opened (Projects / Workbench / Home card all fail) and the advice is false.
"Move the file away" silently starts an **empty** project — the plan, tasks and decisions are gone, although
`events.jsonl` (the event ledger) is still there. Writes themselves are safe (temp file + fsync + `os.replace`),
so this needs an outside cause — rare, but a dead end when it happens.

**Expected:** keep the last good state (e.g. `state.json.prev`, rotated on each write or every N writes) and offer
*Restore the last good copy* in the error; the message must only mention backups that exist.

### BF-006 · S3 · FIXED (session 37) — text with a broken emoji (lone UTF-16 surrogate) makes paste / Quick apply fail with "a bug in AI Workbench"

**Where:** `aiwb/v2/controller.py` `route_answer()` line ~461 (`text.encode("utf-8")` for the response id);
`aiwb/v2/quick.py` `apply()` line ~302 (`i["content"].encode("utf-8")`). Only
`project_version_store.py` uses `errors="surrogatepass"`.

**Reproduce** (scripts `/tmp/hunt/f2.py`, `/tmp/hunt/f3.py`): paste text containing `"\ud83d"` (half of an emoji,
e.g. an answer copied from a chat page that was cut in the middle of 🚀) → `UnicodeEncodeError: … surrogates not
allowed`. In Quick mode, `read_answer` and `plan` accept the file, and **Apply** then fails.

**Why it matters:** low. A normal emoji works (Tk 8.6 clipboard round-trip checked under xvfb: no surrogates). The
global Tk handler shows the "Application error" dialog, so the app does not crash and nothing is written half-way.
The message, though, says it is a bug and gives no way forward ("paste again without the broken character").

**Expected:** pasted text is cleaned once at the entry point (`text.encode("utf-8", "replace").decode()` or
replace lone surrogates with U+FFFD) and a note says *"1 broken character was replaced"*.

### BF-007 · S1 · FIXED (d8af767c, d274ec4f) — Quick mode: an apply that fails half-way cannot be restored, and the retry destroys the original file

**Repair evidence — session 30 / V5.22:** Quick uses the shared preflight/backup/publication boundary. Exact original bytes and a flushed, unique journal exist before the first write; write or application-state-save exceptions roll back in reverse. Failed backup IDs are never reused. Regression injects the second write and state-save failures, then retries and restores the original CRLF bytes. Original reproduction below is historical. Desktop Linux regressions validated; Windows release gate remains pending. These are unreleased source checkpoints, not a release.

**Where:** `aiwb/v2/quick.py` `apply()`: files are written one by one; the apply record is saved (`_save`) only
**after** the last write; the backup id is `A-{len(applies)+1}` — the same id again on the next try.
`aiwb/ui/quick_window.py` `apply` only catches `QuickError`.

**Reproduce** (script `/tmp/hunt/h_quick_paths.py`):
1. Folder has `src/old.py` = `old` and a folder `docs/`.
2. Answer delivers `src/old.py` = `NEW` and a file named `docs` (any write error works: a file that is open in
   Excel / locked by antivirus on Windows, a read-only file, disk full, a Windows-invalid name — see BF-008).
3. *Apply* → `IsADirectoryError` (the "Application error / bug" dialog). `src/old.py` is **already `NEW`**.
4. *Restore last apply* → **"There is no apply to restore."** (no record was saved).
5. The user pastes a fixed answer (`src/old.py` = `NEWER`) and applies → it gets id **A-0001 again** and backs up
   the current file into the same folder → `backups/A-0001/src/old.py` is now `NEW`. *Restore* brings back `NEW`.
   The original `old` is **gone for good**.

**Why it matters:** silent data loss of the user's own code in the mode meant for the simplest users; the button that
promises undo says there is nothing to undo.

**Expected:** save the apply record (status `writing`) right after the backup and before the first write; on any
`OSError` roll back the files already written from the backup and say which file failed and why; never reuse a
backup folder (unique id, refuse if the folder exists).

### BF-008 · S2 · OPEN — paths that are fine on Linux but break or misbehave on Windows are accepted

**Partial repair — session 30 (still OPEN):** canonical Desktop intake/staging/diagnosis rejects Windows devices, ADS, invalid/control characters, trailing-dot/space aliases and case-insensitive protected roots (2a408c58, e55b500e, 02f020bf). The shared fixture was extended (5ce45730) and the Mobile Files.safePath port aligned (7eb0da98). Desktop fixture tests pass; no Kotlin compiler/Android SDK is available in this sandbox and no Android or actual Windows validation is claimed. Keep OPEN pending those cross-platform gates. **Session 41:** the shared fixture now runs on both sides in this sandbox (Desktop `test_files.py` inside the 1102-test suite; Kotlin `FilesTest` inside the 128-test JVM run built with standalone kotlinc), all green. Still OPEN: no real Windows (NTFS) or Android device run exists.

**Where:** `aiwb/intake/answer_files.py` `safe_path()` and its copy `aiwb/v2/files.py` `safe_path()` (same rule,
shared fixture `packages/contracts/fixtures/files/safe-paths.v1.json`). Only `/`, drive letter, `..`, NUL,
`.git`, `.workbench` are refused.

**Accepted today** (script `/tmp/hunt/h_quick_paths.py`): `con.py`, `aux.txt`, `src/NUL`, `LPT1` (reserved device
names), `a.txt:stream` (**NTFS alternate data stream**), `src/x.py.` (Windows drops the trailing dot → writes
`src/x.py`), `src/<a>.py`, `a"b.py`, `src/a|b.py`, `src/a?.py` (invalid characters).

**Why it matters:** the friends use Windows. An AI that writes such a name makes Apply/Accept fail with an OS error
(and in Quick mode / guided mode that error leaves files half-written — BF-007, BF-009). `a.txt:stream` is worse:
on NTFS it **succeeds** and writes into a hidden stream of `a.txt`; the visible file stays as it was, so the user
thinks the change is in the project when it is not. `x.py.` silently overwrites `x.py`.

**Expected:** refuse (with a clear "skipped: not a valid Windows file name" problem) any segment that is a reserved
device name (with or without extension), contains `<>:"|?*` or control characters, or ends with a dot or space —
on every OS, so a project made on Linux also opens on Windows. Add these cases to the shared fixture.

### BF-009 · S1 · FIXED (27636e7a, e55b500e, 9e85aebb) — guided mode: "Accept the delivery" that fails while writing files leaves the task "in review" with half the files and no retry

**Repair evidence — session 30 / V5.22:** Guided publication and acceptance share a filesystem rollback boundary and one state commit. A failed preflight/write leaves the task/handoff/attempt unchanged and staged bodies retryable. Tests reproduce an existing destination directory and a locked second file, assert exact rollback, no temporary leftovers, and successful retry with preserved original backups. Original reproduction below is historical. Desktop Linux regressions validated; Windows release gate remains pending. These are unreleased source checkpoints, not a release.

**Where:** `aiwb/v2/guide.py` `_perform` → `accept_handoff`: `c.resolve_handoff(ref, True, …)` is committed
**first**, then `files.integrate()` writes the files one by one with no error handling; `integrated_files` is only
saved after the last write.

**Reproduce** (script `/tmp/hunt/i_integrate_fail.py`): task scope `src/x/**`; the answer delivers `src/x/a.txt` and
`src/x/b.txt`; on disk `src/x/b.txt` cannot be written (here a folder of that name; on Windows: the file is open in
another program / read-only / locked by antivirus / a BF-008 name). *Accept the delivery* →
`IsADirectoryError` ("Application error / bug" dialog in the app, or an error line on the Home card).
Result:
- handoff = `accepted`, `integrated_files` = none, the staged bodies are still in the state;
- `src/x/a.txt` **was overwritten**, `src/x/b.txt` not written, a stray `src/x/b.txt.aiwb-tmp` is left in the
  project folder;
- the task jumps to *Review TASK* (approve / reject / review prompt). There is **no step to write the missing files
  again** — accept is not offered any more, and approving the task approves files that are not on disk.
- The backup of `a.txt` exists under `.workbench/v2/backups/HO-…/` but nothing in the UI restores it.

**Why it matters:** the project silently ends up with a mix of old and new files, and the plan says the task was
delivered. With friends on Windows (OneDrive folders, editors keeping files open) a locked file is common.

**Expected:** write the files **before** marking the handoff accepted (or in one "integration pending" state);
on an `OSError` restore the files already written from the backup, remove the `.aiwb-tmp`, keep the handoff open and
show *"Could not write src/x/b.txt: … — close the program that uses it and press Accept again"*.

### BF-010 · S1 · FIXED (35ea6c24, b9db856b) — guided mode silently drops delivered files (over 512 KB, over 8 MB in total, or empty) and still approves the task

**Repair evidence — session 30 / V5.22:** Desktop staging retains intentionally empty files. Per-file and total size omissions are persisted as error diagnostics; Home removes Accept for incomplete/conflicting staging and integration independently refuses it. Tests cover empty __init__.py on disk, both limits, visible codes and absent acceptance. Mobile staging is not changed or validated by this Desktop repair. Original reproduction below is historical. Desktop Linux regressions validated; Windows release gate remains pending. These are unreleased source checkpoints, not a release.

**Where:** `aiwb/v2/files.py` `stage()`: `if not p or not _in_scope(...) or not body.strip() or size > MAX_FILE or
total + size > MAX_TOTAL: continue` → no problem, no message. `_diagnose()` only knows about out-of-scope files.

**Reproduce** (script `/tmp/hunt/k2_big.py`): task scope `src/x/**`; the answer delivers `src/x/a.py` (small) and
`src/x/big.py` (~600 KB, e.g. a data file or a bundled library), both inside scope, manifest says `complete`.
Paste → *"2 file(s) read … Check: … four-backtick fence …"* (only style warnings) → step *Check what Implementer
delivered* with **Accept the delivery** as the primary button, explaining *"Accepting adds **1** delivered file(s)"*.
Accept → *"Delivery accepted and TASK approved. 1 file(s) added"* → task `validation_pending`.
`src/x/big.py` **is not on disk** and nothing ever says so (only the number 2 → 1 differs).

**Why it matters:** the task is marked as done with a missing file; the next task (or the build) fails later and the
user cannot see why. The same silent skip happens for a file whose body is only whitespace (an AI writing
"empty `__init__.py`") and for everything after the 8 MB total.

**Expected:** every skipped file becomes a diagnosis problem (`too_large` / `empty_file` / `total_too_large`,
severity error for size limits) listed on the card, so the user can *Build the troubleshooting prompt* or accept
knowingly; an intentionally empty file (e.g. `__init__.py`) should simply be written empty.

### BF-011 · S2 · FIXED (a887ae4e) — "Tests/build failed…": the user's note is thrown away and the next prompt still says "tests pass"

**Repair evidence — session 35 / V5.25–V5.26:** Desktop guided validation (5fd92ec6) now stores the user note as the evidence summary (existing 2000-character bound), with separate explicit/generated run ID and attempt association. Fresh prompts include the latest verified test/build result for this task and current revision; failed validation associated with the previous delivery labels its model claims CONTRADICTED and asks for the reported failure to be fixed. Foreign task and obsolete revision evidence are excluded. Mobile equivalents 52cda1dd/c9d6fc56/88b85e97. Actual guided paste/accept/validation and project-reopen tests in test_v2_guide and StandaloneLoopTest verify long Persian notes, explicit run ID, attempt identity, fresh prompt content and evidence isolation. Initial baseline failures reproduced; Mobile test fixture follows its offered Approve step and existing input trimming. These are unit/JVM tests, not Android device/UI validation.

**Where:** `aiwb/v2/guide.py` `_perform`: `validation_failed` copies the note into `run_id` only when no run id is
given (truncated to 100 chars), then `record_validation` stores `summary="recorded in the guided loop"`. The task
prompt (`aiwb/v2/handoff.py`, section *6. Previous handoff*) lists only the earlier handoff's claims.

**Reproduce** (script `/tmp/hunt/l_valfail.py`): deliver → accept → *Tests/build failed…* with the note
`2 tests fail in test_calc` → task goes back to `in_progress`, Home shows *Start TASK with Implementer* →
*Prepare the prompt*. The new prompt contains **`Claimed (NOT verified): tests pass`** and **nothing** about the
failure or the user's note; evidence summary = `recorded in the guided loop`.

**Why it matters:** the user did the right thing (ran the tests, wrote what failed), but the AI is asked to do the
same task again without being told what is wrong, so it usually sends the same files → a loop. This is the normal
"fix the bug" path the friends will hit first.

**Expected:** store the note as the evidence summary; when a task goes back to work after a failed validation, the
next prompt has a section *"Your last delivery failed the user's tests: <note> — fix that"* (like the repair /
troubleshooting prompts), and the old *"tests pass"* claim is shown as contradicted.

### BF-012 · S3 · FIXED (77b18a25) — the "answer was cut off — ask to continue" step outlives the prompt it belongs to

**Repair evidence — session 34 / V5.23–V5.24:** Desktop and Mobile Home now project a continuation only while its handoff is open, its task is nonterminal and it still belongs to the active attempt. Closed, missing and replaced prompts no longer expose Copy/Paste-the-rest actions. Projection is read-only: legacy saved partial answers remain inspectable rather than being deleted. Actual guided cut-off -> Drop reproductions failed before repair on both platforms; tests now verify hidden stale cards, stale action refusal without mutation, accepted/rejected/superseded/missing legacy handoffs and a newer attempt. Mobile counterpart a4dc6ae4; tests b518b152/73f3d711.

**Where:** `aiwb/v2/guide.py` `steps()` shows `settings.guide.continue` (rank 0, top of Home) without checking that
its `for` handoff is still open; `abandon` / `reject_handoff` / `troubleshoot` do not clear it.

**Reproduce** (script `/tmp/hunt/m_continue.py`): prepare a task prompt → paste a cut-off answer → Home shows
*The last answer was cut off — ask to continue* **and** the handoff step. The user chooses *Drop this prompt…*
(wants to start over). Home still shows the continue step **first**, above *Start TASK*. *Paste the rest* →
*"Answer linked to HO-0001 (**rejected**, complete). 2 file(s) read …"* — the files go onto the dropped handoff,
nothing can be accepted; the step disappears and the user is back to *Start TASK* with the answer lost.

**Why it matters:** confusing more than blocking (*Ignore the cut-off answer* exists), but the top step of Home leads
the user to waste a chat round.

**Expected:** the continue step is dropped automatically when its handoff is no longer open (and on abandon / reject /
troubleshoot of that handoff).

### BF-013 · S2 · FIXED (a887ae4e) — after "Reject…" the reason is lost and the next prompt says "This is the first handoff"

**Repair evidence — session 35 / V5.25–V5.26:** Desktop and Mobile (52cda1dd/88b85e97) select the most recent accepted OR rejected handoff as the next prompt lineage. Its summary/delivered items remain visible, and a rejected handoff carries its user resolution reason plus explicit warning that the listed items were NOT accepted. It no longer calls a rejected delivery the first handoff. Actual guided paste -> Reject with Persian/English reason -> reopen project -> prepare tests on both platforms verify prior handoff ID, retained reason and self-contained feedback. No historical resolution is modified. Unit/JVM evidence only; no Android Activity/device gate claimed.

**Where:** `aiwb/v2/guide.py` `reject_handoff` → `resolve_handoff(ref, False, reason)`; the task prompt
(`aiwb/v2/handoff.py`, section *6. Previous handoff*) only looks at accepted/complete handoffs.

**Reproduce** (script `/tmp/hunt/n_reject.py`): prepare → paste a delivery → *Reject…* with reason
`wrong algorithm` → *"Delivery rejected. A new prompt can be prepared."* → *Prepare the prompt*. The new prompt has
**`## 6. Previous handoff — This is the first handoff for this task.`** and no trace of the reason.

**Why it matters:** same loop as BF-011: the user explains what is wrong, the app forgets it, and the user pastes a
fresh prompt into the chat (often a **new** chat — the prompt calls itself "self-contained"), so the AI repeats the
same mistake. The user has to retype the reason by hand into the chat.

**Expected:** the next prompt for the task includes *"Your previous delivery (HO-…) was rejected by the user:
<reason>"* (and a short list of what it delivered), like the repair / troubleshooting prompts do.

### BF-014 · S2 · FIXED (4fd728bf) — a plan may depend on (or edit) a cancelled task; it is accepted without a word and lands in BF-001

**Repair evidence — session 29 / V5.22–V5.23:** Desktop repair: shared import/review reference guard rejects edits/dependencies involving cancelled or superseded tasks, including raw depends_on and update changes. Review checks current state again; confirm_stale cannot bypass the guard. Removing invalid edges remains possible. Tests cover cancellation before and after import. Original reproduction below is retained as historical evidence. Linux regression validated; Windows release gate is still pending.

**Where:** `aiwb/v2/proposals.py` `import_data()`: an operation is only marked invalid for an **unknown** task id
(`r not in state["tasks"]`); the status of the referenced task is never looked at. `review()` / `apply` then create the
dependency or edit the cancelled task as asked.

**Reproduce** (scripts `/tmp/hunt/o_stale.py`, `/tmp/hunt/o2_fresh.py`):
1. Task X exists, the user cancels it (or the PM superseded it in an earlier plan).
2. The PM — who often still has the old task list in its chat — sends a plan with `create_task N` `depends_on: [X]`
   (fresh `base_state_revision`, so not even the *older state* warning appears) and/or `update_task X`.
3. Card: *Review the plan … Nothing is applied until you accept it.* — every operation `valid`, no problem shown.
   *Accept* → *"Plan accepted. Next roadmap stage: prompts for the next tasks can be generated."*
4. Result: N is immediately `blocked: prerequisite no longer valid: X (cancelled) — re-plan this task`; Home shows
   *N is blocked* with **It can continue now** as primary, which always fails (BF-001). The `update_task` on the
   cancelled X is applied too (objective changed, revision 2) and has no effect at all.

**Why it matters:** the PM is the main source of tasks, so this is the most likely way to reach BF-001; the plan
review was the one place where the user could have seen the problem, and it says everything is fine. The accept
message even promises that prompts can be generated.

**Expected:** at import, an operation that depends on / edits / splits a `cancelled` or `superseded` task gets a
problem (*"TASK-X is cancelled"*), is shown as invalid on the card and is not accepted by *Accept*; the repair prompt
for the PM lists those tasks as cancelled so the next plan does not repeat it.

### BF-015 · S3 · FIXED (af421197) — helper AI: two network edge cases give a misleading message

**Repair evidence — session 36:** Helper HTTP reads allow escaped Persian JSON up to the declared character limit, report a byte/character overflow explicitly, and classify HTTPException/IncompleteRead as a connection problem. Fake-server and injected-opener regressions cover 150,000 Persian characters, interrupted bodies and oversized content. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/helper_ai.py` `chat()`: the reply is read with `resp.read(MAX_REPLY_CHARS * 4 + 1)` (800 001 **bytes**)
and then parsed; `http.client.IncompleteRead` (an `HTTPException`, not an `OSError`) is not caught.

**Reproduce** (script `/tmp/hunt/q_helper.py`, fake opener):
1. A server that escapes non-ASCII in JSON (`\u0633` = 6 bytes per Persian letter) sends a long reply (≥ ~135 000
   Persian characters, below the 200 000-character limit) → the bytes are cut at 800 KB → *"The helper AI sent an
   answer Workbench cannot read (not a Chat Completions reply)"* — wrong: it is a valid reply that was cut by us.
2. The connection drops in the middle of the body → `IncompleteRead` → generic *"The helper AI call failed:
   IncompleteRead."* (from `run_async`) instead of *"could not be reached / connection lost — try again"*.

**Why it matters:** low — the app never crashes, nothing is written, and the user can retry; very long Persian replies
are rare (servers like OpenAI / Ollama send raw UTF-8, which is fine up to the limit). Only the wording misleads.

**Expected:** read up to the limit and, if the limit was hit, say *"the helper AI answer is too long"*; catch
`http.client.HTTPException` together with `OSError` as a connection problem.

### BF-016 · S1 · FIXED (bab16563) — a `settings.json` that is not UTF-8 stops the app from starting at all

**Repair evidence — session 32:** Settings recovery reads raw bytes before UTF-8-sig decode; undecodable input now uses the corrupt-JSON recovery path. A unique exclusive flushed/fsynced backup preserves exact UTF-16, Windows-1252 or invalid bytes before removing the unchanged original. Tests reproduce the startup exception on the old source and verify defaults/retry, byte-exact backups and same-second repeated corruption. Final Desktop suite: 961 tests OK, 10 skipped. Actual Windows application startup/GUI remains a release gate.

**Where:** `AI_Workbench.py` `load_settings_with_recovery()`: `path.read_text(encoding="utf-8-sig")` sits inside
`try … except OSError`; a `UnicodeDecodeError` (a `ValueError`, not an `OSError`) escapes. The corrupt-file backup
logic below it (`settings.json.corrupt-<ts>`) is never reached. `WorkbenchApp.__init__` → `main()` catches it as a
start-up failure.

**Reproduce** (script `/tmp/hunt/r_settings.py` for the function, `/tmp/hunt/r_start.py ok|utf16|cp1252` for the
whole app under xvfb):
1. Save `%LOCALAPPDATA%\AIWorkbench\settings.json` as UTF-16 (Windows PowerShell 5 `… > settings.json` /
   `Out-File`, or Notepad *Save as → Unicode*) or as ANSI / Windows-1252 with a non-ASCII character (e.g. a project
   path `C:\Users\José\…`, PowerShell 5 `Set-Content`).
2. Start AI Workbench → *"The application failed to start. Details were written to …\app.log —
   'utf-8' codec can't decode byte 0xff in position 0"*, exit code 1. Every later start fails the same way.

**Why it matters:** the app cannot be opened until the user finds and deletes / re-saves a file in a hidden folder;
the message does not say which file. The function's own docstring promises tolerance for files *"edited with
Notepad / PowerShell 5"* — exactly the editors that produce these encodings. (A JSON syntax error or a non-object
file is handled correctly: renamed to `.corrupt-<ts>`, app starts with defaults.)

**Expected:** an undecodable file is treated like a corrupt one (preserved as `settings.json.corrupt-<ts>`, start with
defaults and a notice), or decoded as UTF-16 (BOM) / Windows-1252 as a fallback. The two background writers
(`_save_github_account_metadata`, `_save_github_repository_binding_metadata`) read with plain `utf-8` (no `-sig`):
they already catch the decode error, so they are fine.

### BF-017 · S2 · FIXED (bec490b7) — when `settings.json` cannot be written, every settings change says "Saved" and is lost at restart

**Repair evidence — session 35 / V5.25–V5.26:** Global Desktop settings save failure now reports the cause, lost-on-close risk and logs/app.log once per failure period; clears the Saved badge and never lets Toolbar Save claim success. Successful retry persists in-memory preferences and resets warning suppression. HelperService ff72aad6 treats explicit False and raised save callbacks as failures, restores prior helper configuration in the current callable settings dict and rolls back created/replaced/deleted credentials. Failed credential deletion keeps configuration reachable; rollback failure is surfaced explicitly. This is exception rollback, NOT power-loss atomicity across Credential Manager and JSON. Helper Remove 75e06de3 preserves its form and displays the failure. Regressions cover real directory-at-settings.json atomic replacement failure, Toolbar with/without workspace, repeated warning/retry, helper initial/replace/keep/remove-key/clear, callable dict replacement and rollback errors. Real Tk gui_v519_helper_smoke (218d65da) passes under Xvfb with injected save/removal failures, unchanged on-disk settings, retries and normal Save/Test/Explain/Fix/Remove against a local fake API. Native Windows Credential Manager validation remains a platform gate.

**Where:** `AI_Workbench.py` `_save_settings()` catches every exception, writes it to `logs/app.log` and returns
`False`; the callers ignore the result: `_save_prefs()` (theme / language / mode / reduce motion),
`HelperService.configure()` / `clear()` (`save=self._save_settings`, result not checked), `save_now()` (Toolbar ›
Save: `set_status("Saved." / "Settings saved. No project is open.")` is unconditional — only the small status-bar
badge uses `ok`), project register / remove, quick-instruction editor, output format / playbook combos.

**Reproduce** (script `/tmp/hunt/s_savefail.py`, under xvfb; the write is made to fail by putting a folder where
`settings.json` goes — on Windows the same happens when the file is locked by antivirus / OneDrive / a second
Workbench window, or `%LOCALAPPDATA%` is read-only):
1. Settings › Language → فارسی: the UI switches, no message.
2. Toolbar › Save → status *"Settings saved. No project is open."*
3. Settings › Helper AI › Save → *"Saved. m at https://… · key saved"*.
4. `app.log` has 3 errors; `settings.json` was never written. Restart → English, helper AI not set up, newly added
   projects missing from the list. With a key: the key **is** written to Windows Credential Manager but its
   `credential_ref` is not saved anywhere → an orphan secret that *Remove* can no longer delete.

**Why it matters:** the user is told the opposite of what happened and only finds out after a restart (e.g. the
helper AI key "disappears"); nothing points to `app.log`.

**Expected:** a failed settings write is reported once (*"Settings could not be saved: <reason> — changes will be
lost when you close Workbench"*), `save_now()` / the helper card show the real result, and `HelperService.configure()`
rolls back the secret it just stored when the settings save fails.

### BF-018 · S3 · FIXED (session 39) — GitHub state publishing: a dropped connection or an odd reply gives "a bug in AI Workbench" / is never shown

**Where:** `aiwb/v2/publisher.py`: `GitHubStateClient._call()` only turns `OSError` / `URLError` into a `PublishError`;
`urllib_transport()` parses the body with `json.loads` unguarded; `branch_head()` / `default_head()` / `commit_tree()`
index `body["object"]["sha"]` / `["tree"]["sha"]` directly. `StatePublisher.tick()` (*"never raises"*) only catches
`PublishError`. `ProjectsController.publish_now()` does not wrap it; `tick_publisher()` does, but records nothing.

**Reproduce** (script `/tmp/hunt/t_pub.py`, fake transport):
1. Connection drops while GitHub's reply is being read (`http.client.IncompleteRead`), a proxy / captive portal answers
   200 with an HTML page (`JSONDecodeError`), or a reply lacks the expected field (`KeyError: 'object'`).
2. Projects window › *Publish state now* → the exception reaches Tk → *"Application error — That action stopped
   because of a bug in AI Workbench … What happened: IncompleteRead(1 bytes read)"*.
3. Timer path (every 30 s, publishing enabled): `tick_publisher()` returns `{"status": "error", …}`, but the queue keeps
   `last_error=""`, `attempts=0`, no back-off; the status line stays *"Not published yet · local revision 2 · last
   published —"* (no error, even in Advanced mode) and the same failing call is repeated every 30 s.
   (Compare: `RemoteDisconnected` / timeout / reset are `OSError`s → correctly *"GitHub is not reachable"* with back-off.)

**Why it matters:** low — publishing is optional and local work is never affected; but the "bug" dialog is alarming
and the silent timer hides why nothing is published.

**Expected:** `_call()` maps `http.client.HTTPException` and undecodable / unexpected bodies to
`PublishError("network" / "invalid", …)`; `tick()` keeps its *never raises* promise by recording any other exception
in `last_error` with back-off.

### BF-019 · S2 · FIXED (session 38) — a GitHub write (create repo / release) that fails half-way can never succeed on retry

**Where:** `aiwb/v2/repo.py` `RepoService.confirm()` runs several GitHub calls in a row (`_do_create`: create repo →
branch; `_do_release`: tag ref → Release) and keeps `github_pending` on any error, so *Confirm and send to GitHub*
replays **all** calls. None of the steps checks whether it is already done. In addition
`GitHubStateClient._call()` maps every 409/422 on a path containing `/git/refs` to *"the state branch moved on GitHub
since the last read (not fast-forward)"* — also for a tag that already exists.

**Reproduce** (scripts `/tmp/hunt/u_release.py`, `/tmp/hunt/u_create.py`, fake transport):
1. *Release:* tag `v1.0.0` is created, then `POST /releases` gets a 502 → *"GitHub: GitHub server error 502"*. Press
   *Confirm* again (GitHub is fine now) → the tag POST gets 422 *Reference already exists* → *"GitHub: the state branch
   moved on GitHub since the last read (not fast-forward)"* — every retry, forever. The version stays `planned`; on
   GitHub there is a tag without a Release.
2. *Create repository:* `POST /user/repos` succeeds, the branch step gets a 503. *Confirm* again → *"GitHub API POST
   /user/repos failed: 422 Repository creation failed."* — every retry. The project is not connected, although the
   private repository exists on the user's account.

**Why it matters:** the only offered button can never work again and the message (state branch / creation failed)
points the wrong way. Workarounds exist but are not suggested: *Cancel* → *Connect an existing repository…* (create
case), *I did it by hand — record…* with the tag (release case).

**Expected:** each step is idempotent (repo exists and is ours → continue with the branch; tag exists at the same SHA
→ continue with the Release; Release exists → record it); a 422 on `refs/tags/…` is reported as *"the tag already
exists"*; after a partial failure the card says what was already done on GitHub.

### BF-020 · S3 · FIXED (session 39) — "Archive the project": if the final bundle cannot be written, the project is read-only anyway and the card says the bundle exists

**Where:** `aiwb/v2/closeout.py` `archive()`: the `archived_at` transaction is committed **first**, then
`path.parent.mkdir()` / `path.write_text()` run unguarded. `Guide._perform` (`archive` action) does not catch the
`OSError`.

**Reproduce** (script `/tmp/hunt/v_archive.py`; the write is made to fail with a file where `.workbench/archive/`
must go — on Windows also a full disk, an antivirus / OneDrive lock or a read-only project folder):
1. Completed project → *Archive the project* → `FileExistsError` / `OSError` reaches Tk → *"Application error — That
   action stopped because of a bug in AI Workbench …"*.
2. The project is nevertheless archived: the only step is *"The project is archived (read-only) — Nothing can change
   until you reopen it. **The final bundle is in .workbench/archive/.**"* — no bundle was written. Pressing *Archive*
   again is impossible (*"the project is already archived"*).
3. Workaround (works, but nothing suggests it): *Reopen the project* → *Archive the project* again once the cause is
   gone.

**Why it matters:** low — no project data is lost; but the user gets a "bug" dialog and a card that states a false
fact (the final bundle exists).

**Expected:** write the bundle first (to a temp file, then rename) and mark the project archived only after it
exists; a write error is reported as a normal message (*"The final bundle could not be written: <reason>. The project
was not archived."*).

### BF-021 · S2 · FIXED (session 38) — "Export project for the phone" makes a file nobody can import when the folder name has a space, Persian letters, brackets or is long

**Where:** `aiwb/v2/controller.py` `ProjectsController.__init__`: `V2Project(root, root.name)` passes the **raw folder
name** as `project_id`, so `ProjectStore._default_project_id()` (which slugs the name) is never used. `bundle.read_bundle()`
(and `State.PROJECT_ID` in the mobile app, `Bundle.kt`) accepts only `^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$`.
`export_bundle()` does not check the id.

**Reproduce** (script `/tmp/hunt/w_bundle.py`):
1. Open a project in a folder called `My Project`, `پروژه من`, `app (copy)` or a name longer than 80 characters.
2. Settings › *Export project for the phone…* → *"Project exported to … Open it in AI Workbench Mobile → Projects →
   Import."* — the file is written.
3. Import it on the phone, into another Desktop folder, or even back into the same project → *"the project_id in the
   bundle is not valid"*. Same for the final bundle written by *Archive the project* (`closeout.archive`).
   Folders like `todo` work.

**Why it matters:** the Desktop ↔ phone feature silently fails for ordinary folder names (Windows users very often have
spaces; the owner's users write Persian names); the export claims success, the error appears only on the other device
and does not say why.

**Expected:** derive a valid `project_id` (slug, e.g. `my-project`, a hash for non-Latin names) for new projects and
keep the display name separately; or accept any non-empty id in bundles (both apps) and validate only what matters
(length, no control characters); at the very least refuse the export with a clear reason.

### BF-022 · S3 · FIXED (session 39) — bundle export / import: a file error gives the "bug in AI Workbench" dialog; a malformed bundle gives a raw Python message

**Where:** `AI_Workbench.py` `export_project_bundle()`: `Path(path).write_text(...)` unguarded;
`import_project_bundle()`: `Path(path).read_bytes()` unguarded, and `ctl.import_bundle(...)` (backup + write) after the
confirmation unguarded. The menu calls them through `WorkspaceShell._guard`, which only catches `ModelError`.
`bundle.read_bundle()` assumes `project` is an object and `db_version` is a number.

**Reproduce** (script `/tmp/hunt/w_bundle2.py`, under xvfb):
1. *Export project for the phone…* to a place that cannot be written (folder removed / read-only / OneDrive or
   antivirus lock on an existing file) → `FileNotFoundError` / `PermissionError` → *"Application error — That action
   stopped because of a bug in AI Workbench"*.
2. *Import project from the phone…* → confirm → the project folder is read-only / locked → `PermissionError: …
   .workbench/v2/backups` → the same "bug" dialog (nothing changed — the backup step failed first).
3. A bundle with `"project": [1]` → *"'list' object has no attribute 'get'"*; `db_version: "x"` inside state_json →
   *"invalid literal for int() with base 10: 'x'"*; a Windows-1252 file → *"'utf-8' codec can't decode byte 0xe9 …"*.
   (Handled — nothing changes — but the text says nothing to a user.)

**Why it matters:** low — no data is lost; the dialogs are alarming / unhelpful.

**Expected:** catch `OSError` around the file read/write and the import, report *"Could not write/read <file>:
<reason>"*; `read_bundle` reports *"the bundle is damaged (project / db_version)"* and *"the bundle is not UTF-8
text"*.

### BF-023 · S2 · FIXED (session 38) — bundle import into a project that has a goal but no tasks yet: another project's / an older bundle replaces it as "new", with no warning

**Severity raised S3 → S2 (session 18):** BF-049 showed that accepted decisions and a custom team are lost too, and
that a bundle of a **different** project is imported with the same plain *"Import the project (revision N)."*.

**Where:** `aiwb/v2/bundle.py` `plan_import()`: the `new` case (`local` has no `tasks` / `proposals` / `milestones` /
`handoffs`) is checked **before** the `other_project` and `older` checks. The goal, `settings` (team setup, helper
choices, publish settings) and edited agents are not counted as "local work".

**Reproduce** (scripts `/tmp/hunt/w_bundle3.py`, `/tmp/hunt/w_bundle4.py`):
1. Folder `todo`, goal *"track my todos"* written (revision 2+), no plan yet. Import the bundle of project `shop` →
   *"Import the project (revision 2)."* (a plain Yes/No, `safe=True`) → the goal is now *"sell things"* and
   `state.project_id` is `shop`, while the store / event ledger of this folder keep using `todo`.
2. Same folder, goal refined three times (revision 5); import an older bundle of the **same** project (revision 2) →
   again *"Import the project (revision 2)."* → the newer goal is replaced; the *older* warning never appears.
   A backup is kept in `.workbench/v2/backups/`, but nothing in the app can restore it.

**Why it matters:** low — only early-stage work is affected and a backup exists; but the dialog states nothing about
replacing anything, and the project silently takes another project's identity.

**Expected:** check `other_project` first; treat a non-empty goal / changed settings / `state_revision` > 1 as local
work so `older` / `diverged` apply; say *"This replaces the goal '…'"*.

### BF-024 · S3 · FIXED (e277840d) — "Commit completed" dialog shows Persian / non-ASCII file names as `\331\276\330\261…`

**Repair evidence — session 36:** The shared Git command runner passes -c core.quotepath=false, preserving readable Unicode paths in commit/output dialogs. Command-contract regression updated; actual Windows dialog rendering remains untested. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `AI_Workbench.py` `commit_changes()` → `work()` returns `committed.stdout` of `git commit -m …` as the
dialog text; Git's default `core.quotepath=true` writes every non-ASCII path byte as an octal escape inside quotes.
(Status parsing uses `-z` and is correct; only the shown text is affected. Same for other dialogs that show raw Git
output, e.g. `push_changes`.)

**Reproduce** (script `/tmp/hunt/y_git.py`, under xvfb): project folder `apps/پروژه من` in a repository, files
`فایل.py`, `a file.txt` → Git page › *Commit* → *"Commit completed — … create mode 100644
"apps/\331\276\330\261\331\210\332\230\331\207 \331\205\331\206/\331\201\330\247\333\214\331\204.py""*.

**Why it matters:** cosmetic, but the owner's users name folders and files in Persian; the confirmation looks like
garbage.

**Expected:** run Git with `-c core.quotepath=false` (as the status calls already pass `-c status.renames=false`), or
build the message from the staged path list.

### BF-025 · S2 · FIXED (session 39) — Run page: a Python script that prints Persian (or any non-ANSI) text fails on Windows; output of other programs is garbled

**Where:** `AI_Workbench.py` `build_project_file_run_spec()` builds `[sys.executable, file, …]`; `_run_process_bounded()`
starts it with `env=os.environ.copy()` and reads the pipe as `encoding="utf-8", errors="replace"`. Nothing sets
`PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`. On Windows a Python child whose stdout is a **pipe** encodes with the ANSI
code page (cp1252 on en-US, cp1256 on fa-IR), not UTF-8 (UTF-8 mode is not the default before Python 3.15).

**Reproduce** (script `/tmp/hunt/z_runenc.py`; the Windows pipe encoding is simulated with `PYTHONIOENCODING`):
1. Project file `hello.py`: `print("سلام دنیا ✓")`. In a Windows console it prints fine.
2. Run page › *Run / simulate* → en-US Windows: `UnicodeEncodeError: 'charmap' codec can't encode characters` →
   status **Failed**, exit 1, *"File run did not pass … Use 'Repair prompt from latest failure…'"*; fa-IR Windows:
   `ی` (U+06CC) and `✓` are not in cp1256 → also **Failed**, and the part that was written shows as `����` because
   cp1256 bytes are decoded as UTF-8.
3. The same decoding applies to *Run command* and queued actions (`cmd.exe` / tools write in the OEM / ANSI code page):
   any non-ASCII output (Persian file names in `dir`, localized compiler messages) is replaced by `�`.

**Why it matters:** a correct program is reported as failing, the failure is recorded in the task state
(`Action Failed`) and the repair prompt asks the AI to "fix" code that has no bug — exactly the AI-loop risk of
BF-011 / BF-013. The owner's users will often print Persian text.

**Expected:** pass `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` in the child environment for Python runs (and
optionally for shell commands); for other programs decode with `locale.getpreferredencoding()` / the OEM code page
when the bytes are not valid UTF-8.

### BF-026 · S2 · FIXED (d8af767c, d274ec4f) — Quick mode Apply / Restore write through a symbolic link or junction to files outside the project

**Repair evidence — session 30 / V5.22:** Shared destination and backup preflight rejects every symlink/reparse/junction component, escapes, Windows aliases and non-directory parents. Quick preview/apply/restore use it. Linux symlink test preserves external bytes even when a real project folder is replaced by a link before Restore. Actual Windows junction/OneDrive release validation remains pending. Original reproduction below is historical. Desktop Linux regressions validated; Windows release gate remains pending. These are unreleased source checkpoints, not a release.

**Where:** `aiwb/v2/quick.py` `apply()` / `restore()`: the target is `root / path` with only `safe_path()` (text
rules) checked; nothing resolves the path or refuses links. The classic importer (`AI_Workbench.py`
`validate_relative_path`: *"Symbolic-link paths are not accepted"*, *"Path escapes the project folder"*) and guided
`files.integrate()` (`root not in target.resolve().parents` → skipped) both protect against this; Quick does not.

**Reproduce** (script `/tmp/hunt/q_edge.py`):
1. Project folder has `lib` → a symlink to a folder outside the project (on Windows: a directory junction or
   symlink, e.g. a shared library folder, a `node_modules` / `venv` link, a OneDrive-redirected folder).
2. Quick answer delivers `lib/evil.txt` → *Apply* → the file is written **outside the project** (the same for an
   existing file: it is overwritten there, and its backup is taken from there). *Restore* writes / deletes there too.

**Why it matters:** an AI answer can change files the user never put in the project (shared code used by other
projects, files in the user's profile); the plan shows them as ordinary project files. Quick mode is meant for the
least technical users.

**Expected:** the same check as the other two paths: resolve the target and refuse (as a plan problem *"skipped: goes
through a link to outside the project"*) any path whose resolved location is not inside the resolved root, or any
link component.

### BF-027 · S3 · FIXED (f8bf23cc) — a ZIP answer whose entries start with `./` is refused completely ("unsafe path")

**Repair evidence — session 36:** ZIP entries are validated then normalized by safe_path; safe ./ and backslash aliases are accepted, while traversal remains refused. Regression verifies ./README.md and ./src/app.py alongside rejected ./../bad.py. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/intake/answer_files.py` `zip_files()`: an entry is unsafe when
`safe_path(name) != name.replace("\\", "/")`. `safe_path("./src/a.py")` is `src/a.py` (a valid normalisation), so
the comparison fails and every `./…` entry is skipped. Guided `files.unzip_files()` has the same comparison (refuses
the whole archive). Backslash names are accepted, `./` names are not.

**Reproduce** (script `/tmp/hunt/q_edge.py`): a ZIP made with `zf.writestr(os.path.join(".", ...))` — what Python
code that walks `"."` produces (a common way a chat's code tool builds the ZIP) — holding `./README.md`,
`./src/app.py` → Quick *Load ZIP…* → *"./README.md is an unsafe path — skipped; ./src/app.py is an unsafe path —
skipped"*, nothing to apply. (ZIPs from the `zip` tool, Windows Explorer and `shutil.make_archive` have clean names
and work.)

**Why it matters:** low — the user can ask for another ZIP; but the message calls an ordinary file "unsafe".

**Expected:** compare against the normalised path (strip a leading `./`, collapse `//` and `/./`), refusing only what
`safe_path` really refuses (`..`, absolute, drive, `.git`, `.workbench`).

### BF-028 · S3 · FIXED (d274ec4f) — Quick "Restore last apply" that fails half-way: "bug" dialog, and the retry says the files already restored were "edited by you"

**Repair evidence — session 30 / V5.22:** Restore preflights all destinations/backups, uses the shared rollback boundary including state save, reports failures as QuickError, and recognizes bytes already equal to their original backup. Retry after an injected locked second restore has no false edited-by-user entries. Newer user edits remain untouched. Original reproduction below is historical. Desktop Linux regressions validated; Windows release gate remains pending. These are unreleased source checkpoints, not a release.

**Where:** `aiwb/v2/quick.py` `restore()`: files are restored one by one with no `OSError` handling; the record is
marked `restored_at` only after the loop. On the retry, a file that was already restored no longer matches
`after_sha` and is put in `kept`. `aiwb/ui/quick_window.py` `restore_now()` only catches `QuickError`.

**Reproduce** (script `/tmp/hunt/q_edge.py`): apply changes `a.txt` and `b.txt`; `b.txt` is then locked / read-only
(open in an editor that locks, antivirus, OneDrive sync) → *Restore last apply* → `PermissionError` → *"Application
error — a bug in AI Workbench"*; `a.txt` is back to the original, `b.txt` is still the applied version. Unlock and
press *Restore* again → `b.txt` restored, and the message says *"Kept because you edited them after the apply:
a.txt"* — the user did not edit it; it is in fact correctly restored.

**Why it matters:** low — the end state is right after a retry; the dialogs are alarming and the second message is
false (it makes the user think a file was not restored).

**Expected:** catch `OSError` per file, report *"Could not restore b.txt: <reason> — close the program that uses it
and press Restore again"*; on retry treat a file whose current content equals its backup as already restored.

### BF-029 · S2 · FIXED (session 39) — Run page: a script that starts a background process (a server) keeps the app "busy" until that process ends — the time limit does not apply

**Where:** `AI_Workbench.py` `_run_process_bounded()`: after the child exits (or is killed on time-out), the reader
threads are joined with `timeout=5`, then `stream.close()` is called on the pipes. A grandchild that inherited the
pipe (any `subprocess.Popen` / `start` / `npm run dev`-style launcher; on Windows `Popen` inherits handles) keeps the
write end open, the reader thread stays blocked in `read()` holding the buffer lock, and `close()` waits for that
lock — i.e. until the grandchild exits. On time-out, `killpg` / `taskkill /T` miss a grandchild in another session
or one whose parent already exited. Same runner for *Run command* and queued actions.

**Reproduce** (scripts `/tmp/hunt/r_run.py`, `/tmp/hunt/r_run2.py`; `faulthandler` shows the main thread in
`stream.close()`, the readers in `drain` → `stream.read`):
1. `server.py`: starts `python -c "import time; time.sleep(60)"` with `Popen`, prints *"server started"*, exits.
2. Run page › time limit 10 s › *Run / simulate* → returns after **60 s** (when the grandchild ends), status Passed.
3. `bgloop.py` (launches a detached child, then loops): time limit 3 s → *"Process timed out after 3 seconds"* only
   after **40 s**.
With a real server (runs until closed) the run never returns: the progress bar spins, every other action says
*"Another operation is running. Wait for it to finish."*, and on Windows the server has no window
(`CREATE_NO_WINDOW`), so the user cannot find what to close — only killing AI Workbench helps.

**Why it matters:** "run my app" for a web project very often starts a server or opens a browser via a launcher; the
whole app freezes in a busy state with no cancel button.

**Expected:** do not close the pipes while a reader may be blocked — after the deadline, stop waiting for the readers
(they are daemon threads), take the captured tail, and return; note *"a background process is still running and
holds the output"*. Optionally: run the child in a Windows Job Object (kill-on-close) / its own session and kill
the whole tree on time-out; add a *Stop* button for the running job.

### BF-030 · S2 · FIXED (session 38) — Quick mode prompt: `.env`, keys and files behind a link to outside the project are pasted into the AI chat without a word

**Where:** `aiwb/v2/quick.py` `inventory()` / `build_prompt()`: every file (except tool folders) is listed in
*Choose… (files the AI needs to see)* (`quick_window._fill_include_menu`) and its content is copied into the prompt
as is. No `is_sensitive` check (guided `context_step.is_sensitive` refuses `.env`, `*.pem`, `id_rsa`,
`credentials.json`, `.ssh/` … *"never packed without a separate decision"*; classic uses `is_sensitive_path`), no
`redact()` / `scan_for_secrets()`, and no link check (`target.is_file()` follows symlinks / junctions).

**Reproduce** (script `/tmp/hunt/q_prompt.py`): project with `.env` (`TOKEN=ghp_…`), `cfg.env` → a symlink to a
secrets file outside the project, `shared/` → a link to an outside folder. Quick › *Choose…* lists `.env` and
`cfg.env` like any file; tick them → *Copy prompt* → the token and the outside file's `API_KEY=sk-live-…` are in the
prompt text the user pastes into ChatGPT / Gemini; `shared/x.py` (outside the project) too. The file list sent in
every prompt also names `.env`.

**Why it matters:** the user's API keys / tokens go to a third-party chat (and its history / training) in the mode
meant for the least technical users, who cannot judge which files are secret; the other two modes protect exactly
this.

**Expected:** use the shared sensitive-file rule: hide sensitive files from *Choose…* (or show them disabled with
*"secret — not sent"*), refuse them in `build_prompt` (listed under *Not included: … (secret file)*), run
`scan_for_secrets` / `redact` over included bodies, and refuse paths whose resolved location is outside the root.

### BF-031 · S3 · FIXED (6814ae4b) — guided context request: the "sensitive file" refusal can be bypassed by an alias (`.env ` / `id_rsa.` on Windows, or a link to the secret)

**Repair evidence — session 36:** Context resolution checks sensitive Windows aliases and resolved names, and refuses linked file/parent paths. A link named public.txt to .env cannot deliver its secret; explicit sensitive-file consent remains supported. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/context_request.py` `resolve()`: `is_sensitive(it.path)` is checked on the **raw** requested name,
then the file is read from `root / it.path`. `context_step.is_sensitive` matches exact names; `_path_problem`
(`files.safe_path`) accepts a name with a trailing space / dot (it strips them, but the stripped result is not
used). The resolve-inside-root check passes for a link that points to a secret **inside** the project.

**Reproduce** (script `/tmp/hunt/c_ctx.py`):
1. The AI's `AIWB_CONTEXT_REQUEST` asks for `.env ` (trailing space) or `id_rsa.` (trailing dot) →
   `is_sensitive` = False, no path problem. On Windows the file system drops trailing spaces / dots, so the real
   `.env` / `id_rsa` is read and prepared for the user to paste into the chat.
2. A project file `notes.txt` that is a symlink to `.env` (or a hard link / junction) → requested as `notes.txt` →
   the token is in the prepared context.
(Also: secrets inside ordinary files, e.g. `API_KEY = 'sk-live-…'` in `settings.py`, are sent unredacted —
`redact()` / `scan_for_secrets()` are not applied to context packs, while classic Git commit does scan.)

**Why it matters:** low likelihood (needs an odd request or a link), but the rule exists precisely so a secret never
reaches the chat without *"an explicit separate decision"*; the user trusts it and pastes without reading.

**Expected:** check sensitivity on the normalised `safe_path` result **and** on the resolved target's name relative
to the root; refuse names ending in a space or dot (BF-008); optionally run `scan_for_secrets` on the prepared text
and warn before copying.

### BF-032 · S2 · FIXED (307bd806) — guided smart check: a correct delivery written as `./src/app.py` or `src\app.py` is flagged "out of scope / expected file not delivered" and pushed into troubleshooting

**Repair evidence — session 36:** Smart diagnosis normalizes delivered and expected paths through safe_path, and normalizes allowed-path separators and ./ prefixes. Mobile 225be7e0 matches this rule; unit/JVM tests cover src\app.py and ./src aliases. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/v2/diagnose.py` `diagnose()` checks scope (`_in_scope`) and `missing_deliverable` on the **raw**
path from the file block; `aiwb/v2/files.py` `stage()` normalises the same path with `safe_path()` (`./` removed,
`\` → `/`, `//` collapsed) and stages the file correctly. `answer_files.canonical()` leaves AIWB answers unchanged,
so the raw path reaches `diagnose`. (Comparison is also case-sensitive: `Src/app.py` vs scope `src/` — on Windows
that is the same folder.)

**Reproduce** (scripts `/tmp/hunt/d_diag.py`, `/tmp/hunt/d_diag2.py`): task scope `src/`, expected `src/app.py`;
answer block `path="./src/app.py"` (or `src\app.py`, common from models that "think Windows") → the file **is**
staged as `src/app.py`, but the card says *"Problems found in …'s answer — Smart check: [out_of_scope] ./src/app.py
is outside this task's allowed paths; [missing_deliverable] expected file src/app.py was not delivered"* with
*Build the troubleshooting prompt* as the main action. `src//app.py` → only the false *missing_deliverable*.

**Why it matters:** a correct answer is reported as broken; the troubleshooting prompt tells the AI the file is
missing / out of scope, so it resends the same thing; after `TROUBLESHOOT_ATTEMPTS` the task is **escalated and
blocked** (*"stuck after 3 troubleshooting prompts"*). The user must know to use *Accept anyway…*. Same AI-loop
risk as BF-011 / BF-013.

**Expected:** normalise each path with `safe_path()` before the scope / deliverable checks (and compare
case-insensitively, as Windows does), so `diagnose` and `stage` agree; mention *"path normalised: ./src/app.py →
src/app.py"* as a fix, not an error.

### BF-033 · S2 · FIXED (c80a0d36) — "Request a change… › Change this task" on a finished task: the change is recorded and then nothing can ever work on it

**Repair evidence — session 33 / V5.23:** Completed, cancelled and superseded tasks no longer suggest an unusable revise route. Suggestions offer an explicit follow-up task (architecture-wide requests still offer replan); direct revise refuses before mutation. The original task/revision/evidence remain unchanged. Regression covers all three terminal states, no-mutation refusal, a real ready/startable follow-up and unchanged open-task revision behaviour. This change-route UI/service is Desktop-only. Final-source Desktop suite: 966 tests OK / 10 skipped; full Mobile pure-JVM suite: 110 tests OK. These are Linux unit/JVM results, not native Windows, Android APK/lint/device or final GUI gates.

**Where:** `aiwb/v2/changes.py` `apply_route(route="revise")` only refuses cancelled / superseded tasks; for a `done` task it calls
`tasks.update()` (adds *"Change request: …"* to the acceptance criteria, `task_revision` + 1) but the status stays `done`.
`handoff.prepare()` refuses a done task (*"TASK-0001 is done; it must be ready or in progress for a handoff"*), the guide
offers no step for it, and nothing in the app ever uses the `done → in_progress` transition that `models.py` allows.
`suggest_route()` even returns `done: True` and still suggests *revise* for "fix …" requests (the most common wording).

**Reproduce** (script `/tmp/hunt/e_close.py`): task done → *Tasks* › select it › *Request a change…* › *"fix the wrong rounding"*
→ suggested route *revise* (Change this task) → OK → status bar *"TASK-0001 is now revision 2; earlier attempts are for the old
revision…"*. The task is still **Done**, there is no *Prepare the prompt* for it, the guide only shows *"Tell the project
manager what changed"*; and `closeout.can_announce` stays true — the project can be announced **complete** with the requested
fix never sent to any AI.

**Why it matters:** "fix this finished part" is the most natural change request; the app says it was accepted and then silently
drops it. The user has to discover by themselves that they should have picked *New task* instead.

**Expected:** for a done task either move it back to `in_progress` (the allowed transition; emit *task_reopened*, mark the
milestone as no longer accepted) so the guide offers *Prepare the prompt* for revision 2, or refuse *revise* with *"TASK-0001
is finished — use New task (it will build on TASK-0001)"* and suggest `new_task` when `done` is true.

### BF-034 · S3 · FIXED (session 39) — "Archive the project": if writing the final bundle fails, the project is read-only with no bundle, and Archive can never be retried

**Where:** `aiwb/v2/closeout.py` `archive()`: the state transaction sets `archived_at` **first**, then the bundle is written
with `path.write_text(...)` (not atomic, no `OSError` handling). A failed write leaves `archived_at` set; a second *Archive*
raises *"the project is already archived"*. The archive path uses the project id, so also a stale partial file can stay.

**Reproduce** (script `/tmp/hunt/e_close.py`): complete the project → `.workbench/archive/` not writable (OneDrive "files on
demand" folder, antivirus, disk full, read-only share) → *Archive* → `PermissionError` (*"Application error"* / guarded error);
`closeout.is_archived` = True, **no bundle file**. Make the folder writable → *Archive* → *"the project is already archived"*.
The only way out is *Reopen* then announce + archive again; the guide card says *"The project is archived (read-only)"*.

**Why it matters:** low frequency; but the step's whole promise is "a final bundle is kept"; the user believes the archive
exists (the guide says archived) while it does not.

**Expected:** write the bundle first (atomic temp file + `os.replace`), then set `archived_at`; or on failure roll back
`archived_at` and show *"Could not write the final bundle: <reason>"*; let *Archive* re-write a missing bundle of an
archived project.

### BF-035 · S2 · FIXED (21d9b243) — cancelling a task that has an open prompt: the prompt keeps a chat slot, and its answer can still be accepted into the project

**Repair evidence — session 33 / V5.23:** Desktop TaskService and Mobile Project retire every open handoff as superseded, abandon unfinished attempts through legal transitions, and clear active_attempt_id inside the cancellation/supersession transaction. Manager proposals use the same lifecycle boundary (0f2a5f10, dea478eb). Accepted/rejected historical records and staged payloads remain inspectable. Both acceptance and file-publication APIs refuse cancelled/superseded work, including direct integration without acceptance callbacks (10f254f2, d48fad0c, d9ec6cb8). Late responses remain linked to the closed record without reserving a chat or writing files. Deliberate policy: terminal work cannot be accepted even with an override reason; create a follow-up task instead. Desktop tests cover direct/proposal cancellation, supersession, prepared/received deliveries, dispatch-slot reuse, late responses, an exhaustive handoff/attempt-state matrix and injected state-write failure preserving the whole original lifecycle. Kotlin/JVM tests cover the corresponding direct/proposal/supersession and late-file refusal paths. Guide cannot offer task cancellation while an open handoff suppresses the task card; no fabricated guided-action test is claimed. Final-source Desktop suite: 966 tests OK / 10 skipped; full Mobile pure-JVM suite: 110 tests OK. These are Linux unit/JVM results, not native Windows, Android APK/lint/device or final GUI gates.

**Where:** `aiwb/v2/proposals.py` `_apply` › `close_or_cancel_task` (and `guide` › `cancel` → `tasks.transition(…, "cancelled")`)
only sets the task status. The task's open handoff (`prepared` / `prompt_exported` / `response_received` / …) and its active
attempt are left as they are. `waves.dispatch()` counts every open handoff as a busy chat, and `guide.steps()` keeps showing
the handoff card (*Copy the prompt… / Paste the answer*, then *Check what … delivered › Accept the delivery*).

**Reproduce** (script `/tmp/hunt/w_cancel.py`): `max_parallel_chats` 2; T0 and T1 have prompts prepared, T2 waits for a free chat.
1. The PM's plan has `close_or_cancel_task` for T0 → *Accept* → T0 is **cancelled**, but `HO-0001` stays *prepared*: dispatch
   still says 2 of 2 chats busy, T2 stays *queued*; Home still asks to copy T0's prompt.
2. Paste an answer for `HO-0001` → *"Answer linked to HO-0001 (reconciled, complete)"* → *Accept the delivery* → *"1 file(s)
   added to the project files"*: the cancelled task's code is written into the project (`src/a.py`), and the task stays cancelled.
3. The only way to free the slot is *Drop this prompt…*; after the accept, it is gone and the files are already in.

**Why it matters:** the PM cancels a task because its work is no longer wanted (replaced, wrong direction); the app keeps
inviting the user to send / paste / accept it, writes its files, and blocks the next task's chat until the user guesses to drop
the prompt. With one parallel chat the project silently stops advancing.

**Expected:** cancelling (and superseding) a task supersedes its open handoffs and abandons its active attempt in the same
transaction (*"prompt HO-0001 closed: task cancelled"*); a late answer for it is kept as *stale* and cannot be accepted
without *Accept anyway…* that warns *"TASK-0001 is cancelled"*.

### BF-036 · S3 · FIXED (session 39) — guided "Record the release…": a missing run id leaves the version half-advanced with a wrong tag (`vv1.0.0`), and the tag typed on the retry is silently ignored

**Where:** `aiwb/v2/guide.py` `_perform` › `release` runs three separate `advance_version` transactions (proposed → local →
tagged → released). The released step's check (*needs a run id or artifact*) runs **after** the first two are already saved.
The default tag is `"v" + label`, but `propose_version` accepts semver labels that already start with `v` (`_SEMVER = ^v?…`).
On the retry the version is already `tagged`, so the `tag` field is skipped without a word.

**Reproduce** (script `/tmp/hunt/t_rel.py`): version `v1.0.0`, milestone accepted → Home *Release version v1.0.0* › *Record the
release…* with commit `abc1234`, tag empty, run id empty → error *"released needs a real build/run id or artifact"* — but the
version is now **tagged**, tag **`vv1.0.0`**. Retry with tag `release-1`, run id `run-9` → *"Version v1.0.0 released."*, the
recorded tag is still `vv1.0.0` (shown on the timeline, completion summary and expansion prompt as the release tag).

**Why it matters:** the release record is the project's evidence of what was shipped; it now points to a tag that does not
exist, and the user is not told that the tag they typed was dropped.

**Expected:** validate all facts first and run the whole proposed → released move in **one** transaction (all or nothing); default
tag = label if it already starts with `v`; when the version is already tagged and a different tag is given, refuse or ask.

### BF-037 · S3 · FIXED (session 39) — "Accept anyway…" on an answer whose outcome is `failed` / `blocked`-less failure: files are written, the message says "Next: review the task", but there is no review — the guide offers a fresh prompt

**Where:** `aiwb/v2/handoff.py` `resolve()` moves the task to `in_review` only for outcome `complete` / `partial` and to
`blocked` / `needs_decision` for those outcomes; `failed` (and the empty outcome) leaves it `in_progress`. `guide._perform` ›
`accept_handoff` still integrates the staged files and always returns *"Delivery … accepted. Next: review the task."*

**Reproduce** (script `/tmp/hunt/h_res.py`): answer with a file block and `"outcome": "failed"` → card *"Problems found …
[failed_outcome]"* → *Accept anyway…* (reason "ok") → *"Delivery HO-0001 accepted. 1 file(s) added to the project files. Next:
review the task."* — the task is still **in progress**, there is no review card; Home shows *"Start TASK-0001 T with
Implementer — Prepare the prompt"*, i.e. a new attempt from scratch (the accepted delivery is now the "previous handoff").

**Why it matters:** the message names a step that does not exist; the user who accepted a partly useful answer expects to
review it, and instead is pushed to re-send the task. Low impact (nothing is lost), but confusing in the guided mode.

**Expected:** after accepting a `failed` answer either move the task to `in_review` (the user explicitly accepted it) or
say *"Accepted as a failed attempt — the files are kept; prepare a new prompt to continue"*; never promise a review card
that will not appear.

### BF-038 · S3 · FIXED (session 39) — an answer for a prompt the user dropped says "Answer linked to HO-0001 (rejected, complete). 1 file(s) read" — and then nothing happens to it

**Where:** `aiwb/v2/controller.py` `route_answer()` → `_match_handoff()` finds the handoff by the answer's `attempt_id` /
`handoff_id` even when that handoff is already `rejected` (dropped with *Drop this prompt…*); `handoffs.ingest()` then attaches
the response (attempt → `stale`), but every status step is skipped for a rejected handoff, so nothing is staged, no card is
made, no `stale_reasons` / diagnosis. The message is built from the counters only and reads like a success.

**Reproduce** (script `/tmp/hunt/a_late.py`): prepare TASK-0001's prompt (HO-0001) and send it → *Drop this prompt…* → prepare
again (HO-0002). The AI's answer to the first prompt arrives (manifest names HO-0001 / its attempt) → paste → *"Answer linked to
HO-0001 (rejected, complete). 1 file(s) read from AIWB file blocks."* Home still shows only *"Copy the prompt for TASK-0001 …"*
(HO-0002); the delivered file is not staged anywhere, nothing asks the user what to do with it.

**Why it matters:** dropping a prompt and re-asking is common (the chat was slow, the user changed their mind); the late
answer is often the good one. The app says it took the answer, then silently ignores it; the user waits for a card that will
never come or re-sends the task. (Late answers for *superseded* attempts get the *"out of date — Accept anyway… / Reject…"*
card; dropped ones do not.)

**Expected:** if the matched handoff is `rejected` / `superseded`, say so: *"This answer is for prompt HO-0001, which you
dropped. Use it for TASK-0001 instead of HO-0002?"* — offering to link it to the task's open handoff (as a stale answer with
*Accept anyway…*), or keep it in the Inbox only. Never report "linked" for a handoff that cannot take it.

### BF-039 · S2 · FIXED (323b33c8) — charter repair turns "Lead developer", "Tech lead", "Code owner", "Release manager" into a second **project manager**

**Repair evidence — session 36:** Technical leadership is classified before the broad manager fallback: Lead developer, Code owner and Release manager are implementers; Tech lead is architect. Explicit Project manager remains PM. Regression covers these reported roles. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/v2/charter_repair.py` `role_of()` checks `_ROLE_RULES` in order, and the `project_manager` rule
comes first with the keys `lead`, `owner`, `manager`, `coordinator`, `planner`; every key longer than 3 letters
is also matched as a **substring** (`len(k) > 3 and k in words`). So any role text containing *lead* / *owner* /
*manager* becomes `project_manager` before the *developer* / *engineer* rule is ever tried. It also catches
"Team leader", "Product owner", "Release manager", "Senior lead engineer", "Code owner / backend". The same
substring rule makes *"Contest backend dev"* and *"Latest-API integrator"* a **reviewer** (`test` inside
*contest* / *latest*) and *"UI designer"* an **architect**.

**Reproduce** (script `/tmp/hunt/cr_lead.py`): the PM's charter lists `agent-lead-dev`, role *"Lead developer"*,
purpose *"builds the API"*, owning module `api` and task t1 → the import notes
*"team.agents[1].role: 'Lead developer' → project_manager"* (one line among the repair notes, easy to miss) →
accept the plan → the team has **two** `project_manager` agents. Effects seen:
- TASK-0001's prompt starts *"you are Lead developer (agent-lead-dev, role project_manager)"*;
- *Settings › Team › Project manager* now offers `agent-lead-dev` (`pm_choices`);
- `agent_hub` (idle / overload alerts, *rebalance*) and the mission-board lanes skip it as "the PM" — its
  workload is never counted and no task can be rebalanced to or from it;
- charter validation counts it out of `workers`; a charter whose only builder is a *"Lead developer"* fails with
  *"no AI besides the project manager does the work"* — on a team that does have a builder.

**Why it matters:** "lead developer" / "tech lead" is one of the most common ways a model names the main builder.
The app silently changes the agent's job; the prompt tells it it is a manager; team tools ignore it.

**Expected:** match whole words only (no substring for keys like `test`, `lead`, `design`); try the specific work
words (*developer, engineer, dev, programmer, backend, frontend*) before the generic *lead / owner / manager*;
never create a second `project_manager` from a fuzzy guess — if the charter already has a PM, fall back to the
work role or ask, and show the role change as a warning, not a quiet repair note.

### BF-040 · S3 · FIXED (session 37) — paste box live diagnosis says "Manager proposal ✓" for any text with the marker, even when the import will refuse it

**Where:** `aiwb/intake/preview.py` `_preview()` returns `Preview("proposal", True, "Manager proposal ✓ — paste it
to review its changes.")` as soon as `<<<AIWB_MANAGER_PROPOSAL>>>` appears; nothing is parsed. The charter and the
context-request branches use the real reader (*"5.12.0 (owner audit B2): ✓ only when importing works"*); the
proposal branch was left out.

**Reproduce** (script `/tmp/hunt/pv.py`) — the box shows the green ✓ line, then *Use this answer* gives:
- JSON cut off (`"operations": [`) → *"AIWB_MANAGER_PROPOSAL is not valid JSON … the raw answer is kept in the
  Inbox The raw answer is kept in the Inbox."* (also: the sentence is doubled and the first has no full stop);
- no `base_state_revision` → *"base_state_revision (integer) is required …"* (rejected);
- `"operations": []` → *proposal_fix* (*"Nothing to apply"*).

**Why it matters:** the live diagnosis exists so the user knows *before* pasting whether the answer is usable
(and can ask the PM chat to fix it while it is still open). For the PM's answers — the most frequent paste after
the charter — it always says ✓, so the promise does not hold.

**Expected:** run the same reader as `proposals.import_text` in a dry mode (JSON, base revision, at least one
known operation; stale base revision as a warning) and show ✗ with the first problem, like the charter branch.
Drop the duplicated *"The raw answer is kept in the Inbox"* in `route_answer`.

### BF-041 · S2 · FIXED (session 39) — an answer with some files **and** a context request: the box says "Context request ✓", the app takes it as a finished delivery and the request is lost

**Where:** `aiwb/intake/preview.py` checks the context-request marker **before** file blocks, so the preview says
*"Context request ✓ · the model asks for 1 file"*. `aiwb/v2/controller.py` `route_answer()` checks file blocks
**first** (`if ex.files or HANDOFF_RE…` → `handoffs.ingest`) and returns; the context-request branch is never
reached. `ingest()` keeps only the canonical file blocks, so the request is not stored on the handoff, the attempt
or the diagnosis (`context_request` None, `unresolved_items` [], no diagnosis code).

**Reproduce** (script `/tmp/hunt/pv.py`): TASK-0001's prompt is out; the AI writes one file and then (as the
prompt's rule allows) asks for `src/x.py` with an `AIWB_CONTEXT_REQUEST` block — either order. Paste → the box shows
**Context request ✓** → *Use this answer* → *"Answer linked to HO-0001 (reconciled, partial). 1 file(s) read …"*.
Home: *"Check what Implementer delivered — Accept the delivery / Reject…"*; no *"Send the files … asked for"* step,
nothing mentions the request. Accepting moves the task to review with the half-done work.

**Why it matters:** models often send what they could do and ask for the missing file in the same answer. The app
tells the user one thing (request), does another (delivery), and the AI never gets the file it needs; the user
reviews and approves incomplete work, or rejects it without knowing why it is incomplete.

**Expected:** one shared classifier for preview and import. If an answer has both, keep the files staged (not
accepted) and record the context request on the handoff, so the card offers *Send the files … asked for* first;
at least add a diagnosis *"the AI also asked for: src/x.py"* to the delivery card.

### BF-042 · S2 · FIXED (57224e90) — an `AIWB_FILE … action="delete"` (or `"move"`) block is read as "write an empty file": Quick mode empties the file, guided mode drops it and approves the task

**Repair evidence — session 36:** AIWB parsing retains action; non-write actions never become extracted write content. JSON also refuses unknown/move/rename actions rather than treating them as writes. Guided routing rejects unsupported operations visibly before reconciliation; direct staging/integration blocks them, including Mobile. Unit/JVM action matrix and guided existing-file preservation regression pass. Quick legacy typed operations remain separate. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/v2/diagnose.py` `parse_files()` (used by `answer_files._aiwb_files`) keeps only the `path`
attribute of the block header; `action` / `from` are thrown away, so every block becomes `{path, content: ""}`.
The JSON reader in the same module **does** look at `action` (*"delete is not applied by the guided loop —
skipped"*), so the two formats disagree. The prompts only show `action="write"`, but the attribute itself invites
other values and models do send `delete` / `move` / `rename` when a task says "remove" or "rename".

**Reproduce** (scripts `/tmp/hunt/q_read.py`, `/tmp/hunt/g_del.py`):
- **Quick mode:** `src/old.py` exists → answer `<<<AIWB_FILE path="src/old.py" action="delete">>>` +
  `<<<AIWB_END_FILE>>>` → preview *"Files ✓ · 1 file"*, plan *"0 new · 1 changed"* → *Apply* → `src/old.py` is
  now **0 bytes** (not deleted, content gone). Only *Restore last apply* brings it back. `action="move"
  from="src/old.py"` with path `src/new.py` → *"1 new"*: an empty `src/new.py` is created, the old file stays.
- **Guided mode:** task *"remove old module"*, answer = the delete block + manifest *"removed src/old.py",
  outcome complete* → *"Answer linked … 1 file(s) read"*, no diagnosis → *Accept the delivery* → *"Delivery
  HO-0001 accepted and TASK-0001 approved"* — `src/old.py` is still there, unchanged; the summary in the ledger
  says it was removed (the empty body is skipped silently, as in BF-010).

**Why it matters:** in Quick mode a "remove this file" answer silently wipes a file's contents and leaves an
empty file behind (an empty module still imports; an empty config breaks the app). In guided mode the task is
approved although the requested removal never happened.

**Expected:** parse `action`; for `delete` / `move` / `rename` either perform them as explicit, previewed
operations (*"delete src/old.py"* in the plan, with backup) or refuse them visibly as the JSON reader does
(*"src/old.py: delete is not supported — delete it yourself"*) and never turn them into an empty write. Unknown
actions should be a problem, not a write.

### BF-043 · S1 · FIXED (c8cee295) — an answer that comes in through the phone companion, the classic Projects window or Workbench "Import" is never staged: *Accept the delivery* approves the task and writes **no file**

**Repair evidence — session 31 / Desktop:** Every Desktop route_answer caller now stages and diagnoses the canonical handoff response, including Companion and classic import callers. Guide consumes the same persisted result instead of taking a second preview. Integration refuses legacy/unprocessed responses without staged_files. Direct-route regressions prove both files are written only on acceptance and scope/size errors reach the card; legacy unstaged acceptance is refused. Checkpoints: c8cee295, 1a6c444c, 55976ace. Original reproduction below is historical.

**Where:** staging (`aiwb/v2/files.stage`) and the smart check (`guide._diagnose`) run only inside
`guide._paste()` (the Next-step card's *Paste the answer*). The other entry points call
`ProjectsController.route_answer()` directly and stop there:
- `aiwb/companion/service.py` op `submit_response` (the phone's *Send answer*);
- `aiwb/v2/projects_window.py` `do_import` (*Import answer*, linked from the Workbench as "classic");
- `aiwb/workspace/shell.py` `do_import` (scripts / older menu).
`route_answer` links the answer to the handoff (status `reconciled`, outcome from the manifest), so the guide then
shows the normal card *"Check what Implementer delivered … — Accept the delivery / Reject…"*. Its explanation does
not mention files at all (*"core done Accepting records your review approval; tests are recorded next."*),
because `staged_files` is empty.

**Reproduce** (script `/tmp/hunt/comp.py`): TASK-0001's prompt is out → the answer (`src/core.py` in an AIWB block +
manifest *complete*) is sent from the phone (`submit_response`) → *"Answer linked to HO-0001 (reconciled,
complete). 1 file(s) read from AIWB file blocks."* → on the PC, Home shows *Check what Implementer delivered* →
*Accept the delivery* → *"Delivery HO-0001 accepted and TASK-0001 approved. Next: record whether the tests/build
passed."*, `files: []`. Task → `validation_pending`; **`src/core.py` is not on disk**; no smart check ran
(scope, truncation, empty files are not checked either).

**Why it matters:** the phone companion exists precisely so the user can send the AI's answer from the phone; the
work then silently disappears while the task is marked approved. The next tasks build on code that is not there,
and nothing in the app says so (the message even says it was approved). Same class as BF-010, but for every file.

**Expected:** move staging + smart check into `route_answer` (or `handoffs.ingest`) so every entry point stages the
same way; at least, when a handoff with files in its response has no `staged_files`, the card should re-stage from
the stored response or refuse *Accept* with *"the files of this answer were not read — paste it here again"*.

### BF-044 · S3 · FIXED (3fdd40ff) — `body="raw"` is ignored: a raw file that starts with a code fence loses it (Markdown snippets, docs), and a raw file that opens a fence and goes on with prose is flagged "truncated"

**Repair evidence — session 36:** body=raw preserves literal fences, boundary blank lines and Unicode rather than unwrapping a Markdown wrapper or reporting a false unclosed fence. Desktop and Mobile parser regressions cover Markdown plus trailing prose and blank bodies. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/v2/diagnose.py` `parse_files()` keeps only the `path` attribute (same root cause as BF-042);
`_close()` always treats a first line that looks like a fence as the block's wrapper and drops it, plus the
last line if it matches. The salvage prompt (`aiwb/inbox/salvage.py`) explicitly asks the AI for
`<<<AIWB_FILE path="…" action="write" body="raw">>>` + *"the complete file text"*, i.e. **no** wrapper fence.

**Reproduce** (scripts `/tmp/hunt/raw.py`, `/tmp/hunt/raw_g3.py`):
- raw block for `docs/INSTALL.md` whose whole content is ```` ```bash ```` / `npm install` / ```` ``` ```` →
  guided *Paste the answer* → *Accept the delivery* → *"1 file(s) added"*; on disk: `npm install\n` — the
  Markdown code block is gone. Quick mode does the same.
- raw block whose content starts with ```` ```bash ```` … ```` ``` ```` and then a paragraph → written as
  `npm install\n```\n\nThen run the app.` (opening fence dropped, closing one left dangling) and the smart check
  reports *"the code fence in docs/INSTALL.md was never closed"* (`truncated`) on a complete answer.

**Why it matters:** the format the app itself asks for in its "resend only these files" prompt silently corrupts
Markdown / text files that begin with a code block; the second case pushes the user into a pointless
troubleshooting round.

**Expected:** honour `body="raw"`: take the lines between the header and `<<<AIWB_END_FILE>>>` verbatim (only the
final newline normalised), never strip fences; keep the current unwrap only for blocks without `body="raw"`.

### BF-045 · S2 · FIXED (session 41) — rescued proposal: a task assessment that names tasks by **title** creates **duplicate tasks**

**Partial repair — session 36 (not counted fixed):** 9db49bb6 resolves existing task title/short-ID assessments without creating duplicates and retains unresolved prerequisite warnings. Still OPEN: dependencies on new tasks from this same answer and full ambiguity/identity recovery need further implementation and tests.

**Where:** `aiwb/v2/rescue.py` `_task_ops()` treats an item as an update only when it carries an id starting with
`TASK-`; everything else with a `title` becomes `create_task`. `UPDATE_KEYS` (`task_assessment`, `task_updates`,
`updated_tasks` …) and `CREATE_KEYS` are merged into one list, so an *assessment* of existing work that says
`{"title": "Build API", "status": "on track"}` is read as a **new** task "Build API". No check against the titles of
existing tasks. Short ids (`"TASK-1"`, `"task-0001"`, `"1"`) are not normalised either → *"a change for unknown task
TASK-1"*. `depends_on` given by title (`["Write tests"]`) is silently dropped (only existing `TASK-` ids are kept).

**Reproduce** (scripts `/tmp/hunt/rs.py`, `/tmp/hunt/rs2.py`): TASK-0001 "Build API" and TASK-0002 "Build UI" exist.
The PM answers a status prompt with `{"summary": "status check", "task_assessment": [{"title": "Build API", "status":
"on track", "assessment": "fine"}, {"title": "Build UI", "status": "needs work"}]}` → *"Manager proposal PROP-0001 with
2 change(s) is ready for review. Read from the answer: 2 new task(s) read from the answer's own keys."* → review
(accept all) → **TASK-0003 "Build API" and TASK-0004 "Build UI"** exist next to the originals, both `ready`, no owner,
objective = title; the dispatcher queues them for the implementer.

**Why it matters:** the rescue exists for exactly these "assessment" answers (friend's calculator log). The review
card shows "create_task Build API" which looks right to a non-technical user; accepting it duplicates the work and
the next prompts build the same thing twice.

**Expected:** items from `UPDATE_KEYS` never become `create_task`; match by id (normalised: `TASK-1` → `TASK-0001`)
or by exact normalised title against existing tasks; an assessment with no field to change is skipped (as with ids).
Resolve `depends_on` titles against existing tasks and the new tasks of the same answer; list unresolved ones in
`leftover` instead of dropping them.

### BF-046 · S2 · FIXED (session 41) — rescued assessment overwrites the task's **objective** with the PM's comment ("Looks good so far, no change needed")

**Partial repair — session 36 (not counted fixed):** 9db49bb6 no longer maps free-text assessment description/goal/files/outputs to objective/deliverables; explicit changes remain supported. Still OPEN: owner_role normalization and preserving all comments as operation reasons are unfinished.

**Where:** `aiwb/v2/rescue.py` `FIELD_SYNONYMS` maps `description` and `goal` → `objective` (and `files` / `outputs`
→ `deliverables`). In `_task_ops()` an item of `task_assessment` / `task_updates` is read field by field with `_changes()`
— the *whole item*, not only a `changes` object — so the assessment's free-text comment becomes a new objective.
Related: `owner_role` is copied as written (`"Implementer"`, `"developer"`) and `proposals.review()` matches it with
`a["role"] == raw["owner_role"]` (exact, lower-case ids) → the new task gets **no owner**. It is not a dead end
(the dispatcher falls back to the implementer), but the task shows no owner and the role the PM asked for is lost.

**Reproduce** (script `/tmp/hunt/rs4.py`): `task_assessment: [{"task_id": "TASK-0001", "status": "on track",
"description": "Looks good so far, no change needed"}, {"task_id": "TASK-0002", "status": "at risk", "goal": "finish
this week", "files": "src/ui/app.js"}]` → *"2 task change(s) read from the answer's own keys"* → review shows two
`update_task` → accept → TASK-0001 objective = *"Looks good so far, no change needed"*, TASK-0002 objective =
*"finish this week"*. The next developer prompt for TASK-0001 says *"- Objective: Looks good so far, no change
needed"* — the real objective ("Build API objective") is gone from the prompt.

**Why it matters:** the developer AI receives a meaningless objective and builds whatever it guesses; the original
objective can only be restored by hand (Edit task). It happens with the most common "status report" answer shape.

**Expected:** for items without a `changes` object, take only explicit task fields (`acceptance_criteria`, `priority`,
`depends_on`, `scope`, `owner_agent_id`, …); never map `description` / `goal` / `assessment` / `status` / `files` of an
assessment onto `objective` / `deliverables` (keep them as the operation's `reason`). Match `owner_role` through
`charter_repair.role_of()` (case-insensitive), and list an unknown role in the review card instead of dropping it.

### BF-047 · S3 · FIXED (9db49bb6) — rescued decisions: a decision written as text loses the PM's choice; a recommendation *sentence* becomes the only option

**Repair evidence — session 36:** Plain-text PM decisions retain the stated choice as recommendation and option. A recommendation such as SQLite because it is simple uses SQLite as its option label while retaining the explanatory recommendation sentence. Rescue regressions cover both shapes. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/v2/rescue.py` `_decision_ops()`. A string item (`"decision": "Use SQLite"`, `"decisions": ["Use SQLite
for storage", "Use React"]`) becomes `{"title": text}` → `recommendation` empty, `options` empty. A dict with only
`question` + `recommendation` puts the whole recommendation sentence into `options` (`chosen` is prepended when it is not
among the options).

**Reproduce** (scripts `/tmp/hunt/rs5.py`, `/tmp/hunt/rs6.py`):
- `{"decision": "Use SQLite"}` → review → card *"Decide: Use SQLite"* with an empty explanation; the form has no option
  and no "Recommended" — only *Other answer…* — although the PM already said what it chose.
- `{"decisions": [{"question": "Which database?", "recommendation": "SQLite because it is simple"}]}` → card *"Which
  database? Options: SQLite because it is simple. Recommended: SQLite because it is simple."*; one radio button with the
  whole sentence; choosing it stores the sentence as the decision.

Not a dead end (typing an answer works: *"Decision DEC-0001 recorded."*), but the decision log gets odd entries and the
user is asked a question that was already answered.

**Expected:** a plain-text decision is a decision **made** by the PM: title = text, recommendation = text, options =
[text] (the form then offers it pre-selected, plus *Other answer…*). For `recommendation` sentences use
`choices.parse_options()` to split "X because …" into option *X* + rationale.

### BF-048 · S2 · FIXED (c4698f29) — end of the roadmap: "nothing left" written in words is refused, and the correction prompt forces the PM to **invent work**

**Repair evidence — session 34 / V5.23–V5.24:** Desktop and Mobile recognize whole unambiguous completion statements (nothing/nothing left/complete/completed/done/No, the project is complete), case and terminal punctuation, and empty arrays. Shared fixture cca8c072 also rejects ambiguous negatives such as not done, no tests yet and nothing left except testing. No arbitrary no-prefix inference is used. Desktop correction prompt e2244e1d offers actual operations OR operations: [] with roadmap_remaining: false and explicitly forbids inventing work; Mobile refusal 194d0ed8 gives the same recovery contract. Unknown/missing decisions remain unknown, and existing open tasks still prevent completion. Real proposal import/review tests on both platforms verify completion reaches F26 without task mutation; unknown decision refusal does not write state. Mobile parser 00a01d45.

**Where:** `aiwb/v2/report.py` `parse_remaining()` knows only `true/yes/y/1` and `false/no/n/0/none`; anything else
(`"nothing left"`, `"No, the project is complete"`, `"nothing"`, `[]`, missing field) is `None`. `proposals.import_data()`
accepts an empty `operations` list only when `remaining is False`; otherwise it raises `NoOperations` with
`rescue.fix_prompt()`. That prompt says *"`operations` must list at least one change"* and shows only create/update/
decision examples; it **never mentions** `roadmap_remaining: false` — the one field that would make the answer valid.

**Reproduce** (scripts `/tmp/hunt/fp2.py`, `/tmp/hunt/fp3.py`): all tasks are done; Home shows *"Tell the project
manager what changed and ask for the next step"*. The PM answers `{"summary": "Everything is done", "operations": [],
"roadmap_remaining": "nothing left"}` (or omits the field) → *"Nothing to apply: the proposal has no operations. A short
correction prompt is ready…"*. The correction prompt asks for at least one operation. A PM that follows it must add a
`create_task` / `update_task` / `propose_decision` that nobody needs; the project can never reach *"announce
completion"* through this path. Only the exact values `false` / `"false"` / `"no"` work (*"Plan PROP-0001 accepted. The
project manager says no roadmap stage is left — announce completion."*).

**Why it matters:** the very last step of every project. Models phrase "done" freely; the app then pushes the PM into
fake tasks (the same "revision 49 → 63 with no file" loop that 5.18.0 was meant to end) or leaves the user stuck at
*Tell the project manager…* forever.

**Expected:** accept more "no" forms (`nothing`, `nothing left`, `complete(d)`, `done`, strings starting with `no`,
empty list) or ask a yes/no question in the card when it is unknown; when `operations` is empty, the fix prompt must
offer both ways: *"either list at least one change, or — if nothing is left — answer with `\"operations\": [],
\"roadmap_remaining\": false`"*.

### BF-049 · S2 · DUPLICATE (of BF-023) — bundle import: a project with decisions / goal / own team but no tasks yet counts as "empty" → a bundle of **another project** replaces it with only *"Import the project (revision 2)."*

**Note (session 18):** same root cause as BF-023 (`plan_import()` checks `new` before `other_project` / `older`).
It shows the loss is bigger than a goal (accepted decisions, a custom team) — so BF-023 is raised to **S2**. Track
and fix under BF-023.

**Where:** `aiwb/v2/bundle.py` `plan_import()` returns `kind: "new"` (safe) when the local state has no `tasks`,
`proposals`, `milestones` or `handoffs`. It ignores `decisions`, `agents` (custom team), `settings.goal` / wizard
answers, `attempts`, Inbox answers and charter imports in progress. The `other_project` check comes **after** the
`new` branch, so a different `project_id` is never noticed in that case. `AI_Workbench.import_project_bundle()` then
asks a plain yes/no with the message *"Import the project (revision N)."* (no warning icon, nothing about what is lost).

**Reproduce** (script `/tmp/hunt/bd.py`): project B (folder `tmppe513o1i`) has goal *"B's own goal"*, an accepted
decision DEC-0001 *Database → SQLite*, and a custom agent `agent-db`, no tasks yet. Import the bundle exported from
project A → plan `{"kind": "new", "safe": true, "message": "Import the project (revision 2)."}` → after import:
`project_id` = A's id, goal gone, decisions `[]`, `agent-db` gone. Only a file
`.workbench/v2/backups/state-…-pre-bundle-import.json` remains (no UI tells the user it exists or how to restore it).

**Why it matters:** the typical moment to import from the phone is early (the user set up the team and answered the
first decisions on the PC, then picks the wrong bundle on the phone / in Downloads). The work is silently replaced by
a different project, and the folder now holds project A's state over project B's files.

**Expected:** treat any user content (decisions, non-default agents, goal, attempts, Inbox) as local work; check
`project_id` before the `new` branch (`other_project` unless the local state is the untouched default); make the
confirmation list what will be replaced and where the backup is.

### BF-050 · S2 · DUPLICATE (of BF-021) — project folder with a space or non-ASCII name (e.g. `پروژه من`, `my project`): the exported bundle can **never** be imported — on the phone or back on the PC

**Note (session 18):** same root cause and fix as BF-021 (found again independently in session 17). Kept for the
extra examples (`Ürün-Liste`, `-dash`, `۱۲۳`); track and fix it under BF-021.

**Where:** `aiwb/v2/controller.py` creates `V2Project(root, root.name)`, so the raw folder name becomes `project_id`
(`ProjectStore._default_project_id()`, which would sanitise it, is bypassed). `bundle.export_bundle()` writes it as is;
`bundle.read_bundle()` (desktop) and `Bundle.kt` (mobile, `State.PROJECT_ID`) both require
`^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$` and refuse with *"the project_id in the bundle is not valid"*.

**Reproduce** (script `/tmp/hunt/bd3.py`): folders `پروژه من`, `my project`, `Ürün-Liste`, `-dash`, `۱۲۳`, or a name
longer than 80 characters → *Export project to the phone* succeeds (*"Project exported to … Open it in AI Workbench Mobile →
Projects → Import."*) → importing that file, even into the same project on the PC, fails with *"the project_id in the
bundle is not valid"*. Renaming the folder later does not help: the old id is stored in `state.json`.

**Why it matters:** the owner's audience is Persian-speaking; Persian folder names and names with spaces are the norm,
and the user guide recommends *Export → phone*. The feature is dead for them, and the error text gives no hint why or
what to do.

**Expected:** derive a valid id at creation (`ProjectStore._default_project_id()`-like slug, ASCII fallback such as
`project-<hash>` for names without ASCII letters) and keep the display name separately; migrate existing invalid ids
on load (or in `export_bundle`, with the same mapping on import). At minimum, the export should refuse with a clear
message instead of writing a file that cannot be read.

### BF-051 · S2 · FIXED (98f3daa0, 35ea6c24, b9db856b, 02f020bf) — conflicting paths inside **one** answer are never checked: same path twice, case twins, a file named like a folder (→ the BF-009 crash, from a single answer)

**Repair evidence — session 30 / V5.22:** Desktop normalized duplicate staging keeps the last version with a visible duplicate_path warning. Full-set preflight rejects case twins, differently cased ancestor spellings, file/folder prefix conflicts and incompatible existing destinations before writes. Conflicts are visible on Home, cannot be accepted, and are independently checked at integration. Quick uses the same filesystem boundary. Original reproduction below is historical. Desktop Linux regressions validated; Windows release gate remains pending. These are unreleased source checkpoints, not a release.

**Where:** `aiwb/v2/files.py` `stage()` and `aiwb/v2/diagnose.py` look at each block on its own; the preview counts
blocks. Nothing compares the paths of one answer with each other, or with folders that exist on disk.

**Reproduce** (scripts `/tmp/hunt/dup.py`, `/tmp/hunt/dir.py`), guided *Paste the answer* → *Accept the delivery*:
- `src/a.py` twice (v1, then v2) → preview *"Files ✓ · 2 files"*, paste *"2 file(s) read"*, accept *"1 file(s) added"*;
  the first body is dropped silently (`./src/a.py` + `src/a.py` → same).
- `src/A.py` + `src/a.py` → *"2 file(s) added"*; on Windows / macOS (case-insensitive) the second **overwrites** the
  first; on Linux both exist and imports break depending on the OS.
- a block `path="src"` (AI meant the folder) + `src/a.py` → no warning anywhere; *Accept* raises
  `FileExistsError` / `IsADirectoryError` **after** the handoff was committed as accepted: task jumps to *Review*,
  `integrated_files` none, `src` left as a file or a stray `src.aiwb-tmp` in the project. Same if `src/` already exists
  on disk. This is BF-009's half-written state, but reachable from an answer alone (no locked file needed).

**Why it matters:** models repeat a file when they "fix" it later in the same answer, or name a folder in a block;
the user is told everything is fine and either loses the earlier body without knowing or ends in the BF-009 dead end.

**Expected:** in `stage()` / the smart check: merge identical normalised paths keeping the last and say so
(*"src/a.py was sent twice — the last version is used"*); flag case-insensitive twins and file-vs-folder conflicts
(within the answer and against the disk) as errors **before** *Accept* is offered.

### BF-052 · S3 · FIXED (9db49bb6) — "an accepted decision is final" does not hold for Persian titles written with Arabic letters or without the half-space

**Repair evidence — session 36:** Comparable decision titles unify Arabic/Persian letters and both digit sets, remove joiners/tatweel/diacritics, and normalize Persian inter-word spacing. Regression prevents re-proposing an accepted title across the reported keyboard variants. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/v2/rescue.py` `norm()` lower-cases and keeps `0-9a-z` + U+0600–U+06FF, turning everything else
(including ZWNJ U+200C) into a space. It does not unify Arabic `ي`/`ك` with Persian `ی`/`ک`, does not treat a missing
half-space as equal (`پایگاه‌داده` ≠ `پایگاهداده`), and keeps Persian digits. `duplicate_of()` (used by both
`translate()` and `proposals.import_data()` for `propose_decision`) compares these forms exactly.

**Reproduce** (script `/tmp/hunt/fa.py`): DEC-0001 *"انتخاب پایگاه‌داده"* accepted. A later proposal with
`propose_decision` *"انتخاب پايگاه‌داده"* (Arabic yeh — common from Arabic keyboards and some model outputs) or
*"انتخاب پایگاهداده"* (no half-space) → **not** recognised as already decided → a new *Decide:* card asks the same
question again. With ZWNJ or a normal space it is recognised.

**Why it matters:** the 5.18.0 guard against re-deciding (*"DEC-0002 approved three times"*) works only for English;
the owner's users write Persian.

**Expected:** in `norm()` map `ي→ی`, `ك→ک`, `ة→ه`, `ۀ→ه`, drop ZWNJ / tatweel / diacritics (U+064B–U+065F) before
comparing, convert Persian/Arabic digits to ASCII; reuse it wherever titles are compared.

### BF-053 · S2 · FIXED (e2e6bdf5) — one stray `{` in the prose before a marker-free JSON answer → "Cut off ✗", the complete answer is never read

**Repair evidence — session 36:** The JSON locator skips an unclosed prose brace and searches for a later complete object. A genuinely truncated JSON root is not replaced by a balanced nested section (42828f1a). Files regression and existing charter/corpus truncation gates pass. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/intake/lenient.py` `find_object()`: it scans from the **first** `{`; when `_balanced_end()` reaches the
end of the text without closing it and the rest of the text contains the wanted keys (`"files"` / `"tasks"`), it stops
with `truncated=True` — it never tries the next `{`. A `{` in prose (*"the {name placeholder"*, *"each task has a
{title, objective} pair"* without its `}`, *"{{x}"*) therefore swallows the real object that follows. Callers:
`answer_files.json_files()` (JSON-files answers) and `charter._load()` (marker-free charter).

**Reproduce** (scripts `/tmp/hunt/len.py`, `/tmp/hunt/len2.py`, `/tmp/hunt/len3.py`):
- Guided task, prompt HO-0001 open. Paste *"I replaced the {name placeholder. Here you go:\n"* + a complete
  `{"files": [{"path": "src/a.py", "content": "x = 1\n"}], "summary": "done", "outcome": "complete"}` → preview
  *"Cut off ✗ — the answer ends in the middle; paste it to get a continue prompt."*; paste → *"The answer was cut off.
  A continue prompt is ready."*; Home: *"The last answer was cut off — ask to continue"*. Without the stray `{` the
  same answer gives *"1 file(s) read from Strict JSON"*.
- Marker-free charter with *"Each task is a {title, objective pair."* before it → *"the charter JSON was opened but
  never closed (the answer was probably cut off)"*.

**Why it matters:** the answer is complete; the user is sent to ask the model to "continue", the model repeats the
same answer (with the same sentence), and the loop never ends. Nothing on screen points at the real cause.

**Expected:** in `find_object()`, when an object is not closed, keep scanning from the next `{` and prefer a balanced
object with the keys; report `truncated` only when **no** later balanced candidate exists (and ideally only when the
unclosed `{` is followed by `"key":` close to it, i.e. it really is the JSON).

### BF-054 · S2 · FIXED (03e11215) — any auto-repair of a damaged answer silently deletes every Persian half-space (ZWNJ), emoji joiner (ZWJ) and NBSP **inside the delivered files**

**Repair evidence — session 36:** Transport normalization preserves ZWNJ, ZWJ and NBSP inside AIWB bodies and ASCII/smart-delimited JSON strings; only structural transport whitespace is repaired. Mobile be43bdcf mirrors quote-aware preservation. Tests cover damaged headers, Persian and joined emoji, JSON trailing commas and smart-delimited literals. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/intake/normalize.py` `_strip_invisible()` (called first by `normalize()`) removes `ZERO_WIDTH =
"\u200b\u200c\u200d\u2060\ufeff\u00ad"` and replaces `NBSP` with a space in the **whole** text, file bodies included.
The module docstring promises bodies are touched only for "invisible characters that cannot legitimately appear in
source text" — but U+200C (ZWNJ) is a normal, required character of Persian writing (`می‌خواهم`, `پایگاه‌داده`), U+200D
joins emoji sequences, and NBSP is used on purpose in French/Persian UI strings. Callers use the normalised text as soon
as the raw text does not parse cleanly, so one damaged marker is enough to rewrite every file of the answer.
`lenient.loads()` does the same for JSON answers (via `normalize()`).

**Reproduce** (scripts `/tmp/hunt/zw.py`, `/tmp/hunt/zw3.py`, `/tmp/hunt/zw4.py`): a file body
`title = "می‌خواهم"` + `emoji = "👨‍👩‍👧"` + `nb = "10 km"`:
- clean `<<<AIWB_FILE path="src/t.py" action="write">>>` header → written byte-identical. ✓
- the same answer with a smart-quoted header (`path=“src/t.py”`), an escaped marker (`\<\<\<AIWB\_FILE …`) or a bold
  marker (`**<<<AIWB_FILE …>>>**`) — all very common chat-app damage → paste: *"Fixed automatically: the AIWB markers
  were damaged by the chat app (zero_width, marker_lines) — repaired."* → *Accept* → the file on disk is
  `title = "میخواهم"`, `emoji = "👨👩👧"`, `nb = "10 km"`. Quick mode (`quick.read_answer`) gives the same result.
- JSON-files answer with one trailing comma → the repaired file loses its ZWNJ too.

**Why it matters:** the owner's users write Persian; their UI strings, docs and Markdown files are full of half-spaces.
After one cosmetic marker fix every delivered file is silently misspelt (and emoji / string constants changed); the
message only talks about the *markers*, so nobody notices until much later, and the next prompt sends the damaged
text back to the model as the project's truth.

**Expected:** strip invisible characters only on **structural lines** (marker lines, fence lines, outside file bodies
and outside JSON string values); keep ZWNJ / ZWJ / NBSP inside bodies and strings. A leading BOM of the whole answer
may still be removed. If a body ever has to be changed, say so per file.

### BF-055 · S2 · FIXED (780fda13) — custom team (wizard): a task whose owner was removed / disabled, or that has no owner, is sent to the **project manager's** chat

**Repair evidence — session 34 / V5.23–V5.24:** Desktop dispatch, Home and direct task starts now share enabled-owner resolution; Mobile mirrors it (0858ced6/6dc92c5b/ec990505). Explicit enabled owners remain binding. Orphaned owners fall back to the least-busy enabled implementer, else another enabled worker, with deterministic ID tie-break; never to a manager or disabled template by fallback. If no worker exists, dispatch omits the task, Home offers assignment/replanning guidance instead of an impossible Prepare action, and direct start refuses without state mutation. Team editor/start form require explicit reassignment of open tasks before removal (efac9a3d/0a02cd29); the error names tasks and directs the user to their task editor. Historical agents remain disabled, not deleted. Start-form preflight runs before brief writes. Tests reproduce manager fallback and unguarded removal, drive custom-team direct starts/Home, exercise missing/disabled/empty owners, no-worker recovery, explicit-owner/load ranking, terminal history and injected save failure preserving state. No Mobile team-editor API exists in core; no such port is claimed.

**Where:** `aiwb/v2/waves.py` `_owner()` and `aiwb/v2/guide.py` `_owner()`: when the owner is missing or disabled they
fall back to `"agent-implementer"` if it exists, else `next(iter(agents))`. Since 5.9.0 a wizard project has **no**
`agent-implementer` (ids come from names: `agent-dev-a`, `agent-ai-2` …) and the first agent in the dict is always
`agent-project-manager`. `team_setup.save_team()` disables an AI that owns open tasks without reassigning them.

**Reproduce** (scripts `/tmp/hunt/team.py`, `/tmp/hunt/team2.py`): team *Project manager · Dev A · Dev B*.
1. TASK-0001 owned by Dev B, `ready`. Agents page › Edit team › remove Dev B → `{"disabled": ["agent-dev-b"]}`, no
   warning. Home: *"Start TASK-0001 T with Project manager"* → *Prepare* → *"Prompt for TASK-0001 ready. Copy it into
   agent-project-manager's chat."*
2. A task with no owner (e.g. a rescued `owner_role: "Implementer"`, BF-046) → *"Start TASK-0001 T2 with Project
   manager"*.

**Why it matters:** the developer prompt (files, AIWB blocks) lands in the manager's planning chat, mixing the two
roles the app works hard to keep apart; the PM chat's context fills with code and its next plans drift. The user
followed the button, so nothing tells them it is wrong.

**Expected:** fall back to an enabled non-manager AI (the least busy implementer-role agent, else any worker); never
the project manager. When removing / disabling an AI that owns open tasks, ask whom to give them to (or reassign to
the first remaining developer and say so).

### BF-056 · S3 · FIXED (session 37) — Edit team › changing an AI's role keeps the old role's purpose, rules and task types in every prompt

**Where:** `aiwb/v2/team_setup.py` `_write_team()`: for an existing agent only `name`, `role`,
`preferred_model_label`, `enabled` are changed. `purpose`, `instructions`, `allowed_task_types`, `review_policy`,
`escalation_rules` stay those of the template the AI was created with (`_agent_data()` is used only for new rows).

**Reproduce** (script `/tmp/hunt/team3.py`): team *Project manager · Dev A · Dev B* (developers). Edit team › Dev B role
→ *Reviewer / tester* → saved. A review task for Dev B → prompt: *"you are Dev B (agent-dev-b, role reviewer)"* then
*"## 1. Your role — Purpose: Implement one approved task within its scope."*; `allowed_task_types` still
`implementation, bug_fix, tests`.

**Why it matters:** the AI gets contradictory instructions (reviewer by name, implementer by purpose) and tends to
rewrite the code instead of reviewing it; a PM plan that checks task types against the agent sees the old list.

**Expected:** when the role changes, rebuild the role-specific fields from the new role's template (keeping the user's
note), or at least ask *"Reset this AI's instructions to the Reviewer template?"*.

### BF-057 · S3 · FIXED (d2be38db) — after *Drop this prompt…* / *Reject…* the workflow stage, the attention queue and the restart warning disagree with Home

**Repair evidence — session 33 / V5.23:** Rejecting a delivery now closes unfinished attempts (unanswered prompts become abandoned; parsed answers become rejected) and detaches only its own active pointer. Mobile shares this lifecycle repair (87715d22). Desktop workflow projects startable tasks without an active attempt, and legacy rejected/superseded handoffs, as ready_to_prepare before obsolete context flags; restart warnings ignore closed prompts (86ff81e5). Regression drives actual Guide Drop/Reject, checks Home Prepare, dashboard start_task and absent restart warning, verifies legacy projections are read-only, and starts a fresh attempt. Mobile regression verifies Drop/Reject, fresh restart, and that a late old response cannot steal the newer active attempt. Original reproductions are retained below. Final-source Desktop suite: 966 tests OK / 10 skipped; full Mobile pure-JVM suite: 110 tests OK. These are Linux unit/JVM results, not native Windows, Android APK/lint/device or final GUI gates.

**Where:** guided `abandon` rejects the handoff but leaves the task's `active_attempt_id` pointing at an attempt still in
`prompt_ready` (it is never moved to `abandoned`). `aiwb/v2/workflow.py` `task_stage()` reads the attempt, not the
handoff, so the task stays *"Prompt prepared, not copied"*; `WorkflowService.open_attempt_warning()` and
`dashboard.attention_queue()` use the same data. After `reject_handoff` the stage is `rejected`, which is not in
`USER_ACTION_STAGES`, so the attention queue is empty although Home's next step is *Start TASK-0001*.

**Reproduce** (scripts `/tmp/hunt/wf.py`, `/tmp/hunt/wf2.py`):
1. Prepare TASK-0001's prompt (HO-0001) → *Drop this prompt…* (reason "wrong chat"). Handoff `rejected`, attempt still
   `prompt_ready`. Home: *"Start TASK-0001 T with Implementer"* (correct), but the task's workflow line / Agents hub
   / attention queue says *"Prompt prepared, not copied — prompt built, not copied"*, and starting again warns
   *"TASK-0001 already has attempt att-… (prompt_ready). Starting again keeps it, but a late answer to it will be
   marked stale. Continue only if you really want a new attempt."* — about the prompt the user just dropped.
2. Paste an answer → *Reject…* → stage *"Rejected"*, `user_action=False`, attention queue `[]`; Home says *Start
   TASK-0001*.

**Why it matters:** not a dead end (Home works), but three screens give three different stories; the warning makes a
user who just dropped a prompt hesitate to start again.

**Expected:** `abandon` moves the active attempt to `abandoned` (or clears `active_attempt_id`); `task_stage()` returns
`ready_to_prepare` when the latest handoff of the active attempt is `rejected` and the task is still startable; the
restart warning ignores attempts whose handoff was dropped.

### BF-058 · S3 · FIXED (session 39) — before the first task exists, the "next action" (Workspace overview, phone, PROJECT_STATUS.md) says *"write the goal and copy the planning prompt"* even while a plan / decision waits

**Where:** `aiwb/v2/next_action.py` `compute_next_actions()` appends `plan_project` with **rank 1** whenever
`state["tasks"]` is empty; a pending proposal has rank 5 and an open decision 8/30, so `plan_project` always wins
until a plan is accepted. Used by `controller.next_action()` / `next_action_text()` / `next_action_view()` (Workspace
overview *Next step*, classic Projects window, phone companion `project_view`) and by `snapshot.build_snapshot()`
(`next_action` of the published `PROJECT_STATUS.md` and of the manager-update fallback summary).

**Reproduce** (scripts `/tmp/hunt/na.py`, `/tmp/hunt/na2.py`): new project, the PM's first plan PROP-0001 imported,
decision DEC-0001 open. Home (guide): *"Review the plan PROP-0001 (1 change)"* (correct). `next_action_text()`:
*"Write the project goal and copy the planning prompt to your project-manager chat"*; snapshot / PROJECT_STATUS.md:
*"**plan_project** : no tasks yet: prepare the project-manager planning prompt"*; the phone shows the same.

**Why it matters:** at the very first step of every project two screens disagree; a user who follows the overview or
the phone copies the planning prompt again and gets a second plan. The published status tells the PM the project has
not been planned although its plan is waiting.

**Expected:** add `plan_project` only when there are no tasks **and** no pending proposal / charter import / open
decision (or give it a rank after them); ideally derive the overview's next step from the same `Guide.steps()` that
Home uses.

### BF-059 · S3 · FIXED (session 39) — Workspace *Needs your attention › More › Mark as read* hides every **later** item of the same task / kind too (new delivery, new publish error)

**Where:** `aiwb/v2/dashboard.py` `attention_queue()` builds the item key as `f"{kind}:{ref}:{rank}"` — no handoff,
attempt, response or reason in it. `WorkspaceController.mark_seen()` stores these keys in `.workbench/v2/ui.json`
(`ws_seen`) and the overview calls `attention(hide_seen=True)`. So a key marked read once stays "read" for any future
event that lands on the same task at the same rank. Also `mark_seen()` keeps `sorted(cur)[-500:]`: the **alphabetically**
last 500, not the newest (once full, new `decision:` keys are dropped first and come back unread).

**Reproduce** (scripts `/tmp/hunt/dash.py`, `/tmp/hunt/dash4.py`):
1. TASK-0001, answer pasted for HO-0001 → overview: *"TASK-0001 · agent-implementer — Review the delivery"* → *More ›
   Mark as read*. Reject it, start again, paste a **new** answer for HO-0002 → queue item `task:TASK-0001:4`
   `seen=True` → the overview says *"Nothing needs your attention."*
2. Publishing paused *"token expired"* → mark read. Later it pauses for *"repository not found"* → key is still
   `publish:publish:1` → hidden as well.

**Why it matters:** "Mark as read" is meant for *this* notification; it silently mutes the task (or publishing) for
the rest of the project. A new delivery that waits for review, or a new GitHub error, never appears in the overview
list. (Home's guided steps still show the delivery, so it is not a dead end.)

**Expected:** include the event identity in the key (`task:TASK-0001:4:HO-0002`, `publish:<reason hash>`,
`proposal:PROP-0003`), or store the "seen" mark together with the state revision / handoff id and treat a changed one
as unread. Trim `ws_seen` by recency, not by sort order.

### BF-060 · S3 · FIXED (session 41) — Persian (RTL) Workspace still shows English labels and English "why" texts on the Overview and Project pages

**Where:** `aiwb/workspace/shell.py` builds several widgets with literal English text instead of `self.wc.tr((en, fa))`:
line 147 `"Open on Home"` (Next-step card button), 463 / 672 / 813 `"More"` (menu buttons), 468 `"Queue of each AI
(double-click a step to do it)"`, 471–472 headings `"Who"` / `"Step"`, 478–479 `"You"` and `f"{len(steps)} open"`,
605–607 the Project details keys `Goal / Name / Platform / Constraints / Answer format / Folder`, 610 the hint *"Change
them on Home (Next step › Change the project details…) …"*. In `aiwb/v2/dashboard.py` `attention_queue()` the `why`
part is always English (`f"{stage_label(stage, 'en')} — {ts['why']}"`, `"open decision: …"`, `"manager proposal
waiting"`, `"publishing paused: …"`, `"; no owner yet"`), and `WorkspaceController.attention_text()` shows it as
*"(چرا: …)"*.

**Reproduce** (script `/tmp/hunt/dash3.py`, plus reading `shell.py`): `set_language("fa")`, one delivery waiting →
Overview item: *"TASK-0001 · agent-implementer — تحویل را بازبینی کنید (چرا: Waiting for your review — answer parsed;
your review decides)"*; decision: *"DEC-0001 — تصمیم بگیرید (چرا: open decision: پایگاه داده)"*. On the same page the
queue box is titled *"Queue of each AI (double-click a step to do it)"* with columns *Who / Step*, rows *"You — 2 open"*,
buttons *"More"* and *"Open on Home"*.

**Why it matters:** the owner's users pick Persian; half-English screens with mixed-direction sentences (an English
clause inside an RTL line) are hard to read and look unfinished in the friends' demo. `test_dashboard_fa_labels`
checks only `rank_text` / `ask`, so the gap is not caught.

**Expected:** wrap every literal in `self.wc.tr(...)` (or i18n `TERMS`); give `attention_queue()` a translated `why`
(`stage_label(stage, lang)` and FA versions of the fixed phrases); extend the FA test to scan `shell.py` for
`text="[A-Za-z]` literals outside `tr((`.

### BF-061 · S3 · FIXED (ef7c9efe) — editing an **old** chat binding (note, name, link) makes it the AI's current chat again; the next prompt is recorded against the old chat

**Repair evidence — session 36:** Current chat selection uses confirmation/creation time, not metadata updated_at. Editing an old note no longer selects that chat; explicit confirm still can. Regression freezes two creation times then edits and confirms the historical binding. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/v2/resources.py` `current_binding()` picks the enabled binding with the greatest
`(updated_at, chat_binding_id)`. `update_binding()` (any field, e.g. only `note`) and `confirm_binding()` refresh
`updated_at`, so "the binding I touched last" wins, not "the binding I chose last". `workflow.bind_attempt()` freezes
that binding into the attempt when the prompt is copied.

**Reproduce** (scripts `/tmp/hunt/res.py`, `/tmp/hunt/res4.py`): Implementer bound to CHAT-0001 *"old chat"* (GPT free),
later to CHAT-0002 *"new chat"* (GPT paid) → current = *new chat* ✓. Edit CHAT-0001's note to *"archived, do not use"*
→ current = **old chat**; Agents page / Inspector: *"Implementer → GPT free · chat old chat"*; start a task and copy
the prompt → the attempt's `workflow.chat_binding_id` = `CHAT-0001`. *Confirm* on CHAT-0002 flips it back.

**Why it matters:** writing "do not use" on the old chat is exactly what makes the app use it; the history then says the
work was done in the free account's old chat (wrong audit trail, wrong account usage counts), and a user who reads the
Agents page pastes into the old chat.

**Expected:** keep an explicit "current" marker per agent (set by *bind_chat* / *Use this chat*), or order by
`confirmed_at` / creation instead of `updated_at`; editing a note must never change which chat is current. Optional:
creating a new binding disables (or marks "previous") the older ones of the same agent.

### BF-062 · S3 · FIXED (session 37) — the "looks like a password" filter refuses ordinary account / chat labels with the words *token* or *session* (and AI Studio chat links)

**Where:** `aiwb/v2/resources.py` `SECRET_RE` contains `(?:password|passwd|token|cookie|session|api[_ -]?key)\s*[:=]`
and `[A-Za-z0-9+/]{40,}={0,2}`; `_clean()` applies it to **every** text field (`display_name`, `chat_name`, `note`,
`provider`) and `_link()` to the chat link.

**Reproduce** (scripts `/tmp/hunt/res5.py`, `/tmp/hunt/res6.py`) — all refused with *"… looks like a password, token or
key. Workbench never stores model credentials; use a plain label instead."*:
- account profile names *"Gemini — session: work"*, *"GPT paid (token: 128k)"*;
- chat names *"Session: Monday planning"*, *"Login work — max token: 8000"*;
- notes *"token: 32k context"*, *"uses API key = none, web chat only"*;
- link `https://aistudio.google.com/app/prompts/1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd` (Google AI Studio's normal
  chat URL: a 40+ character id). ChatGPT / Claude / Gemini links pass.

In the Workspace the refusal only appears in the status bar (`_guard()`), after the user went through two
`askstring` dialogs, and the dialog values are lost.

**Why it matters:** "token" (context size, limits) and "session" (a chat session) are everyday words for people who use
several AI accounts; the message accuses the user of pasting a secret and gives no hint which part triggered it.
AI Studio users cannot record their chat link at all.

**Expected:** match real secret shapes (known prefixes, long high-entropy strings **without** spaces, `key=value` only
when the value itself looks random, e.g. ≥ 20 chars of `[A-Za-z0-9_-]`), allow long ids in the **path** of an
`https://` link (keep the query-parameter check), and name the matched fragment in the message.

### BF-063 · S3 · FIXED (6814ae4b) — context pack: line numbers and *symbol* slices are shifted when a file contains a form feed, U+2028 / U+2029, NEL or a lone vertical tab

**Repair evidence — session 36:** Context line spans split only CR/LF source line endings, not Python splitlines Unicode/form-feed separators. Regression verifies U+2028 inside source does not shift requested line 2; AST symbol line numbering uses the same source text. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/context_request.py` `resolve()` numbers lines with `text.splitlines()`, which also breaks on
`\x0b \x0c \x1c \x1d \x1e \x85 \u2028 \u2029`. Editors, `ast` (`python_symbol_lines()`), the model and every later
`range` request count only `\n` (and `\r\n`). From the first such character on, every number is off by one per
occurrence, and the symbol span from `ast` cuts the wrong lines.

**Reproduce** (scripts `/tmp/hunt/ctx.py`, `/tmp/hunt/ctx2.py`):
1. `src/mod.py` with a form-feed separator line (`\x0c`, allowed by PEP 8 and common in older / Emacs code) above
   `def target(): return 'T'` on lines 7–8 → request `{"mode": "symbol", "symbol": "target"}` → pack *"lines 7-8"*:
   `7: ` (empty) and `8: def target():` — the body `return 'T'` is missing.
2. `src/app.js` with `'x\u2028y'` in a string on line 2 → request range 3–5 (`function target() { … }`) → pack shows
   `3: y';`, `4: function target() {`, `5:   return 2;` — wrong text under the requested numbers, closing `}` missing.

**Why it matters:** the model is told "line numbers are part of the listing"; it plans edits by those numbers and asks
for follow-up ranges by them, so it reasons about the wrong code (or a truncated function) without any warning.

**Expected:** split with `text.split("\n")` (after normalising `\r\n` / `\r`), the same rule `ast` and editors use;
add a test file with `\x0c` and `\u2028`.

### BF-064 · S3 · FIXED (6814ae4b) — context pack: an **empty** requested file (e.g. `__init__.py`) is listed under *"Not provided"* as *"ready — "* and left out of the ZIP

**Repair evidence — session 36:** A ready/stale context item is deliverable even when content is empty. Empty files remain in inline/ZIP selection instead of being classified Not provided. Empty-file inline regression passes. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/context_request.py` `resolve()` gives an existing empty file status `ready` with `content = ""`;
`ResolvedItem.deliverable` is `status in ("ready", "stale") and bool(self.content)` → `False`. `pack_inline()` then
puts it in *"## Not provided"* as `- pkg/__init__.py: ready — ` (status and empty detail), `pack_zip()` skips it, and
`context_step.prepare()` counts it in `missing`. The window summary says *"N-1/N item(s) ready"* and, if the item is
`required`, *"required but unavailable: pkg/__init__.py"*.

**Reproduce** (script `/tmp/hunt/ctx3.py`): project with an empty `pkg/__init__.py` → request `files: ["pkg/__init__.py"]`
(or the folder `pkg/`) → resolved `status=ready deliverable=False`; inline pack:
*"## Not provided / - pkg/__init__.py: ready — "*.

**Why it matters:** the model is told the file could not be provided, with the contradictory reason "ready", and
typically asks again or assumes the package marker is missing (and then writes a new `__init__.py` or changes imports).
The user sees "required but unavailable" for a file that exists.

**Expected:** `deliverable` should depend on the status only; show an empty file as `## pkg/__init__.py (full_file,
lines 0, sha256 e3b0…) — (empty file)` and write the empty entry into the ZIP.

### BF-065 · S3 · FIXED (6814ae4b) — context pack: binary, UTF-16 and Windows-1252 files are pasted as garbage (U+FFFD, NUL bytes) and presented as "ready"

**Repair evidence — session 36:** Context decoding is strict UTF-8-sig, with explicit BOM-detected UTF-16 support. Binary NULs and unsupported encodings are refused with a convert-to-UTF-8 explanation instead of replacement garbage. Tests cover binary, invalid bytes and Persian UTF-16. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/context_request.py` `resolve()` reads every file with `data.decode("utf-8", errors="replace")` — no
binary check, no BOM / UTF-16 detection, no Windows-1252 fallback (Quick-mode ZIP import does all three, see
*Checked and OK*). A folder request (`assets/`) expands to every file in it, images included.

**Reproduce** (scripts `/tmp/hunt/ctx3.py`, `/tmp/hunt/ctx5.py`): request `assets/logo.png`, `win.txt` (cp1252
`café résumé`), `u16.txt` (UTF-16 `hello`) → all three `status=ready`, suggested delivery *inline*; the pack contains
`## assets/logo.png (full_file, lines 1-31 …)` followed by 31 "lines" of control characters and NUL bytes,
`1: caf� r�sum�`, and `1: ��h\x00e\x00l\x00l\x00o\x00`. The sha256 is of the real file, so nothing marks the text as
damaged.

**Why it matters:** the model receives a corrupted listing labelled as the current file and may "fix" the encoding or
rewrite the text it cannot read (accents lost → it writes `caf? r?sum?` back). NUL characters in the text can also cut
the clipboard copy short on Windows/Tk, so the user pastes an incomplete pack without noticing. Asking for a folder
that holds images (`assets/`, `static/`) is common.

**Expected:** detect binary files (NUL byte / known extensions) and report them as `binary — attach it in the ZIP
instead` (the ZIP path already copies raw bytes); decode UTF-8-BOM / UTF-16 (BOM) properly and fall back to
Windows-1252 with a note, as Quick ZIP import does.

### BF-066 · S3 · FIXED (6814ae4b) — context request for a folder named `build/`, `dist/`, `venv/` … is answered *"the folder does not exist or is empty"*; sub-folders with those names are dropped silently

**Repair evidence — session 36:** Explicit requested build/dist/venv-like folders are no longer silently filtered by generic project-scan exclusions. Protected .git/.workbench and bytecode caches remain excluded. Regression reads build/readme.txt, and the existing folder/noise regression still passes. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/context_request.py` `_expand_folders()` skips every file whose relative path contains a part in
`SKIP_DIRS` (`.git .workbench node_modules __pycache__ .venv venv dist build .idea .vscode`) — including the folder the
model **explicitly asked for**. When nothing is left, it reports `missing` with *"the folder does not exist or is empty"*.
Files under a nested `src/dist/` are also left out without any line in the pack.

**Reproduce** (script `/tmp/hunt/ctx4.py`): project with `build/gen.py` (a hand-written build script) and
`src/dist/x.py` → request `"build/"` → `[('build/', 'missing')]`, pack: *"- build/: missing — the folder does not
exist or is empty"*. Request `"src/"` → only `src/main.py`; `src/dist/x.py` is not mentioned anywhere.

**Why it matters:** many projects keep real source in `build/` (build scripts, Gradle/CMake helpers) or `dist/`
packaging config; the model is told a folder it can see in the file tree does not exist, so it creates a new one or
works around it. The user has no way to send it from the window (no "include anyway").

**Expected:** apply `SKIP_DIRS` only to folders **below** the requested one (and never to the requested folder itself);
report skipped sub-folders (*"src/dist/ skipped (build output) — ask for it by name"*); say "is empty" vs "does not
exist" separately. (Related small issue: requesting `pkg/core.py` and `pkg/` puts `pkg/core.py` in the pack twice;
de-duplicate after expansion.)

### BF-067 · S3 · FIXED (session 37) — a task title with line breaks (from a model's plan) injects fake sections into `PROJECT_STATUS.md` and the manager-update fallback summary

**Where:** `aiwb/v2/models.py` `_text()` only `strip()`s the ends, so `normalize_task()` keeps `\n` inside `title`
(limit 200) — for tasks created from an accepted `AIWB_MANAGER_PROPOSAL` as well as by hand. `aiwb/v2/snapshot.py`
`render_status_md()` writes `- {id} — {title} ({status})` as raw Markdown (same for decision titles and accepted
decision text). The result is published by `publisher.py` as `PROJECT_STATUS.md` and embedded by
`fallback_summary()` in the manager-update prompt; the header promises *"Generated by AI Workbench from local state;
not written by a model."*

**Reproduce** (script `/tmp/hunt/snap2.py`): a manager proposal with
`create_task` `"title": "Login page\n\n## Done with evidence\n\n- TASK-0099 — Payments (done)"` → accept → the status
file now has **two** `## Done with evidence` headings; under *Active tasks* it shows `- TASK-0001 — Login page`, and a
separate *Done with evidence* section lists `- TASK-0099 — Payments (done) (ready)` — a task that does not exist,
presented as verified work.

**Why it matters:** the status file is the "single source of truth" the next manager prompt relies on; a sloppy or
confused model answer (multi-line titles are common when a model puts the description in the title) silently corrupts
it, and the corruption looks like Workbench-verified state. The same title also breaks one-line UI rows (Tk Treeview
shows only the first line).

**Expected:** reject or collapse control characters / line breaks in single-line fields (`title`, decision `title`)
when normalising; in `render_status_md()` escape Markdown per item (replace newlines with spaces, escape a leading
`#`, `-`, `|`) so text from the store can never create a heading or a list item.

### BF-068 · S3 · FIXED (session 40) — a new **draft** task (e.g. created from the phone) is announced as *"Approve finished work so the task can be closed"* on the phone, the classic Projects window and the Workspace

**Where:** `aiwb/v2/next_action.py` emits type `approve_task` only for tasks in `draft` / `proposed` (*"task is draft;
complete it and mark it ready"*). `aiwb/i18n.py` `ACTIONS["approve_task"]` translates that type as
*"Approve finished work so the task can be closed"* / *"کار تمام‌شده را تأیید کنید تا Task بسته شود"*.
`ProjectsController.next_action_text()` / `next_action_view()` use this text; `companion/service.py project_view()`
sends it to the phone as `next_action`.

**Reproduce** (scripts `/tmp/hunt/comp.py`, `/tmp/hunt/comp2.py`): phone (permission *create_task*) → *Add task*
"From phone" → desktop state: TASK-0001 `draft` → phone `get_state` / Projects window next action: *"Approve finished
work so the task can be closed (TASK-0001)"*. Home at the same time says *"Approve TASK-0001 From phone — The task is a
draft. Approve it so it can start"*. Nothing has been worked on yet.

**Why it matters:** the user who just added an idea from the phone is told that finished work waits to be closed; it
reads like someone already did the task, and the phone (which cannot approve anything) shows it as the main message.
The two screens describe opposite situations for the same step.

**Expected:** translate `approve_task` as *"Approve the new task so it can start"* / *"Task جدید را تأیید کنید تا
شروع شود"* (or rename the type to `approve_draft`); keep "finished work" wording for `review_delivery`.

### BF-069 · S3 · FIXED (session 40) — phone pairing: approving the phone after the 10-minute code ran out registers the device, but the phone is told *"The pairing code expired"* and never gets its device id

**Where:** `aiwb/companion/service.py`: `pair_request` is accepted until `expires`; the request then waits in `pending`
for the desktop user. `decide()` does not check `expires` and adds the device to `devices.json` (`status: active`).
The phone learns the result only by polling `pair_status` with the pairing key, but `handle()` answers every `pair-…`
request after `expires` with `403 pairing_expired` — including that poll.

**Reproduce** (script `/tmp/hunt/comp4.py`, fake clock): start pairing → phone sends `pair_request` at t+590 s →
`200 pending` → desktop shows *Pixel* waiting (`pairing_state` already `expired`) → at t+620 s the user clicks
*Approve device* → `decide()` returns the new device (`active`) → phone polls `pair_status` → `403 pairing_expired` →
the phone shows *"The pairing code expired or was already used. Create a new one on the desktop."* The device list on
the desktop shows *Pixel — active*.

**Why it matters:** the two sides disagree. The desktop says the phone is paired; the phone says it is not, and it
cannot learn its device id, so it can never use the registration. Making a new code creates a second *Pixel* entry;
the first one stays *active* with a key nobody uses until the user notices and revokes it.

**Expected:** let `pair_status` (only that op) through for a pairing that is `used` and has a pending request or a
result, for a short grace period after `expires`. Or refuse `decide()` after `expires` (*"This request came too late —
create a new code"*) and clear `pending`, so no device is added. Show the remaining time next to the waiting request.

### BF-070 · S3 · FIXED (session 40) — phone *Send answer*: a Persian answer over ~150 000 characters (or any answer near the 300 000 limit) is refused with *"Companion error: bad_request"*; the `too_large` message is never reached

**Where:** `aiwb/companion/crypto.py` `check_shape()` refuses any envelope field longer than 400 000 characters. `ct`
is base64url of the whole UTF-8 JSON request, so the real ceiling is ~300 000 **bytes** of JSON — not 300 000
characters of text. `service.handle()` maps that `EnvelopeError` (raised before decryption) to
`400 {"error": "bad_request"}`. The size check that has a message, `MAX_TEXT = 300_000` characters in
`_dispatch("submit_response")` (`too_large`, *"answer is too large for the companion channel"*), can never fire:
anything over 300 000 characters is already over the envelope limit. Persian letters are 2 bytes in UTF-8, and JSON
escapes add more for `"`, `\` and line breaks (code). `server.py MAX_BODY` (512 KB) is not the limit either.

**Reproduce** (script `/tmp/hunt/comp6.py`, paired device with *submit_response*): ASCII 299 000 chars → `200`;
ASCII 300 001 chars → `400 bad_request` (not `too_large`); the largest Persian answer accepted is **149 983**
characters; a Persian answer of 175 000 characters (well under `MAX_TEXT`) → `400 bad_request`. On the phone
(`CompanionActivity.background()`) any non-200 code that is not in its list is shown as
*"Companion error: bad_request"*.

**Why it matters:** long Persian answers (a whole module with Persian comments / UI texts) are exactly what users
send from the phone. They fail with a message that looks like a program bug and says nothing about size, so the
user retries the same thing. The documented limit (300 000 characters) is wrong by half for Persian text.

**Expected:** size the envelope limit from the text limit (`ct` ≤ base64 of `MAX_TEXT` × 4 bytes + JSON overhead, and
keep `MAX_BODY` above that), or measure `MAX_TEXT` in UTF-8 bytes. Check the size before the envelope
(`413 too_large` from `handle()`), and on the phone map `too_large` / `bad_size` to
*"This answer is too long for the phone. Paste it on the computer, or send it in parts."* — ideally checked on the
phone before sending.

### BF-071 · S3 · FIXED (session 40) — phone and desktop clocks more than 5 minutes apart: pairing with the **correct** code is counted as *"Too many wrong attempts"*, and a paired phone gets only *"Companion error: unauthenticated"*

**Where:** `aiwb/companion/crypto.py` `open_bytes()` checks the MAC first and then the timestamp window
(`MAX_SKEW_SECONDS = 300`) and raises the same `EnvelopeError` for both. `service.handle()` turns every
`EnvelopeError` into `401 {"error": "unauthenticated"}` and, for a `pair-…` key id, calls `_pair_failure()`, so
after 5 such requests the code is cancelled (`_locked`). The phone (`CompanionActivity.background()`) has no case for
`unauthenticated` and shows *"Companion error: unauthenticated"*. The time is taken from each device's own clock;
nothing tells either side that the clocks differ.

**Reproduce** (script `/tmp/hunt/comp7.py`, fake clock): start pairing → the phone sends a correctly sealed
`pair_request` with its clock 7 minutes slow → `401 unauthenticated` ×5 → desktop: *"Too many wrong attempts - the
code was cancelled. Create a new one."*; 6th try → `403 pairing_expired`. A paired device whose clock is 6 minutes
ahead → every `get_state` → `401 unauthenticated`.

**Why it matters:** a phone with a manually set time, or a desktop that has no time sync, can never pair, and the
desktop blames the user for typing the code wrongly (the code was right — the MAC was valid). New codes fail the same
way. A phone that was paired stops working after a clock change with a message that gives no hint.

**Expected:** tell the cases apart: a valid MAC with a timestamp outside the window → `401 clock_skew` with the
desktop time in the reply, **not** counted as a wrong attempt. On the phone: *"The phone's clock and the computer's
clock differ by N minutes. Set both to automatic time and try again."* (or remember the offset from the reply and use
it). The desktop window should say *"A phone tried to connect but its clock is N minutes off"*.

### BF-072 · S2 · FIXED (session 40) — Mobile Companion › *Set permissions*: selecting a device does not load its permissions, so changing one permission silently removes the others (e.g. *submit answers* is taken away)

**Where:** `aiwb/companion/window.py`: one set of check boxes (`perm_vars`, initialised to `DEFAULT_PERMISSIONS` =
*view project* only) serves both *Approve device* and *Set permissions*. The device list has no `<<TreeviewSelect>>`
handler, so selecting a device never shows its current permissions. `do_permissions()` writes whatever the boxes
show to the selected device, without confirmation and without saying what changed.

**Reproduce** (script `/tmp/hunt/compwin.py`, under xvfb): device *Pixel* has `view_project, create_task,
submit_response` (shown in the list) → select *Pixel* → the boxes still show only *view project* → the user ticks
nothing else (or only adds one box) and clicks *Set permissions* → *Pixel* now has `view_project` only. The phone's
next *Send answer* → *"not allowed to submit response"*. The same carried-over boxes are used by *Approve device*, so
the permissions chosen for one device are silently given to the next phone that pairs.

**Why it matters:** the natural way to use the form (select → change one box → set) removes rights the user never
meant to touch. The user finds out only on the phone, far from the desktop.

**Expected:** on selection, load the device's permissions into the boxes (and reset them to the defaults for a new
pairing request); disable *Set permissions* / *Revoke* when nothing is selected; after saving, say
*"Pixel: view project, create task (submit answers removed)"*.

### BF-073 · S3 · FIXED (session 40) — Mobile Companion › *Pair new device…* while port 47821 is taken (second Workbench, another program) shows *"That action stopped because of a bug in AI Workbench"*

**Where:** `aiwb/companion/window.py` `do_pair()` calls `self.server.start()` without the `try/except OSError` that
`toggle()` has. `CompanionServer.start()` raises `OSError` (*Address already in use* / *Permission denied* / a LAN
address that is gone after a Wi-Fi change) from `ThreadingHTTPServer(...)`. The exception reaches
`_report_callback_exception`, which shows the generic *"Application error — … because of a bug in AI Workbench …
send this file"* dialog. The port is fixed (`DEFAULT_PORT = 47821`, no fallback, no setting); the host is detected
once (`lan_address()`) when the window is first opened and is never refreshed.

**Reproduce** (script `/tmp/hunt/compwin.py`, under xvfb): another socket listens on the companion port → open
Mobile Companion → *Pair new device…* → callback exception `OSError(98, 'Address already in use')` (generic bug
dialog in the app). The *Start* button with the same port → *"Could not start the endpoint: [Errno 98] Address
already in use"* (handled).

**Why it matters:** *Pair new device…* is the first button a new user clicks. A second Workbench window or any other
program on that port makes it look like a crash and asks for a bug report, with no hint about what to do.

**Expected:** handle `OSError` in `do_pair()` like `toggle()`, with a useful text (*"Port 47821 is used by another
program (maybe a second AI Workbench). Close it, or …"*); fall back to a free port (the QR code / manual address
already carry the port); re-detect the LAN address on *Start* / *Pair new device…*.

### BF-074 · S2 · FIXED (session 40) — phone standalone mode: if Android recreates the screen while the file picker is open (rotation, dark-mode switch, low memory), *Export project bundle* / *Save files as ZIP* leave an **empty file** and say nothing; a pasted answer is lost on rotation

**Found by code review** (no Android SDK in the sandbox; the logic is plain Kotlin and easy to follow).

**Where:** `apps/mobile/.../StandaloneActivity.kt`: `pickExport()` builds the bundle text into the field
`pendingExport` (ZIP: `pendingZip`) and only then opens `ACTION_CREATE_DOCUMENT`. The system picker **creates the
file** as soon as the user taps *Save*. `onActivityResult(REQ_EXPORT)` writes `pendingExport` — but if the activity
was destroyed and recreated in the meantime (rotation in the picker, theme / font / language change, process killed
while the picker is in front — normal on low-RAM phones), the field is `null` and the code does
`return@guard` silently. There is no `onSaveInstanceState`, no `configChanges` in `AndroidManifest.xml`, and the
`current` project and the screen content are not restored either. The views are built in code without ids, so the
*Paste the answer* `EditText` text is not restored by Android after a rotation.

**Result for the user:**
1. *Export project bundle* → picker → rotate the phone (or the system kills the app behind the picker) → *Save* →
   back in the app: no message (neither *"Bundle saved."* nor an error); the chosen file exists with **0 bytes**.
   Opening it on the desktop → *"the bundle is not valid JSON"*. The same for *Save files as ZIP* (empty ZIP →
   *"broken / empty ZIP"* on the desktop).
2. A long answer pasted into *Paste the answer* is gone after turning the phone; the open project falls back to the
   project list (or to the project from the launch intent).

**Why it matters:** the bundle is the only way to move a phone project to the desktop. The user thinks it was saved
(they chose a file and the picker closed) and may delete the phone copy or carry an empty file to the computer.

**Expected:** build the export text **in `onActivityResult`** from `current`/the project id (keep the id in
`onSaveInstanceState`), or save `pendingExport` to a cache file; if nothing can be written, delete the empty document
(`DocumentsContract.deleteDocument`) and say *"Export was interrupted — try again"*. Restore the open project and the
paste box text in `onSaveInstanceState`.

### BF-075 · S3 · FIXED (session 40) — phone *Import files from ZIP*: a GitHub "Download ZIP" lands under `myapp-main/…`, Mac `__MACOSX` junk and nested `.git` are imported, a ZIP with `./` or `\` names is refused whole, and existing files are overwritten without a backup

**Found by code review** (the path rule was replayed in Python: script `/tmp/hunt/kzip.py`).

**Where:** `apps/mobile/.../core/Files.kt` `unzip()` (button *Import files from ZIP* in `StandaloneActivity`):
- an entry is accepted only if `safePath(name) == name`, so harmless forms that `safePath` would normalise are
  treated as attacks and refuse the **whole** archive: `./src/a.py` (many zip tools), `src\a.py` (older Windows
  tools / .NET `ZipFile`) → *"Error: unsafe ZIP entry: ./src/a.py"*;
- no top-folder strip (desktop Quick-mode import does it, see *Checked and OK*): GitHub's *Download ZIP*
  (`myapp-main/src/a.py`) is written to `files/myapp-main/src/a.py`, so the next delivery creates a second copy at
  `src/a.py` and the context the phone sends is split in two trees;
- `.git` / `.workbench` are reserved only as the **first** part: `myapp-main/.git/…` (hundreds of objects) and
  `__MACOSX/…/._a.py` are imported; binary files and `.env` are written too (no binary / sensitive check, no
  512 KB per-file limit — `MAX_FILE` is used only for staging);
- each entry is read completely with `readBytes()` before the total is checked, so one large entry (a 25 MB ZIP of a
  big log / database dump expands to hundreds of MB) ends in `OutOfMemoryError` — an `Error`, not caught by
  `guard {}` → the app closes;
- existing files are overwritten in place (no backup, unlike `integrate()` which keeps `backups/<handoff>/`), not
  atomically, and nothing is recorded in the project (no event), so the change is invisible in the timeline.

**Why it matters:** importing the current code from a ZIP is how a phone-only user brings an existing project in. The
two most common ZIP sources (GitHub download, Mac Finder) give a wrong layout or junk, some Windows ZIPs are refused
with a "security" message, and a re-import silently replaces work.

**Expected:** reuse the desktop rules (`intake/answer_files.py`): normalise `./` and `\`, strip one top folder,
skip `__MACOSX`, `.DS_Store`, any `.git` / `.workbench` part, binaries and sensitive files with a list of what was
skipped; enforce a per-entry limit while reading; keep a backup of overwritten files and record a `files_imported`
event; show *"12 files imported, 3 replaced (backup kept), 5 skipped: …"*.

### BF-076 · S1 · FIXED (dd7a2cfa) — phone standalone mode: an answer pasted into the always-visible *Paste an AI answer → Read answer* box is never staged, so *Accept the delivery* writes **no file** (phone twin of BF-043)

**Repair evidence — session 32:** Project.routeAnswer now stages and diagnoses the canonical linked answer for standalone Read answer and guided paste alike; Guide consumes persisted checks without a second preview. Cut-off block/fence diagnostics create the shared Home continuation prompt for both routes (26b880d8, 7b51915d, 05f20187). Unstaged legacy responses cannot integrate. Real Kotlin/JVM tests assert on-disk accepted bytes, staging/diagnosis and standalone/guided cut-off prompts. Final full Mobile JVM suite: 108 tests OK using tools/test_mobile_jvm.py. This validates pure JVM logic, not Activity rendering, Android lint, APK compilation or on-device filesystem behaviour; those release gates remain pending.

**Found by code review** (no Android SDK in the sandbox; the Kotlin path is short and direct).

**Where:** `apps/mobile/.../StandaloneActivity.kt` `render()` puts a free *Paste an AI answer* box with a
*Read answer* button under every project screen. Its handler calls `p.routeAnswer(text)` (`core/Project.kt`)
directly. Staging (`Files.stage`), the smart check (`Guide.diagnoseInto`) and the cut-off check
(`Normalize.truncationReport` → continue prompt) run only in `core/Guide.kt` `paste()`, the step card's
*Paste the answer*. `routeAnswer` still links the answer (handoff `reconciled`, outcome from the manifest).

**Result for the user:** the developer prompt is out → the user pastes the AI's answer (with `AIWB_FILE` blocks) into
the big box at the bottom of the screen and taps *Read answer* → *"Answer linked to HO-0001 (reconciled, complete)."*
→ the top card now says *"Check what Implementer delivered … Accepting never closes the task."* (no *"Accepting adds N
delivered file(s)"*, because `staged_files` is empty) → *Accept the delivery* → `Files.integrate()` returns an
empty list → *"Delivery HO-0001 accepted. Next: review the task."*, task → `in_review`. **No file is written** to
`files/`; *Project files* stays empty / old; the ZIP and the bundle carry no code. A cut-off answer is accepted
the same way (no *"The answer was cut off"* prompt), and no scope / empty-file problems are shown.

**Why it matters:** on the phone the free box is the most visible place to paste (it sits under every screen, with
a big hint *"Paste the full answer from the chat here"*), and the result message looks like success. The work is
lost while the plan moves on; later tasks build on files that are not there. Same class as BF-043 / BF-010.

**Expected:** do staging + diagnosis + truncation handling in one place used by every entry point (move them
into `Project.routeAnswer` / `ingest`, or make *Read answer* call `Guide.run(step, "paste")`); and in
`accept_handoff`, if the stored response has file blocks but `staged_files` is empty, re-stage from the
response or refuse with *"the files of this answer were not read — paste it again"*.

### BF-077 · S2 · FIXED (session 40) — phone pairing: turning the phone (or leaving the Companion screen) while it waits for approval loses the pairing; the desktop then registers an *active* device nobody can use, and the same code can no longer be used

**Found by code review** (no Android SDK in the sandbox).

**Where:** `apps/mobile/.../CompanionActivity.kt` `pair()`: the random device key (`CompanionCrypto.randomBytes(32)`)
and the 5-minute `pair_status` polling loop live only inside the activity (local variable + single-thread
`executor`). Nothing is saved before the desktop approves. `AndroidManifest.xml` declares no `configChanges` for
`.CompanionActivity`, and there is no `onSaveInstanceState`. On rotation / dark-mode or font change / *Back* /
the system killing the app, `onDestroy()` calls `executor.shutdownNow()` → `Thread.sleep` is interrupted → the
result is posted to a destroyed activity and dropped. The new activity shows the pair form again, with no message.

On the desktop (`aiwb/companion/service.py`) the request already sits in `pending` (`used = True`); the user clicks
*Approve device* → `decide()` adds the device to `devices.json` as **active** with the lost key.

**Result for the user:** scan the QR code → *"Code sent. Approve this phone in Workbench on the desktop…"* → turn the
phone to read the code better / go back to take a screenshot → the pair form is back, the phone says nothing → on
the PC *Approve device* → *Pixel — active* in the list. The phone is not paired. Scanning the same QR again →
*"Companion error: this pairing code was already used"* (`pairing_used` has no own text). A new code adds a
second *Pixel* entry; the first stays *active* until someone revokes it (same leftover as BF-069). A *denied*
request also shows only *"Companion error: pairing was denied on the desktop"* (no own string).

**Why it matters:** pairing is the first contact with the Companion, and waiting up to 5 minutes for the user to
walk to the PC makes a rotation or a screen change during the wait very likely. The user ends up with a "paired"
device on the desktop and an unpaired phone.

**Expected:** save the pending pairing (host, port, pairing id, secret, device key, deadline) in prefs before
`pair_request` and resume polling in `onCreate`; do not cancel the poll on a configuration change (or declare
`configChanges` for this simple screen); add texts for `pairing_used` / `denied`; on the desktop, drop a pending
request whose phone stopped polling, or show *"waiting since …"* next to it.

### BF-078 · S1 · FIXED (f5c90e35) — *Ask only for what is missing* (repair) accepts the partial delivery but never writes its files, while the repair prompt tells the AI **not** to resend them: the files that did arrive are lost for good (desktop and phone)

**Repair evidence — session 32:** Mobile repair now integrates complete partial files BEFORE creating the missing-only prompt. Guide acceptance and file integration share one state transaction via resolveHandoffState; full-set preflight, immutable unique flushed backups, checked replacement and reverse rollback preserve the open handoff/payload on failure. State publication no longer deletes the last state on failed rename (19200653). Tests verify actual repaired bytes, blocked-backup refusal, real state-rename failure with rollback, retry without overwriting the first backup, and corrected retained-file overrides. Desktop repair remains covered by its earlier regressions. Final Mobile JVM: 108 tests OK; Desktop: 961 OK / 10 skipped. No Android device/APK gate is claimed.

**Partial repair — session 31:** Desktop now integrates partial files and acceptance through the shared rollback boundary before asking only for missing items. The repair prompt names the actual retained paths. Tests verify on-disk bytes, integrated_files and refusal without closing the handoff when publication/state writes fail. Mobile Guide.kt remains unchanged: this cross-platform finding stays OPEN.

**Where:** desktop `aiwb/v2/guide.py` `Guide.perform(..., "repair")` calls `c.resolve_handoff(ref, True, …)` (handoff →
`accepted`) and builds `repair_prompt()`, but does not call `files.integrate()` — only `accept_handoff` does. The
repair prompt lists the staged files under *"## Arrived complete (do NOT resend)"*. Afterwards the old handoff is
`accepted`, so it never shows a card again and nothing integrates it later. The phone does the same in
`core/Guide.kt` `"repair"` (`p.resolveHandoff(ref, true, …)` without `Files.integrate`).

**Reproduce** (script `/tmp/hunt/repair.py`, guided loop with the test helpers): TASK-0001 prompt → partial answer
(`src/core/a.txt` + manifest `partial`, unresolved *"missing file: src/core/b.txt"*) → *"Answer linked to HO-0001
(reconciled, partial)"*, staged `['src/core/a.txt']` → card *Check what Implementer delivered* → **Ask only for what is
missing** → *"Repair prompt for TASK-0001 ready (only the missing items)."*; the prompt says *Arrived complete (do NOT
resend): - src/core/a.txt* → files on disk: **none**; HO-0001 `accepted`, `integrated_files: None` → the AI sends only
`src/core/b.txt` → *Accept the delivery* → *"Delivery HO-0002 accepted and TASK-0001 approved. 1 file(s) added"* →
on disk only `src/core/b.txt`. **`src/core/a.txt` is gone**; TASK-0001 goes on to validation as approved.

**Why it matters:** the repair button is the recommended way out of a partial delivery (it is placed right after the
primary action). Using it loses exactly the work that was complete, and the prompt itself makes sure the AI will not
send it again. Nothing in the app says so; the task is approved with half its files. Later tasks fail on missing
code, and the user blames the AI.

**Expected:** in `repair`, integrate the staged files of the partial delivery (the same as `accept_handoff`) and say
*"1 file kept (src/core/a.txt); asking only for: …"*. Add the "files on disk" check to the E2E guide test
(`test_v2_guide.py` takes the repair path but only checks the prompt text). Same fix in the phone's `Guide.kt`.

### BF-079 · S1 · FIXED (113cf9d4) — *Troubleshoot* drops the good files of the rejected answer; the prompt says *"Fix ONLY these problems … do not change anything else"*, so a correct fix answer carries no files and is approved with **nothing on disk** (desktop and phone)

**Repair evidence — session 32:** Mobile troubleshooting carries complete safe staged files and original preview hashes into the next handoff, discloses retained paths in the prompt and permits explicit replacement. Manifest-only corrected delivery includes good retained code; a fresh file-scoped answer without code receives missing_deliverable rather than clean acceptance. Tests verify preserved on-disk code after manifest-only scope correction, replacement precedence, refusal of stale retained previews while preserving user CRLF edits, and failure/retry. Mobile staging also reports size/truncation/path conflicts instead of silently dropping them; dangling link regression found and fixed in c1d936e1. Final full JVM suite: 108 OK. Existing Desktop repairs remain tested. Android rendering/device/instrumentation gates are still outstanding.

**Partial repair — session 31:** Desktop troubleshooting carries complete, safe staged payloads into the new handoff; corrected files replace matching retained paths. Original preview hashes remain checked and the prompt discloses retained files. Manifest-only file-scoped tasks without prior published repair files produce missing_deliverable rather than clean acceptance. Regression proves a manifest-only scope fix still writes the retained good code. Mobile equivalents remain unchanged, so this finding stays OPEN.

**Where:** desktop `aiwb/v2/guide.py` `perform(..., "troubleshoot")` rejects the handoff (`resolve_handoff(ref, False, …)`),
so its `staged_files` are never integrated. `diagnose.troubleshoot_prompt()` lists only the problems and says *"Fix
ONLY these problems and send the corrected files completely; do not change anything else"*. It does not list
the files that were fine or ask for them again. The fix answer's smart check uses the task scope only.
`missing_deliverable` does not fire for an answer with **no** file at all. The phone has the same code in
`core/Guide.kt` `"troubleshoot"` + `Diagnose.troubleshootPrompt`.

**Reproduce** (script `/tmp/hunt/trouble.py`): TASK-0001 (scope `src/core/**`) → the answer has `src/core/a.txt` (good) +
`README.md` (out of scope) + manifest `complete` → *"Smart check found problems: out_of_scope"*, staged
`['src/core/a.txt']` → card *Problems found …* → primary **Troubleshoot** → the prompt shows only *"[out_of_scope]
README.md is outside this task's allowed paths"* → the AI does exactly that: *"Removed README.md (out of scope);
nothing else changed."*, manifest only, no file blocks → *"Answer linked to HO-0002 (reconciled, complete)."* → *Check
what Core developer delivered* → *Accept the delivery* → *"Delivery HO-0002 accepted and TASK-0001 approved. Next:
record whether the tests/build passed."* → files on disk: **none**; task `validation_pending`.

**Why it matters:** *Troubleshoot* is the primary button whenever the smart check finds a problem (out of scope,
one empty file, one truncated file). In every such case the good files of the first answer are thrown away. The
prompt invites a minimal fix, and the next answer is approved without its code. The data loss is silent, as in
BF-078.

**Expected:** keep the good staged files of the rejected answer and carry them into the new handoff (integrate them
on accept, unless the fix answer replaces them). Alternatively, list them in the prompt as *"send these files again
unchanged: …"*. In the smart check, flag an answer that has no file for a code task (`missing_deliverable` /
`no_files`), and do not let a clean *Accept* approve the task then.

### BF-080 · S2 · FIXED (session 38) — an answer with **no file blocks at all** (the AI put the code in an ordinary ```` ```python ```` fence) passes the smart check, and *Accept the delivery* approves the task with nothing written

**Where:** `aiwb/v2/diagnose.py` `diagnose()` raises `missing_deliverable` only for `expected_paths`, and the
guided flow never fills them: `controller.start_task()` → `handoffs.prepare()` without `expected_paths`, so the
attempt has `expected_paths: []`. `handoffs.ingest()` uses the same empty list. With zero files there is no
`empty_file` / `out_of_scope` either. The manifest's `completed_items` (e.g. `src/core/lib.py`) are not compared with
the delivered files. The *Check what … delivered* card mentions files only when `staged_files` is non-empty, so
it says nothing about their absence. The phone (`Diagnose.kt`, `Guide.kt`) works the same way.

**Reproduce** (script `/tmp/hunt/nofiles.py`): TASK-0001 *Core library* (scope `src/core/**`, criteria *"Unit tests
pass"*, *"docs/contracts/core-api.md written"*) → answer = attempt line + *"Here is the code:"* + an ordinary
```` ```python ```` block + manifest `complete`, `completed_items: ["src/core/lib.py", "docs/contracts/core-api.md"]` →
*"Answer linked to HO-0001 (reconciled, complete)."* (no *"N file(s) read"*), diagnosis `[]` → card *"Check what
Core developer delivered … Implemented the core library as requested. Accepting records your review approval"*
→ *Accept the delivery* → *"Delivery HO-0001 accepted and TASK-0001 approved. Next: record whether the tests/build
passed."* → files on disk: none; task `validation_pending`.

**Why it matters:** answering with a plain Markdown code block instead of the AIWB file format is the most common way
chat AIs break the format. The app treats it as a clean, complete delivery and approves the task. The only hint is
a missing *"N file(s) read"* phrase. This is also why the fix answer in BF-079 passes.

**Expected:** for a task with a code scope, an answer with no file block → error `no_files` (*"No file arrived — the
code is not in AIWB file blocks"*), with a troubleshooting / salvage prompt; compare `completed_items` that look like
paths with the delivered files (`missing_deliverable`); fill `expected_paths` from `deliverables`; say *"0 files"*
on the card.

### BF-081 · S2 · FIXED (af421197) — *Fix with helper AI* silently sends only the first 60 000 characters of a long answer; the rewritten answer that goes back into the paste box has lost the last files and the manifest, and the card only says *"The helper AI rewrote the answer"*

**Repair evidence — session 36:** Helper fixes over 60,000 characters are refused before any request with Nothing was sent or replaced and instructions to split complete files. Boundary-size answers remain complete. Replies over the response limit are rejected rather than silently sliced; the existing paste text is not replaced on error. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/helper_ai.py` `fix_messages()` cuts the answer to `MAX_ANSWER_CHARS = 60000` and tells only the
helper (*"The answer below was cut to its first part; convert only what is there."*). `aiwb/ui/next_card.py`
`fix_answer()` → `done()` puts the result into the paste box (replacing the user's full answer) with the fixed
message *"The helper AI rewrote the answer into Workbench's format. Check it in the box, then press \"Use this
answer\"."* — no word that a part was dropped. 60 000 characters is a normal size for a multi-file answer (8 files of
~700 lines ≈ 80 000 characters).

**Reproduce** (script `/tmp/hunt/helper_cut.py`, fake opener = an ideal helper that converts everything it is given
and invents nothing): TASK-0001 answer with 8 files `src/core/m0…m7.py` (700 lines each) as `### File:` headings +
```` ```python ```` fences and the manifest as plain JSON at the end (79 177 chars) → *Use this answer* fails → **Fix
with helper AI** → the helper receives the first 60 000 chars → result 60 305 chars, **no `AIWB_HANDOFF`**, `m6.py`
cut in the middle, `m7.py` missing → box filled, message *"The helper AI rewrote the answer…"* → *Use this answer* →
*"Answer linked to HO-0001 (reconciled, partial). 7 file(s) read … Smart check found problems: truncated."*, diagnosis
`no_manifest` + *"the code fence in src/core/m6.py was never closed"* → the user, who was just told the helper fixed
the answer, presses *Accept anyway* → *"7 file(s) added"*; `m6.py` on disk has **63 of 700 lines**, `m7.py` and the
manifest (outcome, open items) are gone.

**Why it matters:** the helper is offered exactly when an answer is long and messy. The problems it then shows look
like the chat AI's fault (*"truncated"*, *"no manifest"*), so the user troubleshoots the chat or accepts, while the
loss was made by Workbench. The original full answer is no longer in the box.

**Expected:** when the answer is longer than the limit, say so before sending (*"Only the first 60 000 of 79 177
characters can be sent to the helper — the last part (from `src/core/m6.py`) will be missing"*) or split it into
several calls by file block; after the call, add *"the helper saw only the first part; check the end"*; keep the
original answer (e.g. *Undo helper fix*).

### BF-082 · S3 · FIXED (session 40) — when the project manager says "complete", the closeout card hides open milestones and the pending release: the cycle is announced with *"0 milestone(s) accepted … Released: none"*, and the old milestones pop up again in the next cycle

**Where:** `aiwb/v2/guide.py` `steps()`: `end = closeout_steps(st)` — *"the end of the algorithm replaces every other
step"*. `closeout.can_announce()` checks only that every **task** is finished and that the last PM route is
`complete`. It does not check milestones still `planned` (their *Accept milestone* step, rank 15) or a version
waiting for *Release version …*. Both steps disappear from Home as soon as the plan with
`roadmap_remaining: false` is accepted. `closeout.expand()` does not close them either.

**Reproduce** (script `/tmp/hunt/close.py`): TASK-0001 done (*Tests/build passed*) → Home shows *Accept milestone Core
ready* and *Release version 0.1.0* → the other tasks are cancelled and the PM's plan says no roadmap stage is left
(`last_decision.route = complete`) → Home shows **only** *Announce the completion* → *"Completion announced. Cycle 1 is
complete: 1 task(s) done, **0 milestone(s) accepted** … **Released: none**."* → only *Expand… / Archive* are offered. The
milestone and the release can no longer be reached (archiving freezes them for good). After *Expand the project…* →
cycle 2 starts with *Accept milestone Core ready* and *Accept milestone Both apps usable* (a cycle-1 milestone whose
two tasks were **both cancelled**, offered with *"All its tasks are done"*; accepting it gives
*"Milestone MS-0002 accepted."*).

**Why it matters:** the completion record and the final archive bundle (the project's permanent summary) say nothing
was accepted or released, even when the user was about to do it. The release step, the one that records the tag and
the CI run, is silently skipped. The next cycle then starts with leftovers from the old roadmap.

**Expected:** `can_announce` (or the closeout card) should list the open milestones and the unreleased version and
offer them first (*"Before announcing: accept milestone Core ready, release 0.1.0 — or skip"*). On *Expand*, close or
carry over the old milestones explicitly. A milestone whose tasks are **all** cancelled should be offered as *Drop*,
not as *"All its tasks are done"*.

**Phone:** the same (`core/Guide.kt` line 48 `closeoutSteps(st)…?.let { return it }`; `core/Closeout.kt`
`canAnnounce` checks only tasks) — fix both.

### BF-083 · S3 · FIXED (session 37; phone port + card text session 41) — an AI decision request written as an object (`{"question": …, "options": […]}`) is silently dropped: the *waits for a decision* card shows only the unresolved item, without the question or its options

**Where:** `aiwb/v2/handoff.py` `ingest()` stores `decision_requests=_list(manifest.get("decision_requests"))`;
`_list()` keeps only `str` / `int` / `float` items, so object items vanish with no `fixes` / issue entry. After
*Accept*, `resolve()` sets `blocked_reason = "; ".join(unresolved_items or decision_requests)`, and
`choices.choice_spec()` builds the *Decide…* form from `decision_requests` (now empty) or from `blocked_reason`. The
prompt shows strings (`"decision_requests": ["what the user must decide"]`), but objects with a question and
options are the natural JSON form, and models often write them that way (the PM rescue reader already accepts
`decision_requests` with objects — `rescue.py` `DECISION_KEYS`).

**Reproduce** (scripts `/tmp/hunt/needdec.py`, `/tmp/hunt/needdec2.py`): TASK-0001 answer with outcome `needs_decision`,
`unresolved_items: ["storage layer"]`, `decision_requests: [{"question": "SQLite or JSON files?", "options": ["SQLite",
"JSON"]}]` → *"Answer linked to HO-0001 (reconciled, needs_decision) … Still open: storage layer"*; stored
`decision_requests: []` → *Accept* → card *"TASK-0001 Core library waits for a decision"*, text **"storage layer"**;
the *Decide…* form asks **"storage layer"** with **no options** → the user types something → *"Decision recorded
(DEC-0001)"*, decision title *"storage layer"*. The same answer with `decision_requests: ["SQLite or JSON files?"]` gives
the form question *"SQLite or JSON files?"* with the options *SQLite / JSON files*. (The card text itself shows
`unresolved_items` before the question even then.)

**Why it matters:** the decision is the only thing the AI needs from the user, and the app throws its wording away.
The user decides on a vague label, and the AI later gets a decision that does not answer its question.

**Expected:** accept object items in `decision_requests` (`question` / `title` / `text` + `options` / `recommendation`),
or at least turn them into text and note it in `fixes`; show the question (not `unresolved_items`) as the card text
of a `needs_decision` task. **Phone:** the same — `core/Project.kt` ingest `lst(k)` keeps only `String` / `Number` items (object items dropped), and `blocked_reason` prefers `unresolved_items` (line ~680) — fix both.

### BF-084 · S3 · FIXED (session 37) — a guided answer over 12 MB is never stored in the Inbox, but every message says *"It is kept in the Inbox"*; the handoff points to a response id that does not exist

**Where:** `aiwb/v2/controller.py` `route_answer()`: `cap = self.make_pipeline(self.root).capture_text(text, …)`;
`rid = cap.response.response_id if cap.response else ""` — `cap.issue` (`too_large`, `aiwb/inbox/store.py`
`MAX_RAW_BYTES = 12 MB`) is ignored and a made-up id is used instead: `rid = rid or "resp-" + sha256(text)[:12]`.
That id is never in the Inbox store (real ids are `resp-YYYYMMDD-HHMMSS-xxxxxxxx`), yet it is written to
`handoff.source_response_id` / proposal `source_response_id`, and the messages (*"This answer names a task/attempt
this project is not waiting for. It is kept in the Inbox; nothing was changed."*, *"… The raw answer is kept in the
Inbox."*, *"the answer is kept in the Inbox"*) are shown as usual.

**Reproduce** (scripts `/tmp/hunt/big.py`, `/tmp/hunt/big2.py`, `/tmp/hunt/big3.py`): TASK-0001 answer with a
third file of 12.6 MB (12 705 704 chars) → *"Answer linked to HO-0001 (reconciled, complete). 3 file(s) read …"*
(only 2 staged — the silent drop is BF-010) → Inbox items **1 → 1** (only the earlier answer), response id
`resp-2e10bee750eb` (not in the store). The same answer with an unknown attempt id → *"… It is kept in the Inbox;
nothing was changed."* → Inbox still 1 item, 1 raw file: the answer is **not** kept anywhere.

**Why it matters:** the user is told the answer is safe and can be found in the Inbox (re-parse, repair evidence,
diagnostics), so they close the chat or overwrite the paste box. The answer is gone. The repair-evidence path
(`_inbox_repair_evidence`) and *reparse* also cannot find it by the stored id.

**Expected:** when `capture_text` returns an issue, stop and say *"The answer is larger than the 12 MB limit and
was not stored; split it into smaller answers"* (nothing linked), or store it in chunks; never make up a response
id, and only say *"kept in the Inbox"* when it really was.

### BF-085 · S3 · FIXED (session 38) — Response Inbox › *Copy repair prompt* on an answer that parsed fine copies *"AI Workbench could not import your previous answer. The response could not be imported."*; the real gap (a missing file) is not named

**Where:** `aiwb/inbox/inbox_window.py` `repair_text()`: when the outcome has no salvage result (the normal case for a
well-formed AIWB answer: `status = parsed`, no issues), it falls into the *"could not import"* branch with the
fallback reason *"The response could not be imported."*. The button is never disabled and nothing checks
`out.status`. Guided-mode problems (missing file, partial outcome — known to the handoff) are not used.

**Reproduce** (script `/tmp/hunt/inboxwin.py`): TASK-0001 partial answer (only `src/core/a.txt`, manifest says
`b.txt` is missing) pasted on the guided card → *"Answer linked to HO-0001 (reconciled, partial) … Still open:
missing file: src/core/b.txt"* → Tools › **Response Inbox…** → the answer is listed (status still `captured`) →
*Reparse* → `parsed`, no issues → **Copy repair prompt** → clipboard:
*"AIWB_ATTEMPT_ID: att-… / AI Workbench could not import your previous answer. / The response could not be imported.
/ Resend the COMPLETE answer …"*.

**Why it matters:** the prompt tells the chat AI its answer failed completely and asks for everything again,
while one file is missing. The AI regenerates the files that were already fine (the *"do NOT regenerate"* list
that `repair_prompt` would give is empty here), and the user cannot tell from the message what is wrong.

**Expected:** disable *Copy repair prompt* (or say *"This answer was read without problems"*) when the last parse is
`parsed` with no issues. For guided answers, build the prompt from the handoff's diagnosis (missing / truncated
files) or send the user to the guided card's *Troubleshoot*. Also update the Inbox status after a guided paste
(it stays `captured`).

### BF-086 · S3 · FIXED (session 37) — *Save response candidate* stops for good after 30 candidates: the error says *"remove one before saving another"*, but the app has no way to remove a candidate

**Where:** `aiwb/candidate_store.py` `save_candidate()` refuses when `len(list_candidates(root)) >= MAX_CANDIDATES`
(30) with *"At most 30 candidates are retained per project; remove one before saving another."*.
`delete_candidate()` exists but has **no caller**: the Tools › *Several answers* menu offers only *Save response
candidate…* and *Compare candidates / choose files…* (`AI_Workbench.py` ~6587), and the compare window has only
*Merge selection and run Preview…* / *Cancel*. Merging does not remove the used candidates either.

**Reproduce** (script `/tmp/hunt/cand.py`): save 30 candidates → the 31st → *"At most 30 candidates are retained
per project; remove one before saving another."*; `list_candidates` = 30. Nothing in the UI deletes one.

**Why it matters:** the feature becomes unusable in an active project (a few tasks with 2–3 alternatives each
reach 30), and the only fix is deleting JSON files by hand inside the hidden `.workbench/candidates` folder. The
compare window also keeps offering all 30 old candidates for every path.

**Expected:** a *Remove* button per candidate (and *Remove all*) in the compare window, or auto-drop the oldest
when the limit is reached (with a note), or remove the candidates that were used in a merge.

### BF-087 · S3 · FIXED (session 39) — preview › *Semantic* tab: for a file over 256 000 characters a change after the cut is reported as *"(no textual differences detected)"* and *"Structural parsing failed … SyntaxError"*

**Where:** `aiwb/semantic_diff.py` `analyze_semantic_diff()` cuts `before` / `after` to `MAX_SEMANTIC_CHARS` (256 000)
**before** parsing and before the unified diff. The AST then sees a file cut in the middle (false *SyntaxError*), and
the diff of two identical prefixes is empty → `format_semantic_report` prints *"Added/Removed/Modified structural
items: none detected"* and *"Bounded unified diff: (no textual differences detected)"*. The only hint is the generic
*"source excerpt truncated to stay within analysis limits"*.

**Reproduce** (script `/tmp/hunt/sem.py`): a 617 780-char Python file with 20 000 functions; the new version renames
the last one (`f19999` → `g19999`) → report: no structural changes, warning *"Structural parsing failed; falling back
to text diff: SyntaxError: '(' was never closed (<unknown>, line 25822)"*, unified diff empty → *"(no textual
differences detected)"*.

**Why it matters:** the Semantic tab is the reviewer's summary of *what changed*. Here it says *nothing changed*
and *your file has a syntax error*, both false, for a change that the answer really makes. Generated files, data
files and large modules hit this.

**Expected:** when a side is over the limit, say *"File too large for semantic analysis (617 780 characters); see
the Diff tab"* and skip the AST, or diff the full text (only the output is bounded); never print *"no textual
differences"* unless the full texts are equal.

### BF-088 · S3 · FIXED (session 39) — dependency / change-impact analysis never resolves a relative import (`./util`, `../lib/x.js`, `#include "../inc/c.h"`): the preview's *Impact* tab says *"Direct dependents: (none resolved by static analysis)"* for ordinary JS/TS/C projects

**Where:** `aiwb/dependency_analysis.py` `scan_dependency_graph()` (line ~106): every reference goes through
`ref = ref.strip().strip(".").replace("\\", "/")`. `strip(".")` removes the leading dots, so `./util` → `/util` and
`../lib/helper.js` → `/lib/helper.js`. `PurePosixPath(rel).parent / "/util"` is then the **absolute** path `/util`,
which never matches a project file → the import is listed as *unresolved*. Only plain names next to the file
(`#include "b.h"`) still resolve. Used by the preview's impact pane (`AI_Workbench.py` `impact_worker` →
`analyze_project_impact`) and by *Static dependency graph…*.

**Reproduce** (script `/tmp/hunt/dep.py`): `src/app/main.js` = `import { x } from './util'` +
`import y from '../lib/helper.js'`; `src/app/a.c` = `#include "b.h"` + `#include "../../inc/c.h"` → forward edges only
`a.c → b.h`; unresolved `main.js: ['/lib/helper.js', '/util']`, `a.c: ['/../inc/c.h']`;
`analyze_project_impact(["src/app/util.js"])` → direct dependents **[]** (`main.js` imports it).

**Why it matters:** in JS/TS, relative imports are almost every internal import, so the impact report tells the reviewer
that changing a shared module affects nothing. A false *"no dependents"* is worse than no report.

**Expected:** do not strip dots from path-style references (only from Python module names); normalise `parent / ref`
with `posixpath.normpath`, and keep `..` that would leave the project as unresolved.

### BF-089 · S3 · FIXED (b2dff985) — architecture plan: a non-text `status` fails with the raw *"unhashable type: 'list'"*; `severity` is never checked, so the schema's placeholder `"low|medium|high"` is saved as a real value

**Repair evidence — session 36:** Architecture status type is validated before enum membership, giving field-specific errors for list/object/null/non-string input. Risk severity is low/medium/high (case normalized), invalid values rejected; the schema example uses medium and round-trips. Regression covers status variants, HIGH, banana and the schema example. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/architecture_plan.py` `validate_plan()`: `if status not in {"draft", …}` with `status = ["proposed"]`
or `{}` raises `TypeError: unhashable type: 'list'` (not `ArchitecturePlanError`). The editor (`AI_Workbench.py`
`open_architecture_plan_editor` › *Validate* / *Import JSON…* / *Validate and save plan*) catches every exception and
shows it as is: **"Invalid architecture plan — unhashable type: 'list'"**. The prompt builder (~9706) adds
*"Saved architecture plan was not embedded because loading/validation failed: unhashable type: 'list'"*.
Also, `risks[].severity` only has a length limit (40). `schema_contract()` (sent to the model) shows
`"severity": "low|medium|high"`, and a model that copies the template has that text accepted and saved as the
severity. `"banana"` / `"HIGH"` are accepted too.

**Reproduce** (script `/tmp/hunt/arch.py`): `schema_contract()` JSON with `"status": ["proposed"]` → `parse_plan` raises
`TypeError | unhashable type: 'list'`; with `risks[0].severity = "banana"` → valid, saved as `banana`; the unchanged
template → valid with severity `low|medium|high`.

**Why it matters:** the user sees a Python internals message with no field name, so they cannot tell which field to
fix (every other check names the field). Unchecked severities make the risk list unreliable, and the plan is embedded
in every prompt as *"validated"*.

**Expected:** check `isinstance(status, str)` first and say *"status must be one of draft, proposed, approved, blocked,
complete"*; accept only `low` / `medium` / `high` for severity (case-insensitive), or turn the placeholder into
`medium` with a note.

### BF-090 · S3 · DUPLICATE (of BF-069) — Mobile Companion: approving a device after the 10-minute code expiry adds an *active* device that the phone can never use; desktop says *"Device approved."*, phone says *"The pairing code expired or was already used"*

**Catalog reconciliation (session 28):** this repeats BF-069: the same `decide()` expiry omission, late approval at 620s, active orphan device and `pair_status` 403. The later report adds UI button-state detail, not a distinct root cause. Preserve its evidence below, track the fix under BF-069, and do not count BF-090 as another open defect.

**Where:** `aiwb/companion/service.py`: `handle()` refuses every `pair-…` request once `clock() > pairing["expires"]`
(`403 pairing_expired`) — including the phone's `pair_status` poll that must fetch the new `device_id`. But
`decide()` does not check the expiry, and `pending` is not cleared at expiry, so `companion/window.py` `refresh()`
keeps **Approve device** / **Deny** enabled under *"Code expired. Click 'Pair new device…'"* (it clears only the QR).
`decide(approve=True)` then calls `registry.add(...)` → a new `status: active` device with the phone's key.

**Reproduce** (script `/tmp/hunt/comp.py`, clock injected): `start_pairing` → phone `pair_request` (pending) at 0 s →
`pair_status` at 590 s → `pending` → user clicks *Approve* at 620 s (the window still shows the request; state
`expired`, `used: True`) → `decide` returns `dev-7d0f…` *active* → phone polls `pair_status` → **403
`pairing_expired`** → phone shows `R.string.pairing_expired`. `registry.list()` holds the active orphan device.

**Why it matters:** the user approved within the dialog, sees *"Device approved."* and a new device in the list, while
the phone reports failure; retrying adds another device each time. The orphan entries look like real paired phones
(`last_seen: never`) and keep a valid key on the desktop until revoked by hand. Slow approval is likely: the code is
consumed at the request, and users read the warning text first.

**Expected:** either let `pair_status` work for a used pairing until the result has been delivered (expiry applies to
`pair_request` only), or make `decide()` refuse after expiry and clear `pending` when the code expires, so the window
disables Approve and says *"The request expired; pair again"*.

### BF-091 · S2 · FIXED (307bd806) — a file block whose `<<<AIWB_END_FILE>>>` is missing swallows the **next** file: the marker line and the next file's text are written into the first file, the next file is lost, and the smart check says nothing

**Repair evidence — session 36:** A new file header terminates an earlier unclosed block as explicitly incomplete, rather than swallowing the next file. Staging refuses incomplete blocks and integration cannot override them. Mobile mirrors per-block completeness. c058de55 prevents canonical repair from manufacturing end markers for cut-off payloads; parser and repaired-cutoff regressions pass. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/v2/diagnose.py` `parse_files()` (used by `v2/files.py` `stage()` and by `diagnose()`): while a block is
open, every line — including a new `<<<AIWB_FILE …>>>` header — is appended to the open block's body until the next
`<<<AIWB_END_FILE>>>`. A header inside an open block is never treated as *"the previous block ended without its end
marker"*. `intake/normalize.py` `truncation_report()` only looks at the **last** header, so a missing end marker
in the middle is reported as *not* cut off; `diagnose()` sees `open_file = False` and no `truncated` problem.
The phone's `core/Diagnose.kt` `parseFiles()` uses the same rule.

**Reproduce** (script `/tmp/hunt/nested2.py`, on top of `/tmp/hunt/repair.py`): guided TASK-0001 answer with
`src/core/a.txt` and `src/core/b.txt`, the first `<<<AIWB_END_FILE>>>` removed (a common chat-copy loss) → paste →
*"Answer linked to HO-0001 (reconciled, **complete**). 1 file(s) read from AIWB file blocks."*, diagnosis only
`unverified_test_claim` → staged `src/core/a.txt` = `"src/core/a.txt content\n\n<<<AIWB_FILE path=\"src/core/b.txt\"
action=\"write\" body=\"raw\">>>\nsrc/core/b.txt content\n"` → *Accept the delivery* → *"1 file(s) added to the project
files"* → `a.txt` on disk contains the AIWB header and b's text; `b.txt` does not exist.

**Why it matters:** a source file in the project is silently corrupted (for code: a syntax error with an AIWB marker
in it), a delivered file is lost, and the task is approved as *complete*. Nothing on the card, the diagnosis or the
truncation check warns the user. Losing one marker line in a copy is common (the BF-053 / copy-damage family), and
the user has no reason to open `a.txt`.

**Expected:** in `parse_files()` (desktop and phone), a new `<<<AIWB_FILE` header while a block is open closes the
open block and records a `truncated` / `missing_end_marker` **error** for it ("the file block a.txt has no
<<<AIWB_END_FILE>>>; the next file started inside it"). Never stage a body that contains an AIWB header line.
`truncation_report()` should check every block, not only the last.

### BF-092 · S2 · FIXED (e2e6bdf5) — a valid JSON answer (files or marker-free charter) whose text contains a typographic quote `“Save”` is reported as *"Cut off ✗"* / *"never closed"*; the complete answer is never read

**Repair evidence — session 36:** Balanced-object scanning tracks the actual opening quote, so typographic quotes inside an ASCII JSON string remain data. A complete files answer containing Press “Save” is extracted without false truncation; existing corpus gates pass. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/intake/lenient.py` `_balanced_end()`: inside a string opened by a straight `"` it also ends the string
on U+201D (`if c == quote or (quote == '"' and c in "\u201d")`). In valid JSON, `”` inside a string is an ordinary
character (English UI text, README prose, Word/Docs copy: *Click the “Save” button*). Once `”` "closes" the string, the
real closing `"` opens a new one, string state is inverted for the rest of the text, and `{` / `}` are counted on the
wrong side. The object is reported as unclosed (`truncated=True`) or cut at a `}` inside a string. Callers:
`answer_files.json_files()` (via `extract()` → paste preview, guided paste, classic import) and `charter._load()`
(marker-free charter, and a charter whose end marker is missing). This is a different root cause from BF-053 (a stray `{`
before the JSON); that fix will not cover it.

**Reproduce** (scripts `/tmp/hunt/lenient.py`, `/tmp/hunt/lenient2.py`, `/tmp/hunt/lenient3.py`):
- `find_object('{"title": "Add the ”Save” button", "objective": "o"}')` → `text=''`, `truncated=True`;
  `find_object('{"a": "use ” then }", "b": 2}')` → `'{"a": "use ” then }'` (cut inside the string; `json.loads` → Unterminated string).
- *"Here is the result:"* + `json.dumps({"files": [{"path": "README.md", "content": "Click the “Save” button.\n"}, …]})`
  (strictly valid JSON) → `extract()` format `''`, no files, `truncated=True`; `preview()` →
  **"Cut off ✗ — the answer ends in the middle; paste it to get a continue prompt."** The same answer with straight
  quotes → *"Files ✓ · 2 files · Strict JSON"*. (Inside a ```json fence it reads fine, because fences skip `find_object`.)
- Marker-free charter (test fixture) with one task objective *"Add the “Save” button to the toolbar"* →
  `parse_charter` **"the charter JSON was opened but never closed (the answer was probably cut off)"**; the same charter
  after `<<<AIWB_PROJECT_CHARTER>>>` with a missing end marker → *"the charter block is not closed … (the answer was
  probably cut off)"*, instead of the planned *"end marker … was missing"* auto-fix.

**Why it matters:** typographic quotes are very common in model prose and docs. The answer is complete, but the user is
told it was cut off and asked to request "continue"; the model resends the same text and the loop never ends. Nothing
on screen points at the quote.

**Expected:** a string opened by `"` ends only at an unescaped `"`. A string opened by `“` (smart-quote damage) may end
at `”` or `"`. Track the opening character instead of treating `”` as closing every string. Add a test with `“…”` inside
a straight-quoted JSON value.

### BF-093 · S3 · FIXED (2e507150) — "copied as rendered text" repair strips every line-end `\` or `/` from **raw (unfenced) file bodies**: a `.gitignore` loses its folder slashes, a shell script / Dockerfile loses its line continuations

**Repair evidence — session 36:** Rendered-copy hard-break stripping excludes all raw AIWB file body lines, including lines ending in legitimate slash/backslash characters. Regression checks multi-line folder rules and continuation characters for both endings. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/intake/normalize.py` `strip_copy_damage()`: the line-end removal targets every line **outside code
fences** (`outside = [i for i … if not fenced[i]]`). The `in_file` guard (lines inside an AIWB file block) is applied only
to the Markdown-escape step, not to the line-end step. A `body="raw"` file (the format the guided prompt asks for:
`AI_Workbench.py` ~3209 *"Return complete text files using <<<AIWB_FILE … body="raw">>> blocks"*) has no fence, so its
lines count as "outside". When ≥ 60 % (and ≥ 3) of those lines end with `/` or `\`, which is normal for a `.gitignore`
(`node_modules/`, `dist/`, …) or a `docker run \` / `RUN apt-get … && \` script, exactly that character is removed from
every such line. Callers: `v2/quick.py` `read_answer()` (Quick mode, **always**) and `normalize()` (guided paste /
classic import / charter, as soon as one marker is damaged, e.g. a smart-quoted `path=“…”`, see `answer_files.extract`).

**Reproduce** (scripts `/tmp/hunt/copydmg.py`, `/tmp/hunt/copydmg4.py`):
- Quick: `<<<AIWB_FILE path=".gitignore" action="write" body="raw">>>` + `node_modules/ dist/ build/ .venv/ __pycache__/
  *.log` + END → file content `node_modules\ndist\nbuild\n.venv\n__pycache__\n*.log\n`, fix *"copy_damage:5 line-end
  slashes removed (answer was copied as rendered text)"*. These patterns now match files with those names, not only folders.
- Quick: a raw `scripts/run.sh` with `docker run --rm \` + 6 continuation lines → every `\` removed; the script runs
  `docker run --rm` alone and then fails on `-p 8080:80`.
- Guided (`answer_files.extract`) with the same blocks and one smart-quoted header `path=“…”` → same damage, reported
  only as *"the AIWB markers were damaged by the chat app (copy_damage, marker_lines) — repaired"*.
- The same files inside a ```` ``` ```` fence, or answers with enough prose, are left alone (so it shows up mostly for
  one-file answers, which are the common case for "update .gitignore" / "add a run script").

**Why it matters:** the user is told the *markers* were repaired; the file body change is silent in the file list.
Applying writes a broken script, or a `.gitignore` with different semantics, over the user's file. The plan shows it
as *changed* against an identical file on disk.

**Expected:** never apply the line-end repair inside an AIWB file block (from header to `<<<AIWB_END_FILE>>>`), the same
as the escape step. Count only prose lines when deciding whether the answer was copied as rendered text.

### BF-094 · S3 · FIXED (2e507150) — JSON auto-repair gives up when a value contains `“…”,` (typographic quote then a comma): an answer with one trailing comma becomes *"Nothing Workbench can read yet"*

**Repair evidence — session 36:** JSON repair only interprets typographic closing quotes when the string was opened with a smart delimiter. Literal “Save”, inside an ASCII string survives trailing-comma repair. Desktop and Mobile regressions pass. Unit/JVM source evidence only; no new release or native device gate claimed.

**Where:** `aiwb/intake/normalize.py` `_scan_json()`: inside a string opened by a **straight** `"`, a `“` or `”` is taken
as the closing quote when the next non-space character is `:` `,` `}` `]` or the end (*"A smart quote closing a string
that was opened by a smart quote"*, but the check never looks at how the string was opened). In `"He said “hi”, then
left"` the `”` before `,` ends the string, ` then left"` opens a new one, and the rest of the object is scanned
inside-out. The repaired text does not parse, so `normalize_json_text()` returns the original unchanged and **no**
repair is applied, including the trailing-comma / comment fixes the answer needed. Callers: `lenient.loads()` (JSON
files answers, marker-free charter) and `context_request._loads()`. This is different from BF-092 (`lenient._balanced_end`,
locating the object): here the object is found (e.g. in a ```json fence) but cannot be repaired.

**Reproduce** (scripts `/tmp/hunt/scanjson.py`, `/tmp/hunt/scanjson2.py`):
- `lenient.loads('{"a": "Click “Save” now", "b": [1,],}')` → OK (the `”` is followed by a space);
  `lenient.loads('{"a": "He said “hi”, then left", "b": [1,],}')` → **"not valid JSON: Illegal trailing comma before end
  of array"**.
- Paste preview, ```` ```json ```` fence with `{"files": [{"path": "README.md", "content": "Press “Save”, then close.\n"},],
  "summary": "done",}` → **"Nothing Workbench can read yet: no charter, no files, no handoff."**; the same answer with
  `Save` unquoted → *"Files ✓ · 1 file · Strict JSON · 1 auto-fix"*; with `“Save”,` but no trailing commas → *"Files ✓"*.

**Why it matters:** `“word”,` is ordinary English prose (and the normal style of many models and of Word/Docs text).
The repair layer exists for trailing commas and comments; one quoted word in any value silently turns it off, and the
user gets "nothing readable" with no hint why.

**Expected:** remember the opening character of each string. Only a string opened by `“`/`„` (smart-quote damage) may be
closed by `”`/`“`; a string opened by `"` closes only at an unescaped `"`. Same fix as BF-092; add a shared test.

### BF-095 · S3 · FIXED (d274ec4f) — Quick mode *Apply* silently overwrites edits the user made **after** the preview (and a file created meanwhile under a "new" path); the classic apply refuses this

**Repair evidence — session 30 / V5.22:** Quick plan captures exact original-byte SHA-256 (or absence); apply rechecks all paths before backing up/publishing and checks again per write. Stale existing and newly-created destinations refuse the whole apply with a review-again message and no writes. Plans missing preview hashes are refused. Original reproduction below is historical. Desktop Linux regressions validated; Windows release gate remains pending. These are unreleased source checkpoints, not a release.

**Where:** `aiwb/v2/quick.py` `apply()`: it trusts the `status` computed earlier by `plan()` (`new` / `changed`) and
writes `i["content"]` without re-reading the target. Nothing compares the file on disk with what the diff was built
from. `aiwb/ui/quick_window.py` `use_answer()` builds the plan when the answer is pasted; `apply_now()` applies it
later (minutes later, after the user has read the diff, often after switching to the editor). The classic
`AI_Workbench.apply_changes_transactionally()` has exactly this guard: *"File changed after preview; preview again to
prevent overwriting new changes"* / *"File was created/deleted after preview"*.

**Reproduce** (script `/tmp/hunt/quickstale.py`):
1. `src/a.py` = `x = 1`. Paste an answer with `src/a.py` = `x = 2` and a new `src/new.py` → plan *changed* / *new*.
2. Before clicking *Apply*, the user adds a line to `src/a.py` in their editor and creates their own `src/new.py`.
3. *Apply* → *"Applied 2 file(s) — backup A-0001."* Both files are replaced with no warning. The diff the user approved
   showed neither their new line nor the existing `src/new.py` (the tree said *new*).
4. *Restore last apply* brings both back (the backup is taken at apply time), so nothing is lost **if** the user
   notices. But the status line says nothing was overwritten that was not in the diff.

**Why it matters:** Quick mode is the "simplest" path and the user is expected to edit freely between rounds. The
approval was given for a diff that is no longer true; a file shown as *new* can overwrite an existing file.

**Expected:** keep the hash (or bytes) of each target as read by `plan()`; in `apply()` re-check every target first. If any
changed, or a *new* path now exists, write nothing and say *"src/a.py changed since the preview — review again"*, then
re-plan, like the classic apply.

### BF-096 · S2 · FIXED (session 39) — Git Review & Sync: a branch that exists on the remote but has no upstream can **never** be pushed ("remote branch changed since the plan" forever); a branch tracking `origin/main` stays *"ahead by 1"* after every successful push

**Where:** `aiwb/git/sync.py`.
- `build_plan()` reads `remote_sha` only from the tracking ref of `snap.branch.upstream`. With no upstream, `remote_sha=''` and the state is `NO_UPSTREAM` (push allowed, *"the first push will create it"*).
- `safe_push()` sets `upstream = plan.upstream or f"{remote}/{plan.branch}"` and calls `remote_branch_sha()` (live `ls-remote`). If `origin/<branch>` already exists, `live != plan.remote_sha ('')`, so the push is refused: *"The remote branch changed since the plan was built (expected none, found 3be6478…). Fetch and build a new plan."* Building a new plan gives `remote_sha=''` again, so the user is stuck in a loop. *Commit selected + Push…* has the same problem: the commit is created, then *"Commit created, push failed"*.
- Related: a branch created with `git switch -c feat origin/main` has upstream `origin/main`. `safe_push` checks the live SHA of **main** and pushes to `refs/heads/feat` without `-u` (because `plan.upstream` is set). The push succeeds, but the upstream stays `origin/main`, so every refresh shows *"Local branch is ahead by 1 commit(s)"* with *Push* enabled again. The "remote moved" guard also watches the wrong branch.

**Reproduce** (script `/tmp/hunt/gitsync.py`, real bare remote):
1. `git switch -c feat2`, commit, `git push origin feat2` (no `-u`, which is very common, and also the result of pushing from another tool or a CLI tutorial), then commit again.
2. Git Review → plan `no_upstream`, Push enabled → *Push…* → refused (above). Refresh/fetch → same plan → same refusal, every time.
3. `git switch -c feat3 origin/main`, commit → plan `local_ahead` (upstream `origin/main`) → push OK → refresh → still `local_ahead`, *"ahead by 1"*.

**Why it matters:** the only offered action always fails, and the advice it gives (*fetch and build a new plan*) cannot help. The user has to know `git branch -u origin/feat2` from a terminal. This is the "stuck with a misleading step" family.

**Also affects Sync & Build:** `aiwb/github/orchestrator.py` `commit()` stores `base_remote_sha = fresh.remote_sha` (same tracking-ref-only `build_plan()`), and `push()` compares it with the live `ls-remote` SHA of `origin/<branch>`. With a bound work branch that exists on GitHub but has no local upstream, every run ends with *"The remote branch moved; nothing was pushed. The local commit is kept."*; a retry gives the same result.

**Expected:** with no upstream (or an upstream whose branch name differs from the pushed branch), read the live SHA of `origin/<branch>` during `build_plan()` and store it as `remote_sha`. Compare and push against that ref. If it exists and is an ancestor of HEAD, push with `-u`; if not, say *"origin/feat2 already exists and has different commits — fetch and merge first"*. When the upstream is a different branch (`origin/main`), push with `-u` to `origin/<branch>`, or warn that the branch tracks `main`.

### BF-097 · S3 · FIXED (session 39) — Sync & Build: after *"The remote branch moved"* the user pulls/rebases as asked, then the resumed operation loops on *"HEAD moved since the commit was recorded; check again"*; *Check* never clears it

**Where:** `aiwb/github/orchestrator.py`. `commit()` records `git.commit_sha` and `base_remote_sha`; `push()` refuses when `snap.branch.head_sha != self.git.commit_sha` (*"HEAD moved … check again"*). `check()` on a record that has a `commit_sha` only logs *"Resuming: Local commit … exists (not pushed)"* and sets the state back to `COMMITTED`. It never compares the recorded commit with HEAD, and it never resets the record. `commit()` / `adopt_head()` return early (*"Idempotent"*) because `commit_sha` is set. `AI_Workbench.py` (~12310) offers *"Resume unfinished operation … ?"* for every record with a `commit_sha` and a non-terminal state, so reopening the window brings back the same dead record.

**Reproduce** (script `/tmp/hunt/sbresume.py`, real bare remote, two clones):
1. Sync & Build on work branch → Check → commit `b.txt`. Meanwhile someone else pushes to the same branch → push: *"The remote branch moved; nothing was pushed. The local commit is kept."*; *Next: "The remote moved: press Check to build a new plan."*
2. The user integrates the remote change (`git pull --rebase`, the normal fix; the local commit gets a new SHA).
3. Reopen → *Resume?* Yes → Check: all OK, state `committed`, *Next: "Press Commit + Push + Build to push the recorded commit."* → *"HEAD moved since the commit was recorded; check again."* → Check → same state → same error, every time.

**Why it matters:** every step the window suggests leads back to the same error. The only exits are *Cancel* (which says *"local commit … is kept"*, so it sounds risky) or answering **No** to *Resume?*, and nothing on screen suggests either one. The rebased commit (same content) is what the user wants to build.

**Expected:** in `check()`, if the recorded commit is not pushed and HEAD differs from it, say so and offer *"Use the new HEAD {sha} instead"* (adopt it after the same ahead-of-remote checks; update `base_remote_sha` from the fresh plan), or mark the record superseded and start a new operation. Also, do not offer *Resume?* for a record whose commit is no longer HEAD or an ancestor of HEAD.

### BF-098 · S3 · FIXED (session 37) — New Project wizard: an empty *Parent folder* is accepted and the project is created in the app's current working directory (on Windows often the install folder or `C:\Windows\System32`)

**Partial repair — session 36 (not counted fixed):** d048bf6a rejects empty/relative parent in the wizard, with a no-display regression. Still OPEN: create_project_folder itself still resolves relative parents; the independent service-boundary guard and actual Windows GUI gate remain.

**Where:** `aiwb/ui/project_wizard.py` `problems()` step 0: `Path(self.vars["parent"].get().strip() or ".").expanduser().is_dir()`. The `or "."` turns an empty field into the current directory, which always exists, so the check passes. `AI_Workbench._create_from_wizard()` → `create_project_folder(Path(d["parent"]).expanduser(), …)` with `d["parent"] == ""` → `Path("")` resolves to the process CWD. Neither layer refuses an empty parent.

**Reproduce** (script `/tmp/hunt/emptyparent.py`): clear the *Parent folder* field (it is pre-filled with `~/Documents`, so the user has to empty it, e.g. intending to *Browse…* and then cancelling after selecting the text) → *Next* is accepted → *Create project* → `create_project_folder(Path(""), "Calc", …)` creates `<CWD>/Calc`. The status says *"Created Calc …"* without the full path. When started from a shortcut, the CWD is the program folder (Program Files → *PermissionError*, shown as a raw error) or wherever the launcher was, so the user cannot find the project.

**Why it matters:** the project ends up somewhere the user did not choose and does not see, often inside the app's own folder (lost on uninstall/update), or the step fails with a confusing permission error.

**Expected:** treat an empty parent as missing: *"Choose an existing parent folder."* Drop the `or "."` fallback, and in `create_project_folder()` refuse an empty or relative parent.

### BF-099 · S3 · FIXED (session 40) — classic Projects window: the proposal review dialog grows one row per operation with no scrollbar; for a normal planning proposal (≥ ~28 operations on a 768 px screen) *Apply selected* / *Cancel* are off-screen

**Where:** `aiwb/v2/projects_window.py` `ProposalDialog`: one `ttk.Checkbutton` per operation is packed straight into the `Toplevel`, then the button bar. There is no scroll container, no size or geometry, and no keyboard binding (`<Return>` / `<Escape>`). `grab_set()` + `wait_window` make it modal. `proposals.MAX_OPS = 60`, and a first plan from the project manager (create tasks + assignments + dependencies) easily has 30–60 operations. Reached through Project Workbench › Tools › *classic* (`classic_projects` → `ProjectsWindow.do_proposal`).

**Reproduce** (script `/tmp/hunt/propdlg.py`, xvfb 1366×768): 40 valid `create_task` operations → dialog requested height **1041 px** on a **768 px** screen. The bottom ~270 px, including the only two buttons, cannot be reached. The window manager cannot make the window taller than the screen, and there is nothing to scroll.

**Why it matters:** the user cannot accept the plan from this dialog at all. The only way out is closing the window (treated as *Cancel*, so nothing is applied). The modal grab blocks the main window meanwhile. Laptops at 125 % scaling hit this with even fewer operations.

**Expected:** put the operation list in a scrollable frame (or a `Treeview` with check marks) with a bounded height, keep the button bar outside it, bind `<Return>` = *Apply selected* and `<Escape>` = *Cancel*, and add *Select all / none*.

### BF-100 · S3 · FIXED (session 40) — decision form: a long question hides OK, rationale and validation feedback below the clipped window

**Where:** `aiwb/ui/action_form.py:50–77`: the full question, all radio options, rationale, error label and button bar are packed into one non-scrollable body. `place_dialog()` caps the window at the available screen height; `choices.form_spec()` does not cap the question.

**Reproduced again in session 28:** Tk 8.6, Xvfb 1366×768, `ActionForm(..., modal=False)`, six options and a rationale field. Use question `("The architect proposes two storage designs for the history feature. " * n).strip()` and six option labels `Option {i}: store history in format {i} with sync`. After `top.update()`, n=14 (951 characters): body 655px, window 663px, OK mapped. n=18 (1223 characters): body 735px, window capped at 696px, OK **not mapped**. n=22 (1495 characters): body 795px, window 696px, both OK and error label **not mapped**. Inspect `f.ok_btn.winfo_ismapped()` and `f.error_label.winfo_ismapped()`.

**Impact:** users cannot see the confirmation button; with longer questions the rationale / Other answer field and validation feedback also disappear. Enter and Escape remain workarounds, so this is not a total deadlock. The missing error feedback makes a rejected submission look unresponsive.

**Expected:** bound or scroll the question/form content; keep confirmation, cancellation and error feedback outside the scroll area. The previous session's attempted BF-100 checkpoint did not reach GitHub; this entry recovers it after a fresh reproduction.

### BF-101 · S2 · FIXED (session 39) — Run workflow: changing Branch / tag keeps the input schema and defaults from the original ref

**Where:** `aiwb/github/build_center_dialogs.py:75–87,100–143`. `dispatch_form(..., ref=ref)` runs only in the constructor. The ref Entry remains editable but has no refresh/trace binding. `submit()` validates against `self.form` and sends that same form with the newly typed ref. `GitHubDispatchService.dispatch()` validates the supplied form; it does not reload the file at the new ref.

**Reproduction (local Tk probe, no real dispatch):** replace `_Worker.run` with a synchronous adapter that invokes `done(work("FAKE"))`; a recording service's `dispatch_form()` returns a required `channel` choice, default `beta`, options beta/stable. Open with ref `main`, set `d.ref_var.set("release")`, then `d.submit()`. Observed schema reads: **["main"]**; submitted ref: **release**; submitted inputs: **{"channel": "beta"}**, using the unchanged main form. The recording service returns a synthetic confirmed result so lookup/polling is not involved.

**User impact:** when release's workflow adds a required input, changes options, or uses a different default, the UI cannot collect the right fields. GitHub can reject the stale payload with HTTP 422; if it accepts the same names/options, the explicit main-branch defaults can override the intended release-branch defaults. Changing back/retrying never reloads the schema. Closing and reopening from the unchanged project branch loads main again.

**Expected:** invalidate and reload the workflow schema when ref changes, retain its ref alongside the form, disable submission while stale/loading, and only validate/dispatch a form associated with the exact submitted ref. Preserve still-valid entered values deliberately rather than silently reusing unrelated defaults.

### BF-102 · S3 · FIXED (session 40) — workflow dispatch form has unbounded input rows and unwrapped descriptions, exceeding the screen in both dimensions

**Where:** `aiwb/github/build_center_dialogs.py:71–86,105–123`: each workflow input and its description is gridded into `inputs_frame`. Description labels have no `wraplength`; neither a scroll container nor screen-fit geometry is installed. Status and Run/Close buttons follow the entire list.

**Measured locally:** Tk 8.6, Xvfb 1366×768; load a `DispatchForm(True, tuple(DispatchInput(f"input_{i}", description="Description " + "x"*250) for i in range(25)))`. The dialog requests **2271×839px**. The parser permits up to 25 inputs (`MAX_INPUTS`) and retains descriptions up to 300 characters, so this is within the application's accepted schema, not an over-limit form. The problem can also occur horizontally with far fewer inputs and a long single-line description.

**Impact:** part of the form and/or the Run/Close bar is outside the visible desktop. A window manager may constrain the window instead, but there is no content scrolling to recover the clipped controls. Manual window movement/resizing is an awkward workaround and does not solve the missing layout bounds. This is a separate dialog from BF-099/BF-100, with the same unbounded-layout family plus an independent horizontal-width issue.

**Expected:** wrap descriptions, bound the dialog to the work area, scroll the input region in both necessary directions, and keep status and Run/Close outside it. Add GUI coverage for maximum supported inputs and long descriptions on laptop-size displays.

### BF-103 · S2 · FIXED (session 39) — Build Center: selecting another run during a job fetch shows jobs/log links from the previous run

**Where:** `aiwb/github/build_center.py` `_load_jobs()`: the run is captured at request start. Selecting a second run clears the job tree but returns immediately when `self.busy` is true. The first request's `done()` unconditionally fills `self.jobs` and the tree; it never verifies that the selection still matches the captured run and never queues the second selection. Tree selections remain enabled during network work. `_open_job()` then opens the stale job's log URL.

**Reproduced locally with real Tk selection events:** construct `BuildCenterWindow` with initial refresh disabled and two completed runs (IDs 1 and 2). Replace `_run` with a deferred callback recorder that sets busy; select `1:1` and process Tk events, then select `2:1` and process events while the first callback is pending. Complete that callback with `WorkflowJob(11, "JOB FOR A", "completed", "failure", "", "", "https://github.com/o/r/actions/runs/1/job/11")`. Observed: selected run **2**, only **one** job request, job tree **["JOB FOR A"]**, status **"Run 1: 1 job(s) ..."**. This deterministically models a slow network response; no GitHub requests are made.

**Impact:** failed steps and the double-click log target belong to run A while run B remains selected. This can send the user debugging the wrong commit/run. The status names A, but the selected row and other run actions still target B. Reselecting B after the request finishes is a workaround; later polling may also repair it.

**Expected:** associate results with a run-ID/attempt selection generation, discard stale results, and schedule a fetch for the latest selection after the current worker finishes. Clear the cached jobs with the displayed rows. Cover run changes and workflow changes during a pending request.

### BF-104 · S3 · FIXED (a6778e48) — Extract artifact lets CRC/decompression errors escape instead of reporting a refused extraction

**Repair evidence — session 29 / V5.22–V5.23:** Extraction boundary normalizes CRC, zlib, EOF and unsupported-compression failures to UnsafeArchiveError after staging cleanup. Unit tests include a valid directory with a corrupted member after a good member; real Tk smoke confirms a refusal message, no callback exception and no extraction leftovers. Original reproduction below is retained as historical evidence. Linux regression validated; Windows release gate is still pending.

**Where:** `aiwb/github/build_center_dialogs.py:275–292`. Initial `inspect_zip()` validates directory metadata, not member CRCs. `safe_extract_zip()` subsequently reads members and may raise `zipfile.BadZipFile`, `zlib.error`, or unsupported-compression errors; the UI only catches `UnsafeArchiveError` and `OSError`. `BadZipFile` is not an OSError. The extractor correctly cleans its staging directory but re-raises the original exception.

**Reproduced locally:** create a ZIP_STORED archive in BytesIO with `a.txt` = `b"hello"`, then flip one payload byte at offset `30 + len("a.txt")` without updating CRC. Save it in a TemporaryDirectory and register that path as the selected artifact's downloaded ZIP in a real `ArtifactsDialog` with loading suppressed and confirmation returning True. `inspect_zip()` accepts one member. Calling `extract()` raises **BadZipFile: Bad CRC-32 for file 'a.txt'** past the UI boundary; status stays **"1 artifact(s). Expired artifacts cannot be downloaded."** instead of a refusal reason. No destination or staging leftovers remain. No network involved.

**Impact:** corrupted/unsupported ZIP content yields the global callback-error path rather than the actionable extraction message. This does **not** demonstrate a whole-app crash, unsafe extraction or partial output: staging cleanup was verified. A locally altered archive, or a consistently corrupt archive without a reference digest, can reach this path; a detected download digest mismatch is already refused earlier.

**Expected:** normalize ZIP/CRC/decompression failures into UnsafeArchiveError at the service boundary (with a safe message) or catch them explicitly in the UI. Keep atomic cleanup and test metadata-valid/payload-corrupt ZIPs, not only invalid ZIP headers and unsafe names.

### BF-105 · S2 · FIXED (a6778e48) — failed artifact integrity check deletes a previously valid download because replacement precedes digest verification

**Repair evidence — session 29 / V5.22–V5.23:** All size/ZIP/SHA-256 checks precede os.replace; cleanup owns only a uniquely created temporary file and never final. Regression injects digest, size, format, cancellation, stream and publish failures with a pre-existing valid final; its bytes remain unchanged and no attempt files remain. Original reproduction below is retained as historical evidence. Linux regression validated; Windows release gate is still pending.

**Where:** `aiwb/github/artifacts.py` `download_artifact()`: after size/ZIP checks, `os.replace(part, final)` overwrites the existing target. SHA-256 is compared with the reference **afterwards**. On mismatch it unlinks `final`, which is now the replacement; the old target has already been destroyed. The UI asks for a folder, not permission to replace an existing file, and offers no backup.

**Reproduced locally using existing test transports:** import `ArtifactTests, make_zip, TOKEN, run` from `tests/test_github_artifacts.py`. Build old=`make_zip([("a.txt", b"hello")])` and incoming=`make_zip([("a.txt", b"jello")])` (same length). Configure `ArtifactTests().service(incoming, payload=artifacts_payload(size_in_bytes=len(incoming), digest="sha256:" + sha256(old).hexdigest()))`. List its artifact, pre-create destination `setup-11.zip` with old's valid bytes, then call `download_artifact(..., run=run())`. It raises category **integrity** as expected, but the pre-existing valid ZIP **no longer exists** and the destination directory is empty. All transports are fake; no network.

**Impact:** a failed retry destroys the user's earlier valid copy rather than leaving it intact. Re-downloading the original artifact may recover it while GitHub retains it, hence S2, but the filesystem loss is real. This does not require bypassing the integrity check: the check detects the error but commits/destructively cleans up in the wrong order.

**Expected:** perform every integrity check on the temporary file before publishing it. On any failure delete only that attempt's temporary file and leave an existing final target byte-for-byte unchanged. Decide replacement policy explicitly and use unique temporary filenames for simultaneous attempts. Add a regression case with a pre-existing valid final file.

### BF-106 · S2 · FIXED (a6778e48, 979b6597, 8ecc7738) — long artifact names truncate away the unique ID and .zip suffix, so different artifacts overwrite each other and cached verification becomes false

**Repair evidence — session 29 / V5.22–V5.23:** Only the human-readable stem is truncated, with a 180-byte UTF-8 budget reserving immutable ID and .zip; attempt paths are unique. DownloadResult.assert_current rechecks bounded-stream size/hash before extraction and after confirmation; row text describes historical download verification. Unit tests cover ASCII/Persian/invalid long stems, two IDs coexisting and extraction targets; Tk smoke covers replacement during confirmation and a missing file. Original reproduction below is retained as historical evidence. Linux regression validated; Windows release gate is still pending.

**Where:** `aiwb/github/artifacts.py`: `download_artifact()` passes `f"{artifact.name}-{artifact.artifact_id}.zip"` into `sanitize_filename()`, which returns `cleaned[:180]`. A long name consumes the entire limit, removing the disambiguating ID and ZIP extension. Names up to 256 characters are retained by `list_artifacts()`. Both final and .part names then collide. `ArtifactsDialog.downloads` indexes results by ID, but their paths can be identical.

**Reproduced locally with existing fake transports:** use `name="x"*200`, artifact IDs 11 and 12, and ZIPs from `make_zip([("a.txt", b"first")])` / `make_zip([("a.txt", b"other")])`. Supply each archive's correct size and SHA-256 digest, download them sequentially to the same TemporaryDirectory. Observed: both downloads succeed and both `DownloadResult.verified` values are **True**, but `first.path == second.path`; only one file remains, with no extension. Hashing `first.path` now differs from `first.sha256`. The second download silently destroyed the first artifact's bytes.

**Related extraction failure:** for a no-extension result, `res.path.with_suffix("")` in the UI equals the archive's own path, so Extract safely is refused because the destination already exists. Even where an earlier dot leaves a suffix, ID collision/provenance loss remains.

**Impact:** two legitimate artifacts with long shared prefixes cannot coexist; selecting the first row can operate on the second archive while still displaying the first row's saved verification metadata. Concurrent attempts also share a temporary path. This is independent of BF-105: both downloads here pass all integrity checks.

**Expected:** sanitize/truncate only the human-readable stem, reserve space for `-<artifact_id>.zip`, and keep the ID/extension unconditionally. Use unique attempt temporary names and verify existing stored paths before claiming cached verification or extraction provenance. Add two-long-name-artifact and extraction-target regression cases.

### BF-107 · S3 · FIXED (session 39) — a pending paste debounce erases ZIP-specific skipped-file warnings immediately after Load ZIP

**Where:** `aiwb/ui/paste_box.py`: `_modified()` schedules `after(DEBOUNCE_MS, refresh)`. `load_zip()` replaces the text, clears its modified flag and displays `preview_zip()`'s source diagnostics, but does not cancel that already queued refresh. `refresh()` later diagnoses only the canonical text, which no longer contains the skipped ZIP entries. ZIP source warnings/fixes are not retained with `zip_text`.

**Reproduced locally:** create a real `PastePanel`, insert `"previous answer"` into the Text widget, and `root.update()` so `_after` is set. Before the 250ms debounce fires, load a temporary ZIP containing `src/a.py` = `print(1)` and `../secret.txt`. Immediately: **"ZIP ✓ · 1 file from answer.zip · 1 skipped item"**, problems contains **"../secret.txt is an unsafe path — skipped"**. Pump events for 0.5s without editing the loaded text: status changes to **"Files ✓ · 1 file · AIWB file blocks"**, `preview.problems == []`; the unsafe-entry warning and ZIP source summary have vanished. Safe-path filtering itself remains correct.

**Impact:** warning visibility depends on timing. A user choosing a ZIP while a normal text refresh is pending may never notice that files were dropped. Quick mode's later `read_answer()` also only sees the canonical text, so that skipped-entry evidence is not reconstructed there. Existing original-ZIP warning tests inspect the immediate state and miss this delayed replacement.

**Expected:** cancel pending refreshes on explicit ZIP loads and retain source preview diagnostics while the current text equals the canonical ZIP text; merge/recompute deliberately when it actually changes. Cancel owned timers on widget destruction as well. Cover loading over recently edited text and inspect status both immediately and after debounce.

### BF-108 · S2 · FIXED (ff1ea5c9) — Build Center from project A persists its selected workflow into project B after the active project changes

**Repair evidence — session 31 / Desktop:** Build Center reuse is keyed by project/binding/account/repository/root/subpath/branch identity. Workflow selection resolves the latest record for the captured project, never the active project, and refuses deletion/relinking. Real callback regression switches from A to B, preserves B preferences, constructs a separate B window and rejects a deleted A binding. Checkpoints: ff1ea5c9. Original reproduction below is historical.

**Where:** `AI_Workbench.py` `open_build_center()` (~12215–12280): the window is created for a captured binding A (owner/repo/branch/token/local HEAD). Its `select_workflow` callback instead resolves `current = self._binding_for_active_project() or binding`, so it writes to whichever project is active later. The singleton reuse check only tests whether an existing window is open; it does not match binding/account/repository/project identity. The window is non-modal.

**Reproduced without network or settings writes:** invoke the real `WorkbenchApp.open_build_center()` on a small recording app adapter with two valid `RepositoryBinding` records for o/a and o/b. Replace only `BuildCenterWindow` with a callback-capturing adapter and the settings save with a recorder; keep real `update_binding_preferences()` and `upsert_binding()`. Open while A is active, switch the adapter's active binding to B, invoke the captured `on_select_workflow(".github/workflows/from-a.yml")`, then request Build Center again. Observed: only **one** window is constructed (still owner/repo **o/a**); recorded A retains **a.yml**, B is changed from **b.yml** to **from-a.yml**; status says **"Main Build workflow for o/b: .github/workflows/from-a.yml"**.

**User path / impact:** open A's Build Center, switch to B in the main app, then select A's workflow and press Use selected as main Build workflow. B's saved build configuration is silently corrupted; the workflow may not exist in B, causing a stale binding or wrong workflow selection next time. Opening Build Center for B merely lifts A's old window, and its Run/Cancel/Artifacts actions remain scoped to A, not the newly active project. The title identifies A, so this is not evidence of an invisible remote mutation; the wrong-project metadata write is the confirmed defect.

**Expected:** key windows by stable binding/project identity, or close/recreate them on a project change. Persist workflow selection only to the binding that owns the displayed workflow; resolve the latest record by captured binding ID and reject deletion/relinking mismatches. Test switching projects while non-modal repository windows remain open.

### BF-109 · S2 · FIXED (c9b80c5d) — Sync & Build completion records project A's CI as verified evidence in newly active project B and can mark B's unrelated task done

**Repair evidence — session 31 / Desktop:** Sync & Build persists captured project/binding/account/repository/task/revision/attempt context and refuses mismatched scoped resumes. Completion uses the originating root, rechecks the saved binding and reads actual local HEAD/branch/origin independently. Ledger rejects unscoped legacy operations, wrong repository/branch/HEAD/run SHA/operation/task revision/attempt and records only the explicitly captured task, never all active tasks. Tests reproduce foreign success/failure contamination and verify the real completion callback writes to A after UI focus switches to B. Operations without an explicitly identifiable V2 task intentionally produce no automatic task evidence; existing CI run/artifact viewing remains available. Checkpoints: c9b80c5d, 4ac06df7, 4b1d53e5. Original reproduction below is historical.

**Where:** `AI_Workbench.py` `_sync_build_finished()` (~12345): uses `root = self.workspace` at callback time rather than the project captured when the orchestrator was created. The non-modal window receives `on_finished=self._sync_build_finished`. `aiwb/v2/ledger.py` `record_build_evidence()` takes every in_progress / in_review / validation_pending task in that project; it does not check git.repository, git.task_id, project identity, binding, or the project's actual HEAD. It passes the foreign commit SHA as `current_commit`, effectively checking evidence against itself.

**Reproduced locally using real V2Project and callback:** create a temporary project B with an `evidence_required` task, required approvals `["validation"]`, create its attempt and transition it to `validation_pending`. Use a recording app adapter with `workspace=B`. Supply an orchestrator with `GitOperationRecord("op-A", "o/project-A", "work", task_id="TASK-FROM-A", commit_sha="a"*40, pushed=True)` and `BuildRunRecord("op-A", run_id=991, head_sha="a"*40, outcome="success")`. Call the real `WorkbenchApp._sync_build_finished(app, orchestrator)`. B's unrelated task changes **validation_pending → done**, with evidence source **github_actions**, run **991**, foreign SHA, **verified=True / passed**. Status: **"Build result recorded as verified evidence for 1 task(s)."** No GitHub calls or actual CI execution are involved; the callback input models an already completed A operation.

**User path / impact:** start A's Sync & Build, switch to B while CI runs, then A finishes. B receives false verified build evidence and may close tasks/unblock dependencies although B was never built. A does not receive its result. Related window reuse also lifts the old A window when B requests Sync & Build. This is distinct from BF-108's workflow-preference write: it contaminates the task/evidence ledger and changes status.

**Expected:** capture and persist the originating project/binding identity in the operation and completion callback; write evidence only there, independent of UI focus. Verify repository/ref/commit against that project and restrict task evidence to explicitly covered tasks/attempts. Never treat a run from another project as validation of all active tasks. Test switching projects during CI, including success and failure outcomes.

## Session 31 validation (2026-11-05)

- 18 Desktop findings FIXED, 88 independent OPEN (4 S1 / 33 S2 / 51 S3); 18/106 = 16.98% count-based, not effort or release readiness. Newly closed: BF-043/108/109. BF-078/079 have tested Desktop repairs but remain OPEN for Mobile.
- Final source unit suite: 959 tests OK, 10 skipped. Static validator restored after sandbox reset: 0 undefined names. Existing socket ResourceWarning and timeout-server BrokenPipe output remain visible.
- No GUI run in this session (xvfb-run is absent); no Windows/Android tests, tag, release or deployment. Platform and frozen-source GUI gates remain pending.

## Session 30 validation (2026-11-05)

- **15 Desktop findings FIXED, 91 independent OPEN** (5 S1 / 35 S2 / 51 S3); 15/106 = 14.15% count-based progress. BF-008 is deliberately still OPEN with partial implementation evidence.
- Final Desktop unit suite: **949 tests OK, 10 skipped**. `tools/check_undefined_names.py`: **0 undefined names** after installing its missing pyflakes dependency. Existing socket ResourceWarning and timeout-test BrokenPipe stderr remain visible.
- Targeted final-source Tk Quick and guided S2 scenarios both PASS. Full GUI suite outcome is recorded in SESSION_NOTES after collection. No Android SDK/Kotlin compiler or actual Windows release gate; no tag/release/deploy.
- Shared transaction tests cover backup fsync failure, linked backup rejection, immutable retry backups, original-byte rollback, caller state failure, ancestor case aliases, journal-name collision, and incomplete rollback reporting while preserving concurrent user edits.

## Session 29 validation (2026-11-05)

- Final unit suite: **933 tests, OK, 10 skipped**; 12 new tests above the 921 baseline. Existing ResourceWarning and timeout-server BrokenPipe stderr remain visible, not counted as test failures.
- Full GUI suite after the initial repair checkpoints: **62/62 passed**, including permanent S5 owner-aware timer cancellation and unsuppressed timer-command destruction regression. Artifact Tk smoke was also rerun after the final provenance changes and passed. A final full GUI rerun is being collected; see SESSION_NOTES for its outcome.
- Scope: **8 catalogued desktop defects fixed; 98 independent OPEN remain**. No release/tag/deploy; no Android implementation or Windows release validation in this session.
- Previous session results below are historical baselines, not the current S5 status.

## Checked and OK

_(areas reviewed with no problem found are listed here so they are not re-checked after a reset)_

- **Unit suite** session 28: 921 tests OK (10 skipped). **GUI suite** session 28: **61/62** unmodified smoke scripts passed; S5 failure investigated as follows.
  `gui_scenario_s5_reopen_smoke` fails with `TclError: can't delete Tcl command` during destruction of the **first** root,
  before the second Tk is created. The earlier explanation that this was caused by the second root / Xvfb was too broad.
  `tests/gui/scenario_driver.py:restart()` cancels every interpreter timer through `old.after_cancel(job)`, including timers
  registered by child widgets. Tkinter removes the Tcl command through the wrong widget, leaving its name in the child's
  `_tclCommands`; child destruction later tries deleting it again. Minimal reproduction with no app: create root and
  `ttk.Frame(root)`, `job=child.after(60000, lambda: None)`, `root.after_cancel(job)`, `root.destroy()` => same error.
  A **diagnostic in-memory** adapter routing cancellation to the widget whose `_tclCommands` owns the callback makes S5 pass
  (10 clicks + 2 pastes; one cross-widget cancellation corrected). No test or production file was patched for that run.
  This isolates a **test harness timer-ownership defect**, not evidence of lost project state or a production second-root bug.
  Keep the unmodified suite's S5 failure visible until the harness itself is corrected; a diagnostic rerun is not a clean suite pass.
- **pyflakes**: no undefined names; only unused locals and one f-string without placeholders (`artifacts.py:521`). Harmless.
- **Guide random walk** (30 projects × 150 actions): 0 unexpected exceptions, 0 states without a step, every step
  has ≥1 action and exactly one primary (apart from BF-001…004, which are logic dead ends, not crashes).
- **Paste robustness** (charter): UTF-8 BOM, CRLF, NUL characters, fenced in ```json, Persian text before the block,
  3 MB of noise before the block (0.3 s), smart quotes (auto-fixed), Persian-only text (→ clear "no block" message),
  normal emoji (Tk 8.6 clipboard round-trip checked): all OK.
- **Writes of `state.json`**: temp file + fsync + `os.replace` — a crash during a save cannot damage it (BF-005 needs an
  outside cause).
- **Path safety against escape**: `..`, absolute, `C:`, NUL, `.git/`, `.workbench/` refused in Quick, guided staging
  and ZIP import; `integrate()` also checks the resolved path stays inside the project. (Windows-specific names: BF-008.)
- **Unhandled exceptions** in Tk callbacks go to `_report_callback_exception` (logged + dialog; the app keeps running);
  Home card actions are wrapped (`home_perform` shows the error on the card).
- **Folder names / permissions** (script `/tmp/hunt/j_folders.py`): a Persian folder name with a space
  (`پروژه من`) works end to end (charter → plan). A read-only new folder → `PermissionError` shown in a dialog by
  `open_projects` / `open_project_workbench`; a folder that becomes read-only later → the action fails with
  *Permission denied …* on the card, the state is untouched (temp file never created), reopening works. The message is
  technical but honest — acceptable.
- **Scope check** (script `/tmp/hunt/k_scope.py`): files outside the task's allowed paths are not staged and are listed
  as `out_of_scope` errors on the card (troubleshoot / accept anyway / reject).
- **Troubleshooting limit** (script `/tmp/hunt/l_valfail.py`): after 3 troubleshooting prompts the card offers
  *Ask the project manager (stuck)* → the task becomes `blocked` with a clear reason and shows on Home
  (*It can continue now / Ask the PM to re-plan / Cancel*). No dead end.
- **Out-of-date answer** (script `/tmp/hunt/n_reject.py`): editing the task after its prompt was made
  (`task_revision` 1 → 2) → the pasted answer is `reconciliation_required`, Home shows *The answer … is out of date*
  with *Accept anyway… / Reject…*. Correct.
- **Stale plan warning** (script `/tmp/hunt/o_stale.py`): a plan written for an older state that touches a task changed
  since then is imported with *"written for an older project state: review carefully"* on the card. Works (the missing
  check for **cancelled** tasks is BF-014).
- **Quick mode ZIP import** (script `/tmp/hunt/p_zip.py`): top-folder strip, `../` / absolute / `C:` / `.git` /
  `.workbench` entries skipped with a message, case duplicates reported, binary files skipped, Windows-1252 text
  converted with a note, 5 MB entry refused (512 KB limit, reported), broken / empty ZIP → clear message, empty
  `__init__.py` kept. All OK (Windows-invalid names: BF-008). `v2/files.py unzip_files()` has no caller (dead code).
- **Settings file load** (script `/tmp/hunt/r_settings.py`): JSON syntax error / non-object file → preserved as
  `settings.json.corrupt-<ts>` and the app starts with defaults; UTF-8 BOM accepted; a folder in its place or no read
  permission → defaults. (Non-UTF-8 encodings: BF-016.) Unknown theme / language / mode values fall back to defaults
  (`ui/prefs.py`).
- **Helper AI settings form** (`ui/helper_card.py`): non-number time limit → clear message; time limit clamped to
  5…300 s; address without `http(s)://` / with spaces → clear message; `/chat/completions` tail stripped; empty model
  refused. (Save failure not reported: BF-017.)
- **GitHub state publisher error mapping** (script `/tmp/hunt/t_pub.py`): 401 → paused *"rejected the token"*; 403 →
  paused *"needs Contents write"*; 403 with `X-RateLimit-Remaining: 0` / 429 → back-off with retry time; 5xx /
  timeout / reset / `RemoteDisconnected` → *"GitHub is not reachable"* with back-off; writing to `main` / `master` /
  `develop` refused. (Other exceptions: BF-018.)
- **Bundle round trip** (script `/tmp/hunt/w_round.py`): export → immediate re-import → *"already up to date"*
  (`same`); reopening the project / showing Home / the publisher tick does not bump the revision, so a phone bundle
  that adds one event is correctly `newer` (*"Update the project from revision 2 to 3 (a backup is kept)"*) and
  imports; exporting right after gives `same` on the phone side. Damaged `state_sha256`, wrong `bundle_type` /
  `bundle_version`, newer `db_version`, > 8 MB → clear messages. (Folder-name ids: BF-021; errors: BF-022; `new`
  case: BF-023.)
- **New-project wizard** (script `/tmp/hunt/x_wizard.py`, under xvfb): existing folder → *"already exists and was not
  modified"*; `CON` / `:` / `/` / 101 characters / blank goal → clear inline message, nothing created; trailing space
  stripped; Persian name with a space creates and opens the project (but see BF-021 for its bundles); read-only
  parent → *"Permission denied …"* inline, nothing registered. Created projects are registered and opened.
- **Git page commit / push** (script `/tmp/hunt/y_git.py`, under xvfb): project nested in a monorepo
  (`apps/پروژه من`) → only in-scope files are staged (Persian names, spaces, a leading space kept intact thanks to
  `-z`), the sibling `other/` stays untouched; already-staged changes are refused; push without `origin` and push from
  `main` / `master` are refused with clear messages. Worker errors are shown as *"Operation failed"*. (Escaped names
  in the result dialog: BF-024.)
- **Run page time limit / output cap** (script `/tmp/hunt/r_run.py`): an endless loop is killed at the limit (3 s →
  3.0 s, *"Timed out"*, exit −9, partial output kept); 400 000 printed lines → bounded to the 50 000-character tail
  with *"output was truncated while running to keep memory bounded"*, *Passed*, memory stays flat. (Background
  processes holding the pipe: BF-029; Windows code page: BF-025.)
- **Queued actions (code review)**: each action is validated again right before it runs (chaining / pipes / blocked
  patterns / `..` / symlinked or escaping working directory refused); the state is saved as `Running` before the
  start and the result right after, so an unclean exit becomes *"Interrupted — the command may have completed"* on the
  next open, never a false Passed / Failed; the batch stops on the first non-passing result; a running action cannot
  be removed; a worker exception lands in *"Action batch error"* with the refreshed queue. (Same runner as the Run
  page: BF-025, BF-029 apply here too.)
- **Classic transactional apply (code review)**: every path is validated (links, escapes, parent-is-file,
  sensitive, size) and compared with the previewed bytes **before** the first write; the backup + manifest are
  written to a fresh, unique app-data folder (`exist_ok=False`); writes are atomic; any exception rolls back the
  touched paths in reverse order from the exact preflight bytes and reports rollback errors. This is the model the
  Quick (BF-007, BF-026, BF-028) and guided (BF-009) writers should follow.
