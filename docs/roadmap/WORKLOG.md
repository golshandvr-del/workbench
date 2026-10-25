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
- [ ] 5 Workbench 3 sections
- [x] 6 Create → Home (2f51d00)
- [ ] 7 audit 8 visible
- [ ] 8 smokes updated, all green
- [ ] 9 docs, version, PR → CI → merge → tag → release
