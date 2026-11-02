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
- (session 3) DONE 5.16.0 step 3+4 (all pushed): 074f140 test_raster_9slice.py (3 tests OK);
  5ce70a5 menu5.py `_OPEN` registry + `close_all()` + `install_auto_close(root)` (root <Configure> geometry change,
  root <Unmap>, bind_all <Button-1> outside menu -> close); 885bfb0 shell.show() closes menus on page change;
  cc2a9c7 AI_Workbench.status_state caches parsed state.json by (path,mtime_ns,size) -> same dict object;
  e4dd41f shell `_poll_once()` skips refresh+listeners when facts_fn returns the identical object
  (`polls_skipped` counter). NEXT: full unit tests + GUI smokes, then test_menu_close (GUI), CHANGELOG, bump, tag.
- (session 3) Verified after 5.16 steps: unit tests 876 OK (10 skipped). GUI smokes (`xvfb-run -a python3
  tests/gui/run_all.py`, ~4 min): 56/57 pass. The one failure gui_scenario_s5_reopen_smoke ("can't delete Tcl
  command" in root.destroy during d.restart) ALSO fails on baseline 0005f3a in this sandbox (Py 3.13 Linux Tk)
  -> pre-existing/environmental, not a 5.16 regression. Investigate briefly; don't block on it.
- (session 3) S5 confirmed sandbox-only: CI run 40886642404 (5.15.0 merge) passed Linux Py3.10+3.13 GUI smokes
  and Windows. CI only runs desktop jobs when a push touches apps/desktop/ or tools/ (docs-only pushes skip);
  `cancel-in-progress` cancels older runs on main. Check CI via
  `curl -H "Authorization: token $T" https://api.github.com/repos/golshandvr-del/workbench/actions/runs?per_page=8`.
  NEXT: tests/gui/gui_v516_light_smoke.py (idle frames 0, menu closes on show()/Unmap/click, poll skip).
- (session 3) DONE 5.16.0 gate: tests/gui/gui_v516_light_smoke.py PASSES (idle 0 fps after LIVE_MS, poll skip,
  menu 113/19 ms, closes on page switch/click/move/minimise). Fixes made for it: 0f595d8 status_state cache also
  for open Workbench; 6dab1cb menu5 MENU_TITLE="AI Workbench menu" + <Destroy> -> closed. Xvfb has no WM:
  iconify is a no-op -> smoke generates <Unmap> itself. Scenario Driver closes unknown Toplevels -> pass
  allow_windows=WORK_WINDOWS+(menu5.MENU_TITLE,). NEXT: full unit+GUI run, then release 5.16.0
  (CHANGELOG, bump_desktop_release.py 5.16.0, ROADMAP ✅, tag desktop-v5.16.0).
- (session 3) 5.16.0 RELEASE: bump commits bbcb377..9ff8166 (APP_VERSION, __version__, UA, manifest +2 tests,
  install.ps1, checklist docs/release/v5.16.0), e30fc8d CHANGELOG, 1b71f73 ROADMAP ✅ (active 5.17.0).
  Tag desktop-v5.16.0 pushed -> release-desktop.yml. Release recipe that worked: run bump in a worktree
  (/tmp/rel) then copy ONE file per checkpoint. NEXT: verify release run; start 5.17.0 (action_form.py).
- (session 4) Sandbox reset; re-cloned, cpush+xvfb reinstalled. VERIFIED: release run 41531157062 desktop-v5.16.0
  success, assets Setup.bat/Payload/Source/SHA256/manifest published. 5.17.0 recon (redone, was lost unpushed):
  step inputs asked with simpledialog.askstring in 3 places: (1) AI_Workbench.mission_menu_pick ->
  _mission_input(need,label) (~5597; test hook `mission_input_hook`); (2) AI_Workbench.mission_column_pick (~5560);
  (3) workspace/shell.py guide_action (~387, INPUT_PROMPTS ~327). Home card ui/next_card.py: check. guide.py `_a(id,label,*needs)`.
- (session 4) 5.17.0 facts: decisions live in state["decisions"][Dn] {title, problem, options[], recommendation,
  status proposed|accepted|rejected, affected_task_ids} (v2/ledger.py DecisionLedger.propose/resolve). Guide steps:
  `decision:Dn` actions decide(choice,rationale)/reject_decision(rationale); `task:Tn` needs_decision (no proposed
  decision for it) -> decide(choice,rationale) + manager_prompt; question text = t.blocked_reason, which handoff.py:311
  sets from "; ".join(h.unresolved_items or h.decision_requests). Guide._perform requires non-optional needs;
  OPTIONAL_INPUTS = note reason rationale run_id commit_sha tag idea + brief optional. Ask sites: workspace/shell.py
  guide_action (INPUT_PROMPTS, askstring), AI_Workbench._mission_input + mission_column_pick (askstring; hook
  mission_input_hook(need,label)). PLAN: v2/choices.py (pure form spec) -> Guide.steps attaches question/choices ->
  ui/action_form.py (one window, radios, "Other answer…", Enter/Esc) -> wire 3 sites -> tests -> release.
- (session 4) DONE 706d633+da8e1d1 v2/choices.py: parse_options(text)->(options,recommended) [bullets, "Options:",
  (a)(b), "A or B?"]; decision_choices(step,state)->{question,options,recommended} (decision:Dn record / task:Tn
  latest handoff decision_requests or blocked_reason / proposed decision options); form_spec(step,action,state,
  optional)->{title,step_title,question,fields[{need,label,kind choice|yesno|note|entry,options,recommended,optional,
  default}]}; initial_values(spec); validate(spec,values)->(inputs,err). OTHER="__other__". NEXT: Guide.steps adds
  step["choices"]; ui/action_form.py; wire sites; tests/test_choices.py.
- (session 4) DONE d3b3625 guide.py `_with_choices`: steps with a `choice` need get step["choices"]+step["question"]
  (names humanized too). DONE 9317f54 ui/action_form.py: ActionForm(parent, spec, modal, on_done) title
  "AI Workbench · <label>", radios (+" (recommended)", "Other answer…" + entry), values()/choose()/write()/
  option_texts()/ok()/cancel(); ask_form(parent, spec) modal, `TEST_HOOK(spec)` module attr. Verified under xvfb.
  NEXT: wire workspace/shell.py guide_action, AI_Workbench._mission_input/mission_menu_pick, mission_column_pick.
- (session 4) DONE wiring (all pushed): 351aa02 workspace/shell.py guide_action -> text via paste box, all other
  needs via ask_form(form_spec(step,act,state,OPTIONAL_INPUTS)) (Home card uses ws.guide_action too);
  2c3fb9a mission_menu_pick form (unless mission_input_hook set); 753a8f9 mission_column_pick form; 1ed3b0b
  _mission_input fallback form. NEXT: fix tests that patched simpledialog for step inputs; tests/test_choices.py;
  GUI smoke gui_v517_forms_smoke.py.
- (session 4) DONE 58a8b1c+fa65945 tests/test_choices.py (14 OK). Test projects: ProjectsController(Path(d),
  make_pipeline=wb.make_inbox_pipeline) (NOT V2Controller). NEXT: full unit run, GUI smokes, gui_v517_forms_smoke.py.
- (session 4) After 5.17 wiring: unit 890 OK (10 skipped); GUI 57/58 (only pre-existing sandbox-only S5 fails).
  run_all takes ~4.5 min -> use timeout 580 + Bash timeout 600000. NEXT: tests/gui/gui_v517_forms_smoke.py.
- (session 4) Real path verified (/tmp/bench/dec.py): charter_to_first_prompt -> paste handoff outcome
  needs_decision + decision_requests ["Should the calculator use vanilla JS or React?"] -> card "Accept the delivery"
  -> card "TASK-0001 ... waits for a decision" buttons ['Decide and continue…','Ask the project manager'];
  step choices options ['vanilla JS','React']. ask_form is modal (wait_window) -> smoke must schedule root.after()
  to drive the form; Driver allow_windows needs action_form.FORM_TITLE_PREFIX ("AI Workbench · ").
- (session 4) DONE 5.17.0 gate: 68b4806 tests/gui/gui_v517_forms_smoke.py PASSES (one window "AI Workbench ·
  Decide and continue", full question, options vanilla JS/React + Other answer, Esc no change, empty OK keeps
  window, React+reason recorded, askstring patched to fail). 4d0c98e: no pre-selection without recommendation.
  NEXT: release 5.17.0 (bump in /tmp/rel worktree with --test test_choices.py + new modules v2/choices.py,
  ui/action_form.py; copy one file per checkpoint; checklist; CHANGELOG; ROADMAP ✅; tag).
- (session 4) 5.17.0 RELEASE: c6e89ed..aa3c8b3 bump (APP_VERSION, __version__, UA, manifest +choices.py
  +action_form.py +test_choices.py, install.ps1), 7668a0b checklist, 8ebe3e9 CHANGELOG, c3c1a8f ROADMAP ✅ (active
  5.18.0). Tag desktop-v5.17.0 pushed. NEXT: verify release run; start 5.18.0 (PM prompt contradiction R1, half-right
  proposals R6). Recon: v2/proposals.py, v2/controller.py, role instructions for PM (grep "only as AIWB_MANAGER_PROPOSAL").
- (session 5) Sandbox reset; re-cloned, cpush+xvfb reinstalled (token also exported as GH_T in ~/.bashrc). VERIFIED:
  release run 41535013005 desktop-v5.17.0 success, assets published. Starting 5.18.0 (R1 PM contradiction, R6).
- (session 5) 5.18 recon R1: v2/agents.py TEMPLATES["agent-project-manager"].instructions[3] = "Return changes only as an
  AIWB_MANAGER_PROPOSAL block based on the given state_revision." ; handoff.build_prompt (~321) section "1. Your role"
  copies agent["instructions"] verbatim, section "9. Expected delivery" wants files + AIWB_HANDOFF -> contradiction.
  Plan: build_prompt drops/rewrites proposal-only lines (works for existing projects without state migration).
- (session 5) DONE R1 code: 4a7ef5d agents.py PROPOSAL_ONLY_MARK/TASK_DELIVERY_RULE/task_instructions(agent) (replaces
  any instruction containing "AIWB_MANAGER_PROPOSAL" by one task-delivery rule; works for old projects, no migration);
  b69fe60 handoff.build_prompt uses it; e1fb741 agent_hub.briefing uses it. NEXT: verify; R6 proposals translation.
- (session 5) After R1: unit 890 OK. NEXT R6 recon: v2/proposals.py ("the proposal has no operations").
- (session 5) R6 recon: proposals.ProposalService.import_data (~75) raises "the proposal has no operations" when
  ops missing/empty (except roadmap_remaining False); base_state_revision required int. controller.route (~488):
  PROPOSAL_RE -> proposals.import_text -> RouteResult("proposal"); ModelError -> RouteResult("rejected", msg+"raw
  answer kept in Inbox"). Charter has fix-prompt path (charter_rejected). OPERATIONS tuple proposals.py:26.
  PLAN: new pure v2/rescue.py translate(data,state)->(ops,fixes,leftover); import_data uses it when ops empty;
  dup decisions (title == accepted decision) marked invalid; build_prompt section 4 "FINAL — do not decide again".
- (session 5) normalize_task editable: title objective task_type owner_agent_id reviewer_agent_ids depends_on scope
  acceptance_criteria acceptance_policy deliverables context_refs priority(low|medium|high|critical)
  risk_level(low|medium|high). _apply: propose_decision -> state decision status proposed; update_task raw.changes.
  Friend's raw log NOT in repo -> 5.18 fixtures are reconstructed from the shapes recorded above (honest label).
- (session 5) DONE 9ad69f1 v2/rescue.py: translate(data,state)->{operations,fixes,leftover} (decisions*/task_assessment/
  task_change_proposals/follow_up_tasks/risks; accepted decision same id/title = FINAL skipped; file_change_proposals ->
  leftover), duplicate_of(title,id,state), fix_prompt(problem,state,leftover) short. Verified by hand. NEXT: wire into
  proposals.import_data (raise NoOperations(ModelError) with .fix_prompt when nothing usable), controller kind
  "proposal_fix" -> guide/shell show prompt; propose_decision dup of accepted -> invalid op; prompts mark FINAL.
- (session 5) DONE 9706db0 proposals.py: class NoOperations(ModelError)(.fix_prompt,.translation); import_data calls
  rescue.translate when ops empty (charter None), raises NoOperations if nothing usable; base_state_revision missing ->
  current revision when rescued; propose_decision duplicate of accepted -> invalid "already decided (Dn, final)".
  NEXT: controller.route catch NoOperations -> RouteResult("proposal_fix", record={"fix_prompt"}); guide.py ~885 &
  shell.do_import treat like charter_rejected (out["prompt"]).
- (session 5) DONE 54f5176 controller: NoOperations -> RouteResult("proposal_fix", record {fix_prompt,...});
  proposal msg appends "Read from the answer: <auto_fixes>". 5d4a88d guide._paste: proposal_fix -> out["prompt"] (card
  copies it, COPY_RESULT has "paste"). 8414122 shell.do_import keeps fix prompt. NEXT: handoff section 4 FINAL label +
  manager_update_prompt FINAL list; tests/test_rescue.py; gate fixture; full tests; release 5.18.0.
- (session 5) DONE c6d8044 handoff section 4 "FINAL — do not decide again: Dn ..."; 4c7369d manager_update_prompt
  rules (decisions FINAL, operations required / roadmap_remaining false, no files). NEXT: tests/test_rescue.py.
- (session 5) DONE 845524c tests/test_rescue.py (12 tests) all pass first run. NEXT: full unit + GUI run; GUI gate
  smoke gui_v518_pm_path_smoke.py (paste half-right proposal on Home -> proposal step; nothing usable -> fix prompt).
- (session 5) After 5.18 code: unit 902 OK (10 skipped). Running GUI run_all next.
- (session 5) After 5.18 code: GUI 58/59 (only pre-existing sandbox-only S5 "can't delete Tcl command"). Bench
  /tmp/bench/pm.py = Home path probe (paste half-right proposal; paste useless proposal -> fix prompt).
