#!/usr/bin/env python3
"""Performance / packaging baseline for the Workspace roadmap (stage 0, Gate F).

    xvfb-run -a python tools/measure_baseline.py [--json out.json] [--events 5000]

Measures, on the machine it runs on (record the machine with the numbers):
* import time of the app module and of the V2 services;
* cold construction of the main window (``WorkbenchApp``) until idle;
* open-project time of the V2 ProjectsController on a synthetic project
  (N tasks, M events) and the Workspace read models when they exist;
* max RSS of the process;
* installer payload size from ``release_manifest.json`` sources.
Numbers are evidence for ADR-008 / the release gate, not guarantees.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "apps/desktop/src"
sys.path.insert(0, str(SRC))


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def synthetic_project(root: Path, n_tasks: int, n_events: int) -> None:
    from aiwb.v2 import V2Project
    p = V2Project(root, "baseline")
    p.open()
    with p.store.transaction("baseline seed") as s:
        from aiwb.v2.store import emit
        for i in range(n_tasks):
            tid = f"TASK-{i + 1:04d}"
            s["tasks"][tid] = {"schema_version": "1.0", "task_id": tid, "task_revision": 1, "project_id": "baseline",
                               "title": f"Synthetic task {i + 1}", "objective": "x", "task_type": "implementation",
                               "owner_agent_id": "agent-implementer", "reviewer_agent_ids": [], "depends_on": [],
                               "scope": {"include": [f"mod{i}/**"], "exclude": []}, "acceptance_criteria": ["ok"],
                               "acceptance_policy": "review_and_evidence", "deliverables": [], "context_refs": [],
                               "priority": "medium", "risk_level": "medium", "required_approvals": ["review"],
                               "origin": "manual", "status": "ready", "revisions": [], "flags": [],
                               "created_at": "2026-10-18T00:00:00Z", "updated_at": "2026-10-18T00:00:00Z",
                               "base_state_revision": 0, "base_commit_sha": ""}
            s["counters"]["TASK"] = i + 1
        for j in range(n_events):
            emit(s, "task_status", task_id=f"TASK-{j % max(n_tasks, 1) + 1:04d}", old="ready", new="ready", why="seed")


def payload_size() -> dict[str, int]:
    m = json.loads((REPO / "apps/desktop/release_manifest.json").read_text(encoding="utf-8"))
    total, files = 0, 0
    for e in m["payload"]:
        f = REPO / e["source"]
        if f.is_file():
            total += f.stat().st_size
            files += 1
    return {"payload_files": files, "payload_bytes": total}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--tasks", type=int, default=200)
    ap.add_argument("--events", type=int, default=2000)
    ap.add_argument("--repeat", type=int, default=5)
    a = ap.parse_args()
    out: dict = {"machine": {"platform": platform.platform(), "python": platform.python_version(),
                             "cpu_count": os.cpu_count()}}
    t0 = time.perf_counter()
    import AI_Workbench as wb  # noqa: F401
    out["import_app_ms"] = _ms(t0)
    t0 = time.perf_counter()
    import aiwb.v2  # noqa: F401
    out["import_v2_ms"] = _ms(t0)
    try:
        import tkinter as tk
        root = tk.Tk()
        os.environ.setdefault("LOCALAPPDATA", tempfile.mkdtemp(prefix="aiwb-baseline-appdata-"))
        t0 = time.perf_counter()
        app = wb.WorkbenchApp(root)
        root.update()
        out["main_window_ms"] = _ms(t0)
        del app
        root.destroy()
    except Exception as exc:  # noqa: BLE001 - no display: record NOT RUN instead of failing
        out["main_window_ms"] = f"NOT RUN ({type(exc).__name__})"
    from aiwb.v2.controller import ProjectsController
    with tempfile.TemporaryDirectory(prefix="aiwb-baseline-") as tmp:
        root_dir = Path(tmp)
        synthetic_project(root_dir, a.tasks, a.events)
        size = (root_dir / ".workbench/v2/state.json").stat().st_size
        opens, reads = [], {}
        for _ in range(a.repeat):
            t0 = time.perf_counter()
            ctl = ProjectsController(root_dir)
            ctl.next_action_text()
            ctl.task_rows()
            opens.append(_ms(t0))
        out["open_project"] = {"tasks": a.tasks, "events_kept": len(ctl.state()["events"]), "state_bytes": size,
                               "median_ms": statistics.median(opens), "max_ms": max(opens)}
        try:
            from aiwb.workspace.controller import WorkspaceController
            wc = WorkspaceController(ctl)
        except ImportError:  # older versions without the workspace
            wc = None
        if wc is not None:
            calls = {"overview": wc.overview, "task_rows": wc.task_rows, "timeline_page": wc.timeline_page,
                     "timeline_lanes": getattr(wc, "timeline_lanes", None), "team_rows": wc.team_rows,
                     "attention": getattr(wc, "attention", None), "dashboard": getattr(wc, "dashboard", None)}
            for name, fn in calls.items():
                if callable(fn):
                    ts = []
                    for _ in range(a.repeat):
                        t0 = time.perf_counter()
                        fn()
                        ts.append(_ms(t0))
                    reads[name] = statistics.median(ts)
            out["ledger_records"] = ctl.project.store.ledger.count()
        out["read_models_median_ms"] = reads or "n/a (workspace read models not present)"
    out["max_rss_mib"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    out.update(payload_size())
    text = json.dumps(out, indent=2, ensure_ascii=False)
    print(text)
    if a.json:
        Path(a.json).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
