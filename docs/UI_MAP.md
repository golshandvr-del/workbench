# App Map — every place and every command (roadmap 5.5.0)

Generated from the running application by `tools/ui_map.py` (Advanced mode, one sample project open).
**Do not edit the tree by hand:** change the UI, then run `xvfb-run -a python tools/ui_map.py`.
`test_ui_map.py` fails when this file and the live application differ; `test_ui_balance.py` applies the balance rules.

Kinds: `area` (Toolbar, Rail, Status bar) · `page` · `section` · `tab` · `button` · `menu` → `item` ·
`option` (choice control) · `link` (opens another page; the command lives there).

Picture: [`design/ui_map.png`](design/ui_map.png) (also in the app for developers: Ctrl+Shift+F12).

## Counts

| Page | Sections | Tabs | Commands | Visible at once | Links |
|---|---:|---:|---:|---:|---:|
| Home | 4 | 0 | 7 | 4 | 0 |
| Agents | 5 | 0 | 7 | 5 | 0 |
| History | 7 | 6 | 10 | 7 | 0 |
| History › Tools › Git / GitHub | 2 | 3 | 24 | 6 | 0 |
| Settings | 18 | 2 | 10 | 7 | 9 |
| Settings › Project › Project settings | 9 | 2 | 3 | 5 | 9 |
| Settings › Tools › Project Profile | 1 | 0 | 4 | 4 | 0 |
| Settings › Tools › Run & Report | 2 | 0 | 11 | 8 | 0 |

## Balance rules

- `page_min_commands` = 3
- `section_max_controls` = 7
- `page_max_visible` = 8
- `menu_max_items` = 12
- `weight_ratio_max` = 4.0
- `more_max_items` = 3
- `home_more` = 0

Audit:

- none: the map is balanced.

## Tree

<!-- ui-map:start -->
- Toolbar [area]
  - New Project [menu]
    - Guided project (recommended) [item]
    - Quick — one AI chat… [item]
    - Add existing folder… [item]
  - Open [button]
  - Save [button]
  - Run [button]
  - Project switcher [menu]
    - All projects… [item]
    - Reveal folder [item]
