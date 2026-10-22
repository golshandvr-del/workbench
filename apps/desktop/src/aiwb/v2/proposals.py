"""Project-manager planning, Manager Update prompt and Proposal Review (roadmap 1.20.0 / slice 2F, spec §13, A.6).

* The manager's answer is analysis + one ``AIWB_MANAGER_PROPOSAL`` block.
* Workbench assigns ``proposal_id`` and all final task IDs itself;
  ``temporary_ref`` only links items inside the same proposal.
* A proposal based on an older ``base_state_revision`` whose referenced tasks
  changed is ``stale`` and needs explicit confirmation per operation.
* Accept/reject per operation. Accepted operations are applied in one
  transaction and the whole resulting graph is validated first; dependent
  operations are re-validated when only part is accepted.
* Nothing is applied by import/parse alone; tasks are never marked done.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from .models import SCHEMA_VERSION, ModelError, check_transition, normalize_task, now_utc
from .store import ProjectStore, emit, next_id, require
from .team import check_team
from .tasks import TaskService, readiness, validate_graph

BLOCK_RE = re.compile(r"(?s)<<<AIWB_MANAGER_PROPOSAL>>>\s*(.*?)\s*<<<AIWB_END_MANAGER_PROPOSAL>>>")
OPERATIONS = ("create_task", "update_task", "add_dependency", "remove_dependency", "assign_agent", "propose_decision",
              "reorder_priority", "split_task", "close_or_cancel_task", "request_more_evidence", "change_scope",
              "report_risk", "create_agent", "assign_account",  # Team Proposal (2.4.0, spec §7.3)
              "create_milestone")  # Project Charter roadmap (3.4.0)
INFO_ONLY = ("request_more_evidence", "report_risk")
MAX_OPS = 60


def find_block(text: str) -> dict[str, Any] | None:
    m = BLOCK_RE.search(text or "")
    if not m:
        return None
    body = m.group(1).strip()
    f = re.match(r"(?s)^`{3,}\s*json\s*\n(.*?)\n`{3,}$", body)
    if f:
        body = f.group(1)
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ModelError(f"AIWB_MANAGER_PROPOSAL is not valid JSON: {exc.msg} (line {exc.lineno}); the raw answer is kept in the Inbox") from None
    if not isinstance(data, dict):
        raise ModelError("AIWB_MANAGER_PROPOSAL must be a JSON object")
    return data


def _op_task_refs(op: dict[str, Any]) -> list[str]:
    refs = [op.get("task_id", "")] + list(op.get("depends_on_refs", []) or []) + [op.get("depends_on_task_id", "")]
    return [r for r in refs if isinstance(r, str) and r.startswith("TASK-")]


class ProposalService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.tasks = TaskService(store)

    def list(self, status: str = "") -> list[dict[str, Any]]:
        items = self.store.load()["proposals"].values()
        return sorted([p for p in items if not status or p["status"] == status], key=lambda p: p["proposal_id"])

    def get(self, proposal_id: str) -> dict[str, Any] | None:
        return self.store.load()["proposals"].get(proposal_id)

    # -- import
    def import_text(self, text: str, *, response_id: str = "", kind: str = "update") -> dict[str, Any]:
        data = find_block(text)
        if data is None:
            raise ModelError("no AIWB_MANAGER_PROPOSAL block found; the answer is kept in the Inbox as analysis only")
        return self.import_data(data, response_id=response_id, kind=kind)

    def import_data(self, data: dict[str, Any], *, response_id: str = "", kind: str = "update",
                    charter: dict[str, Any] | None = None, fixes: list[str] | None = None) -> dict[str, Any]:
        """Import an already parsed proposal (also used for a Project Charter, 3.4.0)."""
        from .report import parse_emergency, parse_remaining
        ops = data.get("operations")
        remaining = parse_remaining(data.get("roadmap_remaining"))
        if isinstance(ops, list) and not ops and remaining is False and charter is None:
            pass  # a pure decision: "nothing left" (roadmap 4.4.0, F25 → F26)
        elif not isinstance(ops, list) or not ops:
            raise ModelError("the proposal has no operations")
        if len(ops) > MAX_OPS:
            raise ModelError(f"too many operations ({len(ops)} > {MAX_OPS}); ask the manager to split the proposal")
        try:
            base = int(data.get("base_state_revision"))
        except (TypeError, ValueError):
            raise ModelError("base_state_revision (integer) is required so Workbench can detect stale proposals") from None
        state = self.store.load()
        normalized, problems = [], []
        temp_refs: set[str] = set()
        for i, op in enumerate(ops):
            if not isinstance(op, dict) or op.get("operation") not in OPERATIONS:
                problems.append(f"operation {i + 1}: unknown or missing 'operation'")
                normalized.append({"index": i, "operation": str((op or {}).get("operation", "?"))[:40] if isinstance(op, dict) else "?",
                                   "raw": op if isinstance(op, dict) else {}, "valid": False,
                                   "problem": "unknown operation", "decision": "rejected"})
                continue
            entry = {"index": i, "operation": op["operation"], "raw": copy.deepcopy(op), "valid": True, "problem": "",
                     "decision": "pending", "reason": str(op.get("reason", ""))[:1000]}
            if op["operation"] in ("create_task", "split_task"):
                ref = str(op.get("temporary_ref") or f"new-{i + 1}")
                if ref in temp_refs:
                    entry.update(valid=False, problem=f"duplicate temporary_ref {ref}")
                temp_refs.add(ref)
                entry["temporary_ref"] = ref
            for r in _op_task_refs(op):
                if r not in state["tasks"]:
                    entry.update(valid=False, problem=f"unknown task {r}")
            normalized.append(entry)
        team = check_team(data, ops, state)
        for idx, msg in team["op_errors"].items():
            e = normalized[idx]
            if e["valid"]:
                e.update(valid=False, problem=msg.split(": ", 1)[-1])
        changed = []
        for e in normalized:
            for r in _op_task_refs(e["raw"]):
                t = state["tasks"].get(r)
                if t and _changed_since(state, r, base):
                    changed.append(r)
        stale = base < int(state["state_revision"]) and bool(changed)
        with self.store.transaction("import manager proposal") as s:
            pid = next_id(s, "proposal")
            p = {"schema_version": SCHEMA_VERSION, "proposal_id": pid, "kind": kind,
                 "proposal_type": str(data.get("proposal_type", "project_plan_update"))[:60],
                 "base_state_revision": base, "imported_at_revision": int(s["state_revision"]),
                 "summary": str(data.get("summary", ""))[:4000], "risks": [str(r)[:500] for r in data.get("risks", []) or []][:30],
                 "questions_for_user": [str(q)[:500] for q in data.get("questions_for_user", []) or []][:30],
                 "operations": normalized, "problems": problems, "stale": stale,
                 "stale_task_ids": sorted(set(changed)), "status": "pending", "source_response_id": response_id,
                 "assumptions": [str(a)[:500] for a in data.get("assumptions", []) or []][:30],
                 "team": team["team"], "team_issues": team["issues"], "team_counts": team["counts"],
                 "is_team": team["is_team"], "charter": charter or None,
                 "roadmap_remaining": remaining, "emergency_tasks": parse_emergency(data.get("emergency_tasks")),
                 "has_decision": "roadmap_remaining" in data or "emergency_tasks" in data,
                 "created_at": now_utc(), "updated_at": now_utc(), "result": {}}
            if fixes:  # 5.10.0: automatic repairs of the model's answer are kept with it, never hidden
                p["auto_fixes"] = [str(f)[:300] for f in fixes][:200]
            s["proposals"][pid] = p
            emit(s, "proposal_imported", proposal_id=pid, operations=len(normalized), stale=stale,
                 **({"auto_fixes": len(fixes)} if fixes else {}))
        return p

    # -- review
    def preview(self, proposal_id: str, accept: list[int]) -> dict[str, Any]:
        """Dry run: apply accepted operations to a copy and validate. Never writes."""
        state = self.store.load()
        p = state["proposals"].get(proposal_id)
        if p is None:
            raise ModelError(f"proposal {proposal_id} does not exist")
        work = copy.deepcopy(state)
        return self._apply(work, p, accept, dry_run=True)

    def review(self, proposal_id: str, accept: list[int], *, confirm_stale: bool = False, note: str = "") -> dict[str, Any]:
        state = self.store.load()
        p = state["proposals"].get(proposal_id)
        if p is None:
            raise ModelError(f"proposal {proposal_id} does not exist")
        if p["status"] != "pending":
            raise ModelError(f"proposal {proposal_id} was already reviewed ({p['status']})")
        if p["stale"] and accept and not confirm_stale:
            raise ModelError("this proposal is stale: tasks " + ", ".join(p["stale_task_ids"])
                             + " changed after its base revision. Re-check each operation and confirm explicitly.")
        with self.store.transaction("review manager proposal") as s:
            p = require(s, "proposals", proposal_id)
            result = self._apply(s, p, accept, dry_run=False)
            if result["errors"]:
                raise ModelError("proposal not applied: " + "; ".join(result["errors"]))
            accepted = set(result["applied"])
            for op in p["operations"]:
                op["decision"] = "accepted" if op["index"] in accepted else "rejected"
            n_valid = sum(1 for op in p["operations"] if op["valid"])
            p["status"] = ("accepted" if not n_valid and not p["operations"] else "rejected" if not accepted
                           else "accepted" if len(accepted) == n_valid else "partially_accepted")
            if p.get("has_decision") and p["status"] != "rejected":
                from .report import apply_decision
                result["decision"] = apply_decision(s, p, result["created"])
            p["result"] = {**result, "note": note[:1000], "reviewed_at": now_utc()}
            if accepted and p.get("charter"):
                s["settings"]["charter"] = {**p["charter"], "proposal_id": proposal_id, "accepted_at": now_utc(),
                                            "task_ids": dict(result["created"])}
                emit(s, "charter_accepted", proposal_id=proposal_id)
            p["updated_at"] = now_utc()
            emit(s, "proposal_reviewed", proposal_id=proposal_id, status=p["status"], applied=sorted(accepted))
            return p

    def _apply(self, s: dict[str, Any], p: dict[str, Any], accept: list[int], *, dry_run: bool) -> dict[str, Any]:
        ops = {o["index"]: o for o in p["operations"]}
        errors, applied, created, notes = [], [], {}, []
        # team operations first, so tasks may name agents created in the same proposal
        order = {"create_agent": 0, "assign_account": 1, "create_milestone": 3}
        selected = sorted([ops[i] for i in sorted(set(accept)) if i in ops],
                          key=lambda o: (order.get(o["operation"], 2), o["index"]))
        selected_refs = {o.get("temporary_ref") for o in selected if o.get("temporary_ref")}
        ts = TaskService(self.store)
        resolve = lambda ref: created.get(ref, ref)  # noqa: E731
        later: list[tuple[dict[str, Any], list[str]]] = []  # forward references to new tasks created later
        for op in selected:
            raw, name = op["raw"], op["operation"]
            if not op["valid"]:
                errors.append(f"#{op['index'] + 1} {name}: {op['problem']}")
                continue
            try:
                if name in ("create_task", "split_task"):
                    deps = [resolve(r) for r in list(raw.get("depends_on_refs") or []) + list(raw.get("depends_on") or [])]
                    pending_refs = [r for r in deps if not r.startswith("TASK-")]
                    if pending_refs:
                        later.append((op, pending_refs))
                        deps = [d for d in deps if d.startswith("TASK-")]
                    missing_refs = [r for r in raw.get("depends_on_refs", []) or [] if not r.startswith("TASK-") and r not in selected_refs]
                    if missing_refs:
                        raise ModelError(f"depends on {', '.join(missing_refs)} which is not accepted in this review")
                    owner = raw.get("owner_agent_id", "")
                    if not owner and raw.get("owner_role"):
                        owner = next((a["agent_id"] for a in sorted(s["agents"].values(), key=lambda a: a["agent_id"])
                                      if a["role"] == raw["owner_role"] and a.get("enabled", True)), "")
                    data = {"title": raw.get("title"), "objective": raw.get("objective") or raw.get("title"),
                            "acceptance_criteria": raw.get("acceptance_criteria"), "depends_on": deps,
                            "scope": raw.get("scope") or {}, "deliverables": raw.get("deliverables"),
                            "owner_agent_id": owner, "priority": raw.get("priority"), "risk_level": raw.get("risk_level"),
                            "task_type": raw.get("task_type"), "origin": "manager_proposal",
                            "acceptance_policy": raw.get("acceptance_policy"),
                            "required_approvals": raw.get("required_approvals")}
                    if raw.get("reviewer_agent_id"):
                        data["reviewer_agent_ids"] = [raw["reviewer_agent_id"]]
                    task = ts._create_in(s, data, status="draft")
                    if raw.get("parallel_group"):
                        task["parallel_group"] = str(raw["parallel_group"])[:20]
                    task["proposal_id"] = p["proposal_id"]
                    created[op["temporary_ref"]] = task["task_id"]
                    if name == "split_task" and raw.get("task_id") in s["tasks"]:
                        notes.append(f"{task['task_id']} split from {raw['task_id']} (original kept; cancel it explicitly if needed)")
                elif name in ("update_task", "change_scope", "reorder_priority", "assign_agent"):
                    tid = raw["task_id"]
                    t = require(s, "tasks", tid)
                    fields = dict(raw.get("changes") or {})
                    if name == "change_scope":
                        fields = {"scope": raw.get("scope") or fields.get("scope")}
                    if name == "reorder_priority":
                        fields = {"priority": raw.get("priority")}
                    if name == "assign_agent":
                        aid = raw.get("agent_id") or raw.get("owner_agent_id")
                        if aid not in s["agents"]:
                            raise ModelError(f"agent {aid} does not exist")
                        fields = {"owner_agent_id": aid}
                    for k in ("status", "task_id", "task_revision"):
                        if k in fields:
                            raise ModelError(f"a proposal cannot set {k} directly")
                    editable = {k: t.get(k) for k in normalize_task({"title": "x", "objective": "x"})}
                    merged = normalize_task({**editable, **fields})
                    from .models import REVISION_FIELDS
                    if any(merged[k] != editable.get(k) for k in REVISION_FIELDS):
                        t.setdefault("revisions", []).append({"task_revision": t["task_revision"], "at": now_utc(),
                                                              "fields": {k: t.get(k) for k in REVISION_FIELDS},
                                                              "reason": f"proposal {p['proposal_id']}"})
                        t["task_revision"] += 1
                    t.update(merged)
                    t["updated_at"] = now_utc()
                elif name == "add_dependency":
                    t = require(s, "tasks", raw["task_id"])
                    dep = resolve(raw.get("depends_on_task_id") or raw.get("depends_on_ref", ""))
                    if dep not in t["depends_on"]:
                        t["depends_on"].append(dep)
                elif name == "remove_dependency":
                    t = require(s, "tasks", raw["task_id"])
                    dep = raw.get("depends_on_task_id", "")
                    if dep in t["depends_on"]:
                        t["depends_on"].remove(dep)
                elif name == "close_or_cancel_task":
                    t = require(s, "tasks", raw["task_id"])
                    target = "cancelled"
                    check_transition("task", t["status"], target)
                    t["status"] = target
                    t["cancel_reason"] = str(raw.get("reason", ""))[:500]
                    notes.append(f"{t['task_id']} cancelled (history kept)")
                elif name == "propose_decision":
                    did = next_id(s, "decision")
                    s["decisions"][did] = {"schema_version": SCHEMA_VERSION, "decision_id": did, "revision": 1,
                                           "title": str(raw.get("title", "Decision"))[:200],
                                           "problem": str(raw.get("problem", ""))[:4000],
                                           "options": [str(o)[:1000] for o in raw.get("options", []) or []][:20],
                                           "recommendation": str(raw.get("recommendation", ""))[:2000], "decision": "",
                                           "rationale": "", "status": "proposed", "origin": f"proposal {p['proposal_id']}",
                                           "approved_by": "", "approved_at": "",
                                           "affected_task_ids": [resolve(x) for x in raw.get("affected_task_ids", []) or []],
                                           "supersedes": "", "superseded_by": "", "previously_rejected": [],
                                           "created_at": now_utc(), "updated_at": now_utc()}
                    notes.append(f"{did} proposed (needs your decision)")
                elif name == "create_agent":
                    from .models import normalize_agent
                    aid = raw.get("agent_id")
                    if aid in s["agents"]:
                        raise ModelError(f"agent {aid} already exists")
                    s["agents"][aid] = normalize_agent({"agent_id": aid, "role": raw.get("role"),
                                                        "name": raw.get("name") or aid, "purpose": raw.get("purpose", ""),
                                                        "instructions": raw.get("instructions", []),
                                                        "template_id": ""})
                    emit(s, "agent_created", agent_id=aid, proposal_id=p["proposal_id"])
                elif name == "assign_account":
                    aid, acc = raw.get("agent_id"), raw.get("account_profile_id")
                    require(s, "agents", aid)
                    a = require(s, "account_profiles", acc)
                    if not a.get("enabled", True):
                        raise ModelError(f"account profile {acc} is disabled")
                    bid = next_id(s, "chat_binding")
                    s["chat_bindings"][bid] = {"schema_version": SCHEMA_VERSION, "chat_binding_id": bid, "agent_id": aid,
                                               "account_profile_id": acc, "chat_name": "", "link": "",
                                               "note": f"from proposal {p['proposal_id']} (choose the chat yourself)",
                                               "enabled": True, "confirmed_at": "", "created_at": now_utc(),
                                               "updated_at": now_utc()}
                    emit(s, "chat_binding_added", chat_binding_id=bid, agent_id=aid, account_profile_id=acc)
                elif name == "create_milestone":
                    notes += _apply_milestone(s, raw, created, p["proposal_id"])
                elif name in INFO_ONLY:
                    notes.append(f"{name}: {str(raw.get('reason') or raw.get('description') or '')[:300]}")
                applied.append(op["index"])
            except (ModelError, KeyError, TypeError) as exc:
                errors.append(f"#{op['index'] + 1} {name}: {exc}")
        for op, refs in later:
            tid = created.get(op.get("temporary_ref", ""))
            if tid:
                for r in refs:
                    if r in created and created[r] not in s["tasks"][tid]["depends_on"]:
                        s["tasks"][tid]["depends_on"].append(created[r])
        problems = validate_graph(s["tasks"])
        if problems:
            errors += ["resulting task graph is invalid: " + "; ".join(problems)]
        new_ids = set(created.values())
        for t in s["tasks"].values():
            if t["task_id"] in new_ids and t["status"] == "draft" and not problems:
                # an approved plan makes its tasks actionable: ready, or blocked by prerequisites
                st, why = readiness(t, s["tasks"])
                t["status"], t["blocked_reason"] = st, why
                emit(s, "task_status", task_id=t["task_id"], old="draft", new=st, why=why or "plan approved")
                continue
            if t["status"] == "ready" and readiness(t, s["tasks"])[0] != "ready":
                t["status"] = "blocked"
                t["blocked_reason"] = readiness(t, s["tasks"])[1]
                notes.append(f"{t['task_id']} is now blocked: {t['blocked_reason']}")
        return {"applied": applied, "created": created, "errors": errors, "notes": notes, "dry_run": dry_run}


def _apply_milestone(s: dict[str, Any], raw: dict[str, Any], created: dict[str, str], proposal_id: str) -> list[str]:
    """Charter milestone → Milestone (+ a proposed Version when it names one). Only accepted tasks are linked."""
    from .timeline import _SEMVER
    title = str(raw.get("title") or "").strip()[:200]
    if not title:
        raise ModelError("milestone title is required")
    notes: list[str] = []
    refs = [str(r) for r in raw.get("task_refs") or []]
    task_ids = [created[r] for r in refs if r in created]
    skipped = [r for r in refs if r not in created and not r.startswith("TASK-")]
    task_ids += [r for r in refs if r.startswith("TASK-") and r in s["tasks"]]
    mid = next_id(s, "milestone")
    s["milestones"][mid] = {"schema_version": SCHEMA_VERSION, "milestone_id": mid, "title": title,
                            "criteria": [str(c)[:500] for c in raw.get("criteria") or [] if str(c).strip()][:30],
                            "task_ids": task_ids, "status": "planned", "target_date": "", "accepted_at": "",
                            "proposal_id": proposal_id, "created_at": now_utc(), "updated_at": now_utc()}
    emit(s, "milestone_created", milestone_id=mid, task_ids=task_ids)
    if skipped:
        notes.append(f"{mid}: tasks {', '.join(skipped)} were not accepted, so they are not linked")
    label = str(raw.get("version") or "").strip()
    if label:
        if not _SEMVER.match(label):
            raise ModelError(f"{label!r} is not a semantic version")
        if any(v["label"] == label and v["status"] != "withdrawn" for v in s["versions"].values()):
            notes.append(f"version {label} already exists; {mid} is not linked to a new version")
        else:
            vid = next_id(s, "version")
            s["versions"][vid] = {"schema_version": SCHEMA_VERSION, "version_id": vid, "label": label, "policy": "semver",
                                  "status": "proposed", "source": "model", "task_ids": list(task_ids),
                                  "milestone_ids": [mid], "notes": f"Planned by the Project Charter ({proposal_id})",
                                  "commit_sha": "", "tag": "", "run_id": "", "artifact": "", "artifact_sha256": "",
                                  "history": [], "created_at": now_utc(), "updated_at": now_utc()}
            emit(s, "version_proposed", version_id=vid, label=label, source="model")
            notes.append(f"{mid} → version {label} ({vid}, proposed)")
    return notes


def _changed_since(state: dict[str, Any], task_id: str, base_revision: int) -> bool:
    return any(e.get("task_id") == task_id and int(e.get("state_revision", 0)) > base_revision
               and e["type"] in ("task_updated", "task_status", "task_created")
               for e in state["events"])


MANAGER_FORMAT = """Return your analysis in plain text, then exactly ONE block:
<<<AIWB_MANAGER_PROPOSAL>>>
{"schema_version": "1.0", "proposal_type": "project_plan_update", "base_state_revision": <the state_revision above>,
 "summary": "…",
 "operations": [
  {"operation": "create_task", "temporary_ref": "new-1", "title": "…", "objective": "…", "owner_role": "implementer",
   "depends_on_refs": ["TASK-0001" or "new-2"], "acceptance_criteria": ["…"], "scope": {"include": ["path/**"], "exclude": []},
   "priority": "medium"},
  {"operation": "add_dependency", "task_id": "TASK-0003", "depends_on_task_id": "TASK-0002", "reason": "…"},
  {"operation": "update_task", "task_id": "TASK-0002", "changes": {"acceptance_criteria": ["…"]}, "reason": "…"},
  {"operation": "assign_agent", "task_id": "TASK-0002", "agent_id": "agent-implementer"},
  {"operation": "propose_decision", "title": "…", "problem": "…", "options": ["…"], "recommendation": "…", "affected_task_ids": ["TASK-0002"]},
  {"operation": "reorder_priority", "task_id": "…", "priority": "high"},
  {"operation": "close_or_cancel_task", "task_id": "…", "reason": "…"},
  {"operation": "request_more_evidence", "task_id": "…", "reason": "…"},
  {"operation": "report_risk", "description": "…"}],
 "risks": ["…"], "questions_for_user": ["…"]}
