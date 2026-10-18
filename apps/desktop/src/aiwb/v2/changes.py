"""One entry point for "what next with this task" (roadmap 2.6.0 / stage 8, spec §12.2–§12.4).

When the user asks for a change, three explicit routes exist — Workbench suggests
one but never silently edits the current task:

* ``revise``  — the change is inside this task's scope/criteria → a new task revision;
* ``new_task`` — an independent goal/deliverable → a new task (optionally after this one);
* ``replan``  — affects architecture / several tasks / overall scope → a re-plan prompt for the manager.

Context requests in a pasted answer are recognised through the existing
``aiwb.context_request`` parser; Workbench records the workflow fact and points
to the existing Context Request tool (no second implementation).
"""
from __future__ import annotations

import re
from typing import Any

from .models import ModelError
from .store import ProjectStore

ROUTES = ("revise", "new_task", "replan")
_REPLAN = re.compile(r"\b(architecture|redesign|rewrite|migrate|whole|entire|all tasks|database|framework|scope)\b|"
                     r"معماری|بازنویسی|کل پروژه|همهٔ|همه‌ی|مهاجرت|پایگاه داده|فریم‌ورک", re.I)
_NEW = re.compile(r"\b(add|new feature|also|another|separate|next)\b|اضافه|قابلیت جدید|جداگانه|همچنین", re.I)
_FIX = re.compile(r"\b(fix|bug|wrong|broken|missing|instead|rename|adjust|change)\b|اصلاح|درست|خطا|باگ|ناقص|تغییر", re.I)


def suggest_route(state: dict[str, Any], task_id: str, request: str) -> dict[str, Any]:
    """Heuristic suggestion with its reason; ``ambiguous`` means: ask the user (spec §12.3)."""
    t = state["tasks"].get(task_id)
    if t is None:
        raise ModelError(f"task {task_id} does not exist")
    text = request.strip()
    if not text:
        raise ModelError("describe the change first")
    hits = {"replan": bool(_REPLAN.search(text)), "new_task": bool(_NEW.search(text)), "revise": bool(_FIX.search(text))}
    scope = " ".join((t.get("scope") or {}).get("include", []) + t.get("acceptance_criteria", []) + [t["title"]]).lower()
    words = {w for w in re.findall(r"[\w/.-]{4,}", text.lower())}
    in_scope = bool(words & set(re.findall(r"[\w/.-]{4,}", scope)))
    if hits["replan"]:
        route, why = "replan", "mentions architecture / several tasks / overall scope"
    elif hits["revise"] and (in_scope or not hits["new_task"]):
        route, why = "revise", "asks to fix or adjust what this task already covers"
    elif hits["new_task"]:
        route, why = "new_task", "adds an independent capability"
    else:
        route, why = "revise" if in_scope else "new_task", "closest match by the task's scope words"
    ambiguous = sum(hits.values()) != 1
    return {"route": route, "why": why, "ambiguous": ambiguous, "in_scope": in_scope,
            "done": t["status"] == "done"}


def apply_route(project: Any, task_id: str, route: str, request: str, *, title: str = "") -> dict[str, Any]:
    """Explicit user choice. Returns {route, task_id?, prompt?, message}."""
    if route not in ROUTES:
        raise ModelError(f"route must be one of {', '.join(ROUTES)}")
    st = project.store.load()
    t = st["tasks"].get(task_id)
    if t is None:
        raise ModelError(f"task {task_id} does not exist")
    req = request.strip()[:3000]
    if not req:
        raise ModelError("describe the change first")
    if route == "revise":
        if t["status"] in ("cancelled", "superseded"):
            raise ModelError(f"{task_id} is {t['status']}; create a new task instead")
        crit = list(t.get("acceptance_criteria", [])) + [f"Change request: {req[:500]}"]
        out = project.tasks.update(task_id, {"acceptance_criteria": crit}, reason=f"change request: {req[:200]}")
        return {"route": route, "task_id": task_id, "revision": out["task_revision"],
                "message": f"{task_id} is now revision {out['task_revision']}; earlier attempts are for the old revision "
                           "and their late answers will be marked stale."}
    if route == "new_task":
        data = {"title": (title or req.splitlines()[0])[:200], "objective": req, "owner_agent_id": t.get("owner_agent_id", ""),
                "acceptance_criteria": [], "origin": "manual"}
        new = project.tasks.create(data)
        if t["status"] != "done":
            try:
                project.tasks.add_dependency(new["task_id"], task_id)
            except (ModelError, AttributeError):
                pass
        return {"route": route, "task_id": new["task_id"],
                "message": f"New task {new['task_id']} (draft) — add scope and acceptance criteria, then mark it ready."}
    lines = ["# Re-plan request (AI Workbench)", "",
             f"The user asks for a change that may affect several tasks or the architecture. Current task: {task_id} "
             f"\"{t['title']}\" (status {t['status']}, revision {t['task_revision']}).", "",
             "## Requested change", req, "",
             "## Current tasks"]
    for x in sorted(st["tasks"].values(), key=lambda x: x["task_id"]):
        lines.append(f"- {x['task_id']} [{x['status']}] {x['title']} (owner {x.get('owner_agent_id') or '—'})")
    lines += ["", f"Answer with ONE AIWB_MANAGER_PROPOSAL block based on state revision {st['state_revision']}. "
              "Only propose the changes this request needs; the user reviews every item. Nothing is applied before that."]
    return {"route": route, "prompt": "\n".join(lines),
            "message": "Re-plan prompt ready — copy it to the project-manager chat. Nothing was changed."}


def detect_context_request(text: str) -> dict[str, Any] | None:
    """Use the existing parser; return a plain summary or None."""
    from ..context_request import ContextRequestError, find_request, parse_request
    if find_request(text) is None:
        return None
    try:
        req = parse_request(text)
    except ContextRequestError as exc:
        return {"ok": False, "error": str(exc), "attempt_id": "", "task_id": "", "files": [], "questions": []}
    return {"ok": True, "error": "", "attempt_id": req.attempt_id, "task_id": req.task_id, "reason": req.reason,
            "files": [f"{i.path} ({i.mode})" for i in req.items], "questions": list(req.questions)}


def note_context_request(store: ProjectStore, workflow: Any, summary: dict[str, Any]) -> str:
    """Record the workflow fact on the matching attempt (by attempt id, else the task's active attempt)."""
    st = store.load()
    aid = summary.get("attempt_id") if summary.get("attempt_id") in st["attempts"] else ""
    if not aid and summary.get("task_id") in st["tasks"]:
        aid = st["tasks"][summary["task_id"]].get("active_attempt_id") or ""
    if aid:
        workflow.note_context_request(aid)
    return aid