- Rail [area]
  - Home [page]
    - Mission Map [section]
      - Task menu [menu]
        - COPY PROMPT [item]
        - SEND PROMPT [item]
        - GET AI RESPONSE [item]
        - MARK AS DONE [item]
    - Map view [section]
      - Hide finished tasks [option]
      - Only AIs with open work [option]
    - Task details [section]
    - Next step [section]
      - Next action [button]
  - Agents [page]
    - Agents [section]
      - Team [section]
        - Edit team… [button]
      - Selected AI [section]
        - Copy briefing [button]
        - More [menu]
          - Memory note… [item]
      - Balance [section]
      - Dispatch desk [section]
        - Prepare all prompts [button]
        - More [menu]
          - Parallel chats… [item]
          - Copy team summary [item]
          - Open task queue [item]
  - History [page]
    - Timeline [section]
    - Project versions… [button]
    - More [menu]
      - Refresh [item]
      - Report error… [item]
    - Filter [section]
      - Clear [button]
    - Selected step [section]
      - More [menu]
        - Copy model output [item]
        - Edit prompt as new revision… [item]
        - Create repair prompt from this step [item]
      - Copy prompt [button]
    - Editable entry metadata [section]
      - Save metadata / notes [button]
      - More [menu]
        - Delete selected entry… [item]
    - Generated prompt [tab]
    - Model output [tab]
    - Errors / context requests [tab]
    - Tools [section]
      - Git / GitHub [page]
        - Local Git [tab]
          - Refresh Git status / project history [button]
          - Commit changes… [button]
          - Push to GitHub… [button]
          - Review & Sync… [button]
          - More [menu]
            - Create work branch [item]
          - Git for Windows [menu]
            - Check Git [item]
            - Install Git [item]
            - Update Git [item]
        - GitHub repositories [tab]
          - GitHub Repository Browser · Project Binding [section]
            - Project binding [menu]
              - Initialize & Link Local… [item]
              - Initial Push Review… [item]
              - Binding Settings… [item]
              - Refresh Binding Metadata [item]
              - Unlink Project [item]
            - More [menu]
              - Open on GitHub [item]
              - Build Center… [item]
            - Sync & Build… [button]
            - Clone Selected… [button]
            - Link to Active Project… [button]
            - Refresh Repositories [button]
        - GitHub accounts [tab]
          - GitHub Accounts · REST API [section]
            - More [menu]
              - Replace Credential… [item]
              - Disconnect [item]
            - Refresh Accounts [button]
            - Test Connection [button]
            - Add PAT… [button]
  - Settings [page]
    - Appearance [section]
      - Light [option]
      - Dark [option]
    - Experience [section]
      - Simple [option]
      - Advanced [option]
    - Application [section]
      - Maintenance [menu]
        - Restore Manager… [item]
        - Validation Profiles… [item]
        - Export redacted diagnostics… [item]
        - Open application data folder [item]
    - Motion [section]
      - Reduce motion [option]
    - Project [section]
      - Project settings… [button]
      - Project settings [page]
        - Next step [section]
          - Open on Home [link]
        - Plan & Tasks [tab]
          - Needs your attention [section]
          - Tasks [section]
          - Queue of each AI (double-click a step to do it) [section]
          - Recent activity [section]
        - Project settings [tab]
          - Project details [section]
          - AI team [section]
            - needs action only [option]
          - Your account profiles (labels only — no passwords or keys) [section]
            - Add account profile… [button]
            - More [menu]
              - Enable / disable selected [item]
          - Files, builds and the phone [section]
            - Project tools [menu]
              - Response Inbox… [link]
              - Context request… [link]
              - Build Center… [link]
              - Sync & Build… [link]
              - Export project for the phone… [link]
              - Import project from the phone… [link]
              - Mobile Companion… [link]
              - Projects window (classic)… [link]
    - Tools [section]
      - Project Profile [page]
        - Architecture plan… [button]
        - Static dependency graph… [button]
        - Additional constraints and acceptance criteria [section]
        - Save profile [button]
        - Restore defaults [button]
      - Run & Report [page]
        - Run command… [button]
        - Run a project file / simulate a circuit [section]
          - Browse… [button]
          - Run / simulate selected file… [button]
        - Model-proposed action queue [section]
          - Run all pending… [button]
          - Build continuation handoff… [button]
          - More [menu]
            - Run selected / retry… [item]
            - Remove selected [item]
            - Repair prompt from latest failure… [item]
        - More [menu]
          - Refresh report [item]
          - Save report… [item]
        - Copy report [button]
- Status bar [area]
  - Agents running [item]
  - Milestone [item]
  - Autosaved [item]
<!-- ui-map:end -->

## Mobile (Android, roadmap 6.0.0–6.1.0)

The phone uses the same five destinations as the desktop rail (bottom bar, `core/Shell5.kt`) and the same four-item
task menu (long press on a Mission Map circle, `core/TaskMenu.kt`). `test_ui_map.py` checks this section against
`structure5`; the Kotlin tests `Shell5Test` / `TaskMenuTest` check the app against the same lists.

<!-- ui-map-mobile:start -->
- Bottom bar [area]
  - Home [page]
    - Mission [section]
  - Projects [page]
    - Your projects [section]
    - Project [section]
      - Next step [section]
      - Mission Map [section]
        - Task menu [menu]
          - COPY PROMPT [item]
          - SEND PROMPT [item]
          - GET AI RESPONSE [item]
          - MARK AS DONE [item]
      - Timeline [section]
  - Agents [page]
    - Desktop companion [section]
  - History [page]
    - Releases [section]
  - Settings [page]
    - Appearance [section]
    - Build [section]
<!-- ui-map-mobile:end -->
