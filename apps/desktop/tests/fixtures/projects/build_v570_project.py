"""Build ``v5.7.0_todo.zip``: a half-done project made by the REAL AI Workbench 5.7.0 code (roadmap 5.15.0, S6).

Run it with the 5.7.0 sources checked out next to the repo, e.g.::

    git worktree add ../aiwb570 desktop-v5.7.0
    python apps/desktop/tests/fixtures/projects/build_v570_project.py ../aiwb570

What the 5.7.0 code does: a project folder ``Todo 570`` with one file of the user's (``src/todo/__init__.py``) →
the project manager's charter (the contract fixture) → the plan accepted (3 tasks, the charter's AIs) → the first
task's prompt prepared and copied (``HO-0001`` waits for the chat's answer). The ZIP holds the folder as 5.7.0 left
it (``.workbench/`` included; no absolute paths inside). ``.workbench/`` is git-ignored, hence the ZIP.
"""
from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "Todo 570"


def build(old_repo: Path, out_zip: Path) -> dict:
    sys.path.insert(0, str(old_repo / "apps/desktop/src"))
    import aiwb
    assert aiwb.__version__ == "5.7.0", f"needs the 5.7.0 sources, got {aiwb.__version__}"
    from aiwb.v2.controller import ProjectsController

    with tempfile.TemporaryDirectory(prefix="aiwb-570-") as temp:
        root = Path(temp) / NAME
        (root / "src/todo").mkdir(parents=True)
        (root / "src/todo/__init__.py").write_text("# mine\n", encoding="utf-8")
        ctl = ProjectsController(root)
        charter = json.loads((old_repo / "packages/contracts/fixtures/valid/project-charter.v1.todo.json")
                             .read_text(encoding="utf-8"))
        charter["base_state_revision"] = ctl.state()["state_revision"]
        r = ctl.route_answer("<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(charter) + "\n<<<AIWB_END_PROJECT_CHARTER>>>")
        assert r.kind == "proposal", r.message
        ops = ctl.state()["proposals"][r.reference_id]["operations"]
        ctl.accept_proposal(r.reference_id, [i for i, o in enumerate(ops) if o["valid"]])
        h = ctl.start_task("TASK-0001")
        ctl.mark_copied(h["handoff_id"])
        st = ctl.state()
        for p in root.rglob("*"):
            if p.is_file():
                assert temp not in p.read_text(encoding="utf-8", errors="replace"), f"absolute path in {p}"
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    z.write(p, f"{NAME}/{p.relative_to(root).as_posix()}")
        return {"version": aiwb.__version__, "tasks": sorted(st["tasks"]), "agents": sorted(st["agents"]),
                "handoff": h["handoff_id"], "status": st["handoffs"][h["handoff_id"]]["status"],
                "state_revision": st["state_revision"]}


if __name__ == "__main__":
    print(json.dumps(build(Path(sys.argv[1]).resolve(), HERE / "v5.7.0_todo.zip"), indent=1))
