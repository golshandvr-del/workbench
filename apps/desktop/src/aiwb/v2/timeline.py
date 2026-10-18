"""Milestones, Versions, progress indicators and timeline lanes (roadmap 2.5.0 / stage 6, spec §5, §6, Gate D).

* Milestone, Version and Release are separate entities (spec §5.1); no forced task↔version mapping.
* A version moves ``proposed → local → tagged → released`` only by explicit user/tool facts; "released"
  needs a real reference (run id, artifact or commit) — never shown as released without one (§5.5).
* Progress is computed, never asked from a model (§6): ``n of m tasks verified`` plus separate counts;
  a weighted figure exists only when the user set weights and is always labelled *estimated*.
* Lanes are a read projection of the Event Ledger per agent (§5.4); a lane is not a git branch.
"""
from __future__ import annotations

import re
from typing import Any

from .models import SCHEMA_VERSION, ModelError, now_utc
from .store import ProjectStore, emit, next_id, require

VERSION_STATES = ("proposed", "local", "tagged", "released", "withdrawn")
_VERSION_FLOW = {"proposed": {"local", "tagged", "withdrawn"}, "local": {"tagged", "withdrawn"},
                 "tagged": {"released", "withdrawn"}, "released": set(), "withdrawn": set()}
MILESTONE_STATES = ("planned", "accepted", "dropped")
_SEMVER = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_SHA = re.compile(r"^[0-9a-f]{7,64}$")
OUT_OF_SCOPE = ("cancelled", "superseded")


def _txt(v: Any, name: str, limit: int, required: bool = False) -> str:
    s = str(v or "").strip()
    if required and not s:
        raise ModelError(f"{name} is required")
    if len(s) > limit:
        raise ModelError(f"{name} is longer than {limit} characters")
    return s


def _task_ids(s: dict[str, Any], ids: Any) -> list[str]:
    out = []
    for t in ids or []:
        require(s, "tasks", str(t))
        if t not in out:
            out.append(str(t))
    return out


