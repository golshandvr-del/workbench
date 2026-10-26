# AI Workbench — UI tree (desktop 5.x, "Mission Map")

This file is the **map of every place and command** the user can see: rail destinations, sections, toolbar commands,
menus and menu items. It keeps the hierarchy meaningful so the app never becomes a confusing pile of buttons.

## Project rule (contract)

1. **Every** added, removed, renamed or moved tab, rail destination, section, toolbar button, menu or menu item is
   recorded **in this file, in the same pull request**.
2. `apps/desktop/tests/test_ui_tree.py` parses the tree below and compares it with the code
   (`apps/desktop/src/aiwb/ui/structure5.py`, which the shell, the Mission Map and the menus are built from).
   Any difference turns CI red.
3. A node has **at most 7 direct children** (Miller's rule). If a list grows beyond that, group it.
4. Every command has **one home**. Other places may *link* to it, but never duplicate it.
5. Labels are short, English (product language policy), and say what happens — not how it is implemented.

The 3.x/4.x tree (pages Prompt, AI Response, Project Profile, Run & Report, Git / GitHub with all their buttons) is
kept in `docs/specs/UI_TREE.md`; in 5.x each of those pages is reached from the **Tools** section of the destination
it belongs to (5.5.0): talking to an AI → **Agents › Tools**; describing and running the project → **Projects › Tools**;
commits, pushes and releases → **History › Tools**.

The *complete* live tree — every section, tab, button and menu item of every page — is `docs/UI_MAP.md` (App Map).

## The tree

Only the lines between the two markers are parsed. Indentation is two spaces per level.

<!-- ui-tree:start -->
- Toolbar
  - New Project
    - Guided project (recommended)
    - Add existing folder…
  - Open
  - Save
  - Run
  - Project switcher
    - Recent projects
    - All projects…
    - Reveal folder
- Rail
  - Home
    - Next step
    - Mission Map
    - Task details
  - Agents
    - Team
    - Selected AI
    - Balance
    - Dispatch desk
  - History
    - Timeline
    - One list
    - Selected step
    - Tools
      - Git / GitHub
  - Settings
    - Appearance
    - Experience
    - Motion
    - Application
    - Project
    - Classic tools (1.x)
      - Prompt
      - AI Response
      - Project Profile
      - Run & Report
- Task menu
  - COPY PROMPT
  - SEND PROMPT
  - GET AI RESPONSE
  - MARK AS DONE
- Status bar
  - Agents running
  - Milestone
  - Autosaved
<!-- ui-tree:end -->

## What each part means

| Node | Meaning |
|---|---|
| **Toolbar › New Project** | Start a new guided project (the owner's algorithm, F1) or add a folder that already exists. |
| **Toolbar › Open / Save / Run** | Open a project folder · save the project state now · do the Guide's next step. |
| **Home › Next step** | The cockpit card (5.11.0): the project's next step with its own buttons (primary + More) and, whenever the step takes an answer, the paste panel inside the page (live diagnosis, Load ZIP…, Use this answer). Clicking an AI on the Mission Map shows that AI's own prompt/answer step here. |
| **Home › Mission Map** | Parallel timelines: one lane per AI, one circle per task in its version's column. |
| **Home › Task details / Your projects** | The clicked task (with a link into the Workbench) · every project as a list to open. |
| **Projects** | Every project as a card; the Project Workbench of the open project — three sections since 5.11.0: **Plan & Tasks** (progress, attention, plan review, tasks, each AI's queue, activity) · **Timeline** · **Project settings** (details, AI team, account profiles, one *Project tools* menu of links); its next-step strip only links to Home. Its profile and run report. |
| **Agents** | One card per AI (number = Mission Map lane, role, live state, current task, load, stats); the selected AI (queue, memory note, briefing for a fresh chat); balance (idle / stuck / overloaded / scope-overlap alerts, suggested moves); the dispatch desk (who gets a prompt now); the manual prompt and AI-response tools. |
| **History** | Everything that happened, on a timeline; old prompts/responses; versions, releases and Git. |
| **Settings** | Theme (Midnight / Daylight), Simple/Advanced, Motion (Reduce motion); application tools; **App Map…** (the live map of every page, section and command — `docs/UI_MAP.md`). |
| **Task menu** | Right-click on a task circle. An item is enabled only when the Guide allows it now. |
| **Status bar** | How many AIs are working, the current milestone, and whether the state is saved. |
