# 2.0.0 — Phase-2 Release Gate (Future Roadmap §27) — evidence

| Gate item | Evidence |
|---|---|
| Three contracts (Agent/Task, Handoff, Project State/Evidence) documented and tested | `packages/contracts/schemas/{agent-task,handoff,project-state}.v1.schema.json` generated from `aiwb.v2.models`; valid/invalid fixtures; real producer output validated in `tools/validate_contracts.py`; ADR-006 |
| Task graph validated for dependencies and cycles | `aiwb/v2/tasks.py`; `test_v2_model.py`; proposals rejected when the resulting graph is invalid (`test_v2_flow.py::ProposalTests`) |
| ≥ two agents with different roles in two different chats/models on one project | `test_v2_reference_scenario.py` steps 6–9 (architect, implementer and a copied mobile agent with a different model label; separate handoffs, prompts, answers) |
| Work transfer without previous chat history | self-contained handoff prompt — `test_v2_flow.py::test_second_agent_continues_from_previous_handoff` |
| Old, partial or foreign answers handled | wrong task refused; late → `stale`; revision change → reconciliation; 4/5 files salvaged + focused repair |
| Project manager analyses the snapshot and proposes | `manager_update_prompt` with link + fallback; reference scenario steps 14–15 |
| Proposal reviewed before applying; stale detected | per-operation preview, partial accept, `confirm_stale` |
| Real evidence separate from model reports | `source_kind="model"` ⇒ `verified=false` (code + schema `if/then`); real Actions runs from Sync & Build become `github_actions` evidence (`record_build_evidence`, `BuildEvidenceTests`) |
| Auto-publish: queue, no-op, retry, conflict | `aiwb/v2/publisher.py`; `PublisherTests`; real GitHub API run `docs/release/v1.20.1/V2_E2E_PUBLISHER_REPORT_v1.20.1.md` |
| Fallback inside the prompt when the model cannot read GitHub | `fallback_summary`; `check_probe` |
| No task done only because a model said so | `update_task {"status":"done"}` refused; evaluation needs verified evidence |
| §18 scenario passes without manual DB/file edits | `tests/test_v2_reference_scenario.py` (16 steps + failure variants) via public services; GUI path `gui_projects_smoke.py` |

## Manual checks on a real user machine (release owner)
- [ ] Run §18 once with two real ordinary chats using *Projects (multi-agent)…*.
- [ ] Enable publishing on a bound repository and open `.aiwb/PROJECT_STATUS.md` on `aiwb-state`.
