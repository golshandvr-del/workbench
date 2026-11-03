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
- (session 5) Home probe: half-right proposal (decisions + file_change_proposals, ops []) -> card "Review the plan
  PROP-0002 (1 change)" ['Accept all valid changes','Reject the plan','Ask for changes…'], msg "Read from the answer:
  ...; not used: 1 proposed file change(s)". A review card has NO paste panel -> in smoke paste useless answer FIRST.
- (session 5) Home probe OK: useless proposal -> msg "Nothing to apply: ... short correction prompt ..." + clipboard =
  fix prompt, card unchanged (paste panel stays); then half-right -> "Review the plan PROP-0002 (1 change)". No dialogs.
  NEXT: tests/gui/gui_v518_pm_path_smoke.py from this probe, then release 5.18.0.
- (session 6) Sandbox reset again; re-cloned, cpush+xvfb reinstalled. Remote HEAD = f4053cd (all session-5 work is
  pushed). CI on f4053cd FAILED only because rescue.py + test_rescue.py are not in release_manifest.json (expected;
  the 5.18.0 bump with --module v2/rescue.py --test test_rescue.py fixes it). NEXT: release 5.18.0.
- (session 6) 5.18.0 RELEASE in progress: bump 48b004c..28cb68c (AI_Workbench, __init__, api_client, manifest,
  install.ps1), 68fb2c9 checklist. Manifest check PASS (225 files). CHANGELOG is apps/desktop/CHANGELOG.md.
  NEXT: CHANGELOG entry, ROADMAP ✅ (active 5.19.0), tag desktop-v5.18.0, verify CI + release run.
- (session 6) 5.18.0: f01c00f CHANGELOG, d15edf3 ROADMAP ✅ (active 5.19.0). NEXT: tag desktop-v5.18.0, verify CI +
  release run, then start 5.19.0 (optional helper AI, OpenAI-compatible API; gate = local fake HTTP server tests).
- (session 6) Tag desktop-v5.18.0 pushed (36d97a8); Release run 41546262347 in progress (verify later).
  5.19.0 recon: secrets -> aiwb/github/credential_store.py (CredentialStore protocol set/get/delete_secret(ref),
  MemoryCredentialStore for tests, WindowsCredentialStore, create_default_credential_store()). App prefs ->
  aiwb/ui/prefs.py AppPrefs (settings.json keys ui_theme/ui_lang/ui_mode/ui_reduce_motion, save callback).
- (session 6) 5.19.0 recon 2: credential_store._validate_ref only accepts "github-api:<uuid>" -> target
  "AIWorkbench/GitHub/API/<uuid>" (tests in test_github_accounts.py check bad refs). Settings page =
  aiwb/ui/shell.py build_settings_page(shell, frame, extra=...) cards rows 0..4 (row 3 = app section via extra);
  called at AI_Workbench.py:4644 (extra=self._settings_app_section); settings_data saved by _save_settings (~4466).
  Home card = aiwb/ui/next_card.py NextStepCard(steps,state,perform,clipboard,status) built at AI_Workbench.py
  ~5818 _make_home_next_card; use_answer(text) -> perform(key, paste_id, {"text"}) -> _done(out) sets message_var.
  guide._paste returns {"message","kind"} (kinds: proposal, proposal_fix, charter_rejected, handoff, rejected ...).
  DESIGN 5.19: aiwb/helper_ai.py (pure: HelperAIError, HelperService(settings, save, store) configured =
  base_url+model (key optional, e.g. Ollama); complete(messages) urllib POST {base}/chat/completions timeout;
  fix_messages(answer, problem), explain_messages(step)); credential ref "helper-ai:<uuid>" ->
  "AIWorkbench/HelperAI/<uuid>"; Settings card "Helper AI (optional)"; NextStepCard optional helper=
  buttons "Fix with helper AI" (after a failed paste) + "Explain this step", hidden when not configured; work in a
  thread, result via after(); fixed text goes through the normal use_answer path.
- (session 6) Settings page grid rows in settings_scroll.body: 0..4 build_settings_page cards, 5 "Project" card
  (_make_settings_project ~4692), 6 classic tools holder -> helper card goes to row 7. App root class WorkbenchApp
  (AI_Workbench.py:4320); github_account_service built ~4359 with create_default_credential_store().
  PLAN files (release bump needs: --module helper_ai.py --module ui/helper_card.py --test test_helper_ai.py):
  1 credential_store._validate_ref also accepts "helper-ai:<uuid>" -> "AIWorkbench/HelperAI/<uuid>";
  2 aiwb/helper_ai.py; 3 tests/test_helper_ai.py (local fake HTTP server); 4 aiwb/ui/helper_card.py (Settings card);
  5 NextStepCard helper= (Explain / Fix buttons, hidden when not configured); 6 AI_Workbench wiring; 7 GUI smoke.
- (session 6) DONE step 1 e8970a9: credential_store.REF_TARGETS {"github-api","helper-ai"}; _validate_ref accepts
  both; 24 credential tests OK. NEXT step 2: aiwb/helper_ai.py.
