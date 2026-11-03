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
| S1 | 7 (BF-002, 003, 004, 007, 009, 010, 016) | 0 |
| S2 | 10 (BF-001, 005, 008, 011, 013, 014, 017, 019, 021, 025) | 0 |
| S3 | 8 (BF-006, 012, 015, 018, 020, 022, 023, 024) | 0 |

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

### BF-011 · S2 · OPEN — "Tests/build failed…": the user's note is thrown away and the next prompt still says "tests pass"

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

### BF-012 · S3 · OPEN — the "answer was cut off — ask to continue" step outlives the prompt it belongs to

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

### BF-013 · S2 · OPEN — after "Reject…" the reason is lost and the next prompt says "This is the first handoff"

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

### BF-014 · S2 · OPEN — a plan may depend on (or edit) a cancelled task; it is accepted without a word and lands in BF-001

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

### BF-015 · S3 · OPEN — helper AI: two network edge cases give a misleading message

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

### BF-016 · S1 · OPEN — a `settings.json` that is not UTF-8 stops the app from starting at all

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

### BF-017 · S2 · OPEN — when `settings.json` cannot be written, every settings change says "Saved" and is lost at restart

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

### BF-018 · S3 · OPEN — GitHub state publishing: a dropped connection or an odd reply gives "a bug in AI Workbench" / is never shown

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

### BF-019 · S2 · OPEN — a GitHub write (create repo / release) that fails half-way can never succeed on retry

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

### BF-020 · S3 · OPEN — "Archive the project": if the final bundle cannot be written, the project is read-only anyway and the card says the bundle exists

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

### BF-021 · S2 · OPEN — "Export project for the phone" makes a file nobody can import when the folder name has a space, Persian letters, brackets or is long

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

### BF-022 · S3 · OPEN — bundle export / import: a file error gives the "bug in AI Workbench" dialog; a malformed bundle gives a raw Python message

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

### BF-023 · S3 · OPEN — bundle import into a project that has a goal but no tasks yet: another project's / an older bundle replaces it as "new", with no warning

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

### BF-024 · S3 · OPEN — "Commit completed" dialog shows Persian / non-ASCII file names as `\331\276\330\261…`

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

### BF-025 · S2 · OPEN — Run page: a Python script that prints Persian (or any non-ANSI) text fails on Windows; output of other programs is garbled

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
