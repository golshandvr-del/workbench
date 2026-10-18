#!/usr/bin/env python3
"""Generate the three V2 JSON Schemas (agent-task, handoff, project-state) from aiwb.v2.models.

Enums come from the code, so a new status cannot be added without the contract changing too.
`--check` fails when the committed schemas differ from what the code would produce (CI gate).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps/desktop/src"))
from aiwb.v2 import models as m  # noqa: E402

OUT = REPO / "packages/contracts/schemas"
ID = "https://github.com/golshandvr-del/workbench/packages/contracts/schemas/"
S = {"type": "string"}
SA = {"type": "array", "items": S}
INT = {"type": "integer", "minimum": 0}
SHA = {"type": "string", "pattern": "^([0-9a-f]{7,40})?$"}


def obj(props, required, extra=True):
    return {"type": "object", "required": sorted(required), "properties": props, "additionalProperties": extra}


agent = obj({"schema_version": {"const": m.SCHEMA_VERSION}, "agent_id": {"type": "string", "pattern": "^agent-[a-z0-9-]{1,40}$"},
             "name": S, "role": {"enum": list(m.ROLES)}, "purpose": S, "instructions": SA, "allowed_task_types": SA,
             "preferred_model_label": S, "enabled": {"type": "boolean"}, "revision": {"type": "integer", "minimum": 1}},
            ["schema_version", "agent_id", "name", "role", "revision", "enabled"])
task = obj({"schema_version": {"const": m.SCHEMA_VERSION}, "task_id": {"type": "string", "pattern": "^TASK-[0-9]{4,}$"},
            "task_revision": {"type": "integer", "minimum": 1}, "project_id": S, "title": {"type": "string", "minLength": 1},
            "objective": S, "status": {"enum": list(m.TASK_STATUSES)}, "owner_agent_id": S,
            "depends_on": {"type": "array", "items": {"type": "string", "pattern": "^TASK-[0-9]{4,}$"}, "uniqueItems": True},
            "acceptance_criteria": SA, "acceptance_policy": {"enum": list(m.ACCEPTANCE_POLICIES)}, "required_approvals": SA,
            "scope": {"type": "object"}, "priority": S, "base_commit_sha": SHA, "active_attempt_id": S},
           ["schema_version", "task_id", "task_revision", "title", "status", "depends_on", "acceptance_policy"])
agent_task = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": ID + "agent-task.v1.schema.json",
              "title": "AI Workbench V2 Agent/Task contract", "type": "object", "required": ["agents", "tasks"],
              "properties": {"agents": {"type": "array", "items": agent}, "tasks": {"type": "array", "items": task}},
              "$defs": {"agent": agent, "task": task}}

manifest = obj({"schema_version": {"const": m.SCHEMA_VERSION}, "handoff_id": {"type": "string", "pattern": "^HO-[0-9]{4,}$"},
                "task_id": {"type": "string", "pattern": "^TASK-[0-9]{4,}$"}, "task_revision": {"type": "integer", "minimum": 1},
                "attempt_id": {"type": "string", "pattern": "^att-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$"},
                "outcome": {"enum": list(m.HANDOFF_OUTCOMES)}, "summary": S, "completed_items": SA, "unresolved_items": SA,
                "assumptions": SA, "decision_requests": SA, "validation_claims": SA, "recommended_next_action": S,
                "artifacts": {"type": "array", "items": obj({"logical_path": S, "sha256": SHA}, ["logical_path"])}},
               ["schema_version", "handoff_id", "task_id", "task_revision", "attempt_id", "outcome", "summary"])
handoff = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": ID + "handoff.v1.schema.json",
           "title": "AI Workbench V2 Handoff manifest (model answer inside <<<AIWB_HANDOFF>>>)", **manifest,
           "$defs": {"handoff_status": {"enum": list(m.HANDOFF_STATUSES)}}}

ev = obj({"schema_version": {"const": m.SCHEMA_VERSION}, "evidence_id": {"type": "string", "pattern": "^EV-[0-9]{4,}$"},
          "type": {"enum": list(m.EVIDENCE_TYPES)}, "subject_type": S, "subject_id": S, "result": S,
          "verified": {"type": "boolean"},
          "source": obj({"kind": {"enum": list(m.EVIDENCE_SOURCES)}, "run_id": S, "commit_sha": S}, ["kind"]),
          "task_revision": INT, "observed_at_utc": S},
         ["schema_version", "evidence_id", "type", "subject_id", "result", "verified", "source"])
ev["allOf"] = [{"if": {"properties": {"source": {"properties": {"kind": {"const": "model"}}}}},
                "then": {"properties": {"verified": {"const": False}}}}]
snap_task = obj({"task_id": {"type": "string"}, "task_revision": INT, "title": S, "status": {"enum": list(m.TASK_STATUSES)},
                 "owner_agent_id": S, "depends_on": SA, "blocked_reason": S, "verified_evidence_ids": SA},
                ["task_id", "task_revision", "status"])
ids = {"type": "array", "items": S}
state = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": ID + "project-state.v1.schema.json",
         "title": "AI Workbench V2 Project State Snapshot (.aiwb/project-state.json) and Evidence record",
         **obj({"schema_version": {"const": m.SCHEMA_VERSION}, "project_id": {"type": "string", "minLength": 1},
                "state_revision": INT, "generated_at_utc": S, "content_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "previous_snapshot_hash": {"type": "string", "pattern": "^([0-9a-f]{64})?$"},
                "source": obj({"repository": S, "branch": S, "commit_sha": S, "local_changes_pending": {"type": "boolean"},
                               "local_changes_count": INT}, ["commit_sha", "local_changes_pending"]),
                "summary": obj({k: INT for k in ("total_tasks", "active_tasks", "blocked_tasks", "needs_decision",
                                                 "awaiting_review", "validation_pending", "verified_complete")},
                               ["total_tasks", "verified_complete"]),
                "active_task_ids": ids, "blocked_task_ids": ids, "needs_decision_task_ids": ids, "done_task_ids": ids,
                "open_decision_ids": ids, "accepted_decisions": {"type": "array"}, "last_verified_evidence_id": S,
                "last_published_state_revision": INT,
                "next_action": {"type": ["object", "null"]}, "tasks": {"type": "array", "items": snap_task}},
               ["schema_version", "project_id", "state_revision", "content_hash", "source", "summary", "tasks"]),
         "$defs": {"evidence": ev}}

FILES = {"agent-task.v1.schema.json": agent_task, "handoff.v1.schema.json": handoff, "project-state.v1.schema.json": state}


def main() -> int:
    check = "--check" in sys.argv
    bad = []
    for name, data in FILES.items():
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        p = OUT / name
        if check:
            if not p.exists() or p.read_text(encoding="utf-8") != text:
                bad.append(name)
        else:
            p.write_text(text, encoding="utf-8")
    if bad:
        print("FAIL: V2 schemas out of date (run tools/gen_v2_contracts.py):", ", ".join(bad))
        return 1
    print(("PASS: V2 schemas match aiwb.v2.models" if check else "wrote") + f" ({len(FILES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
