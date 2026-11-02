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
- (session 2) Menu root cause 4 detail: `ui/menu5.py` FloatingMenu = overrideredirect topmost Toplevel; closes only
  on Esc, pick, or FocusOut+focus_get()==None (unreliable on Windows). `ui/shell.py show()` never closes it; root
  <Configure>/<Unmap> never close it. Popup stored as `app.mission_popup` (AI_Workbench.py ~5501/5526).
  Panel sprite drawn by raster.py in pure python on first open (~240 ms).
- Release process: `python tools/bump_desktop_release.py X.Y.Z [--module m.py --test t.py]` (versions, manifest,
  install.ps1, checklist copy); CHANGELOG entry `## [X.Y.Z] - date`; `tools/check_installer_manifest.py`;
  push tag `desktop-vX.Y.Z` -> .github/workflows/release-desktop.yml builds+publishes on Windows.
- PLAN (new roadmap 5.16 -> 5.20): 5.16 speed+menu, 5.17 clear input forms (decision dialog), 5.18 short PM
  path, 5.19 optional helper AI API, 5.20 gate (friend's calculator log fixture + perf budgets) + release.
- (session 2) DONE: old roadmap archived (docs/roadmap/archive/ROADMAP_v5.8-v5.15_Repair_FA.md); new ROADMAP.md
  5.16 -> 5.20 written (commit fab4d21).
- (session 2) DONE 5.16.0 step 1 (commit 21a2704): store.py pickle cache keyed by (mtime_ns,size,ino);
  migrate_state(copy_input=False); transaction compares dicts. 863 tests OK. Bench 544 KB: load 20->3.5 ms,
  Guide.steps 20->2.5 ms, tx write 64->38 ms, no-op tx 5.8 ms. NEXT: test_store_cache.py, then animations,
  menu, poll.
- (session 2) DONE 5.16.0 step 2 (commit 12d08c0): mission_canvas LIVE_MS=6000 then `_settle()`; `<Unmap>` stops
  loops. Verified: idle frames/s 42 -> 0.0; gui_v5_motion_smoke passes. Run GUI smokes with
  `PYTHONPATH=src:tests/gui xvfb-run -a python3 tests/gui/<file>.py` (or `xvfb-run -a python3 tests/gui/run_all.py`).
  NEXT: menu closing (shell.show/Configure/Unmap/click) + panel pre-render; then poll skip.
- (session 3) Sandbox reset again; last unpushed edit of session 2 (raster 9-slice) was lost and redone:
  commit 13bddfd `Raster.to_png_9slice(w,h,mx,my)` + `_row_bytes` + `_png`. Menu first-open profile: 706 ms,
  almost all in raster `panel` sprite (pure python SDF on full w×h). NEXT: assets.py panel -> draw small
  (2k+1)² source, 9-slice to w×h; then menu close hooks; then poll skip; then gate tests + release 5.16.0.
- (session 3) DONE commit ebab33f: assets.py `panel` sprite drawn as small (2k+1)² source, k=ceil(1.5*shadow+rad)+3,
  then `to_png_9slice`. Verified pixel-identical to old (maxdiff 0 on 5 sizes/scales). 260x300 menu panel @1.5:
  1885 ms -> 116 ms; @1.0: 37 ms. Bench script /tmp/bench/p9.py (lost on reset; trivial to rewrite).
  NEXT: tests/test_raster_9slice.py, then menu close hooks.
