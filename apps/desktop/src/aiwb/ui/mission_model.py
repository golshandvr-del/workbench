"""Mission Map model (roadmap 5.2.0): parallel timelines, one lane per AI, one circle per task in its version's column.

:func:`build` turns the V2 project state into plain data (no Tk); :func:`layout` turns that data into pixel
positions for a given DPI scale. Both are pure and unit-tested; :mod:`mission_canvas` only draws the result.
Reading the state never writes it.

Columns are the project's versions in semantic-version order (withdrawn ones left out). Without versions the
milestones are the columns; without either there is one column, ``Next``. A task belongs to the column of the
version that lists it (directly or through one of the version's milestones), else of the milestone that lists it;
tasks that no column claims go to a trailing ``Later`` column. Several tasks of one AI in one column sit side by
side (``slot``), so every column is as wide as its busiest lane.
"""
from __future__ import annotations

import re
from typing import Any

from .tokens5 import GEOMETRY

HIDDEN_TASK = ("cancelled", "superseded")
ACTIVE_TASK = ("ready", "in_progress", "in_review", "validation_pending")
OPEN_HANDOFF = ("prepared", "prompt_exported", "response_received", "parsed", "reconciled", "stale",
                "reconciliation_required")
NODE_STATES = ("done", "active", "blocked", "attention", "idle")
LATER = "Later"
NEXT = "Next"

_NUM = re.compile(r"\d+")


def _semver_key(label: str) -> tuple[Any, ...]:
    nums = [int(n) for n in _NUM.findall(label)[:3]]
    return (0, *(nums + [0, 0, 0])[:3], label) if nums else (1, 0, 0, 0, label)


def node_state(task: dict[str, Any], *, handoff_open: bool = False) -> str:
    """How a task circle looks: done (green tick) · active (glowing blue) · blocked · attention · idle (grey)."""
    st = task.get("status")
    if st == "done":
        return "done"
    if st == "blocked":
        return "blocked"
    if st == "needs_decision":
        return "attention"
    if st in ACTIVE_TASK or handoff_open:
        return "active"
    return "idle"


