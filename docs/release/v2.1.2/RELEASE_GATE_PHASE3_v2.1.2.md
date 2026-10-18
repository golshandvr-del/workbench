# 2.1.2 — Phase-3 Release Gate (Future Roadmap §19.5, §22, §28) — evidence

| Gate item | Evidence |
|---|---|
| Simple and Advanced both run on one logic and one data set | `aiwb/v2/controller.py` is the only behaviour; `test_v2_controller.py::test_simple_and_advanced_share_operations` forbids write paths in `projects_window.py` |
| A beginner can do the next step without knowing Agent/Task internals | Simple view: next step, one prompt, Copy, one paste box, plain status words + symbols (`aiwb/i18n.py`); `gui_projects_smoke.py` Prompt → Copy → Paste → Review |
| An advanced user sees everything needed for tracing/debugging | Advanced panels: agents, decisions, evidence (verified/reported, run, commit), attempts/handoffs, proposals (stale), state revision, source commit, publish history, last error |
| GUI adds no behaviour that the central service lacks | same test as row 1; the language and view preferences are display-only (`ui.json`) |
| GUI tests pass in both modes | `gui_phase3_gate_smoke.py` runs every §22 flow in Simple *and* Advanced: plan proposal, broken op refused, blocked / needs-decision tasks, publish with network failure, reopen + queue recovery, Last Published vs Local Revision, view switch with no data change and no new publish |
| Switching UI mode changes no data | `test_v2_controller.py::test_mode_switch_changes_no_data_and_persists`; GUI smokes assert unchanged `state_revision` |
| Statuses not by colour alone; one FA/EN vocabulary | `aiwb/i18n.py` + `check_glossary()`; `test_i18n.py` |
| Clear, prioritised errors; sensitive confirmations default to No | `warning_items()` (blocking → action → info); stale proposal confirmation `default="no"` |
