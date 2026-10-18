"""Decision Ledger and Evidence Ledger; task status from policy + evidence (roadmap 1.18.1 / slice 2D).

* Decisions are never deleted: rejected/superseded records stay with their reason.
* Evidence keeps *reported* (model claims, ``verified: false``) strictly apart
  from *verified* (Workbench really ran it, CI result, user review).
* Evidence is bound to a commit/state revision; old evidence never counts for a
  newer task revision or a different commit.
* ``evaluate_task`` is the only path to ``done``.
"""
from __future__ import annotations

from typing import Any

from .models import (EVIDENCE_SOURCES, EVIDENCE_TYPES, SCHEMA_VERSION, ModelError, check_transition, now_utc)
from .store import ProjectStore, emit, next_id, require

VERIFIED_SOURCES = {"workbench_process_runner", "workbench_apply", "github_actions", "git", "user"}
VALIDATION_TYPES = {"test_run", "build_run", "external_artifact"}


class DecisionLedger:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def list(self, status: str = "") -> list[dict[str, Any]]:
        items = self.store.load()["decisions"].values()
        return sorted([d for d in items if not status or d["status"] == status], key=lambda d: d["decision_id"])

    def get(self, decision_id: str) -> dict[str, Any] | None:
        return self.store.load()["decisions"].get(decision_id)

    def propose(self, title: str, problem: str, *, options: list[str] | None = None, recommendation: str = "",
                origin: str = "user", affected_task_ids: list[str] | None = None, supersedes: str = "") -> dict[str, Any]:
        if not title.strip():
            raise ModelError("decision title is required")
        with self.store.transaction("propose decision") as s:
            for t in affected_task_ids or []:
                require(s, "tasks", t)
            if supersedes:
                old = require(s, "decisions", supersedes)
                if old["status"] != "accepted":
                    raise ModelError(f"only an accepted decision can be superseded ({supersedes} is {old['status']})")
            similar = [d["decision_id"] for d in s["decisions"].values()
                       if d["status"] == "rejected" and d["title"].strip().lower() == title.strip().lower()]
            did = next_id(s, "decision")
            d = {"schema_version": SCHEMA_VERSION, "decision_id": did, "revision": 1, "title": title.strip()[:200],
                 "problem": problem.strip()[:4000], "options": [o[:1000] for o in (options or [])][:20],
                 "recommendation": recommendation[:2000], "decision": "", "rationale": "", "status": "proposed",
                 "origin": origin[:60], "approved_by": "", "approved_at": "", "affected_task_ids": list(affected_task_ids or []),
                 "supersedes": supersedes, "superseded_by": "", "previously_rejected": similar,
                 "created_at": now_utc(), "updated_at": now_utc()}
            s["decisions"][did] = d
            emit(s, "decision_proposed", decision_id=did, origin=origin)
            for t in d["affected_task_ids"]:
                task = s["tasks"][t]
                if task["status"] in ("ready", "in_progress", "in_review", "blocked"):
                    old = task["status"]
                    check_transition("task", old, "needs_decision")
                    task["status"] = "needs_decision"
                    task["pending_decision_ids"] = sorted(set(task.get("pending_decision_ids", [])) | {did})
                    emit(s, "task_status", task_id=t, old=old, new="needs_decision", why=f"decision {did} open")
        return d

    def resolve(self, decision_id: str, accept: bool, *, decision: str = "", rationale: str = "",
                approved_by: str = "user") -> dict[str, Any]:
        if not rationale.strip():
            raise ModelError("a reason is required to accept or reject a decision (it is kept forever)")
        with self.store.transaction("resolve decision") as s:
            d = require(s, "decisions", decision_id)
            new = "accepted" if accept else "rejected"
            check_transition("decision", d["status"], new)
            d.update(status=new, decision=decision[:2000] if accept else "", rationale=rationale[:2000],
                     approved_by=approved_by[:80], approved_at=now_utc(), updated_at=now_utc())
            if accept and d.get("supersedes"):
                old = s["decisions"][d["supersedes"]]
                check_transition("decision", old["status"], "superseded")
                old.update(status="superseded", superseded_by=decision_id, updated_at=now_utc())
                emit(s, "decision_superseded", decision_id=old["decision_id"], by=decision_id)
            emit(s, "decision_" + new, decision_id=decision_id)
            for t in d["affected_task_ids"]:
                task = s["tasks"].get(t)
                if not task:
                    continue
                pend = set(task.get("pending_decision_ids", [])) - {decision_id}
                task["pending_decision_ids"] = sorted(pend)
                if task["status"] == "needs_decision" and not pend:
                    from .tasks import readiness
                    target = "in_progress" if task.get("active_attempt_id") else readiness(task, s["tasks"])[0]
                    check_transition("task", "needs_decision", target)
                    task["status"] = target
                    emit(s, "task_status", task_id=t, old="needs_decision", new=target, why=f"decision {decision_id} {new}")
        return d


