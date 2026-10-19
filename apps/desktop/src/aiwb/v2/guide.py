"""Guided loop without dead ends (roadmap 3.5.0).

For every reachable project state :func:`steps` returns at least one *Step*: a title, a plain
explanation, who it is for (an AI's queue or the user), an optional ready prompt and the actions
that move the project on. :class:`Guide` performs those actions through the existing services only
— it adds no state machine of its own. Rules kept from earlier roadmaps:

* nothing is sent to a model: prompts are copied by the user, who records "copied" / "sent" with one
  click each;
* every model answer is pasted, normalized and routed through :meth:`ProjectsController.route_answer`;
* acceptance, decisions, reviews, validation and releases are explicit user actions with their facts.

Automatic prompts: *Manager Update* (state changed since the manager last saw it / nothing else to
do), *Review* (ask a reviewer AI to check a delivery), *Repair* (ask only for what a delivery is
missing) and *Continue* (the pasted answer was cut off).
"""
from __future__ import annotations

import json
from typing import Any

from .models import ModelError, now_utc

USER = "you"            # queue of steps that only the user can do (decisions, reviews, releases)
MANAGER = "agent-project-manager"

# Step kinds: prompt (copy a ready prompt, then paste the answer) · paste (an answer is awaited) ·
# decision (a real choice) · form (one input is needed to build the next prompt).
KINDS = ("prompt", "paste", "decision", "form")


def _a(id_: str, label: str, *needs: str, primary: bool = False) -> dict[str, Any]:
    return {"id": id_, "label": label, "needs": list(needs), "primary": primary}


def _step(key: str, kind: str, title: str, explain: str, actions: list[dict[str, Any]], *, agent: str = USER,
          ref: str = "", prompt: str = "", rank: int = 50, **extra: Any) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(kind)
    if actions and not any(a["primary"] for a in actions):
        actions[0]["primary"] = True
    return {"key": key, "kind": kind, "title": title, "explain": explain, "agent_id": agent, "ref": ref,
            "prompt": prompt, "actions": actions, "rank": rank, **extra}


def _g(state: dict[str, Any]) -> dict[str, Any]:
    return state["settings"].get("guide") or {}


