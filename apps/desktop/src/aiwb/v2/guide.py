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
RESULT_WORDS = {w: "passed" for w in ("passed", "pass", "ok", "yes", "y", "green", "success")}
RESULT_WORDS.update({w: "failed" for w in ("failed", "fail", "no", "n", "red", "failure")})
KINDS = ("prompt", "paste", "decision", "form")
TROUBLESHOOT_ATTEMPTS = 3  # flowchart correction C1: then escalate to the project manager
# Optional inputs of the start form (roadmap 4.0.0, flowchart F4): name, platform, constraints, number of AIs.
BRIEF_OPTIONAL = ("name", "platform", "constraints", "ais")
OPTIONAL_INPUTS = ("note", "reason", "rationale", "run_id", "commit_sha", "tag") + BRIEF_OPTIONAL


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


def continue_project_prompt(update: str, state: dict[str, Any] | None = None) -> str:
    """F18: the status report to the project manager (roadmap 4.4.0) — what changed, what is stuck, GitHub facts and
    the decision contract (emergency tasks, roadmap remaining)."""
    from .report import status_prompt
    return status_prompt(state or {}, update)


def github_steps(ctl: Any, st: dict[str, Any]) -> list[dict[str, Any]]:
    """Blue nodes (roadmap 4.5.0): F3 connect, F22 save, F24 release — every write waits for 'Confirm'."""
    from .repo import release_needed, repo_info, unsaved_files
    out: list[dict[str, Any]] = []
    if not str(st["settings"].get("goal", "")).strip():
        return out
    fs = st["settings"].get("flow") or {}
    pend = fs.get("github_pending")
    has_token = getattr(getattr(ctl, "repo", None), "client_factory", None) is not None
    if pend:
        k = pend["kind"]
        what = {"create": "create the repository", "connect": "connect the repository", "save": "save files on GitHub",
                "release": f"publish {pend['payload'].get('tag', '')}"}[k]
        acts = ([_a("confirm", "Confirm and send to GitHub")] if has_token else []) + [
            _a("record", "I did it by hand — record…", *(("owner", "name") if k in ("create", "connect") else
                                                         ("commit_sha",) if k == "save" else ("tag", "commit_sha", "run_id"))),
            _a("cancel_github", "Cancel")]
        out.append(_step(f"github:{k}", "decision", f"GitHub: {what}",
                         ("Nothing is sent until you confirm. " if has_token else "No GitHub token: do it by hand, then record it. ")
                         + " ".join(pend.get("steps") or []), acts, ref=pend["action_id"], rank=6, github=pend))
        return out
    repo = repo_info(st)
    if not repo.get("full_name"):
        out.append(_step("github:connect", "form", "GitHub: connect or create the project repository (optional)",
                         "Workbench saves approved files on its own branch (never main) and publishes releases — each "
                         "write only after you confirm.",
                         [_a("prepare_connect", "Connect an existing repository…", "owner", "name"),
                          _a("prepare_create", "Create a new private repository…", "owner", "name")], rank=89))
        return out
    if unsaved_files(st):
        out.append(_step("github:save", "decision", f"GitHub: save {len(unsaved_files(st))} approved file(s)",
                         f"Commit them to {repo.get('branch')} on {repo['full_name']} (no force push).",
                         [_a("prepare_save", "Prepare the commit")], rank=77))
    for v in release_needed(st):
        out.append(_step(f"github:release:{v['version_id']}", "decision", f"GitHub: publish version {v['label']}",
                         "All its milestones are accepted. Tag and GitHub Release after your confirmation.",
                         [_a("prepare_release", "Prepare the release")], ref=v["version_id"], rank=79))
    return out


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
        diag = [x for x in h.get("diagnosis") or [] if x.get("severity") == "error"]
        if h["status"] in ("reconciled", "stale", "reconciliation_required") and diag:
            n = int((g.get("troubleshoot") or {}).get(h["task_id"], 0))
            found = "; ".join(f"[{x['code']}] {x['message']}" for x in diag[:4])
            if n >= TROUBLESHOOT_ATTEMPTS:
                acts = [_a("escalate", "Ask the project manager (stuck)"), _a("accept_handoff", "Accept anyway…", "reason"),
                        _a("reject_handoff", "Reject…", "reason")]
                why = f" {n} troubleshooting prompts did not fix it — hand it to the project manager."
            else:
                acts = [_a("troubleshoot", "Build the troubleshooting prompt"), _a("accept_handoff", "Accept anyway…", "reason"),
                        _a("reject_handoff", "Reject…", "reason")]
                why = f" Troubleshooting attempt {n + 1} of {TROUBLESHOOT_ATTEMPTS}."
            out.append(_step(f"handoff:{h['handoff_id']}", "decision", f"Problems found in {who}'s answer for {label}",
                             "Smart check: " + found + "." + why, acts, agent=USER, ref=h["handoff_id"], rank=9,
                             task_id=h["task_id"], problems=diag))
        elif h["status"] == "reconciled":
            missing = [x for x in h.get("unresolved_items", [])]
            acts = [_a("accept_handoff", "Accept the delivery"), _a("reject_handoff", "Reject…", "reason")]
            if missing:
                acts.insert(1, _a("repair", "Ask only for what is missing"))
            out.append(_step(f"handoff:{h['handoff_id']}", "decision", f"Check what {who} delivered for {label}",
                             (h.get("summary") or "The answer was read.") + (f" Missing: {'; '.join(missing[:4])}." if missing else "")
                             + (f" Accepting adds {len(h.get('staged_files') or [])} delivered file(s) to the project files"
                                " (old versions are backed up); it never closes the task." if h.get("staged_files")
                                else " Accepting never closes the task."),
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

    from .waves import dispatch
    desk = dispatch(st)
    if len(desk["next"]) > 1:
        names = ", ".join(f"{x} → {desk['owners'][x]}" for x in desk["next"])
        out.append(_step("dispatch", "prompt", f"Prepare the prompts for {len(desk['next'])} parallel tasks",
                         f"Parallel paths of this wave: {names}. {desk['slots']} of {desk['limit']} chat(s) are free"
                         + (f"; {len(desk['queued'])} more task(s) wait for a free chat." if desk["queued"] else ".")
                         + " Each AI gets its own self-contained prompt.",
                         [_a("prepare_all", "Prepare all prompts")], rank=39, task_ids=list(desk["next"])))

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
                             "Run the tests or the build (e.g. ./gradlew test or a CI run), then record what really happened. "
                             "A model's claim does not count. If you cannot run anything here, accept it on review alone "
                             "— it stays marked NOT RUN.",
                             [_a("validation_passed", "Tests/build passed…", "run_id"),
                              _a("validation_failed", "Tests/build failed…", "note"),
                              _a("waive_validation", "I can't run tests — accept on review…", "reason"),
                              _a("record_validation", "Record the result (passed/failed)…", "result", "run_id")], ref=tid, rank=14))
        elif s_ in ("ready", "in_progress"):
            if tid not in desk["next"]:
                continue  # waits for a free chat or for its wave (roadmap 4.1.0, dispatch desk)
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
    connected = bool(((st["settings"].get("flow") or {}).get("repo") or {}).get("full_name"))
    for v in sorted(st["versions"].values(), key=lambda v: v["version_id"]):
        if v["status"] in ("released", "withdrawn") or connected:  # connected: the GitHub release step (4.5.0)
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
            out.append(_step("design", "form", "Start the project",
                             "Give the project a name, its goal (one or two sentences), the platform, any constraints and "
                             "how many AI chats you can use at the same time. Workbench starts the timeline and builds the "
                             "'design the whole project' prompt for your project-manager chat.",
                             [_a("design", "Start the project…", "goal", *BRIEF_OPTIONAL)], agent=MANAGER, rank=1))
        else:
            out.append(_step("charter", "prompt", "Get the Project Charter from your project-manager chat",
                             f"Goal: {goal[:200]}. Copy the prompt, send it, then paste the whole answer.",
                             [_a("copy", "Copy the charter prompt"), _a("sent", "I sent it"),
                              _a("paste", "Paste the charter", "text"), _a("design", "Change the project details…", "goal",
                                                                              *BRIEF_OPTIONAL)],
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
                         agent=MANAGER, prompt=continue_project_prompt(upd, st), rank=90))
    out += github_steps(ctl, st)  # optional blue nodes never hide the manager update (roadmap 4.5.0)
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

    def flow(self) -> dict[str, Any]:
        """Where the project is in the owner's flowchart (roadmap 4.0.0)."""
        from .flow import current
        return current(self.ctl.state())

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
                g["manager_seen_at"] = now_utc()
            for k, v in kw.items():
                if v is None:
                    g.pop(k, None)
                else:
                    g[k] = v

    def waive_validation(self, task_id: str, reason: str) -> dict[str, Any]:
        """The user cannot run tests/builds: accept on review alone (mobile 1.0.1 / 3.9.1).

        Nothing is faked — no passing evidence is created. The task records the waiver and its reason, its policy
        becomes ``manual_review`` (same task revision, so the recorded review still counts) and the timeline shows it.
        """
        from .store import emit, require
        why = (reason.strip() or "tests/build cannot be run by the user")[:500]
        with self.p.store.transaction("waive validation") as s:
            t = require(s, "tasks", task_id)
            if t["status"] not in ("validation_pending", "in_review", "in_progress"):
                raise ModelError(f"validation can only be waived while the task is being checked (now {t['status']})")
            t["acceptance_policy"] = "manual_review"
            t["validation_waiver"] = {"at": now_utc(), "reason": why, "task_revision": int(t["task_revision"]),
                                      "result": "not_run"}
            flag = f"validation NOT RUN (waived by the user): {why}"
            if flag not in t.setdefault("flags", []):
                t["flags"].append(flag)
            emit(s, "validation_waived", task_id=task_id, why=why, importance="major")
        out = self.p.evidence.evaluate_task(task_id, current_commit=self.ctl.base_commit())
        self.ctl._dirty("validation waived")
        return out

    def perform(self, key: str, action: str, **inp: Any) -> dict[str, Any]:  # noqa: C901
        step = self.find(key)
        if action not in [a["id"] for a in step["actions"]]:
            raise ModelError(f"{action!r} is not possible for this step")
        for need in next(a for a in step["actions"] if a["id"] == action)["needs"]:
            if need not in OPTIONAL_INPUTS and not str(inp.get(need, "")).strip():
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
            from .flow import start_project
            start_project(self.p.store, {k: inp.get(k, "") for k in ("goal",) + BRIEF_OPTIONAL})
            brief = c.state()["settings"].get("brief") or {}
            prompt = c.charter_prompt({**brief, "goal": str(inp["goal"])})
            return {"message": "Project started. Project Charter prompt ready to copy.", "prompt": prompt}
        if action == "accept":
            p = self.p.proposals.get(ref)
            out = c.accept_proposal(ref, [o["index"] for o in p["operations"] if o["valid"]], confirm_stale=True)
            from .report import route_message
            return {"message": f"Plan {ref} {out['status']}." + route_message((out.get("result") or {}).get("decision"))}
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
            from .files import integrate
            c.resolve_handoff(ref, True, str(inp.get("reason", "")) or "accepted in the guided loop")
            written = integrate(self.p.store, c.root, ref)
            added = f" {len(written)} file(s) added to the project files." if written else ""
            return {"message": f"Delivery {ref} accepted.{added} Next: review the task.", "files": written}
        if action == "reject_handoff":
            c.resolve_handoff(ref, False, str(inp.get("reason", "")))
            return {"message": f"Delivery {ref} rejected. A new prompt can be prepared."}
        if action == "troubleshoot":
            from .diagnose import troubleshoot_prompt
            h = self.p.handoffs.get(ref)
            problems = list(h.get("diagnosis") or [])
            c.resolve_handoff(ref, False, "troubleshooting: " + ", ".join(sorted({x["code"] for x in problems})))
            nh = c.start_task(h["task_id"], h["to_agent_id"])
            with self.p.store.transaction("troubleshooting prompt") as s:
                g = s["settings"].setdefault("guide", {})
                tr = g.setdefault("troubleshoot", {})
                tr[h["task_id"]] = n = int(tr.get(h["task_id"], 0)) + 1
                new = s["handoffs"][nh["handoff_id"]]
                new["prompt"] = prompt = troubleshoot_prompt(s, h, new, problems, n)
                new["troubleshoot_of"] = ref
                from .store import emit
                emit(s, "troubleshooting_prompt", task_id=h["task_id"], handoff_id=nh["handoff_id"], attempt=n,
                     codes=sorted({x["code"] for x in problems}))
            return {"message": f"Troubleshooting prompt {n} for {h['task_id']} ready (only the problems found). "
                               f"Copy it into {h['to_agent_id']}'s chat.", "prompt": prompt, "handoff_id": nh["handoff_id"]}
        if action == "escalate":
            h = self.p.handoffs.get(ref)
            c.resolve_handoff(ref, False, "stuck after troubleshooting; escalated to the project manager")
            with self.p.store.transaction("escalate") as s:
                t = s["tasks"][h["task_id"]]
                if t["status"] in ("in_progress", "ready"):
                    from .models import check_transition
                    check_transition("task", t["status"], "blocked")
                    t["status"] = "blocked"
                t["blocked_reason"] = (f"stuck after {TROUBLESHOOT_ATTEMPTS} troubleshooting prompts: "
                                       + "; ".join(x["message"] for x in (h.get("diagnosis") or [])[:3]))[:500]
                from .store import emit
                emit(s, "task_escalated", task_id=h["task_id"], importance="major")
            return {"message": f"{h['task_id']} is handed to the project manager; the update prompt is ready.",
                    "prompt": continue_project_prompt(c.manager_update(), c.state())}
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
        if action == "prepare_all":
            made = [c.start_task(tid, _owner(c.state(), c.state()["tasks"][tid])) for tid in step.get("task_ids", [])]
            return {"message": f"{len(made)} prompts ready: " + ", ".join(f"{h['task_id']} → {h['to_agent_id']}" for h in made)
                    + ". Copy each one into its AI's chat.", "prompt": made[0]["prompt"] if made else "",
                    "handoff_ids": [h["handoff_id"] for h in made]}
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
        if action in ("validation_passed", "validation_failed"):
            inp = {**inp, "result": "passed" if action == "validation_passed" else "failed",
                   "run_id": str(inp.get("run_id", "")).strip() or str(inp.get("note", "")).strip()[:100]}
            action = "record_validation"
        if action == "waive_validation":
            out = self.waive_validation(ref, str(inp.get("reason", "")))
            return {"message": f"{ref} accepted on review without tests (NOT RUN) → {out['status']}."}
        if action == "record_validation":
            result = RESULT_WORDS.get(str(inp["result"]).strip().lower(), "")
            if result not in ("passed", "failed"):
                raise ModelError("result must be 'passed' or 'failed' (or use the 'passed' / 'failed' buttons)")
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
        if kind == "github":
            return self._github(action, step["ref"], inp)
        if action == "withdraw":
            self.p.timeline.advance_version(ref, "withdrawn")
            return {"message": f"Version {ref} withdrawn."}
        raise ModelError(f"unknown action {action!r}")

    def _github(self, action: str, ref: str, inp: dict[str, Any]) -> dict[str, Any]:
        """Blue nodes (4.5.0): prepare → confirm (token) or record (by hand); cancel drops the pending write."""
        r = self.ctl.repo
        if action in ("prepare_connect", "prepare_create"):
            a = r.prepare(action.split("_", 1)[1], owner=inp.get("owner", ""), name=inp.get("name", ""))
        elif action == "prepare_save":
            a = r.prepare("save")
        elif action == "prepare_release":
            a = r.prepare("release", version_id=ref)
        elif action == "confirm":
            out = r.confirm(ref)
            return {"message": "Done on GitHub: " + ", ".join(f"{k} {v}" for k, v in out.items() if v and k != "count")}
        elif action == "record":
            pend = r.pending() or {}
            r.record(pend.get("kind", ""), **{k: inp.get(k, "") for k in ("owner", "name", "commit_sha", "tag", "run_id")
                                             if inp.get(k)})
            return {"message": "Recorded."}
        elif action == "cancel_github":
            r.cancel()
            return {"message": "Cancelled. Nothing was sent to GitHub."}
        else:
            raise ModelError(f"unknown action {action!r}")
        return {"message": "Prepared. " + ("Check it and confirm to send it to GitHub." if not a["manual"]
                                           else "No token: " + " ".join(a["steps"]))}

    def _diagnose(self, handoff_id: str, text: str) -> list[dict[str, Any]]:
        """F13/F14: run the smart check on a linked answer and keep the problems on the handoff."""
        from .diagnose import diagnose, task_paths
        st = self.ctl.state()
        h = st["handoffs"].get(handoff_id)
        if not h:
            return []
        t = st["tasks"].get(h["task_id"]) or {}
        att = st["attempts"].get(h["attempt_id"]) or {}
        res = diagnose(text, attempt_id=h["attempt_id"], allowed_paths=task_paths(t),
                       expected_paths=list(att.get("expected_paths") or []))
        with self.p.store.transaction("diagnose answer") as s:
            s["handoffs"][handoff_id]["diagnosis"] = res["problems"]
        return res["problems"]

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
            if r.kind == "handoff":
                from .files import stage
                staged = stage(self.p.store, r.reference_id, text)
                if staged:
                    out["staged"] = [x["path"] for x in staged]
                probs = self._diagnose(r.reference_id, text)
                errs = [x for x in probs if x["severity"] == "error"]
                if errs:
                    out["message"] += " Smart check found problems: " + "; ".join(x["code"] for x in errs) + \
                        ". A troubleshooting prompt can be built."
                elif probs:
                    out["message"] += " Check: " + "; ".join(x["message"] for x in probs[:3]) + "."
                elif rep.truncated:
                    out["message"] += " The answer looks cut off — use 'Ask only for what is missing'."
                out["problems"] = probs
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
