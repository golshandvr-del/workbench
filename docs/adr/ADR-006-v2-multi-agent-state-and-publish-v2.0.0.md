# ADR-006 — V2 multi-agent state, contracts and publishing (2.0.0)

**Status:** accepted · **Date:** 2026-10-18 · **Scope:** `apps/desktop/src/aiwb/v2`, `packages/contracts`

## Context
Phase 2 turns Workbench from "one prompt, one answer" into a project-management system where several
role-based agents (in different ordinary chats/models chosen by the user) work on one project.
Workbench never talks to a model directly; the user copies prompts and pastes answers.

## Decisions
1. **One local source of truth.** `.workbench/v2/state.json` (inside the project, never committed).
   All writes go through `ProjectStore.transaction()` (process lock + file lock + atomic replace +
   monotonically increasing `state_revision`). Each entity has `schema_version`; `db_version` drives
   idempotent migrations with a backup before the first migration. Newer or corrupt files are refused.
2. **Agents are roles, not accounts.** An agent records a role, instructions and a *label* for the
   preferred model. Four base templates are installed once and never overwritten.
3. **Model output is never authority.** Proposals (`AIWB_MANAGER_PROPOSAL`) and handoffs (`AIWB_HANDOFF`)
   are parsed only after the raw answer is stored in the Response Inbox; nothing changes until the user
   reviews it. Completion is derived from the acceptance policy plus *verified* evidence (process
   runner, GitHub Actions via Sync & Build, Git, user review) for the current task revision.
4. **Contracts are generated from code.** `tools/gen_v2_contracts.py` writes `agent-task.v1`,
   `handoff.v1`, `project-state.v1`; CI fails on drift (`--check`) and validates real producer output.
5. **Publishing is a projection.** The snapshot is built from the local store only and published as
   one atomic Git-Data commit to a dedicated branch (`aiwb-state`). The default branch is refused, no
   force push; a moved remote head or a foreign project pauses publishing instead of overwriting.
   Prompt/response text and local paths are not published.
6. **Simple and Advanced are views.** `ProjectsController` holds all behaviour; the Tk window only calls it.

## Consequences
* Mobile Companion can read `project-state.v1` without new server infrastructure.
* Concurrent writers on two devices are detected (`conflict`) but not merged automatically.
