# Work log — current roadmap step (for resuming after a sandbox reset)

Read this first, then `ROADMAP.md`. Every line here is committed and pushed before the next change (checkpoint rule).

## Environment rebuild (after a reset)

```bash
echo -n '<token>' > ~/.aiwb_gh_token; chmod 600 ~/.aiwb_gh_token
git clone https://x-access-token:$(cat ~/.aiwb_gh_token)@github.com/golshandvr-del/workbench.git /home/user/webapp
cd /home/user/webapp && git config user.name golshandvr-del && git config user.email golshandvr-del@users.noreply.github.com
sudo apt-get install -y xvfb python3-tk imagemagick xdotool; pip install jsonschema pyflakes
# unit:  cd apps/desktop && python3 -m unittest discover -s tests -t .
# smoke: cd apps/desktop && xvfb-run -a -s "-screen 0 1600x1000x24" python3 tests/gui/run_all.py
# map:   xvfb-run -a python3 tools/ui_map.py   (rewrites docs/UI_MAP.md + docs/design/ui_map.svg/.png)
```

Baseline before 5.11.0 (main `5066fe3`, tag `desktop-v5.10.0`): 765 unit tests OK (5 skipped), 46/46 GUI smoke.

## 5.11.0 — DONE

PR #67 merged (main `50967f0`), tag `desktop-v5.11.0` pushed (release-desktop.yml builds the Release). CI run 1 failed
only on Windows: owner_path's final print hit cp1252 → fixed 2af2242; all smokes pass with PYTHONIOENCODING=cp1252.

## 5.12.0 — DONE

PR #68 merged (main `dd1864b`), tag `desktop-v5.12.0` → Release published (Setup.bat, Payload, Source, SHA256SUMS). CI green on
first run (Linux 3.10/3.13 + Windows). Unit 802 OK, GUI 47/47.

## 5.15.0 — Gate of real scenarios (branch `feat/v5.15.0-scenarios`)

Plan (one scenario = one script `apps/desktop/tests/gui/gui_scenario_sN_*_smoke.py`, picked up by run_all.py → runs in
CI on Linux (xvfb) and Windows (installed app); shared driver `tests/gui/scenario_driver.py` (not a smoke itself);
screenshots `AIWB_SCREENSHOT_DIR` → `docs/audit/screens/v5.15-scenarios/sN_*.png`):
- [x] 0 read existing gates. Reuse: gui_owner_path_smoke (Owner: pump/click/click_menu/paste/shot("owner_"), do_step,
      use_answer, menu_labels, walk; wizard via app.project_wizard pages[0] TEntry + goal_text + team.count_box; charter
      fixture packages/contracts/fixtures/valid/project-charter.v1.todo.json with base_state_revision; handoff from
      ws.wc.ctl.state()["handoffs"]; manifest fields handoff_id/task_id/task_revision/attempt_id/outcome…) ·
      gui_context_smoke (windows_copy, clipboard_paste, use_clipboard_answer; owner's real GPT answer
      docs/audit/owner-5.11/HO-0006_gpt_answer_context_request.txt) · gui_quick_smoke (Driver, block(), app.quick_form) ·
      gui_team_editor_smoke (older project = V2Project(old, name).open(); open_workbench helper) · corpus
      tests/fixtures/answers C01–C31 (charters, C26 cut-off, C31 windows copy), F01… (files).
  S5 finding: settings = LOCALAPPDATA/AIWorkbench/settings.json; on_close() → _save_settings() stores last_workspace; WorkbenchApp.__init__ reopens it (set_workspace) → S5 = on_close(), new Tk + WorkbenchApp with the same LOCALAPPDATA. run_all.py globs gui_*smoke.py only (driver file is safe).
- [x] 1 scenario_driver.py f0ff56b..1a18b6c (Driver: start/restart(on_close)/pump/click/click_menu/paste (real clipboard)/wait_line/step/use_answer/shot/finish/say; helpers scenario_home, block, digest, windows_copy, guided_answer, new_guided_project, charter_to_first_prompt, open_handoff; allowed work windows by title prefix)
  S1 gui_scenario_s1_quick_smoke.py 47817b2 PASS (9 clicks + 2 pastes)
  S2 gui_scenario_s2_guided_smoke.py 7a18700 PASS (12 clicks + 2 pastes)
  S3 gui_scenario_s3_broken_smoke.py ad6b4f5 PASS (11 clicks + 3 pastes; fix prompt = charter_fix_prompt via card COPY_RESULT 'paste'; auto-fix msg 'auto-fix')
