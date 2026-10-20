## [4.2.0] - 2026-10-20
### Smart output check and troubleshooting prompt (Roadmap 4.2.0, flowchart F13–F15)
- `v2/diagnose.py`: smart check of every pasted delivery (truncated, no_manifest, wrong_attempt, unsafe_path,
  out_of_scope, empty_file, missing_deliverable, failed_outcome, copy_damage, unverified_test_claim).
- Guide: **Build the troubleshooting prompt** (only the problems found, at most 3), then **Ask the project manager**
  (task blocked, `task_escalated` on the timeline).
- Shared corpus `packages/contracts/fixtures/diagnose/diagnose-corpus.v1.json`; `tests/test_diagnose.py`.

## [4.1.0] - 2026-10-20

### Parallel paths and the dispatch desk (Roadmap 4.1.0, flowchart F9–F12)
- `v2/waves.py`: lanes per AI, dependency waves (cycles / dead prerequisites reported) and the dispatch desk.
- Guide: start steps only for the current wave within `max_parallel_chats`, spread over the AI lanes first;
  **Prepare all prompts** makes one handoff per task of the wave.
- Phase bar: open chats / limit and waves left.
- `tests/test_waves.py`.

## [4.0.0] - 2026-10-20

### Owner's algorithm, nodes F1–F8 (Roadmap 4.x, step 4.0.0)
- Shared contract `project-flow.v1` (schema + fixture): the owner's flowchart as nodes F1–F28
  (kind app / user / github), phases and edges. Desktop and phone check the same fixture.
- `v2/flow.py`: `current(state)` derives the flowchart node from the saved state; `start_project` saves the brief
  and writes `project_started` (F2).
- Guide: **Start the project** form — name, goal, platform, constraints, number of AIs (F4); the Project Charter
  prompt includes the name and brief (F5).
- Workspace: phase bar under the next step; cancelling an optional field skips it.
- `tests/test_flow.py`.

## [3.9.1] - 2026-10-20

### Guided loop fixes (same as mobile 1.0.1)
- Verify step: *Tests/build passed…*, *Tests/build failed…* and *I can't run tests — accept on review…*
  (`waive_validation`: policy `manual_review`, `validation_waiver` with `result: not_run`, a NOT RUN flag and a
  `validation_waived` event; never test/build evidence). `record_validation` accepts ok/yes/pass/fail words.
- Handoff and repair prompts ask for four-backtick fences around every file (chat copies lose indentation and
  backticks outside code blocks).
- `tests/test_verify_step.py`.

## [3.9.0] - 2026-10-19

### Product Release Gate (Roadmap 3.x, Gate 3.9.0)
- `tests/test_release_gate.py`: one end-to-end run — a dirty chat copy of the Project Charter is normalised and
  imported, the guided loop alone takes three AIs to two released versions without a dead end, the project goes
  desktop → phone → desktop as `aiwb-bundle.v1` (plans `new` then `same`), the Kotlin-produced bundle is accepted,
  and open / guide / export stay inside performance budgets.
- `tools/gui_screenshots_3x.py` and `docs/audit/screens/v3.9.0/`: after-screenshots of every rail page and every
  Workbench view in light and dark (before: `docs/audit/screens/v2.6.0/`).
- `docs/USER_GUIDE.md`: English user guide for desktop and phone.
- `docs/release/v3.9.0/RELEASE_GATE_v3.9.0.md`: every 3.x gate, measured performance, explicit NOT RUN list.

### Validation
- Performance (Linux CI-class machine): main window 545 ms, open 200 tasks / 2000 events 155 ms, payload 2.51 MB.
- NOT RUN: physical Windows DPI scaling, real chat models, a physical phone.

## [3.8.0] - 2026-10-19

