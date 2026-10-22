#!/usr/bin/env python3
"""Write packages/contracts/fixtures/mission/mission-map.v1.json (roadmap 6.1.0).

Each case is a V2 project state, view options, and the Mission Map that the desktop ``aiwb.ui.mission_model.build``
returns for it. The mobile ``MissionModelTest`` builds the same cases and must get the same map (parity gate);
desktop ``test_mission_fixture`` fails when this file is stale.

    python tools/gen_mission_fixture.py          # write
    python tools/gen_mission_fixture.py --check  # exit 1 when the file differs
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "desktop" / "src"))

from aiwb.ui import mission_model as mm  # noqa: E402

OUT = ROOT / "packages" / "contracts" / "fixtures" / "mission" / "mission-map.v1.json"


def five_ai() -> dict:
    agents = {f"a{i}": {"agent_id": f"a{i}", "name": f"Agent {i}", "role": "implementer"} for i in range(1, 6)}
    agents["pm"] = {"agent_id": "pm", "name": "PM", "role": "project_manager"}
    tasks, versions = {}, {}
    for vi, lab in enumerate(["1.0.0", "0.2.0", "0.10.0", "0.1.0"]):
        ids = []
        for a in range(1, 6):
            tid = f"t-{lab}-{a}"
            ids.append(tid)
            tasks[tid] = {"task_id": tid, "title": f"{lab} #{a}", "status": "draft", "owner_agent_id": f"a{a}"}
        versions[f"v{vi}"] = {"version_id": f"v{vi}", "label": lab, "status": "planned", "task_ids": ids}
    return {"project_id": "p", "agents": agents, "tasks": tasks, "versions": versions, "milestones": {},
            "handoffs": {}, "state_revision": 3}


def cases() -> list[dict]:
    out = [{"name": "empty", "state": {}, "options": {}}]
    out.append({"name": "five_ai_semver", "state": five_ai(), "options": {}})

    st = five_ai()
    st["milestones"] = {"m1": {"milestone_id": "m1", "status": "planned", "task_ids": ["extra"]}}
    st["tasks"]["extra"] = {"task_id": "extra", "title": "x", "status": "in_progress", "owner_agent_id": "a2"}
    st["versions"]["v1"]["milestone_ids"] = ["m1"]
    st["tasks"]["loose"] = {"task_id": "loose", "title": "l", "status": "draft", "owner_agent_id": "a1"}
    st["tasks"]["gone"] = {"task_id": "gone", "title": "g", "status": "cancelled", "owner_agent_id": "a1"}
    st["tasks"]["orphan"] = {"task_id": "orphan", "title": "o", "status": "blocked", "owner_agent_id": "ghost"}
    st["tasks"]["t-0.1.0-4"]["status"] = "needs_decision"
    st["versions"]["v0"]["status"] = "withdrawn"
    st["handoffs"] = {"h": {"handoff_id": "h", "task_id": "t-0.1.0-3", "status": "prompt_exported"}}
    out.append({"name": "mixed_states_later_unassigned", "state": st, "options": {}})

    st = five_ai()
    st["versions"] = {}
    out.append({"name": "no_versions_next", "state": copy.deepcopy(st), "options": {}})
    st["milestones"] = {"m1": {"milestone_id": "m1", "title": "Alpha", "status": "planned",
                               "task_ids": sorted(st["tasks"])[:10]},
                        "m2": {"milestone_id": "m2", "title": "Beta", "status": "dropped", "task_ids": []}}
    out.append({"name": "milestones_as_columns", "state": st, "options": {}})

    st = five_ai()
    st["tasks"], st["versions"] = {}, {}
    out.append({"name": "team_without_tasks", "state": st, "options": {}})

    st = five_ai()
    for tid, t in st["tasks"].items():
        if t["owner_agent_id"] == "a2" or tid.startswith("t-0.1.0-"):
            t["status"] = "done"
    for opts in ({}, {"hide_done": True}, {"open_only": True}, {"hide_done": True, "open_only": True}):
        out.append({"name": "view_options_" + ("_".join(sorted(opts)) or "none"), "state": copy.deepcopy(st),
                    "options": opts})
    for c in out:
        c["expect"] = mm.build(c["state"], **c["options"])
    return out


def render() -> str:
    doc = {"schema": "aiwb-mission-map-fixture.v1", "producer": "apps/desktop/src/aiwb/ui/mission_model.py",
           "cases": cases()}
    return json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            print(f"FAIL: {OUT.relative_to(ROOT)} is stale; run python tools/gen_mission_fixture.py")
            return 1
        print("PASS: mission fixture up to date")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