- [ ] 2 S1 Quick, one AI, 3 files · S2 Guided 3 named AIs → first milestone accepted · S3 broken GPT answer → auto-fix /
      fix prompt · S4 cut-off → Continue (guided) · S5 close + reopen mid-work · S6 project made by 5.7.0 opens ·
      S7 real GPT ZIP · S8 context request → files → answer · S9 Windows copy with `\` line ends
- [ ] 3 screenshots, full unit + GUI run
- [ ] 4 USER_GUIDE (English) + USER_GUIDE_FA (Persian) with pictures, CHANGELOG, README, checklist (owner NOT RUN list)
- [ ] 5 version 5.15.0, manifest/install.ps1, PR → CI → merge → tag → Release; ROADMAP ✅ (then: mobile — owner only)

## 5.14.0 — DONE

PR #70 merged (main `338ffc8`), tag `desktop-v5.14.0` → Release published (Setup.bat, Payload, Source, SHA256SUMS,
release-manifest.json). CI run 1 + 2 failed only on Windows (test_quick \r\n size; smoke print → on cp1252), run 3 all
green. Unit 855 OK, GUI 48/48. NEXT: 5.15.0 (Gate of real scenarios S1–S9) on branch `feat/v5.15.0-scenarios`.

### 5.14.0 log (kept for reference)

Facts (read in code 2026-10-26): New Project ▾ = `structure5.TOOLBAR["new"]` (new_guided, new_folder) wired in
`AI_Workbench` ~4612 `commands={...}`; reusable intake: `aiwb/intake/answer_files.extract(text)` /
`zip_files(bytes)` → `Extracted(files, format, fixes, problems, truncated)`, `normalize.strip_copy_damage`,
`normalize.truncation_report/continue_prompt`; answer rule `aiwb/v2/handoff.WHOLE_ANSWER_RULE`; paste UI
`aiwb/ui/paste_box.PastePanel(on_use=, state=)`; Classic tools = Settings card `tool_cards["settings"]`
(`_make_settings_project`, structure5.CLASSIC/TOOLS: prompt, response, profile, run).

Plan (one checkpoint per change):
1. Engine `aiwb/v2/quick.py` (pure, no Tk): state `.workbench/quick/quick.json` (rounds: task, format, prompt,
   answer summary, applied id); `build_prompt(root, task, fmt, include=[paths])` (inventory + chosen file contents +
   format rules + WHOLE_ANSWER_RULE); `read_answer(text|zip)` → files + fixes/problems/truncated (+ continue prompt);
   `plan(root, files)` → per file new/changed/same + unified diff; `apply(root, plan)` → backup
   `.workbench/quick/backups/<id>/` + atomic writes + manifest; `restore(root, id)` (hash-guarded: a file changed
   after apply is not overwritten); `to_guided(root, goal, rows)` → V2 project in the same folder, files untouched.
   Tests `tests/test_quick.py` (3 formats aiwb/json/zip, copy damage, truncated, unsafe paths, apply/restore, convert).
2. UI `aiwb/ui/quick_window.py`: one window "Quick — one AI chat": task box + format → *Copy the prompt* → PastePanel
   → preview list with diff → *Apply* → *Restore last apply*; *Make it a multi-AI project…*.
3. New Project ▾ → "Quick — one AI chat…" (structure5 + UI_TREE + commands.py + App Map regen).
4. Remove Classic tools (1.x Prompt / AI Response pages) from Settings; fix ia/map/tree tests; keep internal code
   used by old smokes only where needed.
5. Gate smoke `tests/gui/gui_quick_smoke.py`: three formats end-to-end + Restore + convert to Guided; screenshots
   `docs/audit/screens/v5.14-quick/`.
6. Docs/version/PR/CI/tag/Release.

Progress:
- [x] 1 engine `aiwb/v2/quick.py` d9b6816 (+ fenced files keep final newline ab6c8b0), `tests/test_quick.py` f805d19
  (15 OK; add to bump: --module v2/quick.py --test test_quick.py). API: build_prompt(root, task, fmt, include) ·
  read_answer(text | zip_bytes=) → {files, format, label, fixes, problems, truncated, continue_prompt} ·
  plan(root, files) → [{path, status new/changed/same, diff, content}] · summary(items) · apply(root, items, task=) ·
  last_apply(root) · restore(root) → {restored, kept} · to_guided(root, goal, rows) · state(root). QuickError = message.
- [x] 2 UI `aiwb/ui/quick_window.py` 51d280a: QuickWindow(parent, root, clipboard=, status=, on_convert=) · set_task ·
  set_format · toggle_include · copy_prompt · paste.set_text + use_answer · show_diff · apply_now · restore_now ·
  copy_continue · ask_convert → convert_dialog{win, goal, table, ok, error}. PastePanel(diagnose=) 1623a5c; Quick
  `diagnose` drops the AIWB_HANDOFF warning, explains non-file answers 921d3fe; fits 940x820 0358093. Throwaway check
  /tmp/qw_try.py (prompt/answer/diff/apply/restore/cut-off/convert all OK).
- [x] 3 New Project ▾ → "Quick — one AI chat…": structure5 3c4c776, UI_TREE 1f812e4, quick.mark/is_quick cbdf65e,
  app `new_quick_project(name=, parent=)` → form `app.quick_form{win,name,parent,error,create}` → `_create_quick` →
  `open_quick_window()` (`app.quick_window`), `_quick_converted` → Home 55d2617; is_guided = V2 state has a goal
  (opening a folder creates state.json with template agents!) b750994. Live check /tmp/quick_live.py OK (menu → form →
  apply → convert → Home card "Get the Project Charter"). Home card of a Quick folder = one step key "quick", action
  "quick_open" → open_quick_window (`_home_steps` / `home_perform`) b39f2eb. STEP 3 DONE.
- [x] 4 remove Classic tools from Settings: structure5 TOOLS/TOOL_HOME without prompt/response, CLASSIC = "Tools"
  2c40fcc; UI_TREE 21a2986; ui_map MORE_EXEMPT "Settings › Tools" 6b7e6bc; commands project.new_quick 31a9af1 + test
  1342fbb; Settings card text 56ece43; Workbench Tools without "Classic prompt & response…" f1b6760; UI_MAP regen
  7414353/7f27b93/46aa5d2. Unit 855 OK. The prompt/response *pages* still exist (shell.PAGES, notebook tabs) only for
  old smokes (kept on purpose, plan step 4); Workbench classic_response link dropped d31f09f. GUI run_all 47/47,
  unit 855 OK. STEP 4 DONE.
- [x] 5 gate smoke tests/gui/gui_quick_smoke.py b6902df PASS (menu → form → prompt → AIWB from real clipboard / JSON /
  ZIP via Load ZIP… → apply, Restore, cut-off → continue, Home Quick card, Quick → Guided, files untouched); ZIP label
  "GPT ZIP · name" 3e01acf (only while the box holds the ZIP's text: PastePanel.zip_text 92952da, baeb8da). Home map
  of a Quick folder = empty map with Quick text, no template lanes (MissionCanvas.empty_text 4a3314e, refresh_mission
  b7193b8, smoke a404b66). Screenshots docs/audit/screens/v5.14-quick/quick_01…09 (e7189d9…42be9b1). Full run at
  9fb50fa: unit 855 OK, GUI 48/48. STEP 5 DONE.
- [ ] 6 docs/version/PR/CI/tag/Release (order as 5.13.0: version in AI_Workbench.py, aiwb/__init__.py,
  github/api_client.py · release_manifest.json + install.ps1 (v2/quick.py, ui/quick_window.py, test_quick.py,
  gui_quick_smoke.py, checklist) · docs/release/v5.14.0/ checklist · CHANGELOG · README(s) · USER_GUIDE · ROADMAP)
  - done: version 5d033d5/aad284b/777e2dc, manifest f691c7e, install.ps1 ad01b75 (check_installer_manifest PASS 217),
    checklist 586db09 + 9c864d0. CHANGELOG 352d97a, README de7086f, USER_GUIDE 501794d/5dbef37/2ed8951 (section 3b Quick), ROADMAP (5.14.0 ✅, 5.15.0 active). PR #70 opened (head 61432a0). Windows CI fixes: test_quick wrote text (\r\n → 7 bytes) → write_bytes 6d809b0; gui_quick_smoke PASS line had → (cp1252 console UnicodeEncodeError) → encode/replace 563183b. Next: CI green → merge #70 → tag desktop-v5.14.0 → Release.

## 5.13.0 — One project, one screen (B3, B4, B5) (branch `feat/v5.13.0-one-screen`)

Facts (read in code 2026-10-25): rail = `structure5.RAIL` (5 dests) + `ui/shell.py` RAIL_OF/RAIL_PAGE/PAGES/NAV_ORDER;
pages added in `AI_Workbench._make_ui` (home, workbench, agents, prompt, response, profile, history, run, git,
settings); Projects page = `_make_projects_dashboard` (cards strip) + embedded Workbench (`workspace/shell.py`,
3 sections from `workspace/controller.SECTIONS`); App Map `ui/ui_map.py` extract/audit (RULES, GENERIC,
two_homes by label); tests tied to the rail: test_ui_map (also mobile section of UI_MAP.md = structure5.RAIL),
test_shell5, test_ui_tree; guide steps have keys title/explain/actions[label] and show agent ids
("Paste agent-core-dev's answer for TASK-0001 …"); status bar text = `ui/status5.summary` ("N agents running").

Plan (each step = many small checkpoints; tests green at the end of each step):
1. User words (B4): guide titles/explain/labels use the AI **name** (never `agent-…`), no `F\d+`, `wave`, `handoff`,
   `HO-`; status bar says what is true ("Waiting for <AI>'s answer" / "<AI>: prompt ready" / "Nothing waiting").
   New `tests/test_user_words.py` scans every guide step in the scripted runs of test_v2_guide + corpus scenario.
2. Mission Map carries milestones/versions: column header right-click menu (New milestone… / Accept milestone /
   Propose version… / Record release…) using the existing Workbench functions; Timeline tab of the Workbench removed.
3. History = one list with filter (All · Prompts · Answers · Events · Versions); Workbench events go there.
4. Rail = Home · Agents · History · Settings; Projects leaves the rail → project switcher in the toolbar (the project
   name becomes a menu button "<name> ▾": recent projects, All projects…, Reveal folder, Remove from list). The
   Workbench page stays only as the engine behind Home (not navigable); Project settings → Settings › Project;
   classic pages → Settings › Project › Classic tools (1.x)… (one window). Mobile section of UI_MAP follows RAIL
   (desktop-only change is allowed: mobile keeps its own list in a new `structure5.MOBILE_BAR`).
5. `ui/commands.py`: every command id + its labels (synonyms like Copy prompt / Prepare prompt for this task /
   COPY PROMPT); App Map audit: one home per command id, More ≤ 3 items, Home has no More; remove duplicates.
6. Gate smoke `gui_owner_path_smoke` extended: New Project → Charter → task → context request → files → answer →
   Accept → Milestone, only from Home, ≤ 14 clicks + pastes; screenshots `docs/audit/screens/v5.13-one-screen/`.
7. Fix all smokes/tests, UI_TREE.md, regen UI_MAP, docs, version 5.13.0, PR → CI → tag → Release.

Progress (tick = committed and pushed):

- [x] 1 user words: dispatch text 2a7fe49, guide `_in_user_words` at the source 52ea503, `tests/test_user_words.py` d3d6c0c (add to bump: --test test_user_words.py), status bar `status5.chats/summary` 3f353df (+ tests c8bcce2, 462768a, fb911d3, shell 61cfd12), Workbench phase line 4af65d3; unit 804 OK
- [x] 2 map columns: `ui/column_menu.py` 368b182, canvas `column_at`/`on_column_menu` 8e741fc, app `mission_column_rows/menu/pick` (+`mission_input_hook`) ae3a83a, `tests/test_column_menu.py` b7b5d55 (add to bump), Workbench SECTIONS=(plan, project) 06a0289, Timeline view removed 92650a9..01a30e8, smokes moved (timeline→History, workflow, workspace, menu column) 57d438c..a72f4d7
- [x] 3 one History: `ui/history_feed.py` f4c75c6/e4216df, History "Show" filter (All·Prompts·Answers·Saved·Events·Versions) replaces "Saved only" + events group 6de191f, show_history ceb9915, event details 80741ea, `tests/test_history_feed.py` 70c82a8 (add to bump), smoke b07b9f9; unit 814 OK
- [x] 4 rail of four + project switcher + Settings › Project — structure5 RAIL=4, MOBILE_BAR, PROJECT_MENU,
  CLASSIC 574cb21/a7cac63; UI_TREE 65ceb7f; shell RAIL_OF/RAIL_PAGE + alias projects→home 5834060, workbench→settings
  6db2836; toolbar switcher 93b8465; tests 7cf5809/e1cb430/e86c56a/1c4d5cb; tools card title f10ec49; "All projects"
  window 3c542db; switcher items/switch_project be9e738; Settings › Project + Classic tools 31f1e59/ceae17f; Run and
  Save profile stay on Home 7f27ce0/8d587a1; App Map e2ddf3f/855cbac/d6137ac; regen UI_MAP e103789..047995d; unit 814 OK.
  Smokes for four destinations: ia 7121cef, single_shell 21649c0/fb76411, polish 7732616/a1fc61e (switcher menu
  invoked), UI_MAP regen a32b457/28d9b79 (audit clean); unit 814 OK, GUI 47/47.
- [x] 5 commands.py + audit by command id, More ≤ 3, no More on Home — `aiwb/ui/commands.py` d4fc0e7 (+ a word of
  one job is that job everywhere a29e8fe); audit two_homes by id + `more_max_items`=3 + `home_more`=0 48f5dd7; Home ›
  Task details only tells (goal · done when) 2c9a1f3/f1073ad; Next-step card: other actions as buttons + "All open
  steps (N)" 845d2cf, ui_map frame `_aiwb_dynamic` 876d95e, smokes owner_path/paste_box 12eb9e0/3b9014c, guide
  e0ed8e5/9f0a281; Workbench Plan & Tasks without Copy prompt/Check & import f8c82d1/507fa7b; ActionBar `menus=` (named
  menus) 42f23db; Settings › Application = App Map… + Maintenance ▾ 50173ff/598e104; Git Local "Git for Windows ▾"
  57713d9; GitHub repos "Project binding ▾" 6e2d66e; tests test_next_card e8d56f1/dc72387, test_ui_actions a40173d,
  `tests/test_commands.py` 135eeb6/4231a5b (add to bump: --test test_commands.py), ia smoke 6620975; UI_MAP regen
  7daef66..638dd67 (audit clean); unit OK, GUI 47/47 (ia fixed after the run).
- [ ] 6 owner-path gate ≤ 14 clicks, screenshots — findings 2026-10-26 (explored with a copy of gui_owner_path_smoke, nothing committed): today's path = 11 clicks up
  to "Accept the delivery" (file on disk). After that, on Home: Review → Approve (12) → Verify → "Tests/build passed…"
  (13, needs run_id: opens an input dialog = Owner records it as a dialog → use the card's inline input or accept
  "I can't run tests — accept on review…" path with the inline field) → MS-0001 "Accept milestone Core ready" is in
  "All open steps" behind "Prepare the prompts for 2 tasks" (rank 39 < 75) → reach it via steps_menu (1 click) +
  "Accept the milestone" (1 click). Gate path still missing a context request: use fixture X03 shape
  (AIWB_CONTEXT_REQUEST for src/core/store.py) as the first answer → "Copy the files for the chat" → "I sent them" →
  paste real answer. Budget: 11 + context(2) + approve/verify(2) + milestone(2) = 17 > 14 → must cut: e.g. Accept the
  delivery also approves the review when validation is waived/recorded, or verification asked inline on the card.
  Decide, implement, then MAX_CLICKS=14 + screenshots docs/audit/screens/v5.13-one-screen/.
  DECISION (2026-10-26, run 2): 14 clicks = New ▾(1) Guided(2) Next(3) Next(4) Create(5, also copies the charter
  prompt, like Prepare in 5.11) Use(6 charter) Accept plan(7) Prepare+copy(8) Use(9 context request) Copy the
  files(10) Use(11 real answer; "I sent them" optional) Accept the delivery(12, also records the review approval —
  one judgement, not two) Tests/build passed(13, no run_id dialog: run id optional, auto manual-<time>) Accept the
  milestone(14, milestone rank 15: finish before starting new prompts). Sub-steps: a) guide accept_handoff approves
  b) validation_passed without needs c) milestone rank d) Create copies charter prompt e) smoke + MAX_CLICKS=14 +
  screenshots f) fix tests.
  DONE a 5f28484.. : a) a052329 b) 3128a9d c) 3c115b5 d) dd338ea e) smoke 5f28484 PASS 14 clicks (12 to the first
  file) + 3 pastes; screenshots bd86362..537464c (12 png). f) tests: next = unit run + GUI full run.
- [x] 7 RELEASED desktop-v5.13.0 (PR #69 merged a230eba, CI all green incl. Windows, release workflow success, payload checked: APP_VERSION 5.13.0 + launcher/installer C1 fix). NEXT: 5.14.0 Quick mode on branch feat/v5.14.0-quick. — unit 840 OK, GUI 47/47; bump (5 files, one per checkpoint, via
  /tmp/bump copy of tools/bump_desktop_release.py with --module ui/column_menu.py ui/commands.py ui/history_feed.py and
  --test test_column_menu/commands/history_feed/stale_bytecode/user_words) ..c12d66e; checklist 4e39659; CHANGELOG
  0de50af; USER_GUIDE 27f185b/a93a3af; README 0985334; ROADMAP ✅ 9c48612 → next: PR → CI → merge → tag desktop-v5.13.0

### Owner test of 5.12.0 on Windows (2026-10-26, 4 screenshots → docs/audit/owner-5.12/) — findings C1–C7
- C1 CRITICAL (root cause found): title/status say **5.11.0** after installing 5.12.0. The Setup.bat payload is right
  (APP_VERSION 5.12.0, checked by decoding the release asset), but every zip entry has the same date 2026-10-17 00:00
  and AI_Workbench.py / aiwb/__init__.py / github/api_client.py have the SAME SIZE in 5.11 and 5.12 (only a digit
  changed). Python validates `__pycache__/*.pyc` by source mtime+size → the 5.11 bytecode stays "valid" and keeps
  running (install.ps1 copies over the old dir and `compileall` does not recompile). The owner ran 5.11's main window
  with 5.12 modules: all his screenshots are of that mix. Fix: install.ps1 removes `__pycache__` (and old *.pyc) before
  copying + `compileall -f`; launch_aiwb.py compares AI_Workbench.APP_VERSION with aiwb.__version__ and, on mismatch,
  clears the caches and restarts once; test that both versions match after install (test_release_gate).
- C2 Home Next-step card: a blank blue square (the primary button with no text) + "More"; a faint "Full screen view"
  label floats inside the paste box. (5.11 main + 5.12 card mix and/or empty label when the step has no primary.)
- C3 Projects › Project settings › "Charter start prompts" (agent-architect + Copy start prompt): a template agent
  in a user-team project, old feature with no meaning for the owner → remove from settings (start prompts are built
  by the app on the card).
- C4 Projects › Timeline canvas: "project" lane label clipped, "0.0.0" label on the dot, empty sparse axis. 5.13.0
  drops the Timeline tab (milestones are on the map) → make sure the canvas is gone from the owner's path; if kept,
  fix label placement.
- C5 Agents › "Edit team…" alone in a strip under the cards (bad spacing); card "UI Developer" shows role
  "Implementer" (role text should be the user's description).
- C6 Agents › Balance: "Reviewer: TASK-0004 has been 'blocked' for 93 h" + "Apply suggested moves" with no moves
  listed → show the moves (or hide the button when there are none); "blocked" time should say what to do.
- C7 Settings › App Map…: the app "hangs", switches tabs and opens pages by itself, then a big tree window opens.
  This is ui_map.extract() walking every page to draw the map (developer audit tool, not for users). → move it out of
  Settings (keep it for tests / a hidden dev flag), or at least run without visibly switching pages + explain it.
Plan: C1–C7 are fixed in 5.13.0 step 6g–6m (before step 7 release), all before the mobile app.
Progress: 6f DONE (paste_box smoke accepts the milestone 32c41f8; unit 827 OK, GUI 47/47). C1 DONE: install.ps1
be4ba71, launch_aiwb.clear_stale_bytecode + `.aiwb_version` stamp 9b68dcc/c6e3a4b, tests/test_stale_bytecode.py
9a847ac (add to bump: --test test_stale_bytecode.py). C7 DONE: Settings button removed, Ctrl+Shift+F12 9c509ab, commands 04dc8e1, smokes ia 0d3de9c / map d742ef7,
UI_MAP regen e2ec420..ec3d7e2 (tools/ui_map.py header 5ef9001).
C3 DONE: Charter start prompts box removed 62b5ceb, charter smoke 0663842. C6 DONE: stuck alert says next step
(STUCK_NEXT, days ≥ 48 h) d91ff92/25615ee, Balance names AIs + Apply button only with moves a34238a/af25afb, smokes
agents 11df32d / ia f32e3dc, UI_MAP regen 6befad3/321a34b (ia/map/agents PASS). C5 DONE: card role =
team_setup.ROLE_LABEL ("Developer") b63dc34, Edit team… on the Team title row 22d1eda, tests test_agents_cards
b83c39f (C5+C6); smokes agents/ia/layout/map/team PASS. C2 DONE: next_btn not packed until refresh gives a
non-blank label d429f7f, widget tests test_next_card.CardWidgetTests cf86ea3; owner_path/paste_box/ia/map/layout PASS.
C4 DONE: Timeline tab already gone from the Workbench (step 2); the same canvas is History › Timeline, so its drawing
was fixed: lane = AI name (model `lane_names`) de516c1, names fit by pixel width with "…" 721b5b1, version label
"v0.1.0" above the lanes clear of dots + dated axis ends 4d1bb74, tests test_timeline_canvas 6a993a7, screenshot
docs/audit/screens/v5.13-one-screen/c4_timeline_fixed.png. C1–C7 ALL DONE → next: step 7 (full unit + GUI run,
docs, version 5.13.0, PR, CI, tag, Release).

## 5.12.0 (archive) — Real chat answers work (B1, B2, B8) (branch `feat/v5.12.0-real-answers`)

Owner tested 5.11.0 on real Windows + GPT (2026-10-25). Audit B1–B8 in ROADMAP §1b, evidence `docs/audit/owner-5.11/`.
The old Quick-mode plan (below, branch `feat/v5.12.0-quick-mode`, only a WORKLOG commit) moved to **5.14.0**.
Order now: 5.12 real answers → 5.13 one-screen redesign → 5.14 Quick → 5.15 gate → mobile.

Root causes (verified in code):
- B1: rendered-chat copy on Windows ends every line outside code fences with `\` (Markdown hard break) and escapes
  `_`; `intake/normalize.py` has no rule for it.
- B2: `intake/preview.py` says "Context request ✓" on the marker alone; `context_request.parse_request` needs
  `type` + `files` → GPT wrote `required_files`, no `type` (the task prompt never shows the format: only
  `handoff.py:335` "answer ONLY with an AIWB_CONTEXT_REQUEST"; `CAPABILITY_LINE` is only in the 1.x prompt).
  Even when parsed, `controller.route_answer` only notes an event and points to "Files & Context" (gone in 5.11);
  guide.steps has no step for it → card never changes.

Design:
1. `normalize.strip_copy_damage(text)` (new, in normalize()): outside ``` fences, if ≥60 % of non-empty lines end
   with `\` (or ` /`-free `/`?) → drop that one char; unescape `\_ \* \[ \] \# \-` outside fences; fix list
   reported (`copy_damage:N`). Applied before every parser (charter, files, context, handoff).
2. `WHOLE_ANSWER_RULE` (handoff.py) = "Write your WHOLE answer inside ONE code block fenced with five backticks
   (`````) and copy it with that block's Copy button" — added to task, charter, fix, continue, context prompts.
3. context_request: forgiving parse (`type` optional with marker; synonyms required_files/requested_files/
   files_needed/paths/context_files/file_requests; string item → full_file; folder path `x/` → files under it
   (cap MAX_ITEMS); key `file`/`filename` → path) + `fixes` list. Preview uses the real parser.
   Task prompt §7 gets the short exact format.
4. Guide: context request stored on the handoff (`context_request` {files, questions, fixes, at}); new step
   `context:<hid>` (agent = that AI): "<Name> asked for N file(s)" → actions copy_context (pack_inline, ZIP when
   big), sent, paste. Cleared on the next answer for that handoff. Controller message points to the card.
5. Tests: test_copy_damage.py, test_context_forgiving.py, test_context_step.py; corpus + owner answer (clean +
   backslash-damaged); smoke gui_context_smoke.py pasting via the real clipboard.
6. Docs/version 5.12.0, CHANGELOG, README, USER_GUIDE, install.ps1 + release_manifest, ROADMAP ✅, PR→CI→tag.

Progress (tick = committed and pushed):

- [x] 0 ROADMAP §1b + 5.12–5.15 table (b89cac5, 17482e0); evidence docs/audit/owner-5.11/ (c6948b5…e07ed42)
- [x] 1 strip_copy_damage + test (14fe114, 72d3791 never inside fences; test 7d86a7d; unit 782 OK)
- [x] 2 WHOLE_ANSWER_RULE (aeacabb handoff.build_prompt, 291f1ee Guide.perform wraps every prompt, 556bc6c shell do_copy/start prompt; test 413ca5e)
- [x] 3 forgiving context parser (48856a3, folders 7010d3a, damaged copy 61e1f74), preview = parser (e4781e6), prompt format (9a48fe2), tests 6b73668 35c849e, JSON comma+comment 546f8f7; unit 795 OK
- [x] 4 v2/context_step.py (9153a38), controller links request→handoff (9467def), guide step + copy_context/context_sent + clear on answer (ad512e0, 664d24b), card+shell copy (a78c4df, 9548633), test_context_step f93ec7a; unit 801 OK
- [x] 5 corpus F25 C31 X01-X04 (3432f2f builder, a1c392b replay kind context, 9a91f09…fc0f067 files, 4f9f3dd shape) 60 cases OK; gui_context_smoke.py 13fcb7a PASS; charter smoke expected the raw prompt (Copy now adds the answer rule) → 4941281; full GUI 47/47
- [x] 6 version bump (3e66b2c…9b033fc via tools/bump_desktop_release.py in /tmp copy, one file per checkpoint), checklist cc68083, CHANGELOG 2b86858, README 9724c98, USER_GUIDE 4fb08bc, gate "✓ preview ⇒ card moves" (0d0d05a, d6a9935), ROADMAP e74f362; unit 802 OK, GUI 47/47 → next: PR → CI → merge → tag desktop-v5.12.0

## 5.14.0 (planned, was 5.12.0) — Quick mode

Roadmap: New Project ▾ → "Quick — one AI chat": describe the work → prompt in the chosen format → paste text or ZIP →
preview/diff → transactional apply with Restore; same intake engine as 5.10.0; later "convert to a multi-AI project"
without losing files. Gate: full Quick smoke with the three formats; test Quick → Guided conversion.

Design (decided 2026-10-25, after reading the code):

1. New pure module `aiwb/quick.py` (no Tk): `QUICK_FORMATS` (aiwb/json/zip), `build_prompt(task, files, fmt, name,
   goal, contents)` (short 1.x-style prompt: task, project file list, selected file contents, the delivery rules of
   the format = `v2.handoff.FILE_RULES/JSON_RULES/ZIP_RULES` without the handoff manifest), `read_answer(text|zip)` →
   `aiwb.intake.answer_files.extract/zip_files` (all formats, fixes listed), `plan(root, files)` → per file
   new/changed/same + unified diff (no write), `apply(root, files, summary)` → `AI_Workbench.apply_changes_transactionally`
   is in the app module, so quick.py gets an `apply_fn` callback (the app passes its transactional apply → Restore
   Manager sees it). Quick state in `.workbench/quick.json` (mode, task history, format, rounds).
2. New `aiwb/ui/quick_window.py` — one page/window, 3 steps on one screen: (1) Describe the work + format radio +
   "Copy prompt" (2) PastePanel (live diagnosis, Load ZIP…) "Preview files" (3) file list with new/changed + diff
   view + "Apply" (+ "Restore last apply"). ≤ 8 controls in view.
3. Toolbar New Project ▾ gets "Quick — one AI chat…" (structure5 + UI_TREE): asks name + parent + goal (small form),
   creates the folder (`create_project_folder`), marks it quick, opens the Quick page. Home for a quick project:
   the card shows the Quick step (no Mission Map lanes needed) — decide in step 4.
4. "Convert to a multi-AI project…": opens the wizard in start mode (team + format), applies `team_setup.apply_start`;
   files on disk untouched; quick.json marked converted; Home then shows the guided card.
5. Tests: `test_quick.py` (prompt per format, read answers of the 3 formats + markdown + zip, plan/diff, apply +
   restore via apply_fn stub, conversion keeps files); smoke `gui_quick_smoke.py` (real widgets, 3 formats, Restore,
   convert → Guided card).
6. Docs: UI_TREE/structure5, UI_MAP regen, screenshots `docs/audit/screens/v5.12-quick/`, CHANGELOG, README, USER_GUIDE,
   install.ps1 + release_manifest (quick.py, ui/quick_window.py, test_quick.py), version 5.12.0, ROADMAP.

Progress (tick = committed and pushed):

- [ ] 1 aiwb/quick.py + test_quick.py
- [ ] 2 ui/quick_window.py
- [ ] 3 toolbar entry + create flow
- [ ] 4 Home for quick projects
- [ ] 5 convert to multi-AI
- [ ] 6 smoke gui_quick_smoke.py, full run green
- [ ] 7 docs, version, PR → CI → merge → tag → release

## 5.11.0 (archive) — Home = cockpit (branch `feat/v5.11.0-home-cockpit`)

Design (decided 2026-10-25):

1. `aiwb/ui/paste_box.py`: split out `PastePanel` (embeddable frame: Text + live diagnosis + Load ZIP… + Use this
   answer). `PasteBox` (the popup) wraps a `PastePanel`; its widgets and labels stay the same.
2. New `aiwb/ui/next_card.py`: `card_model(steps, names, focus)` (pure, unit-tested) + `NextStepCard` widget for
   Home › Next step: title (AI *name*, not id), explanation, primary button, More menu, and the **inline** paste panel
   whenever the step has an action that needs the answer text. Actions are performed through the embedded
   Workbench's `guide_action` (same code path as before); "Prepare the prompt" also copies it (one click less).
3. Home: the card replaces "Continue in Workbench"; Task details = [Open task in Workbench] + More (Jump to active
   task, Copy task summary, Copy map summary); Map view keeps its two options. Home ≤ 8 visible controls.
   The embedded Workbench is created in the background when a project is open, so Home always has the next step.
4. Mission Map: clicking an AI's hexagon/name focuses the card on that AI's own queue (its prompt/answer step);
   "Show the next step" returns to the overall next step.
5. Workbench: 7 sections → 3: **Plan & Tasks** (progress, attention, tasks, prompt/answer, plan review, queue,
   activity) · **Timeline** (events, milestones & versions — unchanged) · **Project settings** (project details →
   "Change the project details…", AI accounts, charter start prompts, files & tools links, phone/companion links).
   Old section keys (`overview`, `tasks`, `team`, `files`, `versions`) are aliases. Removed duplicates:
   "Design the whole project…", "Plan project…", "Plan team & tasks…", the Workbench's parallel-chats spinbox / Save
   team settings (home: Agents › Parallel chats…). The embedded Workbench's next-step strip only *points* to Home.
6. After New Project › Create the app shows **Home** (not the Workbench).
7. Audit rule `page_max_visible` 10 → 8 (the gate); fix every page that breaks it.
8. Tests: owner path driven only from Home + click count (≤ 12 + pastes); other smokes moved off `ws.next_btn`.
9. Docs: UI_TREE.md / structure5, UI_MAP.md + ui_map.png, owner-path screenshots `docs/audit/screens/v5.11-owner-path/`,
   CHANGELOG, README(s), USER_GUIDE, install.ps1 + release_manifest.json (`ui/next_card.py`), version 5.11.0.

Progress (tick = committed and pushed):

- [x] 1 PastePanel (ceee371)
- [x] 2 next_card.py + test_next_card.py (3196e07…0aae0cb)
- [x] 3/4 Home card, Task details More, lane click (acec763…95f168c, fix fb08e88; live path New→charter→accept→prompt→answer→file all from Home OK)
- [x] 5 Workbench 3 sections (8365dba controller, 56b7ea8 shell, 97bcea9 on_home, 3837ad2) — Projects now 8 visible; smokes using old keys/next_btn still to fix (step 8)
  - test run after steps 1-4,6 (d0ab492): unit 774 OK; GUI 42/46 — guide (fixed aa801f1), owner_path (expects
    Workbench after Create → rewrite to Home in step 8), v5_map (regen UI_MAP after step 5), v5_polish ("two homes":
    Approve/Cancel were step labels on the card → fixed by ui_map `_aiwb_dynamic` ab75324/48437ac)
- [x] 6 Create → Home (2f51d00)
- [x] 7 audit 8 visible (4f19485 Settings, a428564/c3a6f48/5579a8b Agents, c49a4cc History live filter, 3a3cf86 Run&Report, 0e3ee71 rule=8; audit [] ) — live audit at max 8 (before step 5): Projects 9, Projects › Tools › Run & Report 9,
  Agents 10, History 10, Settings 9 (Home 6). After step 5: Projects 8 ✓; left: Run & Report 9, Agents 10, History 10, Settings 9. Script: /tmp/stats.py = tools/ui_map.live_tree + ui_map.audit(rules)
- [x] 8 smokes updated, all green (3f34046 UI_MAP regen; full run: unit 775 OK, GUI 46/46) — done: guide, team_editor, wizard, charter, team_planner, single_shell, workspace, workflow_timeline, dashboard, test_workspace, paste_box (bb0d7ec, inline panel on Home); owner_path (6b43156: only Home, no popups, 11 clicks + 2 pastes ≤ 12); left: v5_map (regen UI_MAP), then full run
- [ ] 9 docs, version, PR → CI → merge → tag → release. Order (one file per checkpoint, as in 5.10.0): UI_TREE.md +
  structure5 check · owner-path screenshots docs/audit/screens/v5.11-owner-path/ · version 5.11.0 in AI_Workbench.py,
  aiwb/__init__.py, github/api_client.py · release_manifest.json (+ ui/next_card.py, test_next_card.py, checklist) ·
  install.ps1 (same) · docs/release/v5.11.0/WINDOWS_RELEASE_CHECKLIST_v5.11.0.md · CHANGELOG · README(s) · USER_GUIDE ·
  ROADMAP (5.11.0 ✅, 5.12.0 active)
  - done: structure5/UI_TREE (7f91f41, a60281b), version (9aaf907, 37038e6, 7ad39c9), checklist ddc2315, manifest
    f14aa4c, install.ps1 d02de57, CHANGELOG c021ea8, README 7890a85, USER_GUIDE 6e50725/fb6321a, copy message ca4482d,
    screenshots 2d95e71…69536a8, ROADMAP 3ecc846. **PR #67 opened** → wait for CI (Linux + Windows) → merge → tag
    `desktop-v5.11.0` (release-desktop.yml builds the Release on the tag)
  - CI run 1 (cf035eb): Linux/Android/contracts green; Windows 45/46 — owner_path final print hit cp1252 ('▾') →
    fixed 2af2242 (same encode/replace as paste_box); re-run all smokes locally with PYTHONIOENCODING=cp1252
