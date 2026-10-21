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
- Rail
  - Home
    - Mission Map
    - Task details
    - Your projects
  - Projects
    - Project cards
    - Project Workbench
    - Tools
      - Project Profile
      - Run & Report
  - Agents
    - Team
    - Dispatch desk
    - Tools
      - Prompt
      - AI Response
  - History
    - Timeline
    - Prompts & responses
    - Versions
    - Tools
      - Git / GitHub
  - Settings
    - Appearance
    - Experience
    - Motion
    - Application
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
| **Home › Mission Map** | Parallel timelines: one lane per AI, one circle per task in its version's column. |
| **Home › Task details / Your projects** | The clicked task (with a link into the Workbench) · every project as a list to open. |
| **Projects** | Every project as a card; the Project Workbench of the open project; its profile and run report. |
| **Agents** | The team, the dispatch desk (who gets a prompt now); the manual prompt and AI-response tools. |
| **History** | Everything that happened, on a timeline; old prompts/responses; versions, releases and Git. |
| **Settings** | Theme (Midnight / Daylight), Simple/Advanced, Motion (Reduce motion); application tools; **App Map…** (the live map of every page, section and command — `docs/UI_MAP.md`). |
| **Task menu** | Right-click on a task circle. An item is enabled only when the Guide allows it now. |
| **Status bar** | How many AIs are working, the current milestone, and whether the state is saved. |