- (session 6) DONE step 2 d8cb5bc aiwb/helper_ai.py: HelperAIError; normalize_base_url; chat(base,model,messages,
  api_key,timeout,opener) urllib POST {base}/chat/completions (401/403/404/429/timeout/unreachable/bad JSON -> one
  sentence, key redacted); FORMAT_GUIDE/expected_for(step_key)/fix_messages/explain_messages; HelperService(settings,
  save, store, opener) .configured/.config/.summary()/.configure(base,model,api_key None|""|text,timeout)/.clear()/
  .api_key()/.complete/.test/.fix_answer/.explain_step; strip_outer_fence; run_async(fn, done(result,error),
  schedule). settings key "helper_ai" {base_url, model, timeout, credential_ref}. NEXT step 3 tests/test_helper_ai.py.
- (session 6) DONE step 3 89ee218 tests/test_helper_ai.py: 15 tests OK (fake ThreadingHTTPServer). NEXT step 4
  aiwb/ui/helper_card.py (Settings card + thread-safe scheduler), step 5 NextStepCard helper buttons.
- (session 6) DONE step 4 2415a8e aiwb/ui/helper_card.py: build_helper_card(parent, service, on_change, runner) ->
  widgets {url_var, model_var, key_var, timeout_var, status_var, do_save, do_test, do_remove, preset, test, remove,
  runner}; MainThreadQueue(widget).run(fn, done) (thread + queue polled by after(80) only while pending). Probe
  /tmp/hc.py OK (save -> key in store, test -> "✓ ... OK" with Bearer, remove -> settings {}). NEXT step 5:
  NextStepCard(helper=HelperService|None, runner=MainThreadQueue|None, lang=callable) buttons in bar:
  "Explain this step" (configured + a step), "Fix with helper AI" (configured + last paste failed: error or kind in
  rejected/inbox_only/proposal_fix/charter_rejected; text remembered before perform) -> fixed text into paste box,
  never auto-applied.
- (session 6) DONE step 5 319cd00 next_card.py: FIX_KINDS/EXPLAIN_LABEL/FIX_LABEL; NextStepCard(helper=, runner=,
  lang=); .failed {key,text,problem} set by use_answer when error or kind in FIX_KINDS (reset on step change);
  helper_bar (explain_btn, fix_btn) via _helper_buttons() at end of refresh; helper_labels(); explain_step(),
  fix_answer() (result -> paste.set_text, never applied). NEXT step 6 AI_Workbench wiring: self.helper_service after
  github_account_service (~4359); settings card row 7 in _make_settings_project; home card helper=/lang=.
- (session 6) DONE step 6a: 1057900+ba2b245 WorkbenchApp.helper_service = HelperService(lambda: self.settings_data,
  save=self._save_settings, store=create_default_credential_store()); 452c942 HelperService accepts settings getter.
  NEXT 6b: settings card row 7 (_make_settings_project) + home card helper=/lang=/on_change refresh.
- (session 6) DONE step 6b e74a7af: Settings row 7 helper card (self.helper_widgets, _helper_changed refreshes
  home_card); NextStepCard gets helper=getattr(self,"helper_service",None), lang=prefs.lang. NEXT: verify creation
  order (home card after helper_service), unit + GUI tests, then GUI smoke gui_v519_helper_smoke.py.
- (session 6) Order verified: helper_service (4367) < _make_ui (4408) -> _make_home_page (4635) -> settings (4649).
- (session 6) After 5.19 wiring: unit 917 OK (10 skipped). Running GUI run_all (bg, /tmp/gui_all.log). NEXT: GUI gate
  tests/gui/gui_v519_helper_smoke.py (no settings -> no helper buttons, Settings card present; set up with fake
  server -> Explain on Home; bad answer -> Fix button -> fixed text in paste box -> Use this answer works).
- (session 7) Sandbox reset. Restored: clone -> /home/user/webapp, cpush, xvfb. Release desktop-v5.18.0 VERIFIED (5 assets).
  CI c491486 success. gui_v519_helper_smoke.py was NOT committed (lost) -> rewrite it. Then 5.19 release.
- (session 7) Probe /tmp/probe.py OK: no helper btns before setup; app.helper_widgets["save"] with fake url+model (no key)
  -> card.helper_labels()==['Explain this step']; bad answer -> kind inbox_only, card.failed set, labels + 'Fix with helper AI'.
  Writing tests/gui/gui_v519_helper_smoke.py (srv.reply = guided_answer(h, files) for the fix).
- (session 7) DONE cb150cb tests/gui/gui_v519_helper_smoke.py PASS (Save/Test/Explain/Fix->box->accepted/Remove).
  NEXT: full GUI run_all (bg /tmp/gui_all.log) + unit, then 5.19.0 release (bump tool in tools/, manifest new files).
