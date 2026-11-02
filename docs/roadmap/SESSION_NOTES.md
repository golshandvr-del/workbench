# SESSION NOTES (agent memory — survives sandbox resets)

Purpose: the sandbox resets often. Every finding and every step done is written here and pushed
immediately, so a new session can continue without repeating work.

## Environment recovery (do this first after a reset)
- Clone: `git clone https://golshandvr-del:<TOKEN>@github.com/golshandvr-del/workbench.git /home/user/webapp`
- `git config user.name golshandvr-del; git config user.email golshandvr-del@users.noreply.github.com`
- Work directly on `main`; checkpoint rule: ONE change -> add -> commit -> push.
- Tests: `cd apps/desktop && timeout 600 python3 -m unittest discover -s tests -t .` (baseline 863 tests OK, 10 skipped)
- GUI probes need Xvfb: `sudo apt-get install -y xvfb` then `xvfb-run -a -s "-screen 0 1366x800x24" python3 ...`
- Friend's evidence: chat log of the calculator project (PM loop, revision 49..63, "the proposal has no operations").

## Baseline
- Last released: desktop-v5.15.0 (commit 73d7b50). Old roadmap 5.8 -> 5.15 complete.

## Root causes found (measured, session 1)
1. PM loop: PM's role text conflicts with the delivery format in its own prompt; doc task (TASK-0001) is
   owned by the PM, PM answers with a proposal without operations -> rejected -> re-ask loop. Each answer
   moves one tiny decision. Context requests re-send files again.
2. Slowness: every state read = full JSON parse + migrate + deepcopy. Realistic project (625 KB, 2000
   events): load ~20 ms, empty transaction ~64 ms; 2+ reads per click; status poll every 2.5 s.
3. Idle CPU: Mission map runs endless 60 fps loops (`mission:pulse`, `mission:particles`) ~42 fps idle.
4. Right-click menu: first open ~250 ms (raster shadow/panel sprite rendered in pure python); later 13 ms.
   Menu must close on page switch / focus loss / window move.
5. Tiny unclear dialogs: `simpledialog.askstring` ("Your decision") shows no question/options.
6. Freezes: heavy work on UI thread (state read/write, preview of 76 KB paste ~53 ms on every debounce);
   pasted answers without operations become dead-ends.

## Progress log
- (session 2) notes file created.
- (session 2) CONFIRMED root cause 1 in code: `v2/agents.py` PM template instruction "Return changes only as an
  AIWB_MANAGER_PROPOSAL block" is copied into section "1. Your role" of `handoff.build_prompt` (handoff.py:321),
  while section "9. Expected delivery" asks AIWB_FILE + AIWB_HANDOFF. Friend's log: 4 proposal blocks, 3 with
  `operations: []` and invented keys (decisions, file_change_proposals, task_assessment...) -> rejected at
  `proposals.py:84` "the proposal has no operations". PM keeps re-deciding DEC-0002 (rev 49 -> 63).
- (session 2) Store cost breakdown (451 KB state): json.loads 4.7 ms, migrate_state 15.4 ms (it deepcopies the
  whole state every time!), deepcopy 11.9 ms, pickle roundtrip 2.5 ms, dumps-compare 4.8 ms, write 6 ms+fsync.
  transaction() = read+migrate(deepcopy)+dumps(before)+deepcopy(work)+dumps(after)+write. FIX: cache the
  migrated state keyed by (mtime_ns,size); return pickle copy; compare by revision-free hash once.
- Helper: `cpush "msg" files...` (in /usr/local/bin, recreate after reset: add+commit+push, verifies push).
- (session 2) CONFIRMED root cause 5: guide.py:389 task step "waits for a decision" action `decide` needs
  `choice`+`rationale`; GUI asks them with `simpledialog.askstring` labelled only "Your decision"
  (workspace/shell.py:331 INPUT_PROMPTS, AI_Workbench.py `_mission_input` ~5590). The question/options are in
  step["explain"] (task blocked_reason / decision options) but never shown in the dialog. Decision entities have
  `options` + `recommendation` -> radio buttons possible.
