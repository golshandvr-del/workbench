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

## 5.11.0 — Home = cockpit (branch `feat/v5.11.0-home-cockpit`)

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