- (session 7) GUI run_all 58/61: S5 (known sandbox-only), NEW gui_v5_polish_smoke ('Settings: 10 controls at once (max 8)',
  'command with two homes: save (Settings, Toolbar)') + gui_v5_map_smoke ('- Status bar [area]') -> caused by helper card
  in Settings. Fixing (likely: card collapsed by default / buttons not counted as commands / rename Save).
- (session 7) 9e09efc helper_card: collapsed by default (toggle "Show settings"/"Hide settings", w["do_toggle"], w["body"]),
  Save button label "Save helper" (two-homes rule). NEXT: regenerate docs/UI_MAP.md (tools/ui_map.py), smoke opens card,
  rerun polish/map/v519 smokes.
- (session 7) d2947f1 smoke opens card; UI map regenerated 1383e80/902f887/e6f05c4 (Settings 8 visible = max).
  polish + map + v519 smokes PASS. NEXT: unit suite, then release 5.19.0:
  python3 tools/bump_desktop_release.py 5.19.0 --module helper_ai.py --module ui/helper_card.py --test test_helper_ai.py
- (session 7) 5.19.0 RELEASE: unit 917 OK; bump ba3633d..2c2ab98 + 1e6e197 checklist; manifest PASS 228 files.
  NEXT: CHANGELOG (apps/desktop/CHANGELOG.md), ROADMAP ✅ (active 5.20.0), tag desktop-v5.19.0, verify release.
- (session 7) 5.19.0: f26b7f3 CHANGELOG, 244577c ROADMAP ✅ (active 5.20.0). Tagging desktop-v5.19.0 now.
  NEXT 5.20.0: S10 "friends' calculator" scenario (guided PM + 2 devs, log fixture answers, <=2 PM rounds to first
  code file), 5.16 perf budgets as permanent tests, user guide (fa/en) + CHANGELOG, release desktop-v5.20.0.
- (session 7) Tag desktop-v5.19.0 pushed (64ec2ba), Release run 41549833352 in progress (verify later).
  5.20 recon: scenarios tests/gui/gui_scenario_s1..s9_*_smoke.py + scenario_driver.py; budget tests exist:
  test_store_cache.py, test_raster_9slice.py, test_release_gate.py, test_motion.py, gui_v516_light_smoke.py;
  guides docs/USER_GUIDE.md + docs/USER_GUIDE_FA.md.
- (session 7) 5.20 recon 2: S2 pattern = new_guided_project -> charter_to_first_prompt (CHARTER fixture
  packages/contracts/fixtures/valid/project-charter.v1.todo.json: refs t1..t3, m1/m2, team agents agent-core-dev ...)
  -> d.use_answer(guided_answer(h, files)) -> "Accept…" -> file on disk. Raw friend log NOT in repo (test_rescue
  reconstructs shapes). PLAN S10 tests/gui/gui_scenario_s10_calculator_smoke.py: calculator charter (PM owns docs task
  t1, dev1 core t2, dev2 UI t3), PM answers half-right proposal shapes from the log, count PM rounds <= 2 to first code file.
- (session 7) DONE d56e2d9 tests/gui/gui_scenario_s10_calculator_smoke.py PASS (calc charter: PM task t0 spec, log
  proposal ops=[] -> 15-line fix prompt -> spec -> core dev -> src/core/calc.js; 2 PM rounds). NEXT 5.20 item 2:
  perf budgets as permanent tests (check what is already covered), then USER_GUIDE(.md/_FA.md) helper AI section.
- (session 8) Sandbox reset. Restored clone/cpush/xvfb. desktop-v5.19.0 release VERIFIED (5 assets), CI b8378f6 success.
  Perf measured (558 KB, 2000 events): cached load 1.0 ms (gate <=5), transaction 20.7 ms (gate <=40). Already
  permanent: load <15ms (test_store_cache), menu raster <250ms, idle 0 fps + menu closes (gui_v516_light), release gate.
  MISSING: transaction + 5 ms load budget -> new tests/test_perf_budgets.py (release --test it). Then USER_GUIDE(.md/_FA.md)
  helper AI + S10 section, CHANGELOG 5.20.0, bump, ROADMAP ✅, tag desktop-v5.20.0 = roadmap end.
- (session 8) DONE 8579e24+fix: tests/test_perf_budgets.py PASS (4 tests; ProjectStore.revision is a PROPERTY; CI env -> x2 slack).
  NEXT: unit suite, USER_GUIDE.md + USER_GUIDE_FA.md (helper AI section), CHANGELOG 5.20.0, bump
  `python3 tools/bump_desktop_release.py 5.20.0 --test test_perf_budgets.py` (in worktree /tmp/rel, copy file-by-file).
- (session 8) Unit 921 OK. DONE guides: bc49f7a USER_GUIDE.md (§3d 5.16–5.20 + helper AI, privacy, NOT RUN),
  52c8b24 USER_GUIDE_FA.md (§۴الف). NEXT: check tests reading guides, CHANGELOG 5.20.0, bump, ROADMAP ✅, tag.