def _columns(state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Ordered columns and task id → column index."""
    versions = [v for v in (state.get("versions") or {}).values() if v.get("status") != "withdrawn"]
    milestones = {m.get("milestone_id"): m for m in (state.get("milestones") or {}).values()
                  if m.get("status") != "dropped"}
    cols: list[dict[str, Any]] = []
    owner: dict[str, int] = {}
    if versions:
        for v in sorted(versions, key=lambda v: _semver_key(str(v.get("label", "")))):
            ids = list(v.get("task_ids") or [])
            for mid in v.get("milestone_ids") or []:
                ids += list((milestones.get(mid) or {}).get("task_ids") or [])
            cols.append({"key": str(v.get("version_id", "")), "label": str(v.get("label", "")), "kind": "version",
                         "status": str(v.get("status", "")), "task_ids": ids})
    elif milestones:
        for m in sorted(milestones.values(), key=lambda m: str(m.get("milestone_id", ""))):
            cols.append({"key": str(m.get("milestone_id", "")), "label": str(m.get("title") or m.get("milestone_id")),
                         "kind": "milestone", "status": str(m.get("status", "")),
                         "task_ids": list(m.get("task_ids") or [])})
    for i, c in enumerate(cols):
        for tid in c.pop("task_ids"):
            owner.setdefault(tid, i)
    return cols, owner


def build(state: dict[str, Any] | None, *, hide_done: bool = False, open_only: bool = False) -> dict[str, Any]:
    """The Mission Map as data: ``columns``, ``lanes`` (each with its ``nodes``), ``slots`` per column, counts.

    View options (5.7.0, Home): ``hide_done`` leaves finished task circles out; ``open_only`` leaves out the lanes
    with no unfinished task. Lane numbers and ``counts`` always describe the whole project, so "AI 3" stays AI 3.
    """
    if not state:
        return {"columns": [], "lanes": [], "slots": [], "empty": True, "counts": {s: 0 for s in NODE_STATES}}
    agents = state.get("agents") or {}
    tasks = {tid: t for tid, t in (state.get("tasks") or {}).items() if t.get("status") not in HIDDEN_TASK}
    open_h = {h.get("task_id") for h in (state.get("handoffs") or {}).values() if h.get("status") in OPEN_HANDOFF}
    cols, owner = _columns(state)
    if not cols:
        cols = [{"key": "next", "label": NEXT, "kind": "next", "status": ""}]
    unplaced = [tid for tid in tasks if tid not in owner]
    if unplaced and any(c["kind"] != "next" for c in cols):
        cols.append({"key": "later", "label": LATER, "kind": "later", "status": ""})
    fallback = len(cols) - 1
    by_lane: dict[str, list[str]] = {}
    for tid in sorted(tasks):
        aid = str(tasks[tid].get("owner_agent_id") or "")
        if not aid or (agents and aid not in agents):
            aid = "unassigned"
        by_lane.setdefault(aid, []).append(tid)
    if not by_lane:  # a planned team without tasks still shows its lanes
        for aid, a in sorted(agents.items()):
            if a.get("enabled", True) and a.get("role") != "project_manager":
                by_lane[aid] = []
    slots = [1] * len(cols)
    lanes = []
    counts = {s: 0 for s in NODE_STATES}
    order = {a: k for k, a in enumerate((state.get("settings") or {}).get("team_order") or [])}  # 5.9.0: user's order
    for i, aid in enumerate(sorted(by_lane, key=lambda a: (a == "unassigned", order.get(a, len(order)), a))):
        per_col: dict[int, int] = {}
        nodes = []
        states = [node_state(tasks[tid], handoff_open=tid in open_h) for tid in by_lane[aid]]
        for ns in states:
            counts[ns] += 1
        if open_only and by_lane[aid] and all(ns == "done" for ns in states):
            continue
        for tid, ns in zip(by_lane[aid], states):
            if hide_done and ns == "done":
                continue
            t = tasks[tid]
            col = owner.get(tid, fallback)
            slot = per_col.get(col, 0)
            per_col[col] = slot + 1
            slots[col] = max(slots[col], slot + 1)
            nodes.append({"task_id": tid, "title": str(t.get("title") or tid), "status": str(t.get("status", "")),
                          "state": ns, "column": col, "slot": slot})
        a = agents.get(aid) or {}
        lanes.append({"agent_id": aid, "number": i + 1, "name": str(a.get("name") or aid),
                      "role": str(a.get("role", "")), "nodes": nodes,
                      "live": any(n["state"] == "active" for n in nodes)})
    return {"columns": cols, "lanes": lanes, "slots": slots, "empty": not lanes, "counts": counts}


def layout(model: dict[str, Any], scale: float = 1.0) -> dict[str, Any]:
    """Pixel positions (top-left origin) of every element of :func:`build`'s result for a DPI ``scale``."""
    g, s = GEOMETRY, scale
    lane_gap, col_gap = g["lane_gap"] * s, g["col_gap"] * s
    top = 64 * s                      # room for version labels
    capsule_x, capsule_w = 16 * s, 132 * s
    source_x = capsule_x + capsule_w + 22 * s
    hex_x = source_x + 72 * s
    first_x = hex_x + 48 * s          # first column's first slot
    n = max(1, len(model["lanes"]))
    lane_y = [top + lane_gap * (i + 0.5) for i in range(n)]
    mid_y = (lane_y[0] + lane_y[-1]) / 2
    col_x, x = [], first_x
    for k in model["slots"]:
        col_x.append(x)
        x += col_gap * k
    end_x = x - col_gap + 46 * s if model["slots"] else first_x + 46 * s
    nodes = {}
    for i, lane in enumerate(model["lanes"]):
        for nd in lane["nodes"]:
            nodes[nd["task_id"]] = (col_x[nd["column"]] + nd["slot"] * col_gap, lane_y[i])
    return {"capsule": (capsule_x, mid_y, capsule_w), "source": (source_x, mid_y), "hex_x": hex_x,
            "lane_y": lane_y, "col_x": col_x, "end_x": end_x, "nodes": nodes, "top": top,
            "width": end_x + 40 * s, "height": top + lane_gap * n + 24 * s}