<<<AIWB_END_MANAGER_PROPOSAL>>>
Rules: never mark tasks done; Workbench assigns all IDs (use temporary_ref for new tasks); only existing TASK-/agent- IDs may be referenced."""


def planning_prompt(project: dict[str, Any], agents: list[dict[str, Any]]) -> str:
    """New Project Planning prompt (spec 13.2). The answer is a Plan Proposal, not a manifest."""
    lines = ["# AI Workbench — New project planning", "You are the Project Manager for this project. You cannot read files or run anything.",
             "", "## Project", f"- Goal: {project.get('goal', '')}", f"- Audience: {project.get('audience', '')}",
             f"- Constraints: {project.get('constraints', '')}", f"- Environment: {project.get('environment', '')}",
             f"- Success criteria: {project.get('success', '')}", f"- References: {project.get('references', '')}",
             "", "## Available agents (roles)"] + [f"- {a['agent_id']} ({a['role']}): {a['purpose']}" for a in agents] + [
             "", "## Your task",
             "Propose goal/non-goals, architecture, assumptions and open questions, tasks with scope, acceptance criteria and "
             "dependencies, risks and validation method. Keep the first plan small (3–8 tasks).",
             "base_state_revision is 0 for a new project.", "", MANAGER_FORMAT]
    return "\n".join(lines)


def manager_update_prompt(snapshot: dict[str, Any], *, state_url: str = "", fallback: str = "",
                          since_events: list[dict[str, Any]] | None = None, last_seen_revision: int = 0) -> str:
    """Manager Update (spec 13.3): published snapshot link + local fallback; nothing is sent automatically."""
    lines = ["# AI Workbench — Manager update", f"State revision: {snapshot['state_revision']} (generated {snapshot['generated_at_utc']})"]
    if last_seen_revision:
        lines.append(f"Your last report was based on revision {last_seen_revision}; this is newer." if snapshot["state_revision"] > last_seen_revision
                     else "No newer state since your last report.")
    if state_url:
        lines += ["", "## Published state", f"- Read: {state_url}",
                  "- First, quote the exact `state_revision` you see there. If you cannot open it, say \"CANNOT READ STATE\" "
                  "and use only the summary below — never claim you read it."]
    else:
        lines += ["", "## Published state", "- Not published. Use ONLY the summary below; do not claim you read GitHub."]
    lines += ["", "## Local summary (authoritative fallback)", fallback or "(empty)"]
    if since_events:
        lines += ["", "## Events since your last report"] + [
            f"- r{e.get('state_revision')} {e['type']} {e.get('task_id') or e.get('decision_id') or e.get('handoff_id') or ''} "
            f"{e.get('new', '')} {e.get('why', '')}".rstrip() for e in since_events[-40:]]
    lines += ["", "## Rules", "- Separate: read from the snapshot / reported by agents / your inference / unknown.",
              "- Model claims are NOT evidence; only Workbench evidence counts. Never declare a task done.",
              f"- Use base_state_revision {snapshot['state_revision']}.", "", MANAGER_FORMAT]
    return "\n".join(lines)


def probe_prompt(state_url: str) -> str:
    """Compatibility probe (B.2): can this chat actually read the published state?"""
    return ("# AI Workbench — state access check\nOpen this file and reply with ONLY one line:\n"
            "`STATE_REVISION=<the integer value of state_revision>` — or `CANNOT READ STATE` if you cannot open it.\n"
            f"File: {state_url}\nDo not guess.")


def check_probe(answer: str, expected_revision: int) -> str:
    """'readable' | 'unreadable' | 'wrong' (answer does not match the real file → treat as unreadable)."""
    if re.search(r"CANNOT\s+READ\s+STATE", answer or "", re.I):
        return "unreadable"
    m = re.search(r"STATE_REVISION\s*=\s*(\d+)", answer or "")
    if not m:
        return "wrong"
    return "readable" if int(m.group(1)) == expected_revision else "wrong"