- (session 8) 289e59d CHANGELOG 5.20.0. NEXT: bump in /tmp/rel worktree (--test test_perf_budgets.py), copy file-by-file.
- (session 8) 5.20.0 bump 579d2e7..1d76349 + b29d163 checklist; manifest PASS 229 files. Running GUI run_all (bg
  /tmp/gui_all.log) before tag. NEXT: ROADMAP ✅ (all done), tag desktop-v5.20.0, verify release = ROADMAP END.
- (session 8) GUI run_all 61/62 (only S5 = known sandbox-only TclError; passes in CI). NEXT: ROADMAP ✅, tag desktop-v5.20.0.
- (session 8) d645c01 ROADMAP 5.20.0 ✅ (all 5.16–5.20 done). Tagging desktop-v5.20.0 now. After: verify Release run
  assets (5) + CI green -> ROADMAP COMPLETE. Nothing else pending.
- (session 8) ROADMAP 5.16→5.20 COMPLETE. desktop-v5.20.0 release VERIFIED (run 41552064115 success, 5 assets:
  Setup.bat, SHA256SUMS, Source.zip, Windows_Payload.zip, release-manifest.json); CI 630665a success. Nothing pending.
  Next work needs a NEW roadmap from the owner (NOT RUN items in USER_GUIDE §8 need real Windows/real chats).
- (session 9) Owner task: NO new roadmap. Bug hunt before showing app to friends: review code + flows, record every finding
  in docs/BUG_FINDING.md (update continuously, checkpoint each edit). Env restored (clone, cpush, xvfb).
- (session 9) 66ca00f docs/BUG_FINDING.md created. Unit 921 OK (skip 10). pyflakes: only unused locals + 1 f-string w/o
  placeholder (artifacts.py:521) — harmless, no undefined names. GUI run_all started -> /tmp/gui_all.log. NEXT: review
  aiwb/v2/guide.py (next-step engine: every state must offer an action), paste pipeline, charter_repair, proposals.
- (session 9) Read guide.py steps()/perform(). SUSPECTS to verify by script: (a) blocked task with reason
  "prerequisite no longer valid" (dep cancelled) is shown with "It can continue now" -> transition(ready) raises
  "not ready" -> only way out = cancel the task (no UI to drop the dead dependency?). (b) report.apply_decision
  emergency `blocks` appends depends_on WITHOUT cycle check -> possible silent deadlock (blocked "waiting for" tasks
  are hidden from steps and from the PM "stuck" report). Plan: write /tmp/fuzz_guide.py random-walk over Guide actions.
- (session 9) GUI run_all 61/62 (S5 sandbox-only). CONFIRMED + recorded: BF-001 (25c9b1d, S2 dead prerequisite ->
  primary button always fails), BF-002 (4c8ada9, S1 emergency `blocks` edge -> cycle, hidden from Home & PM report).
  Repro scripts in /tmp/hunt (lost on reset; text in BUG_FINDING is enough to recreate). NEXT: random-walk fuzzer
  /tmp/hunt/fuzz.py over Guide steps/actions looking for non-ModelError exceptions + dead ends.
- (session 9) Fuzzer /tmp/hunt/fuzz.py (30 seeds): 0 crashes, 0 dead ends, but exposed BF-003 (754707e: reject/ask-for-
  changes raise while graph has a cycle). BF-004 (54db8b5): remove_dependency leaves task blocked "waiting for" with
  depends_on=[] forever (_refresh_readiness skips empty depends_on). NEXT: corrupt/missing state file, paste edge cases
  (huge, binary, RTL), Quick mode, helper AI errors, summary table in BUG_FINDING.
- (session 9) BF-005 (d5e6cb6, S2): corrupt state.json -> StoreError, message mentions .workbench/v2/backups which
  normally does not exist; events.jsonl exists but no recovery. NEXT: paste edge cases via ctl.route_answer (empty,
  huge 5MB, binary/NUL, RTL Persian, CRLF, BOM, answer for wrong handoff), then Quick mode, helper AI.
- (session 10, after sandbox reset) Env restored. BF-006 (d1aa66b, S3): lone surrogate in pasted text -> UnicodeEncodeError
  in route_answer / quick.apply (caught by Tk global handler -> "bug" dialog). Paste edge cases BOM/CRLF/NUL/fenced/RTL/
  3MB noise/smart quotes all OK. NEXT: Quick mode path safety (../, absolute, C:\, reserved names), non-ASCII + read-only
  project folder, Summary table, GUI S5 failure triage.
- (session 10) Recorded BF-007 (8351b05 S1 Quick apply half-way -> no restore + backup id reuse destroys original),
  BF-008 (37e442d S2 Windows-invalid paths accepted incl. NTFS ADS), BF-009 (bbc4a66 S1 accept_handoff write failure ->
  handoff accepted, half files, no retry). NEXT: Summary table, unzip_files (no backup, partial), non-ASCII/read-only
  folder, GUI S5 triage, helper AI / network errors, Settings.
