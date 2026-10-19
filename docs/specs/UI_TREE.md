# AI Workbench — UI tree (desktop 3.3.0)

Owner request (2026-10-19): *"the AI tab is strange and full of buttons — know exactly, as a tree, which tabs
the user sees when the app opens, what each tab opens, and what each section shows; then tidy it."*

## Rules (enforced by `apps/desktop/tests/gui/gui_ia_smoke.py`)

1. **Rail = pages.** The left rail is the only top-level navigation. Simple mode shows Home, Project Workbench,
   Prompt, AI Response, Settings; Advanced adds Project Profile, History, Run & Report, Git / GitHub.
2. **Each action bar shows at most 4 primary buttons**; everything else is in one grouped **More ▾** menu
   (`aiwb/ui/actions.py`, `ActionBar`). Group headers inside the menu say *when* to use the command
   (e.g. "If something went wrong", "After applying").
3. **Each page/sub-tab shows at most 10 action buttons** in total (navigation entries excluded).
4. **No duplicates of rail pages** inside a page (the old "Project Workbench…" button on AI Response is gone;
   Mobile Companion lives only in Settings › Application).
5. **Nothing removed.** Every command of 3.2.0 is still reachable (the Gate lists them all).
6. Big pages are split into **sub-tabs** (Git / GitHub → Local Git · GitHub repositories · GitHub accounts).
7. English-only UI: the Language card is hidden in Settings.

## Before → after (visible action buttons)

| Page | 3.2.0 | 3.3.0 |
|---|---|---|
| Home | 5 | 3 + More |
| Prompt | 14 | 3 + 2 More + quick-instruction menu |
| **AI Response** | **17** | **3 + More** (12 commands in 4 groups) |
| History | 12 | 7 + 3 More |
| Run & Report | 11 | 7 + 2 More |
| **Git / GitHub** | **24 on one page** | 3 sub-tabs: 4 + More · 4 + More · 3 + More |
| Settings | 11 | theme + mode + 2 + More |

## What the user sees — page → section → button → menu item

Legend: `[Button]`, `( ) option`, `**section / sub-tab**`, `· menu item` (inside the More ▾ menu above it).

## ⌂ Home
- [+ New project]
- [Open selected]
- [Add existing folder…]
- [More ▾]
    · Reveal folder
    · Remove from list

## ◈ Project Workbench
- [☰]
- [ⓘ]
- [Do it]
- [Overview]
- [Timeline]
- [Tasks]
- [Team]
- [Files & Context]
- [Versions & Builds]
- [Settings]
- **Needs your attention**
- **Recent activity**
- [Plan project…]

## ✎ Prompt
- [Select recommended context]
- [More ▾]
    · Why these files?
    · Select all
    · Clear
- ( ) Include project history in this prompt
- [Build prompt]
- [Copy prompt]
- [More ▾]
    · Save prompt…
    · Add history to prompt
- [Add quick instruction ▾]
    · Prioritize quality
    · Ask before risky assumptions
    · Windows-first delivery
    · Keep dependencies justified
    · Tests and evidence
    · Professional GUI
    · Preserve unrelated behavior
    · Security review
    · Update documentation
    · Handle edge cases
    · Manage custom instructions…

## ⇩ AI Response
- [Paste & detect format]
- [Load response / ZIP…]
- [Analyze / preview files…]
- [More ▾]
    · Import diagnostics…
    · Response Inbox…
    · Context request…
    · Import context plan / select requested files
    · Save response candidate…
    · Compare candidates / choose files…
    · Import architecture plan…
    · Save validated prompt + output to history
    · Mark Verified… (manual review)
    · Report manual runtime / test error…
    · Refresh workflow
    · Projects (multi-agent)…

## ☰ Project Profile  *(Advanced)*
- [Architecture plan…]
- [Static dependency graph…]
- **Additional constraints and acceptance criteria**
- [Restore defaults]
- [Save profile]

## ↺ History  *(Advanced)*
- [Project versions…]
- [More ▾]
    · Refresh
    · Report error…
- [Search]
- [Clear]
- ( ) Saved only
- **Editable entry metadata**
  - [Save metadata / notes]
  - [More ▾]
      · Delete selected entry…
- tab: **Generated prompt**
- tab: **Model output**
- tab: **Errors / context requests**
- [Copy prompt]
- [More ▾]
    · Edit prompt as new revision…
    · Create repair prompt from this step
- [Copy model output]

## ▶ Run & Report  *(Advanced)*
- [Run…]
- **Run a project file / simulate a circuit**
  - [Browse…]
  - [Run / simulate selected file…]
- **Model-proposed action queue**
  - [Run selected / retry…]
  - [Run all pending…]
  - [More ▾]
      · Remove selected
      · Repair prompt from latest failure…
  - [Build continuation handoff…]
- [More ▾]
    · Refresh report
    · Save report…
- [Copy report]

## ⑂ Git / GitHub  *(Advanced)*
- sub-tab: **Local Git**
  - [Refresh Git status / project history]
  - [Commit changes…]
  - [Push to GitHub…]
  - [Review & Sync…]
  - [More ▾]
      · Create work branch
      · Check Git
      · Install Git
      · Update Git
- sub-tab: **GitHub repositories**
  - **GitHub Repository Browser · Project Binding**
    - [Refresh Repositories]
    - [Clone Selected…]
    - [Sync & Build…]
    - [More ▾]
        · Open on GitHub
        · Initialize & Link Local…
        · Initial Push Review…
        · Binding Settings…
        · Refresh Binding Metadata
        · Unlink Project
        · Build Center…
    - [Link to Active Project…]
- sub-tab: **GitHub accounts**
  - **GitHub Accounts · REST API**
    - [Test Connection]
    - [Refresh Accounts]
    - [More ▾]
        · Replace Credential…
        · Disconnect
    - [Add PAT…]

## ⚙ Settings
- ( ) Light
- ( ) Dark
- ( ) Simple
- ( ) Advanced
- [Mobile Companion…]
- [Restore Manager…]
- [More ▾]
    · Validation Profiles…
    · Export redacted diagnostics…
    · Open application data folder

