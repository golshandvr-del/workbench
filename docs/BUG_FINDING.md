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
| S1 | 6 (BF-002, 003, 004, 007, 009, 010) | 0 |
| S2 | 3 (BF-001, 005, 008) | 0 |
| S3 | 1 (BF-006) | 0 |

**Top risk for the friends' demo:** the "stuck" family BF-001…004 (planning graph) and the half-written files family
BF-007 / BF-009 (any locked or invalid file on Windows — see BF-008).

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

### BF-005 · S2 · OPEN — a damaged `state.json` blocks the project, and the error points to a backup that does not exist

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

### BF-006 · S3 · OPEN — text with a broken emoji (lone UTF-16 surrogate) makes paste / Quick apply fail with "a bug in AI Workbench"

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

### BF-007 · S1 · OPEN — Quick mode: an apply that fails half-way cannot be restored, and the retry destroys the original file

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

### BF-009 · S1 · OPEN — guided mode: "Accept the delivery" that fails while writing files leaves the task "in review" with half the files and no retry

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

### BF-010 · S1 · OPEN — guided mode silently drops delivered files (over 512 KB, over 8 MB in total, or empty) and still approves the task

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

## Checked and OK

_(areas reviewed with no problem found are listed here so they are not re-checked after a reset)_

- **Unit suite** 921 tests OK (10 skipped) · **GUI suite** 61/62 — the one failure `gui_scenario_s5_reopen_smoke`
  (`TclError: can't delete Tcl command` inside `root.destroy()` of the 2nd Tk in one process) is a known
  sandbox/xvfb artefact: it passes on CI (Linux Py3.10 + 3.13, Windows). Real users never create two Tk roots. NOT A BUG.
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