- (session 10) BF-010 (ac7eb7b S1): files.stage() silently skips >512KB / empty / >8MB-total files; accept approves
  the task with the file missing. Checked OK: Persian folder names, read-only folders, scope check, S5 = sandbox only.
  Summary now 6 S1 / 3 S2 / 1 S3. NEXT: stale proposal (base_state_revision old), continue-step dismissal, Quick ZIP,
  troubleshoot limit (3 attempts -> then?), validation failed path.
- (session 10) BF-011 (afd8935 S2): validation_failed note dropped; next task prompt still "Claimed: tests pass", no
  failure info. Checked OK: troubleshoot x3 -> escalate -> task blocked (visible, unblock/manager/cancel). Summary
  6 S1 / 4 S2 / 1 S3. NEXT: stale proposal, continue-step dismissal, Quick ZIP, reject_handoff->re-prepare loop.
- (session 11, after sandbox reset) Env restored at 23f52e2. BF-012 (22e4627 S3 continue step outlives dropped
  handoff), BF-013 (c50039f S2 reject reason lost, next prompt "first handoff") were recorded at end of session 10;
  checked OK: scope check, troubleshoot limit, out-of-date answer. Summary 6 S1 / 5 S2 / 2 S3. NEXT: stale proposal
  (script o_stale.py was running when the session died), Quick ZIP, helper AI / network errors, Settings.
- (session 11) BF-014 (ce399bd S2): proposal import only rejects UNKNOWN task ids; depends_on / update_task on a
  cancelled task is accepted silently -> new task blocked "prerequisite no longer valid" (BF-001 dead end). Stale
  warning itself works (o_stale.py). Summary 6 S1 / 6 S2 / 2 S3. NEXT: Quick ZIP (unzip_files), helper AI / network.
- (session 11) BF-015 (bdad86c S3): helper AI reads 800 KB bytes then parses -> long \u-escaped Persian reply reported
  as "not a Chat Completions reply"; IncompleteRead not caught (generic message). Checked OK: Quick ZIP import, stale
  plan warning, helper AI HTTP 401/404/429/timeout/reset/SSL/HTML messages. Summary 6 S1 / 6 S2 / 3 S3.
  NEXT: Settings dialog save/load, GitHub publish errors, release/closeout steps.
- (session 12, after sandbox reset) Env restored at 783edb6 (clone + cpush + xvfb). Summary 6 S1 / 6 S2 / 3 S3.
  NEXT: Settings dialog save/load + invalid values, GitHub publish errors, release/closeout steps.
- (session 12) BF-016 (1f188ca S1): settings.json in UTF-16 / cp1252 -> UnicodeDecodeError escapes
  load_settings_with_recovery (only OSError caught) -> "The application failed to start", every start. Checked OK:
  JSON syntax error / non-object -> .corrupt-<ts> backup; BOM; directory / no permission -> defaults.
  Summary 7 S1 / 6 S2 / 3 S3. NEXT: helper AI settings (HelperService), GitHub publish errors, closeout.
- (session 12) BF-017 (27f7b0c S2): _save_settings failure only logged; prefs / helper AI / toolbar Save say "Saved";
  lost at restart; helper key stored in Credential Manager without saved ref (orphan). Summary 7 S1 / 7 S2 / 3 S3.
  NEXT: v2/publisher.py (GitHub publish errors), closeout/release.
- (session 12) BF-018 (7def0de S3): state publisher catches only OSError/URLError; IncompleteRead / bad JSON /
  missing "object" -> "Publish state now" shows the bug dialog; timer path swallows it (no last_error, no back-off,
  retried every 30 s). Checked OK: 401/403/429/5xx/conflict/protected-branch mapping. Summary 7 S1 / 7 S2 / 4 S3.
  NEXT: closeout / release (v2/closeout.py, repo.py _do_release).
- (session 12) BF-019 (5ed6792 S2): RepoService.confirm replays all GitHub calls after a partial failure; create repo
  -> 422 "creation failed" forever; release tag exists -> 422 mapped to "state branch moved" forever.
  Summary 7 S1 / 8 S2 / 4 S3. NEXT: closeout archive (state archived before bundle write), expand.
- (session 12) BF-020 (43b925f S3): closeout.archive commits archived_at before writing the bundle; write error ->
  bug dialog, project read-only, card claims the bundle exists (workaround: Reopen -> Archive).
  Summary 7 S1 / 8 S2 / 5 S3. NEXT: write "Checked and OK" for session 12, report to owner.
- (session 13, after sandbox reset) Env restored at 9820c33 (clone + cpush + xvfb). Summary 7 S1 / 8 S2 / 5 S3 (BF-001..020, all OPEN).
  Owner: keep bug-hunting all areas, do not stop, no questions. NEXT: new-project wizard, bundle export/import, Run/Git page.
- (session 13) Bundle area: BF-021 (1694dbd S2) project_id = raw folder name -> bundles of "My Project" / Persian / long names can never be imported;
  BF-022 (0f945c2 S3) export/import OSError -> bug dialog, malformed bundle -> raw Python text; BF-023 (b3cb781 S3) plan_import "new"
  checked before other_project/older -> goal-only project replaced silently. Summary 7 S1 / 9 S2 / 7 S3.
  NEXT: write checked-OK (bundle round trip), then new-project wizard, Run/Git page.
