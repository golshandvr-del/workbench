"""Right-click menu of a Mission Map column — a milestone or a version (roadmap 5.13.0, owner audit B3; no Tk).

5.13.0 rule: **Home = now and next, History = the past.** Milestones and versions live on the map as its dashed
columns, so what the Workbench's Timeline tab did for them is done here, on the column itself:

* ACCEPT MILESTONE — enabled only when the Guide offers that step now (all its tasks are done);
* RECORD RELEASE — enabled only when the Guide offers the release of that version (its milestones are accepted);
* NEW MILESTONE… — groups the open tasks of this column under a new milestone (asks only the title);
* PROPOSE VERSION… — a new version, made of this column's milestone when the column is one.

Like :mod:`task_menu`, a row never invents a transition the Guide would refuse; rows carry the same keys
(``id``, ``label``, ``icon``, ``enabled``, ``step``, ``action``, ``needs``, ``hint``) so :class:`menu5.FloatingMenu`
draws them unchanged.
"""
from __future__ import annotations

from typing import Any

COLUMN_MENU: tuple[tuple[str, str, str], ...] = (
    ("accept_milestone", "ACCEPT MILESTONE", "check"),
    ("record_release", "RECORD RELEASE", "send"),
    ("new_milestone", "NEW MILESTONE", "plus_circle"),
    ("propose_version", "PROPOSE VERSION", "sparkle"),
)

DISABLED_HINT = {
    "accept_milestone": "Its tasks are not all done yet.",
    "record_release": "Accept its milestones first.",
    "new_milestone": "No open task in this column.",
    "propose_version": "",
}
DONE_TASK = ("done", "cancelled", "superseded")


def column_tasks(model: dict[str, Any], index: int, *, open_only: bool = True) -> list[str]:
    """Task ids drawn in column ``index`` of a :func:`mission_model.build` result (open ones only by default)."""
    out = []
    for lane in model.get("lanes", []):
        for nd in lane.get("nodes", []):
            if nd.get("column") == index and not (open_only and nd.get("status") in DONE_TASK):
                out.append(str(nd["task_id"]))
    return sorted(out)


def items(steps: list[dict[str, Any]], model: dict[str, Any], index: int) -> list[dict[str, Any]]:
    """Menu rows for column ``index`` of ``model`` given the Guide's current ``steps``."""
    col = model["columns"][index]
    kind, key = col.get("kind", ""), str(col.get("key", ""))
    rows = []
    for item_id, label, icon in COLUMN_MENU:
        row = {"id": item_id, "label": label, "icon": icon, "enabled": False, "step": "", "action": "", "needs": [],
               "hint": DISABLED_HINT[item_id], "column": key, "kind": kind}
        if item_id == "accept_milestone":
            if kind != "milestone":
                continue
            st = next((s for s in steps if s["key"] == f"milestone:{key}"), None)
            if st is not None:
                row.update(enabled=True, step=st["key"], action="accept_milestone", hint=st["title"])
            elif col.get("status") == "accepted":
                row["hint"] = "Already accepted."
        elif item_id == "record_release":
            if kind != "version":
                continue
            st = next((s for s in steps if s["key"] in (f"version:{key}", f"github:release:{key}")), None)
            if st is not None:
                act = next((a for a in st["actions"] if a["id"] in ("release", "prepare_release")), None)
                if act is not None:
                    row.update(enabled=True, step=st["key"], action=act["id"], needs=list(act.get("needs", [])),
                               hint=st["title"])
            elif col.get("status") == "released":
                row["hint"] = "Already released."
        elif item_id == "new_milestone":
            tasks = column_tasks(model, index)
            if tasks:
                row.update(enabled=True, needs=["title"], task_ids=tasks,
                           hint=f"Group the {len(tasks)} open task{'s' if len(tasks) != 1 else ''} of {col['label']}")
        elif item_id == "propose_version":
            row.update(enabled=True, needs=["label"], milestone_ids=[key] if kind == "milestone" else [],
                       hint="A new version" + (f" made of {col['label']}" if kind == "milestone" else ""))
        rows.append(row)
    return rows