class EvidenceService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def list(self, subject_id: str = "") -> list[dict[str, Any]]:
        items = self.store.load()["evidence"].values()
        return sorted([e for e in items if not subject_id or e["subject_id"] == subject_id], key=lambda e: e["evidence_id"])

    def record(self, *, type: str, subject_type: str, subject_id: str, source_kind: str, result: str,
               summary: str = "", commit_sha: str = "", run_id: str = "", details: dict[str, Any] | None = None,
               attempt_id: str = "", artifact_sha256: str = "") -> dict[str, Any]:
        if type not in EVIDENCE_TYPES:
            raise ModelError(f"evidence type must be one of {', '.join(EVIDENCE_TYPES)}")
        if source_kind not in EVIDENCE_SOURCES:
            raise ModelError(f"evidence source must be one of {', '.join(EVIDENCE_SOURCES)}")
        if result not in ("passed", "failed", "observed", "approved", "rejected", "not_run", "claimed"):
            raise ModelError("invalid evidence result")
        if type == "model_report" and source_kind != "model":
            raise ModelError("model_report evidence must come from source 'model'")
        if source_kind == "model" and type != "model_report":
            raise ModelError("a model can only produce model_report evidence; it cannot verify tests or builds")
        if type in ("test_run", "build_run") and not (run_id or commit_sha):
            raise ModelError(f"{type} evidence needs the run ID or commit it was observed for")
        verified = source_kind in VERIFIED_SOURCES and result != "claimed"
        with self.store.transaction("record evidence") as s:
            coll = {"task": "tasks", "handoff": "handoffs", "attempt": "attempts"}.get(subject_type)
            task_rev = 0
            if coll:
                subj = require(s, coll, subject_id)
                task_rev = int(subj.get("task_revision", 0))
            eid = next_id(s, "evidence")
            e = {"schema_version": SCHEMA_VERSION, "evidence_id": eid, "type": type, "subject_type": subject_type,
                 "subject_id": subject_id, "attempt_id": attempt_id, "task_revision": task_rev,
                 "source": {"kind": source_kind, "run_id": str(run_id)[:120], "commit_sha": commit_sha[:64]},
                 "result": result, "verified": verified,
                 "verification_method": source_kind if verified else "unverified model claim",
                 "summary": summary[:2000], "observed_at_utc": now_utc(), "state_revision": int(s["state_revision"]) + 1,
                 "artifact_sha256": artifact_sha256[:64], "details": details or {}}
            s["evidence"][eid] = e
            emit(s, "evidence_recorded", evidence_id=eid, subject_id=subject_id, verified=verified, kind=type)
        return e

    def evaluate_task(self, task_id: str, *, current_commit: str = "") -> dict[str, Any]:
        """Compute the policy status of a task from evidence; move it if the result differs.

        Returns {"status", "reasons", "verified", "reported"}.
        """
        with self.store.transaction(f"evaluate {task_id}") as s:
            t = require(s, "tasks", task_id)
            ev = [e for e in s["evidence"].values() if e["subject_type"] == "task" and e["subject_id"] == task_id
                  and int(e.get("task_revision", 0)) == int(t["task_revision"])]
            if current_commit:
                ev = [e for e in ev if not e["source"].get("commit_sha") or e["source"]["commit_sha"] == current_commit
                      or e["type"] in ("manual_review", "model_report")]
            verified = [e for e in ev if e["verified"]]
            reported = [e for e in ev if not e["verified"]]
            policy = t.get("acceptance_policy", "review_and_evidence")
            needs_review = "review" in t.get("required_approvals", []) or policy in ("review_and_evidence", "manual_review")
            needs_validation = policy in ("evidence_required", "review_and_evidence")
            last = lambda kinds: sorted([e for e in verified if e["type"] in kinds], key=lambda e: e["evidence_id"])  # noqa: E731
            reviews = last({"manual_review"})
            validations = last(VALIDATION_TYPES)
            reasons: list[str] = []
            review_ok = bool(reviews) and reviews[-1]["result"] == "approved"
            valid_ok = bool(validations) and validations[-1]["result"] == "passed"
            if needs_review and not review_ok:
                reasons.append("rejected by review" if reviews and reviews[-1]["result"] == "rejected" else "review missing")
            if needs_validation and not valid_ok:
                if validations and validations[-1]["result"] == "failed":
                    reasons.append(f"validation failed ({validations[-1]['evidence_id']})")
                else:
                    reasons.append("no verified test/build evidence (model claims do not count)" if reported
                                   else "validation not run")
            if t["status"] in ("cancelled", "superseded", "draft", "proposed", "blocked", "needs_decision", "ready"):
                target = t["status"]
            elif not reasons:
                target = "done"
            elif needs_review and not review_ok and (not needs_validation or valid_ok):
                target = "in_review"
            elif any(r.startswith("rejected") or r.startswith("validation failed") for r in reasons):
                target = "in_progress"
            elif needs_review and not review_ok:
                target = "in_review"
            else:
                target = "validation_pending"
            if target != t["status"]:
                check_transition("task", t["status"], target)
                old = t["status"]
                t["status"] = target
                t["updated_at"] = now_utc()
                emit(s, "task_status", task_id=task_id, old=old, new=target, why="; ".join(reasons) or "policy satisfied")
                if target == "done":
                    from .tasks import TaskService
                    TaskService._refresh_readiness(s)
            t["evaluation"] = {"at": now_utc(), "reasons": reasons, "verified": [e["evidence_id"] for e in verified],
                               "reported": [e["evidence_id"] for e in reported]}
            return {"status": target, "reasons": reasons, "verified": t["evaluation"]["verified"],
                    "reported": t["evaluation"]["reported"]}


def record_build_evidence(project: Any, git: Any, build: Any) -> list[dict[str, Any]]:
    """Turn a finished Sync & Build operation (real GitHub Actions run) into verified build
    evidence for every task that is waiting for validation. Model text is never involved;
    returns the new evidence records."""
    outcome = str(getattr(build, "outcome", "") or "")
    run_id = getattr(build, "run_id", None)
    sha = str(getattr(git, "commit_sha", "") or "")
    if not run_id or outcome not in ("success", "failure", "cancelled", "timed_out"):
        return []
    result = "passed" if outcome == "success" else "failed"
    out = []
    for t in project.tasks.list():
        if t["status"] not in ("validation_pending", "in_review", "in_progress"):
            continue
        if any(e["type"] == "build_run" and e["source"].get("run_id") == str(run_id)
               for e in project.evidence.list(t["task_id"])):
            continue
        out.append(project.evidence.record(type="build_run", subject_type="task", subject_id=t["task_id"],
                                           source_kind="github_actions", result=result, run_id=str(run_id),
                                           commit_sha=sha, summary=f"GitHub Actions run {run_id}: {outcome}"))
        if t["status"] == "validation_pending":
            project.evidence.evaluate_task(t["task_id"], current_commit=sha)
    return out
