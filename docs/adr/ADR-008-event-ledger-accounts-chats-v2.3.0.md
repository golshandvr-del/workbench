# ADR-008 — Event Ledger, Account Profiles, Chat Bindings, Milestones/Versions (2.3.0)

**Status:** accepted · **Date:** 2026-10-18 · **Scope:** `aiwb/v2/events.py`, `aiwb/v2/resources.py`, `aiwb/v2/store.py`
**Source:** `docs/specs/AI_Workbench_GUI_Team_Orchestration_Roadmap_FA.md` §5, §8, §9, §16.3

## Context
`state.json` keeps only the last `MAX_EVENTS = 2000` events inside the current state. The timeline needs a
long, trustworthy history without becoming a second source of truth. The team planner needs the user's
real resources (accounts, chats) without any credential.

## Decisions
1. **Event Ledger = `.workbench/v2/events.jsonl`, append-only, schema `event-ledger.v1`.** It is *derived*
   from the events every `ProjectStore.transaction` already emits: after the atomic state write the store
   appends the new events (`state_revision` > last ledger revision). One write path, no events invented by
   views. `event_id = LE-<state_revision:06>-<index:02>` is deterministic, so re-syncing is idempotent.
2. **Current state stays in `state.json`.** The ledger is history only; nothing computes status from it.
   Ledger failures never fail or roll back a transaction (the state is authoritative); on open the ledger
   is re-synced from the in-state events, which also closes a crash gap between the two writes.
3. **Time is never guessed.** `timestamp_utc` is the Workbench clock at the transaction; `time_source` is
   `workbench_clock`, `user_confirmed` (self-declared user actions such as "I sent this prompt") or
   `unknown` (legacy event without `at`). Events imported from an existing state on first open are marked
   `legacy_import: true` with their original timestamps.
4. **Redaction by allow-list.** Only IDs, statuses, short reasons/labels (≤ 300 chars) and counts are copied.
   Prompt/response text, file contents, URLs with tokens and any key named like `prompt|text|response|token|
   secret|password|cookie|key` are dropped. View/language/layout changes live in `ui.json` and produce no event.
5. **Account Profile** (`account_profiles`, `ACC-0001`): display name, provider label, self-declared plan
   (`free|paid|team|unknown`), note, usage tags, enabled. **No credential fields exist**; values that look
   like secrets (`sk-…`, `ghp_…`, long base64/hex) are refused. Never published to GitHub.
6. **Chat Binding** (`chat_bindings`, `CHAT-0001`): agent_id, account_profile_id, local chat name, optional
   user-entered link, note, enabled, `confirmed_at` (user's last confirmation). Workbench never opens,
   reads or monitors the chat. Changing a binding never changes `agent_id` or rewrites past attempts.
   An agent's *current* binding is its most recently updated enabled binding with an enabled profile.
7. **Milestone** (`milestones`, `MS-0001`) and **Version** (`versions`, `VER-0001`) are separate entities
   (2.5.0). A version has states `proposed → tagged → released` and links tasks, commit, run id, artifacts;
   tasks never create versions automatically.
8. **Migration is additive, db_version stays 1.** New collections are added by `migrate_state` (backup
   first, idempotent). Older 2.2.x builds keep unknown collections untouched (they copy the whole state),
   so a downgrade does not delete data; it only hides the new features. `preferred_model_label` is kept as
   a legacy label; it is never converted into an account profile automatically.
9. **Workflow (manual send) is a projection**, not new task statuses: Attempt/Handoff status + ledger
   events `prompt_copied` and `user_confirmed_sent` yield `prompt_prepared → prompt_copied →
   user_confirmed_sent/waiting_for_response → response_received → parse_failed/partial_response →
   needs_user_review → stale/blocked → validation_pending → verified_done`.

## Consequences
* Timeline, dashboard and progress read models are pure and testable over (state, ledger).
* The ledger grows without bound; pages are read from the end (200 per page). Retention policy: none in
  2.x (history is evidence); size is reported in the release gate.