def _open_handoff(state: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    hs = [h for h in state["handoffs"].values() if h["task_id"] == task_id and h["status"] in
          ("prepared", "prompt_exported", "response_received", "parsed", "reconciled", "stale", "reconciliation_required")]
    return max(hs, key=lambda h: h["handoff_id"]) if hs else None


def _sent(state: dict[str, Any], h: dict[str, Any]) -> bool:
    att = state["attempts"].get(h.get("attempt_id", "")) or {}
    return bool((att.get("workflow") or {}).get("sent_confirmed_at"))


def _copied(state: dict[str, Any], h: dict[str, Any]) -> bool:
    att = state["attempts"].get(h.get("attempt_id", "")) or {}
    return bool((att.get("workflow") or {}).get("copied_at")) or h["status"] != "prepared"


def _owner(state: dict[str, Any], t: dict[str, Any]) -> str:
    o = t.get("owner_agent_id") or ""
    if o and (state["agents"].get(o) or {}).get("enabled", True) and o in state["agents"]:
        return o
    return "agent-implementer" if "agent-implementer" in state["agents"] else next(iter(state["agents"]), "")


# -- prompts ---------------------------------------------------------------------------------------
def repair_prompt(state: dict[str, Any], h: dict[str, Any], new: dict[str, Any] | None = None) -> str:
    """Ask the same AI only for what its delivery ``h`` is missing — never for what arrived. ``new`` is the
    fresh handoff/attempt the answer must name (defaults to ``h``)."""
    t = state["tasks"][h["task_id"]]
    n = new or h
    done = [a["logical_path"] for a in h.get("artifact_refs", [])] or list(h.get("completed_items", []))
    missing = [x for x in h.get("unresolved_items", [])]
    lines = [f"AIWB_ATTEMPT_ID: {n['attempt_id']}", "(Repeat the line above as the first line of your answer.)", "",
             f"# AI Workbench — repair request for {h['handoff_id']} ({t['task_id']} {t['title']})",
             "Your previous delivery was incomplete. Send ONLY what is missing; do not resend what already arrived."]
    if done:
        lines += ["", "## Arrived complete (do NOT resend)"] + [f"- {p}" for p in done]
    lines += ["", "## Still missing"] + ([f"- {m}" for m in missing] or ["- (see the acceptance criteria below)"])
    lines += ["", "## Acceptance criteria"] + ([f"- [ ] {c}" for c in t.get("acceptance_criteria", [])] or ["- (none)"])
    from .handoff import FILE_RULES
    lines += ["", "## Format", *FILE_RULES, "- Then one manifest:", "<<<AIWB_HANDOFF>>>",
              json.dumps({"schema_version": "1.0", "handoff_id": n["handoff_id"], "task_id": n["task_id"],
                          "task_revision": n["task_revision"], "attempt_id": n["attempt_id"],
                          "outcome": "complete|partial", "summary": "…", "completed_items": ["…"],
                          "unresolved_items": [], "validation_claims": []}, ensure_ascii=False),
              "<<<AIWB_END_HANDOFF>>>"]
    return "\n".join(lines)


def review_prompt(state: dict[str, Any], task_id: str) -> str:
    """Ask a reviewer AI to check a delivery against the acceptance criteria (its answer is advice only)."""
    t = state["tasks"][task_id]
    hs = sorted([h for h in state["handoffs"].values() if h["task_id"] == task_id and h["status"] == "accepted"],
                key=lambda h: h["handoff_id"])
    last = hs[-1] if hs else {}
    lines = [f"# AI Workbench — review request for {task_id} {t['title']}",
             "You have NO access to earlier chats or to the project files. Review only what is below.", "",
             f"## Objective\n{t['objective']}", "", "## Acceptance criteria"]
    lines += [f"- [ ] {c}" for c in t.get("acceptance_criteria", [])] or ["- (none)"]
    lines += ["", "## Delivery summary", str(last.get("summary") or "(no summary)")]
    lines += [f"- Done: {x}" for x in last.get("completed_items", [])]
    lines += [f"- Open: {x}" for x in last.get("unresolved_items", [])]
    lines += [f"- Claimed (NOT verified): {x}" for x in last.get("validation_claims", [])]
    lines += [f"- File: {a['logical_path']}" for a in last.get("artifact_refs", [])[:40]]
    lines += ["", "## Answer", "For every criterion answer PASS, FAIL or UNKNOWN with one sentence. Then one line "
              "`VERDICT: APPROVE` or `VERDICT: CHANGES` and the exact changes needed. Never claim you ran anything."]
    return "\n".join(lines)


def continue_project_prompt(update: str) -> str:
    return update + ("\n\n## What I need now\nEvery planned task is finished or waiting. Propose the next step: new "
                     "tasks for the next milestone, fixes for blocked work, or say that the project is complete. "
                     "Answer with one AIWB_MANAGER_PROPOSAL block.")


# -- steps -----------------------------------------------------------------------------------------
def steps(ctl: Any) -> list[dict[str, Any]]:  # noqa: C901 — one flat table of states is the clearest form
    """All open steps, most urgent first. Never empty."""
    st = ctl.state()
    g = _g(st)
    out: list[dict[str, Any]] = []
    tasks = st["tasks"]

    cont = g.get("continue")
    if cont:
        out.append(_step("continue", "prompt", "The last answer was cut off — ask to continue",
                         "The pasted answer ended before it finished. Copy this prompt into the same chat; "
                         "it asks for the rest only. Then paste the new answer.",
                         [_a("copy", "Copy continue prompt"), _a("paste", "Paste the rest", "text"),
                          _a("dismiss", "Ignore the cut-off answer")],
                         agent=cont.get("agent_id") or USER, prompt=cont.get("prompt", ""), rank=0))

    for p in sorted(st["proposals"].values(), key=lambda p: p["proposal_id"]):
        if p["status"] == "pending":
            n = sum(1 for o in p["operations"] if o["valid"])
            out.append(_step(f"proposal:{p['proposal_id']}", "decision",
                             f"Review the plan {p['proposal_id']} ({n} change{'s' if n != 1 else ''})",
                             (p.get("summary") or "The project manager proposed changes.") + " Nothing is applied "
                             "until you accept it." + (" It was written for an older state — check it." if p.get("stale") else ""),
                             [_a("accept", "Accept all valid changes"), _a("reject", "Reject the plan"),
                              _a("request_changes", "Ask for changes…", "note")],
                             ref=p["proposal_id"], rank=5))

    for d in sorted(st["decisions"].values(), key=lambda d: d["decision_id"]):
        if d["status"] == "proposed":
            out.append(_step(f"decision:{d['decision_id']}", "decision", f"Decide: {d['title']}",
                             (d.get("problem") or "") + (f" Options: {', '.join(d['options'])}." if d.get("options") else "")
                             + (f" Recommended: {d['recommendation']}." if d.get("recommendation") else ""),
                             [_a("decide", "Decide…", "choice", "rationale"), _a("reject_decision", "Reject…", "rationale")],
                             ref=d["decision_id"], rank=8))

    for h in sorted(st["handoffs"].values(), key=lambda h: h["handoff_id"]):
        t = tasks.get(h["task_id"]) or {}
        who = h["to_agent_id"]
        label = f"{h['task_id']} {t.get('title', '')}".strip()
        if h["status"] == "reconciled":
            missing = [x for x in h.get("unresolved_items", [])]
            acts = [_a("accept_handoff", "Accept the delivery"), _a("reject_handoff", "Reject…", "reason")]
            if missing:
                acts.insert(1, _a("repair", "Ask only for what is missing"))
            out.append(_step(f"handoff:{h['handoff_id']}", "decision", f"Check what {who} delivered for {label}",
                             (h.get("summary") or "The answer was read.") + (f" Missing: {'; '.join(missing[:4])}." if missing else "")
                             + " Accepting never applies files and never closes the task.",
                             acts, agent=USER, ref=h["handoff_id"], rank=10, task_id=h["task_id"]))
        elif h["status"] in ("stale", "reconciliation_required"):
            out.append(_step(f"handoff:{h['handoff_id']}", "decision", f"The answer for {label} is out of date",
                             "; ".join(h.get("stale_reasons", []))[:300] or "The task changed after the prompt was made.",
                             [_a("accept_handoff", "Accept anyway…", "reason"), _a("reject_handoff", "Reject…", "reason")],
                             ref=h["handoff_id"], rank=11, task_id=h["task_id"]))
        elif h["status"] in ("prepared", "prompt_exported", "response_received", "parsed"):
            copied, sent = _copied(st, h), _sent(st, h)
            if not copied:
                title, kind, rank = f"Copy the prompt for {label} into {who}'s chat", "prompt", 22
                acts = [_a("copy", "Copy prompt"), _a("sent", "I sent it"), _a("paste", "Paste the answer", "text")]
            elif not sent:
                title, kind, rank = f"Send the copied prompt for {label} to {who}", "prompt", 21
                acts = [_a("sent", "I sent it"), _a("copy", "Copy again"), _a("paste", "Paste the answer", "text")]
            else:
                title, kind, rank = f"Paste {who}'s answer for {label}", "paste", 20
                acts = [_a("paste", "Paste the answer", "text"), _a("copy", "Copy the prompt again")]
            acts.append(_a("abandon", "Drop this prompt…", "reason"))
            out.append(_step(f"handoff:{h['handoff_id']}", kind, title,
                             "Workbench never sends anything itself. Paste the whole answer when it is ready; "
                             "a cut-off answer gets a continue prompt.", acts, agent=who, ref=h["handoff_id"],
                             prompt=h.get("prompt", ""), rank=rank, task_id=h["task_id"]))

    for t in sorted(tasks.values(), key=lambda t: t["task_id"]):
        tid, s_ = t["task_id"], t["status"]
        name = f"{tid} {t['title']}"
        if _open_handoff(st, tid):
            continue
        if s_ == "in_review":
            out.append(_step(f"task:{tid}", "decision", f"Review {name}",
                             "Compare the delivery with the acceptance criteria: " + "; ".join(t.get("acceptance_criteria", []))[:300],
                             [_a("approve", "Approve"), _a("reject_review", "Needs changes…", "note"),
                              _a("review_prompt", "Ask a reviewer AI")], ref=tid, rank=16))
        elif s_ == "validation_pending":
            out.append(_step(f"task:{tid}", "decision", f"Verify {name}",
                             "Run the tests or the build, then record the real result with its run ID or commit. "
                             "A model's claim does not count.",
                             [_a("record_validation", "Record the test/build result…", "result", "run_id")], ref=tid, rank=14))
        elif s_ in ("ready", "in_progress"):
            who = _owner(st, t)
            out.append(_step(f"task:{tid}", "prompt", f"Start {name} with {who}",
                             "All prerequisites are done. Workbench builds a self-contained prompt for that AI's chat.",
                             [_a("prepare", "Prepare the prompt")], agent=who, ref=tid, rank=40))
        elif s_ == "needs_decision" and not any(d["status"] == "proposed" and tid in d["affected_task_ids"]
                                                 for d in st["decisions"].values()):
            out.append(_step(f"task:{tid}", "decision", f"{name} waits for a decision",
                             t.get("blocked_reason") or "The AI asked for a decision.",
                             [_a("decide", "Decide and continue…", "choice", "rationale"),
                              _a("manager_prompt", "Ask the project manager")], ref=tid, rank=9))
        elif s_ == "blocked" and not str(t.get("blocked_reason", "")).startswith("waiting for"):
            out.append(_step(f"task:{tid}", "decision", f"{name} is blocked",
                             t.get("blocked_reason") or "The task cannot continue as it is.",
                             [_a("unblock", "It can continue now"), _a("manager_prompt", "Ask the project manager to re-plan"),
                              _a("cancel", "Cancel the task…", "reason")], ref=tid, rank=60))
        elif s_ in ("draft", "proposed"):
            out.append(_step(f"task:{tid}", "decision", f"Approve {name}",
                             "The task is a draft. Approve it so it can start, or cancel it.",
                             [_a("make_ready", "Approve the task"), _a("cancel", "Cancel…", "reason")], ref=tid, rank=70))

    for m in sorted(st["milestones"].values(), key=lambda m: m["milestone_id"]):
        if m["status"] != "planned" or not m["task_ids"]:
            continue
        if all(tasks.get(x, {}).get("status") in ("done", "cancelled", "superseded") for x in m["task_ids"]):
            out.append(_step(f"milestone:{m['milestone_id']}", "decision", f"Accept milestone {m['title']}",
                             "All its tasks are done. Check its criteria: " + "; ".join(m.get("criteria", []))[:300],
                             [_a("accept_milestone", "Accept the milestone")], ref=m["milestone_id"], rank=75))
    for v in sorted(st["versions"].values(), key=lambda v: v["version_id"]):
        if v["status"] in ("released", "withdrawn"):
            continue
        ms = [st["milestones"].get(x) or {} for x in v.get("milestone_ids", [])]
        if ms and all(m.get("status") == "accepted" for m in ms):
            out.append(_step(f"version:{v['version_id']}", "decision", f"Release version {v['label']}",
                             f"Its milestones are accepted (status now {v['status']}). Record the real commit, tag and "
                             "build run or artifact; Workbench never assumes a release.",
                             [_a("release", "Record the release…", "commit_sha", "tag", "run_id"),
                              _a("withdraw", "Withdraw the version")], ref=v["version_id"], rank=78))

    if not tasks and not any(p["status"] == "pending" for p in st["proposals"].values()):
        goal = str(st["settings"].get("goal", "")).strip()
        if not goal:
            out.append(_step("design", "form", "Describe the project",
                             "Write the goal in one or two sentences. Workbench builds the 'design the whole project' "
                             "prompt for your project-manager chat.", [_a("design", "Design the whole project…", "goal")],
                             agent=MANAGER, rank=1))
        else:
            out.append(_step("charter", "prompt", "Get the Project Charter from your project-manager chat",
                             f"Goal: {goal[:200]}. Copy the prompt, send it, then paste the whole answer.",
                             [_a("copy", "Copy the charter prompt"), _a("sent", "I sent it"),
                              _a("paste", "Paste the charter", "text"), _a("design", "Change the goal…", "goal")],
                             agent=MANAGER, prompt=ctl.charter_prompt({"goal": goal, **(st["settings"].get("brief") or {})}),
                             rank=2))

    manager_rev = int(g.get("manager_seen_revision", 0))
    actionable = [s for s in out if s["agent_id"] == USER or s["kind"] in ("prompt", "form")]
    if not actionable:
        due = int(st.get("state_revision", 0)) > manager_rev
        upd = ctl.manager_update()
        out.append(_step("manager_update", "prompt",
                         "Tell the project manager what changed and ask for the next step" if due
                         else "Ask the project manager for the next step",
                         "Nothing else is waiting for you. Copy the update, send it, then paste the manager's plan.",
                         [_a("copy", "Copy manager update"), _a("sent", "I sent it"), _a("paste", "Paste the plan", "text")],
                         agent=MANAGER, prompt=continue_project_prompt(upd), rank=90))
    out.sort(key=lambda s: (s["rank"], s["key"]))
    return out


def queues(ctl: Any) -> dict[str, list[dict[str, Any]]]:
    """Steps grouped by whose chat they belong to (each AI) or the user."""
    q: dict[str, list[dict[str, Any]]] = {}
    for s in steps(ctl):
        q.setdefault(s["agent_id"], []).append(s)
    return q


# -- actions ---------------------------------------------------------------------------------------
class Guide:
    """Performs the actions of a step through the existing services. Returns {"message", "prompt"?}."""

    def __init__(self, ctl: Any) -> None:
        self.ctl = ctl
        self.p = ctl.project

    def steps(self) -> list[dict[str, Any]]:
        return steps(self.ctl)

    def next(self) -> dict[str, Any]:
        return self.steps()[0]

    def queues(self) -> dict[str, list[dict[str, Any]]]:
        return queues(self.ctl)

    def find(self, key: str) -> dict[str, Any]:
        for s in self.steps():
            if s["key"] == key:
                return s
        raise ModelError(f"step {key} is no longer open")

    def _set_guide(self, *, seen: bool = False, **kw: Any) -> None:
        """Update settings.guide; ``seen`` records that the manager has seen this very revision."""
        with self.p.store.transaction("guide") as s:
            g = s["settings"].setdefault("guide", {})
            if seen:
                g["manager_seen_revision"] = int(s["state_revision"]) + 1
            for k, v in kw.items():
                if v is None:
                    g.pop(k, None)
                else:
                    g[k] = v

    def perform(self, key: str, action: str, **inp: Any) -> dict[str, Any]:  # noqa: C901
        step = self.find(key)
        if action not in [a["id"] for a in step["actions"]]:
            raise ModelError(f"{action!r} is not possible for this step")
        for need in next(a for a in step["actions"] if a["id"] == action)["needs"]:
            if need not in ("note", "reason", "rationale", "run_id", "commit_sha", "tag") and not str(inp.get(need, "")).strip():
                raise ModelError(f"{need.replace('_', ' ')} is required")
        kind, ref = key.split(":", 1) if ":" in key else (key, "")
        c = self.ctl

        if action == "paste":
            return self._paste(step, str(inp.get("text", "")))
        if action == "copy":
            if kind == "handoff":
                c.mark_copied(ref)
            elif kind in ("manager_update", "charter"):
                self._set_guide(manager_copied_at=now_utc())
            return {"message": "Copied. Paste it into the chat, send it, then click 'I sent it'.", "prompt": step["prompt"]}
        if action == "sent":
            if kind == "handoff":
                c.confirm_sent(ref)
            else:
                self._set_guide(seen=True, manager_sent_at=now_utc())
            return {"message": "Recorded as sent. Paste the answer when you have it."}
        if action == "dismiss":
            self._set_guide(**{"continue": None})
            return {"message": "The cut-off answer is ignored; it stays in the Inbox."}
        if action == "design":
            prompt = c.charter_prompt({"goal": str(inp["goal"])})
            return {"message": "Project Charter prompt ready to copy.", "prompt": prompt}
        if action == "accept":
            p = self.p.proposals.get(ref)
            out = c.accept_proposal(ref, [o["index"] for o in p["operations"] if o["valid"]], confirm_stale=True)
            return {"message": f"Plan {ref} {out['status']}."}
        if action == "reject":
            c.accept_proposal(ref, [])
            return {"message": f"Plan {ref} rejected. Nothing changed."}
        if action == "request_changes":
            prompt = c.proposal_revision_prompt(ref, str(inp.get("note", "")))
            c.accept_proposal(ref, [])
            return {"message": "Change request ready to copy to the project manager.", "prompt": prompt}
        if action in ("decide", "reject_decision"):
            why = str(inp.get("rationale", "")).strip() or "decided in the guided loop"
            if kind == "task":
                t = self.p.tasks.get(ref)
                d = self.p.decisions.propose((t.get("blocked_reason") or "Decision")[:200], t.get("blocked_reason") or "",
                                             affected_task_ids=[ref] if t["status"] != "needs_decision" else [])
                c.resolve_decision(d["decision_id"], True, decision=str(inp["choice"]), rationale=why)
                with self.p.store.transaction("decision recorded for task") as s:
                    task = s["tasks"][ref]
                    if task["status"] == "needs_decision":
                        from .tasks import readiness
                        task["status"] = "in_progress" if task.get("active_attempt_id") else readiness(task, s["tasks"])[0]
                        task["blocked_reason"] = ""
                return {"message": f"Decision recorded ({d['decision_id']}); {ref} can continue."}
            c.resolve_decision(ref, action == "decide", decision=str(inp.get("choice", "")), rationale=why)
            return {"message": f"Decision {ref} recorded."}
        if action == "accept_handoff":
            c.resolve_handoff(ref, True, str(inp.get("reason", "")) or "accepted in the guided loop")
            return {"message": f"Delivery {ref} accepted. Next: review the task."}
        if action == "reject_handoff":
            c.resolve_handoff(ref, False, str(inp.get("reason", "")))
            return {"message": f"Delivery {ref} rejected. A new prompt can be prepared."}
        if action == "repair":
            h = self.p.handoffs.get(ref)
            c.resolve_handoff(ref, True, "partial delivery accepted; repair requested for the missing items")
            if self.p.tasks.get(h["task_id"])["status"] == "in_review":
                self.p.tasks.transition(h["task_id"], "in_progress", "repair requested")
            nh = c.start_task(h["task_id"], h["to_agent_id"])
            with self.p.store.transaction("repair prompt") as s:
                s["handoffs"][nh["handoff_id"]]["prompt"] = prompt = repair_prompt(s, h, s["handoffs"][nh["handoff_id"]])
                s["handoffs"][nh["handoff_id"]]["repair_of"] = ref
            return {"message": f"Repair prompt for {h['task_id']} ready (only the missing items).", "prompt": prompt,
                    "handoff_id": nh["handoff_id"]}
        if action == "abandon":
            c.resolve_handoff(ref, False, str(inp.get("reason", "")) or "dropped by the user")
            return {"message": f"Prompt {ref} dropped."}
        if action == "prepare":
            h = c.start_task(ref, step["agent_id"])
            return {"message": f"Prompt for {ref} ready. Copy it into {h['to_agent_id']}'s chat.", "prompt": h["prompt"],
                    "handoff_id": h["handoff_id"]}
        if action == "approve":
            out = c.review_task(ref, True, str(inp.get("note", "")))
            return {"message": f"{ref} review approved → {out['status']}."}
        if action == "reject_review":
            out = c.review_task(ref, False, str(inp.get("note", "")))
            return {"message": f"{ref} needs changes → {out['status']}."}
        if action == "review_prompt":
            return {"message": "Review prompt ready for a reviewer AI (its answer is advice; you decide).",
                    "prompt": review_prompt(c.state(), ref)}
        if action == "record_validation":
            result = str(inp["result"]).lower()
            if result not in ("passed", "failed"):
                raise ModelError("result must be 'passed' or 'failed'")
            run = str(inp.get("run_id", "")).strip() or "manual-" + now_utc()
            self.p.evidence.record(type="test_run", subject_type="task", subject_id=ref, source_kind="user",
                                   result=result, run_id=run, summary="recorded in the guided loop")
            out = self.p.evidence.evaluate_task(ref, current_commit=c.base_commit())
            c._dirty("validation recorded")
            return {"message": f"Validation {result} recorded → {ref} {out['status']}."}
        if action == "make_ready":
            self.p.tasks.transition(ref, "ready", "approved in the guided loop")
            return {"message": f"{ref} approved."}
        if action == "unblock":
            self.p.tasks.transition(ref, "ready", "unblocked by the user")
            return {"message": f"{ref} can continue."}
        if action == "cancel":
            self.p.tasks.transition(ref, "cancelled", str(inp.get("reason", "")) or "cancelled by the user")
            return {"message": f"{ref} cancelled."}
        if action == "manager_prompt":
            return {"message": "Manager update ready to copy.", "prompt": c.manager_update()}
        if action == "accept_milestone":
            self.p.timeline.accept_milestone(ref)
            return {"message": f"Milestone {ref} accepted."}
        if action == "release":
            v = self.p.timeline.versions()
            v = next(x for x in v if x["version_id"] == ref)
            sha, tag, run = (str(inp.get(k, "")).strip() for k in ("commit_sha", "tag", "run_id"))
            if v["status"] == "proposed":
                self.p.timeline.advance_version(ref, "local", commit_sha=sha)
                v["status"] = "local"
            if v["status"] == "local":
                self.p.timeline.advance_version(ref, "tagged", tag=tag or "v" + v["label"])
            self.p.timeline.advance_version(ref, "released", run_id=run)
            return {"message": f"Version {v['label']} released."}
        if action == "withdraw":
            self.p.timeline.advance_version(ref, "withdrawn")
            return {"message": f"Version {ref} withdrawn."}
        raise ModelError(f"unknown action {action!r}")

    def _paste(self, step: dict[str, Any], text: str) -> dict[str, Any]:
        from ..intake.normalize import continue_prompt, truncation_report
        if not text.strip():
            raise ModelError("the answer is empty")
        rep = truncation_report(text)
        r = self.ctl.route_answer(text)
        out: dict[str, Any] = {"message": r.message, "kind": r.kind}
        if r.kind == "charter_rejected":
            out["prompt"] = r.record.get("fix_prompt", "")
        if r.kind in ("proposal", "handoff", "charter_rejected"):
            self._set_guide(**{"continue": None})
            if step["key"] in ("manager_update", "charter"):
                self._set_guide(seen=True)
            if r.kind == "handoff" and rep.truncated:
                out["message"] += " The answer looks cut off — use 'Ask only for what is missing'."
            return out
        if rep.truncated:
            att = ""
            if step["key"].startswith("handoff:"):
                att = (self.p.handoffs.get(step["ref"]) or {}).get("attempt_id", "")
            prompt = continue_prompt(rep, attempt_id=att)
            self._set_guide(**{"continue": {"prompt": prompt, "agent_id": step["agent_id"], "for": step["key"],
                                            "at": now_utc()}})
            out.update(message="The answer was cut off. A continue prompt is ready.", prompt=prompt, kind="truncated")
        return out
