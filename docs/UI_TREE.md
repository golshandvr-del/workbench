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
kept in `docs/specs/UI_TREE.md`; in 5.x those pages are reached from **Agents › Tools**.

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
    - AI Assistant
  - Projects
    - Project cards
    - Project Workbench
  - Agents
    - Team
    - Dispatch desk
    - Tools
      - Prompt
      - AI Response
      - Project Profile
      - Run & Report
      - Git / GitHub
  - History
    - Timeline
    - Prompts & responses
    - Versions
  - Settings
    - Appearance
    - Experience
    - Application
- Task menu
  - COPY PROMPT
  - SEND PROMPT
  - GET AI RESPONSE
  - MARK AS DONE
- Assistant menu
  - Copy status
  - Clear notes
  - Hide panel
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
| **Home › AI Assistant** | Plain-language status and next step, built locally; notes for the project manager. |
| **Projects** | Every project as a card; the Project Workbench of the open project. |
| **Agents** | The team, the dispatch desk (who gets a prompt now) and the expert tools. |
| **History** | Everything that happened, on a timeline; old prompts/responses; versions and releases. |
| **Settings** | Theme (Midnight / Daylight), Simple/Advanced and reduce motion; application tools. |
| **Task menu** | Right-click on a task circle. An item is enabled only when the Guide allows it now. |
| **Assistant menu** | The ⋯ button of the assistant panel. |
| **Status bar** | How many AIs are working, the current milestone, and whether the state is saved. |