class TimelineService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    # -- milestones
    def milestones(self) -> list[dict[str, Any]]:
        return sorted(self.store.load()["milestones"].values(), key=lambda m: m["milestone_id"])

    def create_milestone(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.store.transaction("milestone created") as s:
            mid = next_id(s, "milestone")
            m = {"schema_version": SCHEMA_VERSION, "milestone_id": mid,
                 "title": _txt(data.get("title"), "title", 200, True),
                 "criteria": [_txt(c, "criterion", 500) for c in (data.get("criteria") or []) if str(c).strip()][:30],
                 "task_ids": _task_ids(s, data.get("task_ids")), "status": "planned",
                 "target_date": _txt(data.get("target_date"), "target_date", 20), "accepted_at": "",
                 "created_at": now_utc(), "updated_at": now_utc()}
            s["milestones"][mid] = m
            emit(s, "milestone_created", milestone_id=mid, task_ids=m["task_ids"])
            return m

    def update_milestone(self, milestone_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self.store.transaction("milestone updated") as s:
            m = require(s, "milestones", milestone_id)
            if m["status"] != "planned":
                raise ModelError(f"{milestone_id} is {m['status']}; only planned milestones can change")
            if "title" in changes:
                m["title"] = _txt(changes["title"], "title", 200, True)
            if "task_ids" in changes:
                m["task_ids"] = _task_ids(s, changes["task_ids"])
            if "criteria" in changes:
                m["criteria"] = [_txt(c, "criterion", 500) for c in changes["criteria"] if str(c).strip()][:30]
            m["updated_at"] = now_utc()
            emit(s, "milestone_updated", milestone_id=milestone_id, task_ids=m["task_ids"])
            return m

    def accept_milestone(self, milestone_id: str, *, force: bool = False) -> dict[str, Any]:
        """User acceptance; refused while a linked task is not done unless ``force`` (recorded)."""
        with self.store.transaction("milestone accepted") as s:
            m = require(s, "milestones", milestone_id)
            if m["status"] != "planned":
                raise ModelError(f"{milestone_id} is already {m['status']}")
            open_ = [t for t in m["task_ids"] if s["tasks"][t]["status"] not in ("done",) + OUT_OF_SCOPE]
            if open_ and not force:
                raise ModelError(f"{milestone_id} still has open tasks: {', '.join(open_)}")
            m.update(status="accepted", accepted_at=now_utc(), updated_at=now_utc(), accepted_with_open=open_)
            emit(s, "milestone_accepted", milestone_id=milestone_id, open_tasks=open_)
            return m

    def drop_milestone(self, milestone_id: str) -> dict[str, Any]:
        with self.store.transaction("milestone dropped") as s:
            m = require(s, "milestones", milestone_id)
            if m["status"] != "planned":
                raise ModelError(f"{milestone_id} is {m['status']}")
            m.update(status="dropped", updated_at=now_utc())
            emit(s, "milestone_dropped", milestone_id=milestone_id)
            return m

    def milestone_progress(self, milestone_id: str) -> dict[str, Any]:
        st = self.store.load()
        m = require(st, "milestones", milestone_id)
        return progress(st, task_ids=m["task_ids"])

    # -- versions
    def versions(self) -> list[dict[str, Any]]:
        return sorted(self.store.load()["versions"].values(), key=lambda v: v["version_id"])

    def propose_version(self, data: dict[str, Any]) -> dict[str, Any]:
        label = _txt(data.get("label"), "label", 60, True)
        policy = data.get("policy") or "semver"
        if policy == "semver" and not _SEMVER.match(label):
            raise ModelError(f"{label!r} is not a semantic version (e.g. 1.2.0); choose policy 'free' for other labels")
        with self.store.transaction("version proposed") as s:
            if any(v["label"] == label and v["status"] != "withdrawn" for v in s["versions"].values()):
                raise ModelError(f"version {label} already exists")
            vid = next_id(s, "version")
            v = {"schema_version": SCHEMA_VERSION, "version_id": vid, "label": label, "policy": policy,
                 "status": "proposed", "source": data.get("source") if data.get("source") in ("user", "model") else "user",
                 "task_ids": _task_ids(s, data.get("task_ids")),
                 "milestone_ids": [require(s, "milestones", m)["milestone_id"] for m in data.get("milestone_ids") or []],
                 "notes": _txt(data.get("notes"), "notes", 2000), "commit_sha": "", "tag": "", "run_id": "",
                 "artifact": "", "artifact_sha256": "", "history": [], "created_at": now_utc(), "updated_at": now_utc()}
            s["versions"][vid] = v
            emit(s, "version_proposed", version_id=vid, label=label, source=v["source"])
            return v

    def advance_version(self, version_id: str, status: str, **facts: Any) -> dict[str, Any]:
        """Explicit fact: local (commit), tagged (tag+commit), released (run id or artifact), withdrawn."""
        with self.store.transaction(f"version {status}") as s:
            v = require(s, "versions", version_id)
            if status not in _VERSION_FLOW.get(v["status"], set()):
                raise ModelError(f"{version_id} cannot go from {v['status']} to {status}")
            for k in ("commit_sha", "tag", "run_id", "artifact", "artifact_sha256"):
                if facts.get(k):
                    val = _txt(facts[k], k, 300)
                    if k in ("commit_sha", "artifact_sha256") and not _SHA.match(val.lower()):
                        raise ModelError(f"{k} must be a hex hash")
                    v[k] = val
            if status in ("local", "tagged") and not v["commit_sha"]:
                raise ModelError(f"{status} needs the commit SHA it points to")
            if status == "tagged" and not v["tag"]:
                raise ModelError("tagged needs the tag name")
            if status == "released" and not (v["run_id"] or v["artifact"]):
                raise ModelError("released needs a real build/run id or artifact; Workbench never assumes a release")
            old = v["status"]
            v["history"].append({"from": old, "to": status, "at": now_utc()})
            v.update(status=status, updated_at=now_utc())
            etype = {"released": "release_published", "withdrawn": "version_withdrawn"}.get(status, "version_created")
            emit(s, etype, version_id=version_id, label=v["label"], old=old, new=status, commit_sha=v["commit_sha"],
                 run_id=v["run_id"])
            return v


# -- progress (§6) ------------------------------------------------------------
def progress(state: dict[str, Any], *, task_ids: list[str] | None = None) -> dict[str, Any]:
    tasks = [state["tasks"][t] for t in task_ids if t in state["tasks"]] if task_ids is not None \
        else list(state["tasks"].values())
    scope = [t for t in tasks if t["status"] not in OUT_OF_SCOPE]
    by = lambda *sts: sum(1 for t in scope if t["status"] in sts)  # noqa: E731
    done = by("done")
    out = {"done": done, "total": len(scope), "percent": round(100 * done / len(scope)) if scope else 0,
           "excluded": len(tasks) - len(scope), "validation_pending": by("validation_pending"),
           "in_review": by("in_review"), "blocked": by("blocked"), "needs_decision": by("needs_decision"),
           "in_progress": by("in_progress"), "not_started": by("draft", "proposed", "ready"),
           "weighted": None}
    weights = (state["settings"].get("task_weights") or {})
    if scope and all(isinstance(weights.get(t["task_id"]), (int, float)) and weights[t["task_id"]] > 0 for t in scope):
        tot = sum(weights[t["task_id"]] for t in scope)
        out["weighted"] = {"percent": round(100 * sum(weights[t["task_id"]] for t in scope if t["status"] == "done") / tot),
                           "estimated": True, "method": "user-set task weights"}
    crit = [c for t in scope for c in t.get("acceptance_criteria", [])]
    out["criteria_total"] = len(crit)
    out["criteria_in_done_tasks"] = sum(len(t.get("acceptance_criteria", [])) for t in scope if t["status"] == "done")
    return out


def set_task_weights(store: ProjectStore, weights: dict[str, float]) -> dict[str, float]:
    with store.transaction("task weights") as s:
        clean = {}
        for tid, w in weights.items():
            require(s, "tasks", tid)
            w = float(w)
            if w <= 0 or w > 1000:
                raise ModelError("weights must be between 0 and 1000")
            clean[tid] = w
        s["settings"]["task_weights"] = clean
        emit(s, "project_settings_updated", field="task_weights", count=len(clean))
        return clean


# -- lanes (§5.4) -------------------------------------------------------------
def lanes(records: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Group ledger records (oldest first) by agent; records without an agent go to 'project'."""
    owner = {tid: t.get("owner_agent_id", "") for tid, t in state["tasks"].items()}
    out: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        refs = rec.get("refs", {})
        lane = refs.get("agent_id") or refs.get("to_agent_id") or owner.get(refs.get("task_id", ""), "") or "project"
        out.setdefault(lane, []).append(rec)
    return out


def planned_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Future items (milestone targets, proposed versions) — always marked planned, never mixed with history."""
    out = [{"kind": "milestone", "ref": m["milestone_id"], "title": m["title"], "date": m.get("target_date", ""),
            "planned": True} for m in state["milestones"].values() if m["status"] == "planned"]
    out += [{"kind": "version", "ref": v["version_id"], "title": v["label"], "date": "", "planned": True,
             "status": v["status"]} for v in state["versions"].values() if v["status"] in ("proposed", "local")]
    return out
