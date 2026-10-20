"""Completion, expansion or archive — the end of the owner's algorithm (roadmap 4.6.0, flowchart F26–F28).

* F26 ``announce`` — only when the project manager decided that no roadmap stage is left and no task is open:
  a completion summary built from Workbench state (tasks, milestones, released versions with their evidence,
  integrated files) is stored in ``settings.flow.completion`` and put on the timeline (``project_completed``).
* F27 ``expand`` (yes → F1) — starts the next major cycle: the finished cycle is kept in ``settings.flow.history``
  and an *expansion prompt* (history + the user's idea) is ready for the project-manager chat. Its answer is a
  normal ``AIWB_MANAGER_PROPOSAL`` (new milestones / tasks), reviewed like any plan.
* F28 ``archive`` (no) — writes the final ``aiwb-bundle.v1`` to ``.workbench/archive/`` and makes the project
  read-only: ``ProjectStore.transaction`` refuses every change except ``reopen``.

The phone has the same rules in ``core/Closeout.kt``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import ModelError, now_utc
from .store import emit

REOPEN_REASON = "reopen project"
_OPEN = ("done", "cancelled", "superseded")


def _fs(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("settings", {}).get("flow") or {}


def is_archived(state: dict[str, Any]) -> bool:
    return bool(_fs(state).get("archived_at"))


def can_announce(state: dict[str, Any]) -> bool:
    """F25 'no' → F26: the manager's last decision is 'complete' and nothing is open."""
    fs = _fs(state)
    return (not fs.get("completed_at") and not fs.get("archived_at")
            and (fs.get("last_decision") or {}).get("route") == "complete"
            and bool(state.get("tasks"))
            and all(t.get("status") in _OPEN for t in state.get("tasks", {}).values()))


def summary(state: dict[str, Any]) -> dict[str, Any]:
    """Facts of the finished cycle, all from Workbench state."""
    tasks = list(state.get("tasks", {}).values())
    versions = sorted(state.get("versions", {}).values(), key=lambda v: v.get("version_id", ""))
    released = [{"label": v.get("label", ""), "tag": v.get("tag", ""), "commit_sha": v.get("commit_sha", ""),
                 "evidence": v.get("run_id") or v.get("artifact") or ""} for v in versions if v.get("status") == "released"]
    files: list[str] = []
    for h in sorted(state.get("handoffs", {}).values(), key=lambda h: h.get("handoff_id", "")):
        files += [p for p in h.get("integrated_files") or [] if p not in files]
    return {"cycle": int(_fs(state).get("cycle", 1) or 1), "goal": str(state.get("settings", {}).get("goal", "")),
            "tasks_done": sum(1 for t in tasks if t.get("status") == "done"),
            "tasks_cancelled": sum(1 for t in tasks if t.get("status") in ("cancelled", "superseded")),
            "milestones_accepted": sum(1 for m in state.get("milestones", {}).values() if m.get("status") == "accepted"),
            "versions_released": released, "files": files[:500], "file_count": len(files),
            "repo": (_fs(state).get("repo") or {}).get("full_name", "")}


def summary_text(s: dict[str, Any]) -> str:
    rel = ", ".join(f"{v['label']} ({v['tag'] or 'no tag'}{'; ' + v['evidence'] if v['evidence'] else ''})"
                    for v in s["versions_released"]) or "none"
    return (f"Cycle {s['cycle']} is complete: {s['tasks_done']} task(s) done, {s['milestones_accepted']} milestone(s) "
            f"accepted, {s['file_count']} file(s) in the project. Released: {rel}."
            + (f" Repository: {s['repo']}." if s["repo"] else ""))


def announce(store: Any) -> dict[str, Any]:
    """F26: record the completion and its summary on the timeline."""
    st = store.load()
    if not can_announce(st):
        raise ModelError("the project is not complete yet: the project manager must decide that no roadmap stage "
                         "is left and every task must be finished")
    s_ = summary(st)
    with store.transaction("project completed") as s:
        fs = s["settings"].setdefault("flow", {})
        fs["completed_at"] = now_utc()
        fs["completion"] = s_
        emit(s, "project_completed", cycle=s_["cycle"], tasks_done=s_["tasks_done"],
             versions=[v["label"] for v in s_["versions_released"]], importance="major")
    return s_