- (session 13) Wizard + Git commit/push checked OK. BF-024 (168e92e S3) commit dialog shows Persian paths as octal escapes (core.quotepath);
  BF-025 (5c81cea S2) Run page: Python child on Windows writes pipe in ANSI code page -> print("سلام") fails -> false "Action Failed"
  + repair prompt. Summary 7 S1 / 10 S2 / 8 S3. NEXT: run timeout/kill, queued actions, Quick mode restore, context request.
- (session 14, after sandbox reset) Env restored at 3a2a60c (clone + cpush + xvfb). Summary 7 S1 / 10 S2 / 8 S3 (BF-001..025, all OPEN). Session 13 was cut (credits) while starting Quick mode Apply/Restore. NEXT: Quick mode apply/restore, run timeout/kill, queued actions, context request.
- (session 14) Quick mode: BF-026 (ac03fc9 S2) apply/restore follow symlinks/junctions outside the project; BF-027 (f7ed9cf S3) ZIP
  entries with ./ refused as unsafe; BF-028 (4ca5cfd S3) restore failing half-way -> bug dialog, retry says "edited by you".
  Summary 7 S1 / 11 S2 / 10 S3. NEXT: run timeout/kill + output cap, queued actions, context request, Quick prompt build.
- (session 14) BF-029 (3278b0e S2) run hangs past time limit when a grandchild holds the pipe (server launchers);
  BF-030 (7fef491 S2) Quick prompt sends .env / keys / outside-link files unredacted. Checked OK: run limit/output cap,
  queued actions. Summary 7 S1 / 13 S2 / 10 S3. NEXT: guided context request packing, classic apply_changes_transactionally.
- (session 15, after sandbox reset) Env restored at ea7c2c2; pushed the cut summary line (BF-032 -> S2, 1d224ff).
  BF-031 (5323620 S3) context request sensitive refusal bypassed by trailing space/dot or link alias; classic
  transactional apply checked OK; BF-032 (ea7c2c2 S2) smart check uses raw path -> false out_of_scope loop.
  Summary 7 S1 / 14 S2 / 11 S3. NEXT: closeout/waves/timeline/charter_repair/changes/attempts, paste_box, guide actions.
- (session 15) BF-033 (68b627e S2) "revise" route on a done task: change recorded, task stays done, no prompt possible,
  project can still be announced complete; BF-034 (5734643 S3) archive sets read-only before writing bundle, failed write
  cannot be retried. Summary 7 S1 / 15 S2 / 12 S3. NEXT: waves/dispatch, timeline, charter_repair, paste_box, handoff.
- (session 15) BF-035 (df5b3ae S2) cancelling a task leaves its open handoff: holds a chat slot, answer still accepted
  and written into the project. Summary 7 S1 / 16 S2 / 12 S3. NEXT: timeline (milestones/versions), charter_repair,
  paste_box live diagnosis, handoff stale/late answers, attempts.
- (session 15) BF-036 (828dc0c S3) guided release: 3 separate transactions, missing run id leaves version tagged with
  default tag "vv1.0.0"; retry tag ignored. Summary 7 S1 / 16 S2 / 13 S3. NEXT: handoff late/stale answers, attempts,
  charter_repair, paste_box.
- (session 15) BF-037 (303308e S3) "Accept anyway" on outcome failed: files written, message promises a review that
  never appears (task stays in_progress, guide offers a fresh prompt). Summary 7 S1 / 16 S2 / 14 S3.
  NEXT: attempts late answers, charter_repair, paste_box, i18n/RTL text, bundle import edge cases.
- (session 15) BF-038 (605ae2b S3) answer for a dropped (rejected) prompt is reported "linked", then silently ignored.
  Summary 7 S1 / 16 S2 / 15 S3. NEXT: charter_repair, paste_box, bundle import edge cases, i18n.
- (session 16, after sandbox reset) Env restored at 9865011 (clean). Previous chat ended mid-test on charter_repair
  role_of("Lead developer") -> 'project_manager' (substring "lead"). Summary 7 S1 / 16 S2 / 15 S3.
  NEXT: finish charter_repair role check, paste_box, bundle import edge cases, i18n.
- (session 16) BF-039 (b54ff2f S2) charter_repair role_of(): "lead"/"owner"/"manager" substring rule first ->
  "Lead developer"/"Tech lead" become a 2nd project_manager (skipped by agent_hub, offered as PM, prompt says PM).
  Summary 7 S1 / 17 S2 / 15 S3. NEXT: charter_repair other normalizers (versions, refs, ownership), paste_box, bundle import, i18n.
- (session 16) BF-040 (3fc6f4c S3) paste preview always "Manager proposal ✓" (no parse); BF-041 (8851c89 S2) answer with
  files + context request: preview says request, route_answer treats as delivery, request lost.
  Summary 7 S1 / 18 S2 / 16 S3. NEXT: bundle import edge cases, i18n/RTL, Quick mode read_answer, rescue prompts.
