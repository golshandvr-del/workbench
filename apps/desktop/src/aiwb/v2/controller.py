"""UI-independent controller for the V2 Projects window (roadmap 1.20.1 / 2.0.0 / 2.1.0).

The Simple and Advanced views are two *views* of this one controller (spec §19,
gate §28): the GUI never adds behaviour that is not defined here or in the
central services. Every model answer is captured raw in the Response Inbox
first and only then routed to a V2 service (proposal or handoff).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import V2Project, build_snapshot
from .handoff import BLOCK_RE as HANDOFF_RE
from .models import ModelError
from .proposals import BLOCK_RE as PROPOSAL_RE, manager_update_prompt, planning_prompt
from .snapshot import fallback_summary, render_status_md

# Plain-language labels for the Simple view: status words + a symbol, never colour alone (spec §19, 2.1.x).
SIMPLE_STATUS = {
    "draft": ("○", "Not planned yet"), "proposed": ("○", "Proposed"), "ready": ("▶", "Ready to start"),
    "in_progress": ("…", "Waiting for the model"), "blocked": ("■", "Blocked"),
    "needs_decision": ("?", "Needs your decision"), "in_review": ("◆", "Needs your review"),
    "validation_pending": ("◇", "Needs a real test/build"), "done": ("✓", "Done (verified)"),
    "cancelled": ("✕", "Cancelled"), "superseded": ("↷", "Replaced"),
}
SIMPLE_ACTION = {
    "plan_project": "Write the project goal and copy the planning prompt to your project-manager chat",
    "review_proposal": "Review the manager's proposal and accept the parts you agree with",
    "resolve_decision": "Make a decision the work is waiting for",
    "start_task": "Start the next task: copy its prompt to the agent's chat",
    "copy_prompt": "Copy the prepared prompt into the agent's chat",
    "import_response": "Paste the model's answer here",
    "review_handoff": "Review what the agent delivered",
    "run_validation": "Run the tests/build so the result is verified",
    "repair": "Ask the model only for what is missing",
    "publish_state": "Publish the project state to GitHub",
    "manager_update": "Send the manager an update",
    "replan": "Re-plan a blocked task",
    "unblock_task": "Unblock a task whose prerequisites changed",
    "approve_task": "Approve finished work so the task can be closed",
    "review_delivery": "Review what the agent delivered",
    "prepare_handoff": "Prepare the prompt for the next agent",
    "review_task": "Review the finished task",
}

MODES = ("simple", "advanced")


@dataclass
class RouteResult:
    kind: str                       # proposal | handoff | inbox_only | rejected
    response_id: str = ""
    message: str = ""
    reference_id: str = ""
    record: dict[str, Any] = field(default_factory=dict)


class ProjectsController:
    def __init__(self, root: Path, *, make_pipeline: Callable[[Path], Any] | None = None,
                 publisher: Any = None, base_commit: Callable[[], str] = lambda: "",
                 state_url: Callable[[], str] = lambda: "") -> None:
        self.root = root
        self.project = V2Project(root, root.name)
        self.notes = self.project.open()
        self.make_pipeline = make_pipeline
        self.publisher = publisher
        self.base_commit = base_commit
        self.state_url = state_url
        self.ui_path = self.project.store.dir / "ui.json"
        self.mode = self._load_ui().get("mode") or str(self.project.store.load()["settings"].get("ui_mode", "simple"))
        if self.mode not in MODES:
            self.mode = "simple"

    # -- mode: a view preference kept OUTSIDE the project state (spec §19.5: switching views changes no data,
    #    does not bump state_revision and never triggers a publish)
    def _load_ui(self) -> dict[str, Any]:
        try:
            d = json.loads(self.ui_path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ModelError("mode must be simple or advanced")
        self.mode = mode
        try:
            self.ui_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.ui_path.parent), prefix=".ui-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({**self._load_ui(), "mode": mode}, fh)
            os.replace(tmp, self.ui_path)
        except OSError:
            pass  # a view preference that cannot be saved is not an error

    def next_action_view(self) -> dict[str, Any] | None:
        """The same next action in both views (§19.1): Simple gets the summary, Advanced also the reason,
        the referenced entity and the queue behind it."""
        a = self.next_action()
        if not a:
            return None
        v = {"type": a["type"], "reference_id": a.get("reference_id", ""), "needs_approval": bool(a.get("needs_approval")),
             "summary": SIMPLE_ACTION.get(a["type"], a["label"])}
        if self.mode == "advanced":
            pending = bool(self.publisher and getattr(self.publisher, "pending", False))
            v.update(reason=a.get("reason", ""), label=a.get("label", ""),
                     queue=[f"{x['type']} {x.get('reference_id', '')}".strip()
                            for x in self.project.next_actions(publish_pending=pending)[1:6]])
        return v

    def advanced_panels(self) -> dict[str, str]:
        """Read-only texts for the Advanced view (§19): registry, ledgers, attempts, proposals, publish history.
        Pure projections of the same state; nothing here writes."""
        st = self.state()
        agents = [f"{a['agent_id']} · {a['name']} · role {a['role']} · rev {a['revision']} · "
                  f"{'enabled' if a.get('enabled', True) else 'disabled'} · model label "
                  f"{a.get('preferred_model_label') or '—'}" for a in st["agents"].values()]
        decisions = [f"{d['decision_id']} [{d['status']}] {d['title']}"
                     + (f" → {d.get('decision')}" if d.get("decision") else "")
                     + (f" · why: {d.get('rationale')}" if d.get("rationale") else "")
                     + (f" · superseded by {d['superseded_by']}" if d.get("superseded_by") else "")
                     for d in st["decisions"].values()]
        evidence = [f"{e['evidence_id']} {e['type']} {e['result']} · {e['subject_id']} rev {e.get('task_revision', '')} · "
                    f"{'VERIFIED' if e['verified'] else 'reported only'} ({e['source']['kind']}"
                    + (f", run {e['source']['run_id']}" if e['source'].get('run_id') else "")
                    + (f", commit {str(e['source'].get('commit_sha'))[:12]}" if e['source'].get('commit_sha') else "") + ")"
                    for e in st["evidence"].values()]
        attempts = [f"{a['attempt_id']} · {a.get('task_id', '')} rev {a.get('task_revision', '')} · {a.get('kind', '')} · "
                    f"{a['status']}" for a in st["attempts"].values()]
        handoffs = [f"{h['handoff_id']} {h.get('from_agent_id') or '—'} → {h['to_agent_id']} · {h['task_id']} · "
                    f"{h['status']} {h.get('outcome', '')}" for h in st["handoffs"].values()]
        proposals = [f"{p['proposal_id']} [{p['status']}] base rev {p.get('base_state_revision')} · "
                     f"{len(p.get('operations', []))} op(s){' · STALE' if p.get('stale') else ''} · {p.get('summary', '')}"
                     for p in st["proposals"].values()]
        pub = st["settings"].get("publish", {})
        lines = [f"State revision {st.get('state_revision', self.project.store.revision)} · source commit "
                 f"{self.base_commit() or '—'}",
                 f"Publishing {'on' if pub.get('enabled') else 'off'} · branch {pub.get('branch') or 'aiwb-state'}"]
        if self.publisher is not None:
            q = self.publisher.queue()
            lines += [f"Last published revision {q['last_published_revision']} · commit {q['last_commit'][:12] or '—'}",
                      f"Paused: {q['paused'] or 'no'} · last error: {q['last_error'] or '—'}"]
            lines += [f"  {h.get('publish_id', '')} rev {h.get('state_revision')} {h.get('commit', '')[:12]}"
                      for h in q.get("history", [])[-10:]]
        else:
            lines.append("No GitHub repository bound: state is kept locally only.")
        empty = "—"
        return {"Agents": "\n".join(agents) or empty, "Decisions": "\n".join(decisions) or empty,
                "Evidence": "\n".join(evidence) or empty, "Attempts": "\n".join(attempts + [""] + handoffs).strip() or empty,
                "Proposals": "\n".join(proposals) or empty, "Publish": "\n".join(lines)}

    # -- read models
    def state(self) -> dict[str, Any]:
        return self.project.store.load()

    def next_action(self) -> dict[str, Any] | None:
        pending = bool(self.publisher and getattr(self.publisher, "pending", False))
        acts = self.project.next_actions(publish_pending=pending)
        return acts[0] if acts else None

    def next_action_text(self) -> str:
        a = self.next_action()
        if not a:
            return "Nothing is waiting. Add a task or ask the manager for the next step."
        base = SIMPLE_ACTION.get(a["type"], a["label"])
        ref = f" ({a['reference_id']})" if a.get("reference_id") else ""
        return base + ref + ("" if self.mode == "simple" else f" — {a['reason']}")

    def task_rows(self) -> list[dict[str, Any]]:
        rows = []
        for t in self.project.tasks.list():
            sym, word = SIMPLE_STATUS.get(t["status"], ("·", t["status"]))
            row = {"task_id": t["task_id"], "title": t["title"], "symbol": sym, "status_text": word,
                   "status": t["status"], "owner": t.get("owner_agent_id", ""), "reason": t.get("blocked_reason", "")}
            if self.mode == "advanced":
                row.update(revision=t["task_revision"], depends_on=", ".join(t["depends_on"]),
                           attempt=t.get("active_attempt_id", ""), policy=t.get("acceptance_policy", ""))
            rows.append(row)
        return rows

    def warnings(self) -> list[str]:
        """Prioritised warnings: decisions and blockers first (2.1.x)."""
        st = self.state()
        out = [f"Decision needed: {d['title']} ({d['decision_id']})" for d in st["decisions"].values()
               if d["status"] == "proposed"]
        out += [f"Blocked: {t['title']} — {t.get('blocked_reason') or 'see details'}" for t in st["tasks"].values()
                if t["status"] == "blocked"]
        out += [f"Not verified yet: {t['title']}" for t in st["tasks"].values() if t["status"] == "validation_pending"]
        if self.publisher is not None:
            q = self.publisher.queue()
            if q.get("paused"):
                out.insert(0, "State publishing is paused: " + q["paused"])
        return out

    def task_details(self, task_id: str) -> str:
        st = self.state()
        t = st["tasks"].get(task_id)
        if not t:
            return ""
        lines = [f"{t['task_id']} · {t['title']}", f"Status: {SIMPLE_STATUS.get(t['status'], ('', t['status']))[1]}",
                 f"Goal: {t['objective']}"]
        if t.get("acceptance_criteria"):
            lines += ["Done when:"] + [f"  - {c}" for c in t["acceptance_criteria"]]
        if t.get("blocked_reason"):
            lines.append("Why blocked: " + t["blocked_reason"])
        if self.mode == "advanced":
            lines += ["", f"Revision {t['task_revision']} · policy {t['acceptance_policy']} · approvals "
                      f"{', '.join(t.get('required_approvals', []))}",
                      f"Depends on: {', '.join(t['depends_on']) or '—'}",
                      f"Active attempt: {t.get('active_attempt_id') or '—'}"]
            for h in self.project.handoffs.list(task_id):
                lines.append(f"Handoff {h['handoff_id']} → {h['to_agent_id']}: {h['status']} {h['outcome']}")
            for e in self.project.evidence.list(task_id):
                lines.append(f"Evidence {e['evidence_id']}: {e['type']} {e['result']} "
                             f"({'verified' if e['verified'] else 'reported only'}, {e['source']['kind']})")
            ev = t.get("evaluation") or {}
            if ev.get("reasons"):
                lines.append("Policy: " + "; ".join(ev["reasons"]))
        return "\n".join(lines)

    # -- prompts (Workbench prepares; the user copies)
    def planning_prompt(self, goal: str, constraints: list[str] | None = None) -> str:
        with self.project.store.transaction("project goal") as s:
            s["settings"]["goal"] = goal.strip()[:2000]
        return planning_prompt({"goal": goal, "constraints": constraints or []}, self.project.agents.list())

    def start_task(self, task_id: str, agent_id: str = "") -> dict[str, Any]:
        t = self.project.tasks.get(task_id)
        if t is None:
            raise ModelError(f"task {task_id} does not exist")
        agent = agent_id or t.get("owner_agent_id") or "agent-implementer"
        h = self.project.handoffs.prepare(task_id, agent, base_commit_sha=self.base_commit())
        self._dirty("handoff prepared")
        return h

    def mark_copied(self, handoff_id: str) -> None:
        self.project.handoffs.mark_exported(handoff_id)
        self._dirty("prompt copied")

    def manager_update(self) -> str:
        st = self.state()
        snap = build_snapshot(st, source={"commit_sha": self.base_commit()})
        return manager_update_prompt(snap, state_url=self.state_url(), fallback=fallback_summary(snap, st))

    def status_markdown(self) -> str:
        st = self.state()
        return render_status_md(build_snapshot(st), st)

    # -- one paste box for every answer
    def route_answer(self, text: str, *, file_hashes: dict[str, str] | None = None) -> RouteResult:
        if not text.strip():
            return RouteResult("rejected", message="The answer is empty.")
        rid = ""
        if self.make_pipeline is not None:
            cap = self.make_pipeline(self.root).capture_text(text, source="v2-projects")
            rid = cap.response.response_id if cap.response else ""
        rid = rid or "resp-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        try:
            if PROPOSAL_RE.search(text):
                p = self.project.proposals.import_text(text, response_id=rid)
                msg = f"Manager proposal {p['proposal_id']} with {len(p['operations'])} change(s) is ready for review."
                if p.get("stale"):
                    msg += " It was written for an older project state: review carefully."
                return RouteResult("proposal", rid, msg, p["proposal_id"], p)
            if HANDOFF_RE.search(text):
                hid = self._match_handoff(text)
                if not hid:
                    return RouteResult("rejected", rid, "This answer names a task/attempt this project is not waiting "
                                       "for. It is kept in the Inbox; nothing was changed.")
                h = self.project.handoffs.ingest(hid, rid, text, file_hashes=file_hashes)
                self._dirty("handoff answer")
                msg = f"Answer linked to {hid} ({h['status']}, {h['outcome'] or 'no outcome'})."
                if h["unresolved_items"]:
                    msg += " Still open: " + "; ".join(h["unresolved_items"][:5])
                return RouteResult("handoff", rid, msg, hid, h)
        except ModelError as exc:
            return RouteResult("rejected", rid, f"{exc} The raw answer is kept in the Inbox.")
        return RouteResult("inbox_only", rid, "No manager proposal or handoff block found. If it contains files, "
                           "use the normal Analyze / preview flow on the Response tab.")

    def _match_handoff(self, text: str) -> str:
        from .handoff import find_manifest
        try:
            data = find_manifest(text) or {}
        except ModelError:
            data = {}
        st = self.state()
        hid = str(data.get("handoff_id", ""))
        if hid in st["handoffs"]:
            return hid
        att = str(data.get("attempt_id", ""))
        for h in st["handoffs"].values():
            if att and h["attempt_id"] == att:
                return h["handoff_id"]
        return ""

    # -- review actions (the only state changes, each one a user decision)
    def accept_proposal(self, proposal_id: str, indices: list[int], *, confirm_stale: bool = False) -> dict[str, Any]:
        out = self.project.proposals.review(proposal_id, indices, confirm_stale=confirm_stale)
        self._dirty("proposal reviewed")
        return out

    def resolve_handoff(self, handoff_id: str, accept: bool, reason: str = "") -> dict[str, Any]:
        out = self.project.handoffs.resolve(handoff_id, accept, reason)
        self._dirty("handoff resolved")
        return out

    def review_task(self, task_id: str, approved: bool, note: str = "") -> dict[str, Any]:
        self.project.evidence.record(type="manual_review", subject_type="task", subject_id=task_id, source_kind="user",
                                     result="approved" if approved else "rejected", summary=note[:500])
        out = self.project.evidence.evaluate_task(task_id, current_commit=self.base_commit())
        self._dirty("review recorded")
        return out

    def resolve_decision(self, decision_id: str, accept: bool, decision: str = "", rationale: str = "") -> dict[str, Any]:
        out = self.project.decisions.resolve(decision_id, accept, decision=decision, rationale=rationale)
        self._dirty("decision")
        return out

    def publish_now(self) -> dict[str, Any]:
        if self.publisher is None:
            return {"status": "disabled", "message": "No GitHub repository is bound; state is kept locally."}
        return self.publisher.tick(force=True)

    def _dirty(self, reason: str) -> None:
        if self.publisher is not None:
            try:
                self.publisher.mark_dirty(reason)
            except Exception:  # noqa: BLE001 - publishing never blocks local work
                pass
