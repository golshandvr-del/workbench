"""Half-right manager answers without dead ends (roadmap 5.18.0, R1 + R6). Pure functions, no Tk, no store.

Before 5.18 a manager proposal without ``operations`` was refused with "the proposal has no operations" — even
when it clearly said what to do with keys the models invent (``decisions``, ``task_assessment``,
``task_change_proposals``, ``follow_up_tasks``, ``risks``, ``file_change_proposals`` …). The user then sent the same
long prompt again, and the manager "decided" the same thing again (the friend's calculator log: four proposal
blocks, three with ``operations: []``, DEC-0002 approved three times, revision 49 → 63 with no file).

* :func:`translate` turns those keys into real operations (``propose_decision``, ``update_task``, ``create_task``,
  ``report_risk``) and says what it did (``fixes``) and what it could not use (``leftover``). It never invents
  content: every operation carries only what the answer said.
* A decision that is already accepted (same id or same title) is **final**: it is skipped, never proposed again.
* :func:`fix_prompt` — when nothing can be used — asks only for what is missing, in a few lines, instead of the
  whole prompt again.
"""
from __future__ import annotations

import re
from typing import Any

from .charter_repair import role_of

TASK_FIELDS = ("title", "objective", "task_type", "owner_agent_id", "depends_on", "scope", "acceptance_criteria",
               "deliverables", "context_refs", "priority", "risk_level")
LIST_FIELDS = ("depends_on", "acceptance_criteria", "deliverables", "context_refs")
FIELD_SYNONYMS = {"new_acceptance_criteria": "acceptance_criteria", "updated_acceptance_criteria": "acceptance_criteria",
                  "acceptance": "acceptance_criteria", "criteria": "acceptance_criteria",
                  "description": "objective", "goal": "objective", "dependencies": "depends_on",
                  "files": "deliverables", "outputs": "deliverables", "owner": "owner_agent_id",
                  "assignee": "owner_agent_id", "risk": "risk_level"}
DECISION_KEYS = ("decisions", "decision_proposals", "proposed_decisions", "decisions_made", "decision_requests",
                 "decision")
UPDATE_KEYS = ("task_change_proposals", "task_updates", "task_changes", "task_assessment", "task_assessments",
               "updated_tasks", "task_revisions")
CREATE_KEYS = ("follow_up_tasks", "followup_tasks", "follow_up_task_proposals", "follow_ups", "new_tasks",
               "tasks_to_create", "additional_tasks", "proposed_tasks", "tasks")
RISK_KEYS = ("risks", "risk_register", "identified_risks")
FILE_KEYS = ("file_change_proposals", "file_changes", "proposed_files", "files")
PRIORITIES = ("low", "medium", "high", "critical")
RISKS = ("low", "medium", "high")


def norm(text: Any) -> str:
    """Comparable form of a title: lower case, letters and digits only."""
    value = str(text or "").lower().translate(str.maketrans("يكۀة۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "یکهه01234567890123456789"))
    value = re.sub(r"[\u200c\u200d\u0640\u064b-\u065f]", "", value)
    value = re.sub(r"(?<=[\u0600-\u06ff])\s+(?=[\u0600-\u06ff])", "", value)
    return re.sub(r"[^0-9a-z\u0600-\u06ff]+", " ", value).strip()


def _text(v: Any) -> str:
    if isinstance(v, dict):
        for k in ("text", "title", "name", "label", "description", "value", "option"):
            if v.get(k):
                return str(v[k]).strip()
        return ""
    return str(v).strip() if v is not None else ""


def _strs(v: Any) -> list[str]:
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple)):
        return [t for t in (_text(x) for x in v) if t]
    if isinstance(v, str):
        parts = [p.strip(" -•*\t") for p in re.split(r"\n|;", v)]
        return [p for p in parts if p]
    t = _text(v)
    return [t] if t else []


def _items(v: Any, id_key: str) -> list[Any]:
    """A list of items from a list, a single item, or a dictionary ``{id: item}``."""
    if v is None or v == "" or v == [] or v == {}:
        return []
    if isinstance(v, list):
        return [x for x in v if x not in (None, "", {}, [])]
    if isinstance(v, dict):
        if any(k in v for k in ("title", "task_id", "decision_id", "id", "decision", "changes", "objective",
                                "description", "question")):
            return [v]
        out: list[Any] = []
        for k, x in v.items():
            if isinstance(x, dict):
                out.append({id_key: k, **x} if id_key not in x else x)
            elif x not in (None, ""):
                out.append({id_key: k, "text": x})
        return out
    return [v]