- (session 16) BF-042 (c5c92e7 S2) AIWB_FILE action="delete"/"move" parsed as empty write (diagnose.parse_files drops
  action): Quick apply empties the file; guided silently drops it and approves. Summary 7 S1 / 19 S2 / 16 S3.
  NEXT: bundle import edge cases, i18n/RTL, rescue prompts, diagnose.parse_files other attrs (body="raw").
- (session 16) BF-043 (0251ef1 S1) staging + smart check only in guide._paste; companion submit_response, classic
  ProjectsWindow import, shell.do_import call route_answer only -> accept approves task, writes no file.
  Also checked: body="raw" blocks strip a leading fence of a raw Markdown file (minor, folded into notes, not filed yet).
  Summary 8 S1 / 19 S2 / 16 S3. NEXT: raw-body fence strip (verify impact), bundle import, rescue prompts, i18n.
- (session 16) BF-044 (a81421d S3) body="raw" ignored by parse_files: leading code fence of a raw Markdown file stripped;
  fence + prose flagged truncated. Summary 8 S1 / 19 S2 / 17 S3. NEXT: bundle import edge cases, rescue prompts, i18n/RTL.
- (session 17, after sandbox reset) Env restored at 0a9377f (clean). Previous chat stopped (credit) right before reading
  src/aiwb/v2/rescue.py. Summary 8 S1 / 19 S2 / 17 S3. NEXT: rescue prompts, bundle import edge cases, i18n/RTL.
- (session 17) BF-045 (0679819 S2) rescue: assessment by title -> duplicate create_task; BF-046 (c5da09d S2) rescue:
  assessment "description"/"goal" overwrites objective; owner_role case-sensitive. Summary 8 S1 / 21 S2 / 17 S3.
  NEXT: rescued decisions (string / no options), fix_prompt, bundle import, i18n/RTL.
- (session 17) BF-047 (55d0397 S3) rescued text decisions lose PM choice / recommendation sentence as option.
  Summary 8 S1 / 21 S2 / 18 S3. NEXT: fix_prompt (NoOperations path), bundle import edge cases, i18n/RTL.
- (session 17) BF-048 (1ed2ef9 S2) end of roadmap: roadmap_remaining "nothing left"/missing -> NoOperations; fix prompt
  never mentions roadmap_remaining:false, forces fake ops. Summary 8 S1 / 22 S2 / 18 S3. NEXT: bundle import, i18n/RTL.
- (session 17) BF-049 (fa46ddc S2) bundle import: project with decisions/goal/team but no tasks = "new"; other project
  replaces it, other_project check skipped. Summary 8 S1 / 23 S2 / 18 S3. NEXT: bundle MAX_EVENTS / descends(), i18n/RTL.
- (session 17) BF-050 (ea53ce9 S2) project_id = raw folder name (controller passes root.name); spaces / Persian names
  -> bundle export unreadable everywhere. Bundle newer/older/same round trip checked OK. Summary 8 S1 / 24 S2 / 18 S3.
  NEXT: i18n/RTL (Persian text in tasks/prompts/paths), duplicate file blocks, huge answers.
- (session 17) BF-051 (ccaf8ad S2) one answer: duplicate paths / case twins / file-vs-folder unchecked -> silent drop or
  BF-009 crash. Persian file paths + backslash paths checked OK. Summary 8 S1 / 25 S2 / 18 S3.
  NEXT: Persian text in task titles/prompts (RTL), huge answers, Quick mode restore.
- (session 17) BF-052 (fa6f81a S3) rescue.norm() does not unify Arabic ي/ك, ZWNJ-less forms, Persian digits -> accepted
  decision re-asked. Summary 8 S1 / 25 S2 / 19 S3 (summary row pushed 5f4ff9b in session 18).
- (session 18, after sandbox reset) Env restored at 5f4ff9b (clean). NEXT: Persian text in prompts (RTL), huge answers,
  Quick mode restore, then remaining modules not yet hunted.
- (session 18) Dedup: BF-050 = DUPLICATE of BF-021, BF-049 = DUPLICATE of BF-023 (BF-023 raised to S2). New status
  `DUPLICATE (of BF-NNN)` in the legend. Before filing a new BF, grep BUG_FINDING.md for the function name first.
  Summary 8 S1 / 24 S2 / 18 S3 (+2 duplicates).
- (session 18) BF-053 (09c0fea S2) lenient.find_object stops at the first unclosed `{` -> stray `{` in prose makes a
  complete JSON-files answer / marker-free charter "cut off". Summary 8 S1 / 25 S2 / 18 S3.
  NEXT (never hunted so far): intake/normalize.py, v2/team_setup.py, v2/workflow.py, v2/snapshot.py, v2/dashboard.py,
  v2/next_action.py, i18n.py.