### Project bundles between desktop and phone (Roadmap 3.x, Gate mobile 1.0.0 + 3.8.0)
- New `aiwb/v2/bundle.py` (`aiwb-bundle.v1`): export the whole project document as one file with a SHA-256 of the
  exact state text, read it back (damage, tampering and newer schema versions are refused), plan the import and
  import it. A bundle is never merged: the plan says *new*, *same*, *newer*, *older* or *diverged*; only *new* and
  *newer* are applied directly, *older*/*diverged* need an explicit replace, and a backup is always written first.
- Settings → *Export project bundle* / *Import project bundle*.
- AI Workbench Mobile 1.0.0 opens the same bundles and can run the whole guided loop on the phone.

### Validation
- `test_bundle.py`: round-trip, byte-identical re-export, every plan kind, damage/tamper refusal, backup before
  replace, and import of the bundle produced by the Kotlin core (`fixtures/bundle/todo.mobile.aiwb-bundle.json`).
- NOT RUN: moving a bundle between a real Windows PC and a physical phone.

## [3.7.0] - 2026-10-19

### Pairing with QR (Roadmap 3.x, Gate 3.7.0 + mobile 0.4.0)
- New `aiwb/ui/qr.py`: a pure-Python QR Code encoder (ISO/IEC 18004 byte mode, versions 1-10, levels L/M/Q/H,
  all 8 masks with penalty scoring) drawn on a Tk Canvas - no PIL, no third-party code. The code is always black
  on white, also in the dark theme, so phone cameras can read it.
- New `aiwb/companion/pairing.py` (pairing code v2): one 80-bit secret shown as a QR / deep link
  `aiwb://pair?h=<ipv4>&p=<port>&k=<code>` and as a 16-character Base32 manual code `ABCD-EFGH-IJKL-MNOP`.
  The envelope key and the pairing id are derived from the secret with HMAC-SHA256, so the code never travels.
- Pairing is valid 10 minutes, single use, and is cancelled after 5 failed attempts (wrong code or forged
  envelope); the window shows a countdown and the lockout.
- Mobile Companion window: QR code, manual code, desktop address, *Copy link*.
- Breaking: the old `aiwb1:` pairing codes are replaced; pair phones with AI Workbench Mobile 0.4.0.

### Validation
- `test_qr_pairing.py`: Reed-Solomon reference vector, structure, version selection, every version 1-10 x level
  x mask decoded by the reference decoder zbar (required on CI Linux via `AIWB_REQUIRE_QR_DECODER=1`), shared
  `companion-pairing.v2` vectors, 5-attempt lockout, expiry.
- `gui_companion_smoke.py`: QR drawn and manual code shown; pairing over the real LAN endpoint with the v2 code.
- NOT RUN: scanning the code with a physical phone.

## [3.6.0] - 2026-10-19

### Visual timeline (Roadmap 3.x, Gate 3.6.0)
- New `aiwb/ui/timeline_canvas.py`: a horizontal time axis with one lane per AI (plus "project"). Every
  ledger event is a circle whose size and colour show its importance (minor / normal / major / critical;
  an explicit `payload.importance` wins). Every version is a vertical line — dashed while proposed /
  local / tagged, solid once released (drawn at its release time); withdrawn versions are hidden.
- Zoom (mouse wheel or +/-, anchored at the cursor), pan (drag or arrow keys), tooltip on hover, click →
  the event opens in the Inspector and is revealed in the event list.
- Legacy events without a timestamp keep their order (they take the time of the neighbouring event).
- Uses the Workbench theme tokens, so light and dark both work. English only.
- Project Workbench → Timeline shows the canvas above the filterable event list.

### Validation
- `test_timeline_canvas.py`: importance levels, circle sizes, lanes, version lines (solid / dashed /
  hidden), undated events, empty project.
- `gui_timeline_smoke.py`: 2000 events redraw in < 300 ms (median ~45 ms on CI-class Linux), circle size
  per importance, solid vs dashed version line, dark palette, zoom/pan, click → Inspector.
- NOT RUN: physical Windows at 125/150/200 % DPI.

## [3.5.0] - 2026-10-19

### Guided loop without dead ends (Roadmap 3.x, Gate 3.5.0)
- New `aiwb/v2/guide.py`: for every project state a list of *steps* — title, plain explanation, whose chat it
  belongs to, the ready prompt (if any) and the actions that move the project on. The guide only calls the
  existing services; it adds no state machine of its own and never sends anything to a model.
- Covered states: empty project (describe the goal → Project Charter prompt), pending plans, open decisions,
  prompts not copied / copied but not sent / sent and waiting for the answer, deliveries to check (with
  *Ask only for what is missing* for partial deliveries), stale answers, reviews, validation (real result with
  run ID), blocked / waiting-for-decision tasks, drafts, milestones whose tasks are done, versions whose
  milestones are accepted (release with commit, tag and run), and — when nothing else waits — the manager update.
- Automatic prompts: **Manager Update / Continue** (asks the project manager for the next step), **Review**
  (a reviewer AI checks a delivery against the acceptance criteria — advice only), **Repair** (only the missing
  items, named with the fresh attempt) and **Continue** (a cut-off pasted answer).
- "Copied" and "I sent it" are one click each and are recorded (attempt workflow / manager-seen revision).
- Project Workbench: the Next-step strip shows the first step with its explanation, one primary button and a
  More menu for the other actions; Overview lists the **queue of each AI** (double-click runs the step).
- Home: a **Next step** card for the active project.

### Validation
- `test_v2_guide.py`: no-dead-end invariant checked in every state reached (every step has exactly one primary
  action; prompt steps carry their prompt); edge states (blocked, needs decision, cancelled-only, cut-off answer,
  incomplete charter); scripted E2E from idea to two released versions with three AIs, two of them working in
  parallel, including a cut-off answer and a partial delivery repaired by a focused prompt.
- `gui_guide_smoke.py`.
- NOT RUN: real ChatGPT/Gemini/Claude chats; physical Windows.

## [3.4.0] - 2026-10-19

### Project Charter (Roadmap 3.x, Gate 3.4.0)
- New `aiwb/v2/charter.py` and contract `project-charter.v1` (schema + valid/invalid fixtures).
- Project Workbench › Overview › **Design the whole project…**: one prompt asks the project-manager chat for the
  architecture and modules, how many AI chats work in parallel and why (plus a simpler alternative), the coordination
  protocol (file/path ownership, shared contracts, sync points, conflict resolution), a roadmap of milestones with
  versions, the tasks of every AI and a start prompt for every AI.
- The answer (`AIWB_PROJECT_CHARTER` block) is read raw first and through the 3.2.0 chat-copy normalizer as a fallback.
  Every required part is checked with a precise message (e.g. `tasks[1].owner_agent_id: agent-x is not in team.agents`,
  overlapping file ownership, dependency cycles, versions that do not grow). An incomplete or cut-off charter is
  refused, nothing changes, and a ready fix prompt is shown.
- A valid charter is imported once as an ordinary proposal and reviewed per operation: agents (`create_agent`), tasks
  (`create_task` with dependencies), milestones with a proposed version (new `create_milestone` operation). Only
  accepted tasks are linked to milestones. The charter (architecture, coordination, start prompts) is kept in the
  project state after acceptance.
- Team view: **Copy start prompt** for each AI, framed with its owned paths, shared contracts, sync points and tasks.

### Validation
- `test_v2_charter.py` (prompt asks for every section; each missing section named; precise errors; chat-copy damage
  repaired; cut-off detected; fix prompt; full import → agents/tasks/milestones/versions; partial acceptance; rejection
  changes nothing). `gui_charter_smoke.py`. `tools/validate_contracts.py` checks that schema and code agree on fixtures.
- NOT RUN: a real ChatGPT/Gemini/Claude chat answering the charter prompt; physical Windows.

## [3.3.0] - 2026-10-19

### UI information architecture (Roadmap 3.x, Gate 3.3.0 — owner request)
- New `aiwb/ui/actions.py`: `ActionBar` shows at most 4 primary buttons; every other command lives in one
  grouped **More** menu whose group headers say when to use it. Menu commands keep a button-compatible handle,
  so enable/disable logic is unchanged.
- **AI Response:** 17 buttons → Paste & detect format · Load response / ZIP… · Analyze / preview files… + More
  (If something went wrong · Several answers · After applying · Multi-agent). The duplicate "Project Workbench…"
  and "Mobile Companion…" buttons are gone (they are a rail page / a Settings item).
- **Git / GitHub:** one 24-button page → three sub-tabs: Local Git, GitHub repositories, GitHub accounts.
- **Prompt, History, Run & Report, Home, Settings:** every toolbar uses the same 4 + More pattern;
  quick instructions are one menu.
- Settings: the Language card is hidden (English-only policy).
- `docs/specs/UI_TREE.md`: the full page → section → button → menu tree, generated from the running app.

### Validation
- `gui_ia_smoke.py` (Gate 3.3.0): every page ≤ 10 visible action buttons, every bar ≤ 4 primary + More,
  every 3.2.0 command still reachable, no duplicates of rail pages. `test_ui_actions.py`.
- NOT RUN: physical Windows at 125/150 % DPI.

## [3.2.0] - 2026-10-19
### Reliable intake of model output (Roadmap 3.x, Gate 3.2.0, problem P7)
- New `aiwb/intake/normalize.py`, used as a fallback before every parser (raw text is always tried first, so an answer that parsed before can never be broken): BOM, NBSP, zero-width characters, CR/CRLF; smart quotes, Markdown escapes (`\<\<\<AIWB\_FILE`), HTML entities, bold/backtick wrappers and stray spaces on AIWB marker lines only (file bodies untouched); an outer fence around the blocks, even after leading prose; JSON comments, trailing commas, smart quotes and Python literals outside strings.
- Truncation detection: unclosed block, unbalanced fence, cut JSON. A precise "continue from where you stopped" prompt (listing complete files) is copied to the clipboard; nothing is applied.
- The default output format is now "AIWB file blocks — any chat (recommended)"; the old "Gemini named code blocks" setting is migrated.
- Language policy: the UI is English-only for now (Desktop and Android).

### Validation
- Shared corpus `packages/contracts/fixtures/intake/chat-copy-corpus.v1.json`: 36 real breakage cases, 6 healthy cases (stay unchanged), 3 truncated cases. `test_intake_normalize.py` and `gui_intake_smoke.py` (Gate 3.2.0).
- NOT RUN: a live paste from real ChatGPT/Gemini/Claude chats.

## [3.1.0] - 2026-10-19

### Robust, symmetric layout (Roadmap 3.x, Gate 3.1.0, problem P2)

- New `aiwb/ui/layout.py`: `place_dialog` / `keep_on_screen` (dialogs fitted to the screen work area, minimum size never larger than the screen), `FlowBar` (toolbars wrap onto new rows instead of pushing buttons out of the window), `auto_flow` (converts every existing button row automatically), `ScrollPage` (scrollable page bodies), a shared 4 px spacing grid, and an overflow probe used by the tests.
- Every dialog is fitted to the work area the first time it is shown.
- Prompt page: the task setup scrolls and the generated prompt keeps its own resizable pane, so it is usable at 1024×640.
- Settings page and the Workbench overview/versions/settings views scroll instead of being cut off.
- Cards are flat surfaces with a 1 px border; button rows inside cards share the card colour (light and dark).

### Validation

- `gui_layout_smoke.py` (Gate 3.1.0): no squeezed or clipped button on any page at 1024×640, 1280×720 and 1920×1080 (English); an oversized dialog is fitted to the work area. The same probe reports 18 overflow cases on 3.0.0.
- All 491 unit tests and the previous GUI smoke tests pass.
- NOT RUN: physical Windows at 125/150/200 % DPI.

## [3.0.0] - 2026-10-19

### One application: single shell, one theme, one settings page (Roadmap 3.x, Gate 3.0.0, ADR-009)
- **Single window.** A navigation rail (Home · Project Workbench · Prompt · AI Response · Project Profile · History · Run & Report · Git / GitHub · Settings), a title bar with the active project and the main actions, a page stack and a status bar. The **Project Workbench is a page of the main window** — it no longer opens a second window with its own language, theme and mode.
- **One Settings page** for the whole application: Appearance (light/dark), Language (English/فارسی, the rail mirrors in RTL) and Experience (Simple/Advanced). Changes apply to every page immediately and are saved in the application settings; they never change project data.
- **Simple / Advanced is global.** Simple shows the guided path (Home, Workbench, Prompt, AI Response, Settings); Advanced adds Project Profile, History, Run & Report and Git / GitHub.
- **Professional Fluent look.** The vendored Sun Valley theme (Windows 11 Fluent style, MIT, Tcl + PNG only, no pip dependency) is used for every control; all styles map to the semantic design tokens; navigation items use a Fluent selection pill. Every hard-coded colour was removed from the main window, so dark mode is complete (tables, diff colours, status rows).
- The main window is sized to the screen work area and its minimum size never exceeds the screen.

### Validation
- `test_single_shell.py` (preferences, page model, vendored theme) and `gui_single_shell_smoke.py` (Workbench embedded with no new window, one theme, one language, one mode, settings persisted, no hard-coded colours). All previous unit tests and GUI smokes pass.
- NOT RUN: physical Windows at 125/150/200 % DPI.

## [2.7.0] - 2026-10-19

### GUI redesign foundation (GUI roadmap stages 0–4; Gate 0–4)
- **Audit and baseline:** `docs/audit/GUI_AUDIT_FA.md` with 72 reproducible screenshots of desktop 2.6.0 (`docs/audit/screens/v2.6.0/`, conditions in `manifest.json`), component inventory, prioritized issues (IA, hierarchy, consistency, responsive/accessibility) and the "must not change" list.
- **Research, information architecture, wireframes:** `docs/specs/GUI_RESEARCH_FA.md`, `GUI_INFORMATION_ARCHITECTURE_FA.md` (destinations, glossary, ten flows), `GUI_WIREFRAMES_FA.md` (three widths, all views, decision log).
- **Design System 1.0:** `docs/specs/GUI_DESIGN_SYSTEM_FA.md` and new semantic tokens in `workspace/theme.py` — surfaces, text, borders, selection, focus, one accent, status and banner colours for light and dark; type roles; 4px spacing scale; control and layout tokens. All workspace ttk styles are scoped under `WS.` (the classic window is untouched); tables, buttons, inputs and scrollbars now follow the theme in dark mode.
- `tools/gui_screenshots.py`: before/after screenshots for every view × theme × language × size; verifies that taking them changes neither project state nor the event ledger.

### Validation
- `test_gui_design_system.py`: token completeness, WCAG contrast for every text role on every surface (4.5:1) and for focus/control borders (3:1), type and spacing scales, scoped styles, no raw colours or fonts in views.
- NOT RUN: user testing with independent participants; physical Windows at 125/150/200 % DPI.

## [2.6.0] - 2026-10-18

### Team Dashboard, integration and Release Gate (Workspace Roadmap stages 7, 8, 9; Gate C, E, F, G)
- **Needs Attention queue** (Overview): deterministic, explainable ranking (decisions, parse failures/repairs, stale or partial answers, context requests, waiting for your paste, blocked work, paused publishing). Every item shows *what* and *why* with a traceable reference; large groups collapse into "… and n more"; **Mark as read** is a UI preference only — history is never removed.
- **Team Dashboard** (Team view): status counts (verified · working · waiting for your paste · blocked · needs action), current workflow step and "needs you" per agent, text filter, and "needs action only" on by default for 7–10 agents. Workbench never claims a model is working.
- **Request a change…** (task Inspector): one entry point with three explicit routes — change this task (new revision), new task (depends on the open one), or ask the project manager to re-plan; the suggested route is explained and ambiguous cases ask you.
- **Context requests** pasted into the Inbox are detected with the existing parser, recorded on the attempt and routed to Files & Context (never sent automatically).
- `tools/measure_baseline.py` measures the real Workspace read models.

### Validation
- `test_dashboard.py` (18) with a synthetic 10-agent dataset; `gui_dashboard_smoke.py`. Full suite: 475 tests, 28 GUI smokes.
- Release Gate: `docs/release/v2.6.0/RELEASE_GATE_WORKSPACE_v2.6.0.md` (perf vs baseline; manual two-chat E2E and physical-Windows DPI remain NOT RUN).

## [2.5.0] - 2026-10-18

### Workflow tracking, Timeline and Progress (Workspace Roadmap stages 5, 6; Gate B, D)

- **Workflow stage per task** (projection, no new central status): planned · ready · prompt prepared · copied (not
  confirmed sent) · you confirmed sending · answer received · parse failed / repair ready · partial · needs review ·
  context requested / prepared · blocked · needs decision · stale · validation pending · done. Shown in the Tasks list
  and the Inspector with the reason. Workbench never says a model is "working".
- **"I sent this prompt"**: a separate user confirmation (timestamp = confirmation time, `time_source: user_confirmed`);
  copying is recorded as `prompt_copied` and never means sent. The attempt freezes the agent's account profile / chat
  binding at copy/send time; later binding changes do not rewrite history.
- **Duplicate start warning**: preparing a new prompt while an attempt may still receive an answer asks first; declining
  changes nothing.
- **Timeline**: list with family filter plus **lanes by agent** (a lane is a work stream, not a git branch); legacy
  events keep the "time unknown" label.
- **Milestones** (task set + criteria; acceptance refused while tasks are open unless explicitly forced, recorded) and
  **Versions** (`proposed → local → tagged → released`): local/tagged need a commit SHA (and tag), released needs a real
  run id or artifact; adding tasks never creates a version.
- **Progress**: "n of m tasks verified" with cancelled/superseded excluded and shown separately; separate counts for
  waiting for test/build, review, blocked, needs decision, in progress; weighted progress only from user-set weights and
  always labelled *estimated*.

### Validation

- `test_workflow_timeline.py` (19); `gui_workflow_timeline_smoke.py`.

## [2.4.0] - 2026-10-18

### Team Planner (Workspace Roadmap stage 4, Gate A)
- **Team view:** account profile manager (add, enable/disable; labels only, secret-like values refused), chat
  bindings per agent, **chats you follow at the same time** (1–12, separate from the number of agents) and
  project-manager selection.
- **Plan team & tasks…:** short brief (goal required; non-goals, success, platform, constraints, limits optional) →
  a planning prompt listing the registered account profiles (self-declared, not verified), the parallel-chat
  limit and an explicit team-size question. Prompt is copied by the user; nothing is sent.
- **Team Proposal** (`team-proposal.v1`, backward compatible with `AIWB_MANAGER_PROPOSAL`): `team` block
  (`pm_counted`, `total_agents`, `additional_workers`, rationale, simpler alternative), new operations
  `create_agent` and `assign_account`, task `reviewer_agent_id` and `parallel_group`.
- **Validation:** invented/disabled account profiles and unknown agents/owners are errors on the affected item;
  warnings for unclear or inconsistent agent counts, parallel groups wider than the chat limit, overlapping file
  scopes inside a parallel group, account reuse, and tasks missing owner/scope/acceptance criteria.
- **Review:** counts and issues first; accept selected (dry-run preview, dependencies re-validated), reject all,
  or **Request changes** (a prompt listing the issues; nothing applied). Old proposals work unchanged.

### Validation
- `test_team_planner.py` (15, incl. the Gate A flow); `gui_team_planner_smoke.py`; `team-proposal.v1` fixtures.

## [2.3.0] - 2026-10-18

### Project Workbench foundation (Workspace Roadmap stages 0–3)
- **Project Workbench…** (menu + primary button): one workspace with Project Bar, Sidebar (Overview, Tasks,
  Team, Timeline, Settings), Next Action strip, collapsible Inspector and Status footer; responsive layout
  (side/stacked inspector, compact sidebar) at 960–1920 px; RTL Persian / LTR English; light/dark tokens.
  Existing tools (classic prompt/response, Inbox, Context Request, Build Center, Sync & Build, Companion,
  classic Projects window) are linked, not re-implemented. Layout preferences live in app data, never in
  project state.
- **Event Ledger** `.workbench/v2/events.jsonl` (`event-ledger.v1`, ADR-008): append-only, idempotent,
  allow-list redaction (no raw prompts/responses), legacy events imported once with `time_source: unknown`.
- **Account Profiles / Chat Bindings** data (ADR-008): local labels only; values that look like passwords,
  tokens or keys are refused; old projects open unchanged.
- ADR-007 (keep Tkinter/ttk, spike evidence), stage-0 audit and `tools/measure_baseline.py` baseline.

### Validation
- `test_workspace.py` (16); `gui_workspace_smoke.py` (4 sizes, RTL/LTR, light/dark, no state writes);
  `event-ledger.v1` checked against real ledger output in `validate_contracts.py`.

## [2.2.0] - 2026-10-18

### Mobile Companion (Integration Spec §11, P3.1–P3.3)
- **Mobile Companion…** window: start/stop a local-network endpoint (single `POST /aiwb/v1`, size-limited,
  no request logging, stopped on exit), one-time pairing code (10 minutes, single use), **desktop approval**
  of each phone, paired-device list, per-device permissions (`view_project` default; `create_task`,
  `submit_response` opt-in) and immediate **revoke**.
- Envelope v1 (`aiwb/companion/crypto.py`, standard library only): HMAC-SHA256 CTR + encrypt-then-MAC,
  timestamp window and nonce replay protection; shared vectors in
  `packages/contracts/vectors/companion-envelope.v1.json` checked by desktop and Android tests.
- Every phone request goes through the same `ProjectsController` as the desktop UI; Preview/Apply/Run are not
  exposed; GitHub tokens never leave the PC; device keys live in `companion_devices.json` in app data.
- Tasks created from the phone carry `origin: "companion"`.

### Validation
- `test_companion.py` (11, incl. the real LAN endpoint); `gui_companion_smoke.py` (pair, approve, create task,
  view, revoke).

## [2.1.2] - 2026-10-18

### Phase-3 Release Gate (Future Roadmap §28)
- **Last Published vs Local Revision** (`publish_status`) shown in both views (paused / not published yet /
  up to date); Advanced adds the last error.
- **Timer trigger** for the state publisher in the Projects window (every 30 s, alongside the event trigger);
  publishing never blocks local work and stops when the window closes.
- `gui_phase3_gate_smoke.py` runs every Future Roadmap §22 GUI flow in Simple and Advanced views.
- Gate evidence: `docs/release/v2.1.2/RELEASE_GATE_PHASE3_v2.1.2.md`.

## [2.1.1] - 2026-10-18

### Phase 3 polish (roadmap 2.1.x, Future Roadmap §19.2–§19.4)
- **One FA/EN glossary** `aiwb/i18n.py`: every task status, evidence state (Verified / Reported / Not run /
  Failed), warning severity, next action and UI term has exactly one English and one Persian text and a
  symbol. `check_glossary()` rejects missing or duplicate translations; program logic uses keys only (test
  forbids comparisons against Persian text).
- **Language switch** in *Projects (multi-agent)*: display only, stored in `ui.json`, never changes data.
- **Prioritised warnings** (`warning_items`): blocking first (publishing paused), then actions (stale
  proposals, decisions, stale answers, blocked tasks), then info (not verified yet); de-duplicated; each
  shown with a severity symbol, not colour alone.
- Applying a stale proposal asks with **No** as the default button.

### Validation
- `test_i18n.py` (5); GUI smoke switches to Persian and back without changing `state_revision`.

## [2.1.0] - 2026-10-18

### Phase 3: Simple and Advanced views on one logic (Future Roadmap §19, §28)
- The view preference lives in `.workbench/v2/ui.json`, **outside** the project state: switching
  Simple ⇄ Advanced never changes data, never bumps `state_revision` and never triggers a publish.
- `ProjectsController.next_action_view()`: the same next action (type, reference, approval flag, summary)
  in both views; Advanced adds the reason and the queue behind it.
- Advanced read-only panels: Agent Registry, Decision Ledger, Evidence Ledger (verified vs reported, run id,
  commit), Attempt/Handoff history, Manager Proposal queue (stale marked), State revision / source commit /
  publish history and pause reason.
- The window contains no write path of its own (test enforces it): both views call the same controller.

### Validation
- `test_v2_controller.py` (8), `gui_projects_smoke.py` covers both views and asserts no data change on switch.

## [2.0.0] - 2026-10-18

### Phase-2 Release Gate (Future Roadmap §27)
- Real GitHub Actions results from **Sync & Build** are recorded automatically as verified
  `build_run` evidence (`github_actions`, run id + commit SHA) for in-progress / review / validation
  tasks; idempotent per run; validation-pending tasks are re-evaluated (`aiwb/v2/ledger.record_build_evidence`).
- ADR-006 (V2 state, contracts, publishing) and gate evidence `docs/release/v2.0.0/RELEASE_GATE_v2.0.0.md`.

### Validation
- `test_v2_flow.py::BuildEvidenceTests`; all V2 suites, contracts and 22 GUI smokes.

## [1.20.1] - 2026-10-18

### Multi-agent project management V2 (roadmap 1.17.0 → 1.20.1, slices 2A–2G)
- **Data model & migration (2A):** `aiwb/v2` — Agent, Task, Attempt, Handoff, Decision, Evidence, Proposal with
  `schema_version`, stable IDs (`TASK-0001`, `HO-0001`, `EV-0001` …), task revisions and central state machines.
  One local source of truth `.workbench/v2/state.json`, transactional (lock + atomic replace + `state_revision`),
  idempotent migration with pre-migration backup, newer/corrupt files refused without writing, unknown fields kept,
  malformed collections quarantined. The legacy task and its Inbox attempts are linked once.
- **Agent Registry & Task Graph (2B):** four base roles (project manager, architect, implementer, reviewer) installed
  once and never overwritten; copy/disable/edit with revisions. Dependencies validated (unknown, self, cycles);
  ready only when prerequisites are done; cancelled prerequisites block dependants with a re-plan reason; contract
  changes create a new revision and flag dependants; parallel candidates only for non-overlapping scopes.
- **Handoff protocol (2C):** self-contained prompt for a fresh chat (task contract, accepted decisions, previous
  handoff summary, claims marked NOT verified, `AIWB_HANDOFF` manifest). Answers are matched by handoff/attempt;
  wrong-task answers are refused, late answers become `stale`, revision changes need reconciliation; missing expected
  files downgrade the outcome to `partial`. Accepting a handoff never writes files and never completes a task.
- **Decision & Evidence ledgers (2D):** decisions are never deleted (rejected/superseded kept with reason, repeated
  rejected proposals flagged). Evidence from model claims is always `verified=false`; task status follows the
  acceptance policy + verified evidence for the current task revision (and commit when given).
- **State snapshot & auto-publish (2E):** `PROJECT_STATUS.md` + `project-state.json` built from the local store only,
  published as one atomic commit to the `aiwb-state` branch (never the default branch, no force push): persistent
  queue, debounce, no-op detection, retry with backoff, `Retry-After`, auth pause, conflict pause without overwrite,
  foreign-project guard. Checked against the real GitHub API (`docs/release/v1.20.1/V2_E2E_PUBLISHER_REPORT_v1.20.1.md`).
- **Project manager (2F):** planning prompt, Manager Update prompt with link + in-prompt fallback, state probe;
  `AIWB_MANAGER_PROPOSAL` with 12 operation types, per-operation preview and partial acceptance, forward references
  between new tasks, graph validation, stale-proposal confirmation, "mark done" never accepted from a model.
- **Next Action (2G):** derived only from local state and policies, ranked, with reason and approval flag.
- **Projects (multi-agent) window:** one controller, Simple and Advanced views of the same data; one paste box
  that captures every answer raw in the Inbox before routing it to a proposal or handoff.
- **Contracts:** `agent-task.v1`, `handoff.v1`, `project-state.v1` JSON Schemas generated from `aiwb.v2.models`
  (`tools/gen_v2_contracts.py --check` in CI) and validated against real producer output.

### Validation
- `test_v2_model.py` (15), `test_v2_flow.py` (15), `test_v2_reference_scenario.py` (Future Roadmap §18 end-to-end +
  failure variants), `test_v2_controller.py` (4); GUI smoke `gui_projects_smoke.py`.

## [1.16.3] - 2026-10-18
### Smart repair, diagnostics bundle and Context Request (roadmap v1.16.2 + v1.16.3) — Phase 1 complete
- **Smart repair prompt (1.16.2):** an import repair is built from the real Inbox evidence — a new `repair` attempt
  linked to the failed one, the stable error codes, the files that arrived intact (must NOT be regenerated) and only
  the files to resend. After 3 consecutive failed repair rounds for a task Workbench stops and asks the user to decide.
- **Diagnostics bundle (1.16.2, spec v1.11 §7.4):** *Help → Diagnostics bundle (local, redacted)…* builds a ZIP on
  this computer only, with a full preview before saving. Default content: versions, redacted log tail, Inbox status
  summary (codes only), task/attempt metadata. No source, prompt/response text, raw Inbox data or credentials; user
  paths are replaced. Task text and full history are explicit opt-ins.
- **Context Request (1.16.3):** versioned `AIWB_CONTEXT_REQUEST` contract (described in the Capability Manifest of
  every prompt). Items: `full_file`, `range` (≤500 lines) or Python `symbol` (`func`, `Class`, `Class.method`,
  decorators included). Unsafe paths, missing files, invalid ranges, too-large files and sensitive files (.env, keys)
  are reported per item; sensitive files need a separate explicit decision. Files changed since the model saw them
  (`base_hashes`) are marked stale and the current version is prepared. Delivery is an inline listing (clipboard) or a
  ZIP context pack with `AIWB_CONTEXT_MANIFEST.json`; Workbench only prepares, the user pastes/attaches.
- Context requests are routed through the Inbox with their own status (`context_request`), not as an import error.
  Plain-text answers that seem to ask for files get a suggestion only.

### Validation
- `test_repair_diagnostics.py` (9), `test_context_request.py` (9); GUI smokes `gui_repair_diag_smoke.py`,
  `gui_context_request_smoke.py`.

## [1.16.0] - 2026-10-18

### Response Inbox & understandable import errors (roadmap v1.16.0 + v1.16.1)
- New package `aiwb/inbox` (UI-independent) and a **Response Inbox…** window on the Response tab.
- **Raw first:** every analysed text response is stored byte-for-byte in `.workbench/inbox/responses/<response_id>.raw` (SHA-256 checked on read, identical responses deduplicated) *before* any parser runs. Parse results are appended separately (`schema_version`, last 20 kept); a response can be **reparsed** later without asking the model again.
- **Attempts:** every built prompt gets a stable `attempt_id` (`AIWB_ATTEMPT_ID: att-…` line at the top, linked to task ID, task revision and a fingerprint of the project tree).
- **Staged pipeline:** Capture → Classify (ranked parser suggestions) → Parse → Validate (the app's existing strict validators) → Reconcile. Each stage reports ok/warn/failed.
- **Stable error codes** with plain-language explanation (what happened, stage, what is safe, what to do next): `empty_response`, `too_large`, `duplicate_response`, `unknown_format`, `json_invalid`, `truncated`, `duplicate_path`, `context_plan`, `protocol_invalid`, `unsafe_path`, `attempt_unknown`, `attempt_mismatch`, `stale_base`, `partial_parse`, `internal_error`.
- **Partial salvage:** when AIWB blocks fail as a whole, each block that is complete on its own is re-parsed with the same strict parser and path validator; cut-off, duplicate and unsafe blocks are reported, never guessed. A focused **repair prompt** asks only for the missing files.
- **Wrong/old answers:** an answer whose attempt belongs to another task is blocked (`attempt_mismatch`); a changed project tree since the prompt is a warning (`stale_base`).
- Import still never writes project files; the existing preview → diff → approve → apply flow is unchanged.

### Validation
- 24 unit tests (`tests/test_inbox.py`) using the real Workbench validators; GUI smoke `gui_inbox_smoke.py` through the real app.

## [1.15.0] - 2026-10-18

### Integrated GitHub & Monorepo Stable
- Stable release of the 1.14.x GitHub chain: accounts → repository binding → review/sync → Build Center → dispatch/artifacts → one-click Sync & Build, with monorepo CI, shared contracts and protected releases.
- No functional changes over 1.14.13 (RC); Definition-of-Done evidence in `docs/release/v1.15.0/DEFINITION_OF_DONE_v1.15.0.md`.

## [1.14.13] - 2026-10-18

### Release Candidate & Native Windows Validation (roadmap v1.14.13)
- **Real E2E** on a separate test repository (`tools/e2e_github_sandbox.py`): Sync & Build from preflight to verified artifact whose content is the pushed commit, idempotent commit/push, stale-plan refusal after a concurrent push, confirmed manual dispatch, no token leak. Report: `docs/release/v1.14.13/E2E_REPORT_v1.14.13.md`.
- **Windows CI upgrade test:** the previous published release is installed first, sentinels are written to `settings.json` and the data folder, then this build is installed over it and the sentinels must survive. The installed app is also smoke-tested from a Unicode path with spaces.
- **Settings recovery:** a corrupt `settings.json` is kept as `settings.json.corrupt-<timestamp>` instead of being silently overwritten on the next save; files with a UTF-8 BOM are accepted.
- **RC hardening tests** (`tests/test_rc_hardening.py`, 13): token redaction across URL/header/assignment forms, network errors never echo the token, rate-limit/401 polling policy, 16-thread operation-lock race, cancel-before-commit, resume after a lost push result without a second commit, records free of tokens, unreadable credential = failed preflight.
- **Protected signing:** the `release` Environment now requires a reviewer; mobile releases wait for approval.
- Docs: rollback plan (`docs/release/ROLLBACK_PLAN.md`), release-owner decisions, RC checklist with explicit NOT RUN items, ARCHITECTURE section for 1.14.5–1.14.13.

## [1.14.9] - 2026-10-18

### Repository policy & shared contracts (roadmap v1.14.9 – v1.14.11)
- ADR-005: monorepo layout, protected `main`, work-branch naming, independent `desktop-v*` / `mobile-v*` tags created only on green merge commits.
- `packages/contracts/`: JSON Schemas `release-manifest.v1`, `build-metadata.v1`, `capabilities.v1` with valid/invalid fixtures.
- `capabilities.yml` (reporting only, no feature gating).
- `tools/validate_contracts.py` (CI job `contracts`) validates schemas, fixtures, `capabilities.yml`, the real desktop `release-manifest.json` produced by the builder and the Sync & Build record conversion.
- `aiwb.github.orchestrator.build_metadata()` converts a Sync & Build record to the shared `build-metadata.v1` contract (no local paths).
- Android consumes the release-manifest contract (`ReleaseManifest.kt`, tested on the shared fixtures); the mobile release now publishes a contract `release-manifest.json`.

## [1.14.8] - 2026-10-18

### One-click Sync & Build Orchestrator (roadmap v1.14.8)
- New **Sync & Build…** window in the GitHub panel (`aiwb/github/orchestrator.py` service, `aiwb/github/sync_build_window.py`). Visible state chain: Checking → Review Required → Ready to Commit → Committed → Pushing → CI Queued → CI Running → Build Passed/Failed → Artifact Verified/Downloaded, with the last successful step, the real effect on Git and the next action.
- **Preflight:** account token, selected Build workflow, bound work branch (never `main`/`master`) checked out, remote `origin`, fetch, sync state (diverged/conflict/remote-ahead stop the flow).
- **Review:** each change is flagged *sensitive* (cannot be committed), *outside_scope* or *workflow_change* (both need explicit confirmation).
- **Stale plan:** the remote is fetched again before commit and checked live before push; if it moved, nothing is committed/pushed.
- **Exact build tracking:** runs are looked up by bound workflow + branch + the pushed commit's full SHA; artifacts must match `repository_id + run_id + head_sha` (+ the binding's artifact pattern).
- **Cancel:** before commit — nothing changed; after commit — local commit kept; after push — the Actions run is cancelled, the commit stays. No commit is ever deleted or undone.
- **Idempotency & lock:** operation ID per flow; repeated commit/push/download reuse the record (a push whose result was lost is detected from the remote SHA); one flow per repository/branch; unfinished operations can be resumed after reopening.
- **Records:** `GitOperationRecord` + `BuildRunRecord` in `.workbench/sync_build_operations.json` (Task → approved paths → Commit SHA → Run ID → Artifact ID → SHA-256); no credentials or prompt text.
- Fixed an undefined name (`RepositoryBindingError`) that turned a failed binding save into a NameError; CI now has an undefined-name gate (`tools/check_undefined_names.py`, pyflakes).

### Validation
- 10 new orchestrator tests on real Git repositories with a local bare remote; new GUI smoke `gui_sync_build_smoke.py` (18 GUI smokes).

## [1.14.7] - 2026-10-18
### Workflow Dispatch & Safe Artifact Download (roadmap v1.14.7)
- New `aiwb/github/artifacts.py` (no Tk) and `aiwb/github/build_center_dialogs.py`; Build Center gets **Run workflow…** and **Artifacts…**.
- **Run workflow…** is enabled only for active workflows whose file declares `workflow_dispatch`. The form is generated from the file's real `workflow_dispatch.inputs` (string / boolean / choice / number / environment, required, default, options) by a small dependency-free YAML reader; values are validated before sending. The ref (branch/tag) is explicit and validated.
- Dispatch asks GitHub for run details. A run is reported as *the* dispatched run only if GitHub returned its ID, or if strict matching (same workflow, `workflow_dispatch` event, same ref, created after the request, not seen before) finds exactly one candidate. HTTP 204 without a run is reported as **Not confirmed**, never as success; several candidates are reported as ambiguous.
- **Artifacts…** lists ID, name, size, expiry, GitHub digest and run/commit. Expired artifacts and artifacts of another run/commit cannot be downloaded as this run's output.
- Download uses the official `/artifacts/{id}/zip` endpoint without following the redirect automatically; the short-lived URL is fetched **without** the token, only from GitHub/Azure blob hosts, and never appears in logs, errors or the UI. Streaming into a `.part` file with size and time caps, cancel button, size check against GitHub's value and ZIP validation; partial files are removed on any failure. HTTP 410 → "expired".
- SHA-256 is computed while downloading. The UI distinguishes **"matches the digest GitHub reported"** from **"computed; no reference (not verified)"**; a mismatch deletes the file.
- **Extract safely…** validates every entry first and extracts into a new folder via a staging directory: path traversal, absolute/drive paths, backslashes, duplicate and case-colliding names, file/folder collisions, Windows reserved/invalid names, symlinks and special files, encrypted entries, entry count, total size, suspicious compression ratio and entries that expand beyond their declared size are all rejected.
- Release tooling: `tools/bump_desktop_release.py` and `tools/mark_roadmap_step.py`.

### Validation
- 23 new unit tests (`tests/test_github_artifacts.py`), 282 in total; new GUI smoke `gui_dispatch_artifacts_smoke.py` (17 GUI smokes).
- Verified against the live GitHub API on this repository: a real `workflow_dispatch` returned a confirmed run ID; a real CI artifact downloaded with SHA-256 **matching** GitHub's digest and extracted safely.

## [1.14.6] - 2026-10-17
### Build Center: Workflow & Run Monitoring (roadmap v1.14.6)
- New **Build Center…** window in the GitHub panel (`aiwb/github/actions.py` service + `aiwb/github/build_center.py` window; no Tk in the service).
- Discovers `.github/workflows/*.yml|*.yaml` via the Actions API and reads each file to list its real triggers. "Manual run" is `yes` only when the file declares `workflow_dispatch`; unreadable files show `unknown`, never `yes`. Dynamic (Dependabot) workflows are excluded.
- The project's main Build workflow can be selected from the list and is saved in the binding; a renamed/deleted file is reported as a stale binding, a disabled workflow as disabled.
- Runs show status/result (success / failure / cancelled / skipped / timed out / … kept distinct), branch, commit SHA, run ID, attempt, created/updated times and a GitHub link.
- **Commit correlation:** the local HEAD is matched to a run only by exact 40-character SHA; if the newest run belongs to another commit, the window says so explicitly instead of showing it as the result of the latest changes.
- Jobs and their failed steps for the selected run; double-click opens the job log on GitHub (the short-lived raw-log URL is never copied).
- Non-blocking polling (worker thread + queue polled on the Tk thread) with a 5 s cache window, 10 s while runs are active, 60 s idle, exponential backoff on errors, `Retry-After`/rate-limit reset respected, and polling stopped on HTTP 401.
- **Cancel run…** only for unfinished runs, after confirmation; 403/404 → "needs Actions: write", 409 → already finishing.
- `RepositoryOperationGuard` prevents two Sync/Build operations on the same repository/ref (used by 1.14.8).
- No dispatch, Artifact download or push in this release.

### Validation
- 17 new unit tests (`tests/test_github_actions.py`), 259 in total; new GUI smoke `gui_build_center_smoke.py` (16 GUI smokes); verified read-only against the live GitHub API.

## [1.14.5] - 2026-10-17
### Safe Git Review & Sync Plan (roadmap v1.14.5)
- New **Review & Sync…** window in the Git / GitHub tab, backed by the UI-independent `aiwb/git/sync.py` service.
- Status is read with `git status --porcelain=v2 --branch -z`; each path is shown as staged / unstaged / untracked / deleted / renamed (with original path) / conflict, with its in/OUT active-project scope and a per-file diff (staged and unstaged shown separately, binary and outside-repo paths refused).
- File-by-file selection for commit. In-scope files are pre-selected; selecting outside-scope files requires an extra confirmation.
- Pre-existing staged changes that were not selected **block** the commit (nothing is mixed in). After `git add`, the index is re-read and any unexpected path aborts before committing.
- `Fetch + build Sync Plan` classifies: clean / local ahead / remote ahead / diverged / local changes / conflict / no upstream / detached, with explicit manual options for diverged and conflict states.
- Only a `merge --ff-only` is ever performed, and only when the remote is strictly ahead, the tree is clean and HEAD/branch still match the plan.
- Before push the live remote branch SHA is re-read with `ls-remote`; if it changed since the plan, nothing is pushed and a new plan is required. No force push exists. Push to `main`/`master` remains blocked.
- Editable commit message with `Workbench-Task` / `Workbench-Run` / `Workbench-Apply` trailers prefilled from local task/run/apply metadata. The prompt is never stored in the commit.
- Results distinguish "commit failed" from "local commit WAS created, but push failed".
- Secret scanning stays a best-effort auxiliary check and is reported as such.

### Windows portability fixes (found by the new native Windows CI)
- Fixed a crash recording an applied project version when the project path is a Windows 8.3 short path / junction (`relative_to` on unresolved root).
- Fixed four tests that assumed POSIX (shell-script fake LTspice runner, text-mode newline translation, unresolved temp path).

### Release engineering
- The app now lives in the `golshandvr-del/workbench` monorepo (`apps/desktop`). The installer is built reproducibly by `tools/build_desktop_installer.py` (it rebuilds the published 1.14.4 installer byte-for-byte from tag `desktop-v1.14.4`).
- CI runs the full suite on Linux (Python 3.10/3.13) and natively on Windows, installs from `Setup.bat` on a clean runner, checks shortcuts, and runs GUI smokes of the installed copy and of the new review window.

### Validation
- 242 unit/regression tests (17 new real-repository sync tests using a local bare remote: ff-only, dirty-tree block, stale plan, divergence, concurrent remote update before push, commit-created-but-push-failed, pre-staged files, main/master block, first push without upstream).

## [1.14.4] - 2026-10-17
### Project binding v2 and Monorepo-aware Git scope
- Extended `RepositoryBinding` to schema v2 with validated Workflow path, Artifact-name pattern, release channel, last-known remote SHA and sync/metadata timestamps. Schema-v1 bindings migrate idempotently with a timestamped settings backup before persistence.
- Added binding settings UI for working branch, workflow file, artifact pattern and release channel; the values are configuration only and do not dispatch workflows or download artifacts.
- Added Clone Selected and Initialize & Link flows with explicit destination/origin confirmation. Initialization starts on a non-main `workbench/initial-sync-*` branch and does not stage, commit or push files.
- Added non-mutating Initial Push Review for scope, sensitive-path/secret-signature and large-file warnings, plus explicit `.gitignore` suggestion/append behavior that preserves existing content.
- Git status now warns about changed paths outside the active project subpath. Workbench Commit stages only paths inside the active Monorepo scope; pre-staged index changes block the operation rather than being silently mixed in. Commit uses literal pathspecs and revalidates root/scope/status before staging. Branch/push remain repository-wide, and direct push to main/master remains blocked.
- Fixed `.workbench/` exclusion path resolution to target the real Git root's private `info/exclude`, including a Workbench project nested in a Monorepo.
- Added v1.14.4 service and GUI integration tests, including an actual local-Git commit proving a sibling/root path is not included.

### Validation limits
- `compileall`, 225 unit/regression tests, 14 Linux/Xvfb GUI smoke tests, installer payload byte-identity, clean payload-layout import and the v1.14.4 repository-binding tests passed. Native Windows installation, PowerShell execution, Windows Credential Manager, and live GitHub clone/API auth remain **NOT RUN**. See `WINDOWS_RELEASE_CHECKLIST_v1.14.4.md`.

## [1.14.3] - 2026-10-17
### GitHub Repository Browser and project binding
- Added bounded, paginated `GET /user/repos` support to the independent GitHub REST client. Repository IDs are deduplicated and API payload metadata, URLs, pagination bounds and response sizes are validated.
- Added the GitHub Repository Browser UI with account selection, search over owner/name/description, All/Private/Public/Forks/Archived filters, default branch, updated timestamp, description and reported push permission.
- Added versioned `github_repository_bindings` records storing repository numeric ID, account reference, canonical local Git root, active project path, Monorepo subpath and non-secret metadata. No PAT or raw origin URL is persisted in binding records.
- Added explicit, guarded origin add/replace actions for HTTPS and supported SSH GitHub remotes, with verification and best-effort compensation if metadata persistence fails. Linking does not stage, commit or push; unlinking removes Workbench metadata only.
- Added API pagination, validation, real-local-Git, Monorepo, rollback/redaction and GUI smoke tests; installer payload now includes the new binding service and its tests.

### Validation limits
- Compile, unit/regression, Linux/Xvfb GUI smoke and offline payload-integrity checks run for this release. Native Windows install, live PAT/API access, and real Windows Credential Manager remain NOT RUN in this environment. See `WINDOWS_RELEASE_CHECKLIST_v1.14.3.md`.

## [1.14.2] - 2026-10-17
### Secure GitHub Accounts and Personal Access Tokens
- Added the UI-independent `aiwb.github` package: PAT validation/redaction, injectable REST transport, authenticated-user verification, account metadata registry, and safe add/replace/test/refresh/disconnect lifecycle.
- Added a Windows Credential Manager implementation for persistent generic credentials. Production has no plaintext or memory-store fallback; the in-memory credential store is an explicit unit-test double only.
- Added the GitHub Accounts panel inside Git / GitHub with masked PAT input and background work for network/credential operations.
- Added `GET /user` REST client with User-Agent, Accept, `X-GitHub-Api-Version: 2026-03-10`, bounded timeout and response size, no redirect following, and categorized authentication, permission/policy, rate-limit, network, timeout, server and invalid-response errors.
- Settings contain only safe account metadata and an opaque credential reference. A successful identity check leaves repository, Git write, Actions, dispatch, artifact and release capabilities as `not_checked`.
- Replacing a credential verifies the same immutable GitHub user ID before switching references; disconnect removes account metadata and attempts to delete the OS credential without touching local projects or Git transport credentials.
- Added API/account unit tests, GUI smoke test, native Windows Credential Manager test script, ADR-002 and Windows release checklist.
- Restricted live bearer-token transport to `https://api.github.com`; non-GitHub HTTPS hosts and path prefixes are rejected unless an HTTP transport is explicitly injected for tests.
- Separated account metadata persistence from Tk-dependent settings serialization and synchronized both settings writers with a shared lock, preventing background PAT operations from accessing Tk variables or clobbering concurrent settings saves.
- Added regression coverage for live-host allowlisting and account creation from a background worker.

### Validation limits
- Native Windows Credential Manager and actual `.bat` install/update were not run in this Linux environment. Execute `test_windows_credential_store.py` on a Windows target and complete `WINDOWS_RELEASE_CHECKLIST_v1.14.2.md`; do not infer native success from mocked or Xvfb tests.

# Changelog

## [1.14.1] - 2026-10-17
### Modular local Git service foundation
- Extracted Git executable discovery, version reporting, shell-free command execution, porcelain status parsing, local repository status inspection and changed-path collection into the UI-independent `aiwb.git` package.
- Added immutable `GitStatusEntry` / `GitStatusSnapshot` models and kept the former dictionary/tuple interfaces as compatibility adapters.
- Added injectable `GitCommandRunner` dependencies for executable discovery, subprocess launching, environment, redaction and quiet Windows process settings. The runner disables Git terminal prompting, enforces bounded timeouts, rejects invalid argument sequences/NUL bytes and always launches with `shell=False`.
- Routed project initialization (`git init`) through the shared service boundary instead of launching Git directly from a GUI callback.
- Updated installer copying logic for nested `aiwb/git/` modules and added `test_git_service.py` to the release/diagnostic payload.
- Added service tests for argument-vector integrity, timeout/missing executable handling, secret redaction, legacy status shape, Unicode and unusual filenames. Existing UI-facing adapter signatures and status result fields are preserved.

### Validation limits
- New Git-service tests and the full regression/GUI suites are reported in `AI_Workbench_Test_Report_v1.14.1.txt`. Native Windows install/upgrade and actual Windows Credential Manager behavior remain **NOT RUN** in this environment. No GitHub REST API, PAT store, Repository Browser or Actions support is claimed in v1.14.1.

## [1.14.0] - 2026-10-17
### Typed operations, architecture plans, candidate comparison and modular services
- Added strict `workbench-v3` typed operations for `write`, `delete`, `rename`, and `move`; legacy `workbench-v1` / `workbench-v2` remain supported as write-only protocols. All paths are validated before mutation; rename is same-directory only; move/rename destinations must be absent; duplicate operation IDs and path collisions are rejected.
- Generalized Apply transactions to snapshot every affected endpoint, including paths expected to be absent. Delete/Move/Rename generate pre/post state hashes and verified backups; rollback attempts restore pre-apply bytes, and Restore can reverse a delete or both endpoints of a move while refusing post-apply edits.
- Added a validated, round-trippable `workbench-architecture-v1` plan: the new-project Wizard accepts a plan, Project Profile can reopen it, model JSON can be imported/exported/edited, and plans are saved to `.workbench/architecture_plan.json` for optional prompt context. A plan never authorizes edits.
- Added local, bounded response candidate storage and a per-destination comparison window. Every destination defaults to Skip; chosen operations are composed as v3 JSON and sent through the ordinary Preview/approval pipeline. Candidate commands are never silently merged.
- Added task playbooks for general work, feature implementation, bug fixing, refactoring, security, performance, documentation/release, and engineering/simulation. Selection is persisted in app settings and injected into generated prompts.
- Added structured semantic diffs for Python definitions (AST), JSON paths/values, and CSV columns/keyed rows/cells; selected source languages use explicitly labeled regex heuristics. Added static dependency graph / direct/transitive impact analysis for Python, JS/TS, C/C++, Java, C#, Go, Rust, Ruby, PHP, Swift, Kotlin and Scala source files. Scan limits and coverage caveats remain visible.
- Began incremental modularization in the new `aiwb/` package, retaining `AI_Workbench.py` as the stable GUI entry point rather than making a high-risk all-at-once rewrite. Updated the installer to install the package and added dedicated service, transaction, protocol, and installer-packaging tests.

### Validation limits
- The Python unit/regression suite, compile checks, GUI smoke tests and offline installer-payload checks were run in this environment; results are recorded in `AI_Workbench_Test_Report_v1.14.0.txt`. Native Windows double-click install/update and real LTspice simulation remain NOT RUN here. Do not label the release Windows-verified until the v1.14 release checklist has target-machine evidence.

## [1.13.0] - 2026-10-17
### Transaction recovery, selective review, validation profiles and binary ZIP artifacts
- Added per-file Apply selection in the review tree (all/new/changed/none). Apply uses only the selected subset, rechecks original bytes immediately before writing, keeps command approval separate, warns when a queued command appears to reference an excluded path, and records partial application distinctly.
- Every successful write transaction now receives a stable transaction ID and an immutable transaction manifest linking task/history IDs, canonical paths, before/after SHA-256 hashes, sizes and backup locations. Failure to persist the manifest is treated as an Apply failure and triggers the existing rollback path.
- Added a Restore Manager for selecting historical Apply transactions and files. Restore is allowed only when current hashes match the recorded post-Apply hashes and required backup bytes verify. Conflicts stop the selected batch; no force-overwrite option exists. Restore is itself recorded as a reversible transaction, with an execution event and project-version ledger entry.
- Added project-local validation profiles in `.workbench/validation_profiles.json`. Profiles use typed `argv` with no shell by default, bounded timeouts, ordered steps, explicit approval, optional expected-file freshness checks, and evidence statuses. Missing tools/working directories are Blocked; manual steps remain Not run; process exit is not represented as domain verification.
- ZIP import now retains binary entries as exact bytes alongside text entries. Binary review shows size and SHA-256 instead of fabricating a text diff; import remains read-only, and Apply/backup/Restore use the same transactional path. ZIP traversal, symlink/special entries, duplicate/case-colliding paths, entry/file-count limits and expanded-size limits remain enforced.
- Context recommendation now respects a conservative subset of `.gitignore` and `.workbenchignore`, preserves existing selections when recommending additional files, and offers a rationale/exclusion view. Ignore matching is explicitly not claimed to be a full Git-compatible implementation; manual selection does not bypass security-protected path checks.
- Added a reviewed, local-only redacted diagnostics JSON export. By default it excludes source, prompts, model responses, command text, process output and full user paths; the UI warns that redaction is not a perfect guarantee.
- Added `restore_service.py` and `validation_profiles.py` service boundaries, regression tests, release checklist, installer inclusion, and architecture/changelog documentation. Legacy JSON/AIWB/Markdown and text-only ZIP adapters remain supported.

### Verification limits
- Python compilation, unit/regression tests and GUI smoke flows were run in Linux/Xvfb. Native Windows double-click installation/update and real LTspice integration are **NOT RUN** here; see `WINDOWS_RELEASE_CHECKLIST_v1.13.0.md`. Do not treat the package as Windows-verified until a target Windows run records evidence.
- At the time v1.13.0 shipped, Delete/Rename/Move, architecture-plan round-trip, candidate comparison, task playbooks, change-impact analysis and multi-language semantic/dependency analysis remained follow-on work. v1.14.0 implements the first versions described at the top of this changelog; richer YAML-aware semantic parsing, compiler-backed dependency resolution and context-budget optimization remain future improvements.


All notable changes to AI Workbench are recorded here. Versions follow semantic versioning where practical.

## [1.12.0] - 2026-10-17
### Context-plan protocol migration and diagnostics
- Fixed the contract split between prompts saying “return `workbench-plan-v1`” and the importer expecting only a newer field schema. New base, repair and continuation prompts share the canonical `workbench-plan-v2` schema; the schema explicitly overrides file-delivery transport when required source context is missing.
- Added a constrained legacy migration adapter for `requests`, singular `request`, the documented whole-file/line-range/manual-upload modes, `manual_attachments`, `manual_attachment`, and the reported typo `manual_attechent`. Retained `next_steps` and `completion_status`; no legacy context request can become a file write or command action.
- Added strict adapter validation for unknown top-level/nested keys and malformed canonical list fields. Migrated paths/ranges still pass the same normal validators for project-relative paths, traversal, sensitive paths, symlinks, line ranges, list limits and text lengths.
- Context-plan diagnostics now classify plan replies separately from implementation manifests, display request counts/paths, deduplicate duplicate error messages and make it clear that no files were applied. Context-plan import refreshes the file inventory before selecting requested files and saves the exact plan/history association before moving stages.
- Hardened malformed protocol/status/action/scope type handling so user/model JSON errors become actionable `WorkbenchError` validation failures instead of internal type exceptions. Valid context plans receive a distinct diagnostic status color.
- Added regression coverage for malformed schema value types, response identity, and failed-plan history persistence; the full suite contains 144 unit/regression tests. The exact-reproduction GUI test covers legacy `workbench-plan-v1` → canonical migration → file-tree selection/history, plus a rejected-plan attempt.

### Validation limits
- 144 unit/regression tests and nine GUI smoke flows passed in Linux/Xvfb. Python compilation and installer payload byte-integrity checks passed. Native Windows installer execution was not performed in this environment; target-machine install/update remains unverified.

## [1.11.0] - 2026-10-17
### Project history, provenance and versioning redesign
- Split the local history concept into two linked but distinct records: the automatically maintained conversation/audit trail, and user-curated `project_history_saved` checkpoints. The Response tab enables “Save validated prompt + output to history” only after a successful import/validation; editing the response text immediately invalidates the old preview and checkpoint authorization.
- Added a project-local version ledger at `.workbench/project_versions/`, with a baseline and monotonically recorded semantic versions for actual file-tree changes. Each applied version records its parent, file inventory and hashes, changed paths, exact source history-step ID, prompt/output SHA-256 hashes, and an immutable response snapshot when the bounded source snapshot is available. A no-op file tree does not fabricate a new version.
- Added explicit one-shot semantic-version bump policy (`patch`, `minor`, or `major`) in Project versions…; `patch` is the default. `minor` resets patch to zero; `major` resets both minor and patch. A no-op does not consume the selected bump, and a real applied change resets the policy to `patch`.
- Linked each newly applied version to the exact history prompt/output entry, surfaced version IDs in the History tree and Project versions dialog, and added a UI action to open the source prompt/output. Project history can be added directly to a generated prompt or be included when the model requests recent summaries, version links, or selected history IDs. History content remains local and is not sent unless included in a generated prompt the user chooses to copy/send.
- Added right-click tree actions to rename/edit metadata, edit prompt as a new revision, save/unsave a checkpoint, change parent, indent/outdent, reorder siblings, and delete a step. Deleting a parent safely lifts its children rather than leaving dangling references; cyclic parent changes are rejected.
- Moved project baseline/hash inventory and applied-version hashing to progress-backed workers. Serialized pending version records behind active workers so a concurrent Git refresh cannot drop a version record after files have already been applied. Split file-tree refresh from its Git follow-up at the version-recording boundary.
- Suppressed visible transient Windows consoles for background subprocesses using `CREATE_NO_WINDOW` and retained the progress indicator for startup inventory, Git refresh, and version recording. Real errors remain visible; hiding console windows is not error suppression.
- Added regression coverage for curated checkpoint validity, stale preview invalidation, parent cycle prevention and deletion behavior, version-bump semantics, exact prompt/output provenance, no-op detection, and GUI apply→checkpoint→version-link workflow.

### Validation limits
- Unit/regression tests and eight GUI smoke flows run in Linux/Xvfb. The Windows installer payload is checked byte-for-byte; native Windows install/run behavior is still not claimed without a Windows target-machine test. Project-version records are provenance/inventory records, **not** full source snapshots or automatic restore points.

## [1.10.0] - 2026-10-17
### Model-response intake reliability (root-cause fix)
- Reworked response intake so JSON parsing is not limited to a response beginning exactly with `{`: a single supported protocol object may be extracted from surrounding explanation/fences, while multiple conflicting protocol objects are rejected instead of guessed. JSON-like parse errors now remain JSON-specific when the Markdown fallback cannot safely identify files.
- Added an explicit `body="raw"` flag for AIWB file/action blocks. The new generated contract no longer guesses whether a leading Markdown fence is file content or a wrapper; files that begin or end with fenced Markdown are preserved exactly. The older auto-detected fenced format remains supported for compatibility.
- Fixed unsafe boundary recovery: a new AIWB header before the previous block's end marker now rejects the whole response with the missing marker and line number. The former parser could consume a later file into the previous file and appear to succeed.
- Improved import errors so prose-only answers, incomplete diffs, unlabeled code blocks, and text claims about nonexistent downloadable attachments are distinguished from actual importable files. The diagnostic no longer tells users to chase unrelated marker/attribute-order fixes.
- Kept the validation and review model intact: all candidate files/actions are validated before preview; preview stays read-only; applying files and executing proposed actions still require separate approval. ZIP/JSON/legacy-block compatibility remains covered by regression tests.
- Added targeted tests for raw content starting with fences, raw command blocks, JSON error preservation, conflicting/unknown protocols, missing end markers, prompt contracts, prior sample responses, and GUI preview/apply/rejection paths.

### Validation limits
- Python unit/regression tests and Tk GUI smoke tests run in the available Linux/Xvfb build environment. The embedded one-click installer is checked for byte-identical payload integrity, but a native Windows double-click install/update cannot be claimed from Linux and remains a target-machine integration check.

## [1.9.0] - 2026-10-17
### Connected prompt/response workflow
- Added a project-local, indexed conversation history with `Start` / `Step N` sequencing, parent links, editable title/feature/project-version metadata and notes, prompt-stage/protocol/version records, metadata filtering, UI inspection/copy/delete controls, and a linked prompt-revision editor that preserves the original body.
- Every newly generated prompt is stored before the workflow reports it as ready. Model outputs—including invalid/import-error responses—are associated with the active step and bounded by documented storage limits; GPT ZIP imports store the normalized payload plus archive provenance instead of a placeholder response marker.
- Added a manual runtime/build/test/simulation/installation error dialog that stores the user's error and reproduction steps against the selected prompt, writes an execution-journal event, sets it as active evidence, and generates a linked repair-prompt step.
- Extended context planning to request whole files, exact 1-based line ranges up to 500 lines, and manual file uploads. The next prompt automatically re-reads requested ranges under path/size/symlink/secret checks and lists files the user must attach to the same model chat. The app does not claim or attempt automatic chat upload.
- Added recent thread summaries plus active/ancestor manual-error and context details to continuation hand-offs; capability/help text and both READMEs now document the linked flow and local persistence.
- Extracted the durable history service into `conversation_store.py` and included it in installation. History uses atomic JSON writes, safe project-local paths, a lightweight bounded metadata index, explicit deletion, bounded input reads, and bounded entry/output sizes.
- Added regression tests for history sequence and prompt revisions, bounded history reads, range validation/formatting, manual upload reminders, task-change isolation, parent-step error continuity, continuation hand-off and GUI flow from planning context request through model response and manual-error repair.

### Limits and validation
- Prompt and response transfer to regular GPT/Gemini chats remains manual. Binary attachments requiring model inspection must be manually attached by the user; Workbench only prepares a checklist.
- History is local project data and can include sensitive prompt/output content. Native Windows install was not executed in this build environment; see the current release test report.

## [1.8.0] - 2026-10-17
### GPT artifact delivery and runtime reliability
- Added a ZIP-first GPT output profile with exact usage/file-map documentation requirements and a strict JSON fallback when the chat interface cannot attach downloadable files.
- Added secure ZIP artifact intake. Archive entries are validated without extraction, converted to ordinary file changes, and routed through the existing diff/backup/approval pipeline. Root `AIWB_RESPONSE.json` contributes validated summary/next-step/action metadata but is never written into the project; its actions array may be empty.
- Added archive provenance to the normalized response snapshot: source filename, SHA-256, byte size and import counts (without persisting the absolute local source path).
- Unified the transport instructions used by repair prompts and continuation handoffs so ZIP/JSON/Gemini choices do not drift mid-task. Planning state records JSON as the actual protocol.
- Rejected file/directory conflicts (for example `settings` and `settings/app.json`), existing parent-file blockers and Windows-invalid control characters during response validation, before the preview/apply stage. ZIP imports now surface a review warning when the contract-required root README is missing/empty, preserving that warning even when the model summary uses its full character limit.
- Hardened context-file reads by revalidating sensitive paths and every path component for symlinks and enforcing the byte limit while reading.
- Added a GUI integration test that loads an actual ZIP, confirms preview is non-mutating, applies reviewed files, and verifies the control manifest is never written into the workspace.
- Added streaming bounded `argv` execution for project-file runners. Both output streams are drained concurrently and their captured tails are capped during execution; timeout handling attempts to terminate the process tree.
- New installations default to the GPT ZIP-first format; existing saved user format choices are preserved.

### Limits and validation
- ZIP artifacts accept UTF-8 text files only. Binary assets, invalid encodings, archive traversal, symlinks/special entries, sensitive paths, duplicate Windows-casefolded paths, excessive size/count and invalid metadata are rejected explicitly.
- Added ZIP safety/provenance, GPT prompt contract, bounded-output and timeout regression tests plus delivery-transport continuity, path-conflict and bounded context-read coverage.
- Native Windows installer execution and native LTspice simulation remain platform integration checks and are not inferred from Linux tests.

## [1.7.1] - 2026-10-17
### Windows installer reliability (root-cause fix)
- Fixed the installer packaging defect that put multiline Base64 data inside a PowerShell `-Command` string. Windows CMD split the payload into commands and PowerShell reported an unterminated string.
- Replaced that design with a one-line `-EncodedCommand` bootstrap, an embedded payload placed after `exit /b`, exact begin/end markers, Base64 validation, unique temporary extraction, and a checked child-process exit code.
- Documented the packaging invariant in `ARCHITECTURE.md` and updated regression expectations to version 1.7.1.

### Validation limits
- Payload decoding and archive-byte identity are checked in the build environment; unit and GUI smoke tests are rerun.
- A native Windows double-click installation is still not executed in this Linux build environment and remains the final machine-specific integration check.

## [1.7.0] - 2026-10-16
### Architecture and reliability
- Added `ARCHITECTURE.md` as the architecture baseline, including layer boundaries, response protocol rules, execution/evidence semantics, project initialization contract, test gates and migration debt.
- Added a change-control rule: every user-reported defect needs a reproduction, root cause, invariant, regression test and documented residual limitation.
- Corrected Windows `.bat/.cmd` command construction. The old `cmd.exe /d /s /c` quoting lost reliable quoting around script paths containing spaces; command construction is isolated in `build_windows_batch_argv` and regression-tested without running a Windows shell.
- Kept project-file execution and model-proposed command execution separate from import/preview; the execution result must be recorded before it can be included as observed evidence in a follow-up prompt.
- Updated the live capability manifest release version to 1.7.0.

### Validation
- Regression test added for `.bat` paths and arguments containing spaces.
- The test suite must be rerun for the release build; native Windows `.bat` execution and a real LTspice simulation remain platform/integration checks, not inferred from unit tests.

## [1.6.0] - 2026-10-16
- Added project-file runner and execution diagnostics, including LTspice batch support.
- Added right-click editing context menus, file-run result evidence, and deliverable-neutral engineering project guidance.
- Fixed Markdown fence parsing and normalization of Markdown-wrapped `__init__.py` paths.

## [1.5.0] - 2026-10-16
- Added live capability manifest, import diagnostics, file preview/diff, workflow states and repair prompts from recorded failures.