def _first(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if d.get(k) not in (None, "", [], {}):
            return d[k]
    return None


def accepted_decisions(state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {i: d for i, d in ((state or {}).get("decisions") or {}).items() if d.get("status") == "accepted"}


def duplicate_of(title: str, decision_id: str, state: dict[str, Any] | None) -> str:
    """The accepted decision this one repeats (same id or same title), else ``""``."""
    acc = accepted_decisions(state)
    if decision_id in acc:
        return decision_id
    n = norm(title)
    if not n:
        return ""
    for did, d in sorted(acc.items()):
        if norm(d.get("title")) == n:
            return did
    return ""


def _decision_ops(items: list[Any], state: dict[str, Any] | None, fixes: list[str],
                  leftover: list[str]) -> list[dict[str, Any]]:
    decisions = (state or {}).get("decisions") or {}
    tasks = (state or {}).get("tasks") or {}
    ops: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in items:
        d = it if isinstance(it, dict) else {"title": _text(it), "decision": _text(it)}
        did = str(_first(d, "decision_id", "id") or "")
        chosen = _text(_first(d, "decision", "choice", "chosen", "chosen_option", "selected_option", "resolution",
                              "recommendation", "recommended", "answer") or "")
        title = _text(_first(d, "title", "name", "topic", "question", "summary", "text") or "")
        if did in decisions and not title:
            title = str(decisions[did].get("title", ""))
        title = title or chosen[:80]
        if not title:
            leftover.append("a decision without a title or a choice")
            continue
        dup = duplicate_of(title, did, state)
        if dup:
            fixes.append(f"{dup} is already decided (final) — not proposed again")
            continue
        if did in decisions:
            st = decisions[did].get("status")
            fixes.append(f"{did} {'already waits for your decision' if st == 'proposed' else 'was ' + str(st)}"
                         " — not proposed again")
            continue
        if norm(title) in seen:
            continue
        seen.add(norm(title))
        options = _strs(_first(d, "options", "alternatives", "choices"))
        # A recommendation sentence is not itself an option label.
        option = re.split(r"\s+(?:because|since|as it)\s+", chosen, maxsplit=1, flags=re.I)[0].strip()
        if chosen and norm(option) not in {norm(o) for o in options}:
            options = [option] + options if options else [option]
        affected = [t for t in _strs(_first(d, "affected_task_ids", "task_ids", "tasks", "task_id", "affects"))
                    if t in tasks]
        ops.append({"operation": "propose_decision", "title": title[:200],
                    "problem": _text(_first(d, "problem", "context", "question", "rationale", "reason") or "")[:4000],
                    "options": options[:20], "recommendation": chosen[:2000], "affected_task_ids": affected,
                    "reason": "translated from the answer's decisions (5.18.0)"})
    if ops:
        fixes.append(f"{len(ops)} decision(s) read from the answer's own keys — you confirm each one")
    return ops


def _changes(d: dict[str, Any]) -> dict[str, Any]:
    src = d.get("changes") if isinstance(d.get("changes"), dict) else d
    out: dict[str, Any] = {}
    for k, v in src.items():
        k = FIELD_SYNONYMS.get(k, k)
        if k not in TASK_FIELDS or k in out or v in (None, "", [], {}):
            continue
        if k in LIST_FIELDS:
            v = _strs(v)
            if not v:
                continue
        elif k == "scope":
            if isinstance(v, list):
                v = {"include": _strs(v), "exclude": []}
            if not isinstance(v, dict):
                continue
            v = {"include": _strs(v.get("include")), "exclude": _strs(v.get("exclude"))}
        elif k == "priority":
            v = str(v).lower()
            if v not in PRIORITIES:
                continue
        elif k == "risk_level":
            v = str(v).lower()
            if v not in RISKS:
                continue
        else:
            v = _text(v)
            if not v:
                continue
        out[k] = v
    return out


def _lookup(ref: str, tasks: dict[str, Any]) -> list[str]:
    """Existing task ids a reference names: an id (``TASK-1``, ``1``) or an exact normalised title."""
    if ref in tasks:
        return [ref]
    match = re.fullmatch(r"(?:task-)?0*(\d+)", ref, re.I)
    if match and f"TASK-{int(match.group(1)):04d}" in tasks:
        return [f"TASK-{int(match.group(1)):04d}"]
    return [key for key, row in tasks.items() if ref and norm(row.get("title")) == norm(ref)]


def _new_refs(items: list[Any]) -> dict[str, str]:
    """``{normalised title: temporary_ref}`` of the tasks this answer creates (ref = position in the create list)."""
    out: dict[str, str] = {}
    for n, it in enumerate(items, 1):
        title = _changes(it if isinstance(it, dict) else {"title": _text(it)}).get("title")
        if title and norm(title) not in out:
            out[norm(title)] = f"new-r{n}"
    return out


def _owner_for(role: str, state: dict[str, Any] | None) -> str:
    agents = (state or {}).get("agents") or {}
    return next((aid for aid, a in sorted(agents.items()) if a.get("role") == role and a.get("enabled", True)), "")


def _comment(it: dict[str, Any], skipped: bool) -> str:
    """The assessment's free text, kept as the operation's reason and never as a task field (BF-046)."""
    parts = [_text(it.get(k)) for k in ("reason", "rationale", "assessment", "summary", "comment", "notes")]
    if it.get("status"):
        parts.append(f"status: {_text(it['status'])}")
    if skipped:
        for k in ("description", "goal", "files", "outputs"):
            parts.append("; ".join(_strs(it.get(k))))
    return " · ".join(x for x in parts if x)[:1000]


def _task_ops(items: list[Any], state: dict[str, Any] | None, fixes: list[str], leftover: list[str],
              *, allow_create: bool = True, new_refs: dict[str, str] | None = None,
              deferred: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    tasks = (state or {}).get("tasks") or {}
    agents = (state or {}).get("agents") or {}
    new_refs = new_refs or {}
    ops: list[dict[str, Any]] = []
    upd = new = 0
    for position, it in enumerate(items, 1):
        if not isinstance(it, dict):
            t = _text(it)
            if t:
                it = {"title": t}
            else:
                continue

        def known(ref: str, what: str) -> str:
            found = _lookup(ref, tasks)
            if len(found) > 1:
                leftover.append(f"ambiguous {what} {ref!r} matches {', '.join(sorted(found))}")
            return found[0] if len(found) == 1 else ""

        raw_tid = str(_first(it, "task_id", "id", "task") or "")
        tid = known(raw_tid, "task") if raw_tid else ""
        if not tid and not allow_create and not (raw_tid and len(_lookup(raw_tid, tasks)) > 1):
            tid = known(_text(it.get("title")), "task")
        if not tid and not allow_create:
            if not any(x.startswith("ambiguous") and (raw_tid or _text(it.get("title"))) in x for x in leftover):
                leftover.append(f"a change for unknown task {raw_tid or _text(it.get('title'))}")
            continue
        has_changes = isinstance(it.get("changes"), dict)
        source = it
        if not allow_create and not has_changes:
            source = {k: v for k, v in it.items() if k not in ("description", "goal", "files", "outputs")}
        ch = _changes(source)
        if ch.get("owner_agent_id") and ch["owner_agent_id"] not in agents:
            ch.pop("owner_agent_id")
        role_text = _text(_first(it, "owner_role", "role") or _first(it.get("changes") or {}, "owner_role") or "")
        role = role_of(role_text) if role_text else ""
        if role_text and not role:
            leftover.append(f"unknown role {role_text!r}")
        own_ref = new_refs.get(norm(ch.get("title"))) if ch.get("title") else None
        dep_ids: list[str] = []
        dep_refs: list[str] = []
        for x in ch.pop("depends_on", []):
            found = known(x, "prerequisite")
            ref = new_refs.get(norm(x))
            if found and found != tid:
                dep_ids.append(found)
            elif not found and ref and ref != (own_ref if not tid else None):
                dep_refs.append(ref)
            elif not found and not any(x in y for y in leftover if y.startswith("ambiguous")):
                leftover.append(f"unresolved prerequisite {x}")
        if tid:
            cur = tasks[tid]
            if dep_ids:
                ch["depends_on"] = sorted(set(dep_ids) | set(cur.get("depends_on") or []))
            if role and "owner_agent_id" not in ch:
                owner = _owner_for(role, state)
                if owner:
                    ch["owner_agent_id"] = owner
                else:
                    leftover.append(f"no enabled agent with the role {role}")
            ch.pop("title", None) if ch.get("title") == cur.get("title") else None
            ch = {k: v for k, v in ch.items() if cur.get(k) != v}
            for ref in dep_refs:
                (deferred if deferred is not None else ops).append(
                    {"operation": "add_dependency", "task_id": tid, "depends_on_ref": ref,
                     "reason": "translated from the answer (5.18.0)"})
            if not ch:
                continue  # an assessment ("on track", "needs review") with nothing to change: not an operation
            ops.append({"operation": "update_task", "task_id": tid, "changes": ch,
                        "reason": _comment(it, not has_changes) or "translated from the answer (5.18.0)"})
            upd += 1
            continue
        title = str(ch.get("title") or "")
        if not title:
            leftover.append("a task without a title")
            continue
        new += 1
        op = {"operation": "create_task", "temporary_ref": f"new-r{position}", "title": title[:200],
              "objective": str(ch.get("objective") or title)[:4000], "reason": "translated from the answer (5.18.0)"}
        for k in ("acceptance_criteria", "deliverables", "scope", "priority", "risk_level", "owner_agent_id",
                  "task_type"):
            if ch.get(k):
                op[k] = ch[k]
        if dep_ids:
            op["depends_on"] = dep_ids
        if dep_refs:
            op["depends_on_refs"] = dep_refs
        if role and "owner_agent_id" not in op:
            op["owner_role"] = role
        ops.append(op)
    if upd:
        fixes.append(f"{upd} task change(s) read from the answer's own keys")
    if new:
        fixes.append(f"{new} new task(s) read from the answer's own keys")
    return ops


def translate(data: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    """``{"operations", "fixes", "leftover"}`` for a proposal whose ``operations`` is missing or empty."""
    fixes: list[str] = []
    leftover: list[str] = []
    ops: list[dict[str, Any]] = []
    for k in DECISION_KEYS:
        if k in data:
            ops += _decision_ops(_items(data[k], "decision_id"), state, fixes, leftover)
    task_items: list[Any] = []
    for k in CREATE_KEYS:
        if k in data:
            task_items += _items(data[k], "task_id")
    new_refs = _new_refs(task_items)
    deferred: list[dict[str, Any]] = []  # an edge to a new task is applied only after that task exists
    for k in UPDATE_KEYS:
        if k in data:
            ops += _task_ops(_items(data[k], "task_id"), state, fixes, leftover, allow_create=False,
                             new_refs=new_refs, deferred=deferred)
    ops += _task_ops(task_items, state, fixes, leftover, new_refs=new_refs)
    ops += deferred
    useful = bool(ops)
    for k in RISK_KEYS:
        if k in data and useful:
            for r in _items(data[k], "risk_id"):
                text = _text(r) if not isinstance(r, dict) else _text(_first(r, "description", "risk", "title",
                                                                             "text") or "")
                if text:
                    ops.append({"operation": "report_risk", "description": text[:500]})
    for k in FILE_KEYS:
        if k in data and _items(data[k], "path"):
            leftover.append(f"{len(_items(data[k], 'path'))} proposed file change(s): files come in a task answer "
                            "(files + AIWB_HANDOFF), not in a proposal")
    return {"operations": ops, "fixes": fixes, "leftover": leftover}


def fix_prompt(problem: str, state: dict[str, Any] | None = None, leftover: list[str] | None = None) -> str:
    """A short correction prompt: what was wrong, what to send — never the whole prompt again."""
    rev = int((state or {}).get("state_revision") or 0)
    acc = accepted_decisions(state)
    lines = ["# AI Workbench — please correct your last answer (short)",
             f"Your last answer could not be used: {problem}.",
             "Do not repeat your analysis. Answer with ONLY one block:",
             "<<<AIWB_MANAGER_PROPOSAL>>>",
             '{"schema_version": "1.0", "proposal_type": "project_plan_update", "base_state_revision": '
             f'{rev}, "summary": "one line", "operations": [',
             ' {"operation": "update_task", "task_id": "TASK-0001", "changes": {"acceptance_criteria": ["…"]}, '
             '"reason": "…"},',
             ' {"operation": "create_task", "temporary_ref": "new-1", "title": "…", "objective": "…", '
             '"acceptance_criteria": ["…"]},',
             ' {"operation": "propose_decision", "title": "…", "options": ["…", "…"], "recommendation": "…"}]}',
             "<<<AIWB_END_MANAGER_PROPOSAL>>>",
             "- Either list the actual changes in `operations` (create_task, update_task, add_dependency, "
             "propose_decision, close_or_cancel_task, report_risk …), or, if nothing is left, use "
             '\"operations\": [], \"roadmap_remaining\": false in the same block with the base_state_revision above.',
             "- Do not invent work to fill the list. If completion is unknown, clarify what remains instead of claiming completion.",
             "- Files are never part of a proposal: they come in the task's own answer (files + AIWB_HANDOFF)."]
    if acc:
        lines.append("- FINAL decisions — do not decide them again: "
                     + "; ".join(f"{i} {d.get('title', '')}: {d.get('decision', '')}" for i, d in sorted(acc.items())))
    if leftover:
        lines.append("- Not usable in your answer: " + "; ".join(leftover[:5]))
    return "\n".join(lines) + "\n"