- (session 18) BF-054 (c66e5a5 S2) normalize._strip_invisible removes ZWNJ/ZWJ/NBSP from the WHOLE answer incl. file
  bodies; triggered by any marker repair (smart quotes, escaped/bold marker) or JSON repair. Summary 8 S1 / 26 S2 / 18 S3.
  NEXT: v2/team_setup.py, v2/workflow.py, v2/snapshot.py, v2/dashboard.py, v2/next_action.py, i18n.py.
- (session 18) BF-055 (615429f S2) waves/guide `_owner()` fallback = agent-implementer else FIRST agent = PM; wizard teams
  have no agent-implementer -> ownerless / removed-owner tasks go to the PM chat. Summary 8 S1 / 27 S2 / 18 S3.
  NEXT: team_setup leftovers (pending plan names removed AI; role change keeps old template text), workflow.py, snapshot.py.
- (session 18) BF-056 (e8cb76b S3) Edit team role change keeps old template purpose/instructions/task types.
  Checked OK: a pending plan naming a removed AI -> accept refused with a clear "owner agent … does not exist",
  partial accept of the other changes works (no dead end). Summary 8 S1 / 27 S2 / 19 S3.
  NEXT: workflow.py, snapshot.py, dashboard.py, next_action.py, i18n.py.
- (session 18) BF-057 (e9e782e S3) abandon leaves active attempt prompt_ready -> workflow stage / attention queue /
  restart warning say "prompt prepared"; after reject stage "rejected" not a user-action stage. Summary 8 S1 / 27 S2 / 20 S3.
  NEXT: snapshot.py, dashboard.py, next_action.py, i18n.py, resources.py.
- (session 18) BF-058 (ae4a170 S3) next_action plan_project rank 1 beats pending proposal/decision when no tasks yet ->
  overview / phone / PROJECT_STATUS.md disagree with Home. Summary 8 S1 / 27 S2 / 21 S3 (summary row babd31c, session 19).
- (session 19, after sandbox reset) Env restored at babd31c. NEXT: dashboard.py, i18n.py, resources.py,
  context_request_window.py, snapshot.py details.
- (session 19) BF-059 (ef83754 S3) attention item key = kind:ref:rank (no handoff/reason) -> "Mark as read" mutes later
  deliveries / publish errors of the same task; ws_seen trimmed alphabetically. Summary 8 S1 / 27 S2 / 22 S3.
  Seen in passing (Persian UI): attention `why` text is always English (candidate for the i18n pass).
  NEXT: i18n.py (Persian-mode leftovers), resources.py, context_request_window.py.
- (session 19) BF-060 (c42c695 S3) Persian Workspace: English literals in shell.py (Open on Home, More, Queue of each AI,
  Who/Step, You/N open, Project details keys) + attention `why` always English. Summary 8 S1 / 27 S2 / 23 S3.
  NEXT: resources.py (bindings / accounts), context_request_window.py, snapshot.py details.
- (session 19) BF-061 (1017097 S3) current_binding = max updated_at -> editing an OLD binding's note makes it current;
  the attempt freezes the old chat. Summary 8 S1 / 27 S2 / 24 S3. Checked OK: a binding disabled on purpose does not
  block Prepare (readiness ok=False only shows a hint). NEXT: SECRET_RE false positives (notes "max token: 8000",
  AI Studio links), context_request_window.py.
- (session 19) BF-062 (f2ef5b5 S3) SECRET_RE refuses labels "session: work", "token: 128k", chat names, notes, and
  AI Studio links (40+ char id in path). Summary 8 S1 / 27 S2 / 25 S3.
  NEXT: context_request_window.py / context_request.py, then snapshot.py details, publisher.py.
- (session 19) BF-063 (18c9afb S3) context pack numbers lines with splitlines() -> \x0c / U+2028 / NEL shift line numbers and symbol slices. Summary row a554025 (session 20). Summary 8 S1 / 27 S2 / 26 S3.
- (session 20, after sandbox reset) Env restored at a554025. NEXT: context_request_window.py, rest of context_request.py (folder mode, ZIP pack), snapshot.py, publisher.py.
- (session 20) BF-064 (e285b99 S3) empty requested file: deliverable needs content -> listed as "Not provided: ready — ", left out of ZIP. Summary 8 S1 / 27 S2 / 27 S3. Seen, to record next: binary / UTF-16 / cp1252 files dumped as mojibake; folder request "build/" reported missing (SKIP_DIRS hits the requested folder); file + its folder -> duplicate blocks.
- (session 20) BF-065 (0b0e11b S3) context pack decodes every file utf-8/replace: PNG, UTF-16, cp1252 pasted as garbage + NUL, status "ready". Summary 8 S1 / 27 S2 / 28 S3. NEXT: folder request of a SKIP_DIRS name ("build/") -> "missing"; file + its folder -> duplicate blocks.
- (session 20) BF-066 (35c0f76 S3) _expand_folders applies SKIP_DIRS to the requested folder itself ("build/" -> missing) and drops nested dist/build silently; file + its folder duplicated. Summary 8 S1 / 27 S2 / 29 S3. Checked OK: folder request skips/refuses .env and secrets/ (refused_sensitive per file). NEXT: snapshot.py, publisher.py.
