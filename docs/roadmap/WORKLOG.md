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
- [ ] 4 rail of four + project switcher + Settings › Project — done so far: structure5 RAIL=4, MOBILE_BAR, PROJECT_MENU,
  CLASSIC 574cb21/a7cac63; UI_TREE 65ceb7f; shell RAIL_OF/RAIL_PAGE + alias projects→home 5834060, workbench→settings
  6db2836; toolbar switcher 93b8465; tests 7cf5809/e1cb430/e86c56a/1c4d5cb; tools card title f10ec49; "All projects"
  window 3c542db; switcher items/switch_project be9e738; Settings › Project + Classic tools 31f1e59/ceae17f; Run and
  Save profile stay on Home 7f27ce0/8d587a1; App Map e2ddf3f/855cbac/d6137ac; regen UI_MAP e103789..047995d; unit 814 OK.
  Left: GUI smokes fixed for the four-item rail, then tick.
- [ ] 5 commands.py + audit by command id, More ≤ 3, no More on Home
- [ ] 6 owner-path gate ≤ 14 clicks, screenshots
- [ ] 7 tests/docs/version/PR/CI/tag/Release

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