def expansion_prompt(state: dict[str, Any], idea: str = "") -> str:
    """F27 'yes': a prompt for the next major cycle, with the whole history."""
    from .report import DECISION_FORMAT
    from .proposals import MANAGER_FORMAT
    fs = _fs(state)
    lines = ["# AI Workbench — Expand the project (next major cycle)",
             "You are the Project Manager. The previous roadmap is complete. Plan the next major cycle on top of what "
             "exists; never redo finished work.", "", f"State revision: {int(state.get('state_revision', 0))}",
             f"Goal so far: {state.get('settings', {}).get('goal', '')}", "", "## History (from Workbench)"]
    for h in (fs.get("history") or []) + ([fs["completion"]] if fs.get("completion") else []):
        lines.append("- " + summary_text(h))
    lines += ["", "## Files in the project"] + [f"- {p}" for p in summary(state)["files"][:80]]
    lines += ["", "## The user's expansion idea", idea.strip() or "(none given — propose the most valuable next stage)",
              "", "## Your task",
              "1. Say what changes in the architecture (new modules, paths each one owns).",
              "2. Create the new milestones (next major version) and the tasks of every AI, with dependencies, scope "
              "and acceptance criteria.", "3. Set roadmap_remaining to true while any stage of this cycle is left.",
              "", MANAGER_FORMAT, "", DECISION_FORMAT]
    return "\n".join(lines)


def expand(store: Any, idea: str = "") -> dict[str, Any]:
    """F27 'yes' → F1: keep the finished cycle in the history and open the next one."""
    st = store.load()
    fs0 = _fs(st)
    if not fs0.get("completed_at") or fs0.get("archived_at"):
        raise ModelError("only a completed (not archived) project can be expanded")
    with store.transaction("project expanded") as s:
        fs = s["settings"].setdefault("flow", {})
        fs.setdefault("history", []).append({**(fs.get("completion") or summary(s)), "completed_at": fs["completed_at"]})
        cycle = int(fs.get("cycle", 1) or 1) + 1
        fs.update(cycle=cycle, expansion={"open": True, "idea": idea.strip()[:2000], "at": now_utc()})
        for k in ("completed_at", "completion", "last_decision"):
            fs.pop(k, None)
        fs["roadmap_remaining"] = True
        emit(s, "project_expanded", cycle=cycle, importance="major")
    return {"cycle": cycle, "prompt": expansion_prompt(store.load(), idea)}


def archive_path(root: Path, state: dict[str, Any]) -> Path:
    return Path(root) / ".workbench" / "archive" / f"{state.get('project_id') or 'project'}-final.aiwb-bundle.json"


def archive(store: Any, root: Path, *, version: str = "") -> Path:
    """F28: final bundle + read-only."""
    from . import bundle
    st = store.load()
    fs = _fs(st)
    if fs.get("archived_at"):
        raise ModelError("the project is already archived")
    if not fs.get("completed_at"):
        raise ModelError("announce the completion first (F26)")
    with store.transaction("project archived") as s:
        s["settings"].setdefault("flow", {})["archived_at"] = now_utc()
        emit(s, "project_archived", importance="major")
    final = store.load()
    path = archive_path(root, final)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bundle.dumps(bundle.export_bundle(final, name=Path(root).name, version=version)), encoding="utf-8")
    return path


def reopen(store: Any) -> None:
    """Leave the read-only state (the only write an archived project accepts)."""
    with store.transaction(REOPEN_REASON) as s:
        fs = s["settings"].setdefault("flow", {})
        if not fs.pop("archived_at", None):
            raise ModelError("the project is not archived")
        emit(s, "project_reopened", importance="major")
