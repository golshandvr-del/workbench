"""Team Planner: team settings, resource summary, team planning prompt and Team Proposal checks
(roadmap 2.4.0 / stage 4, spec §7, Gate A).

* Resources are what the *user* registered (Account Profiles, Chat Bindings) — never guessed from
  words such as "paid account"; registering a profile is not a verification of the account.
* ``max_parallel_chats`` is how many chats the user is willing to follow at the same time. It is
  separate from the number of logical agents.
* A Team Proposal is the existing ``AIWB_MANAGER_PROPOSAL`` block (``proposal_type: "team_plan"``)
  plus an optional ``team`` object and two operations: ``create_agent`` and ``assign_account``.
  Old proposals without ``team`` keep working unchanged.
* :func:`check_team` never changes state; it returns explicit issues (errors block the affected
  operation, warnings are shown in the review) so nothing is silently ignored.
"""
from __future__ import annotations

import re
from typing import Any

from .models import ROLES, ModelError, valid_id
from .resources import current_binding

PRIORITIES = ("balanced", "speed", "simplicity", "quality", "low_cost")
DEFAULT_TEAM_SETTINGS = {"max_parallel_chats": 2, "pm_agent_id": "agent-project-manager", "priority": "balanced"}
MAX_PARALLEL_CHATS = 12


def team_settings(state: dict[str, Any]) -> dict[str, Any]:
    cur = dict(DEFAULT_TEAM_SETTINGS)
    cur.update({k: v for k, v in (state.get("settings", {}).get("team") or {}).items() if k in DEFAULT_TEAM_SETTINGS})
    return cur


def normalize_team_settings(state: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    out = team_settings(state)
    unknown = [k for k in changes if k not in DEFAULT_TEAM_SETTINGS]
    if unknown:
        raise ModelError(f"unknown team setting(s): {', '.join(unknown)}")
    if "max_parallel_chats" in changes:
        try:
            n = int(changes["max_parallel_chats"])
        except (TypeError, ValueError):
            raise ModelError("max_parallel_chats must be a whole number") from None
        if not 1 <= n <= MAX_PARALLEL_CHATS:
            raise ModelError(f"max_parallel_chats must be between 1 and {MAX_PARALLEL_CHATS}")
        out["max_parallel_chats"] = n
    if "pm_agent_id" in changes:
        aid = str(changes["pm_agent_id"] or "")
        agent = state["agents"].get(aid)
        if agent is None or agent["role"] != "project_manager":
            raise ModelError("the project manager must be an existing agent with role project_manager")
        out["pm_agent_id"] = aid
    if "priority" in changes:
        if changes["priority"] not in PRIORITIES:
            raise ModelError(f"priority must be one of {', '.join(PRIORITIES)}")
        out["priority"] = changes["priority"]
    return out


def resources_summary(state: dict[str, Any]) -> dict[str, Any]:
    accs = [a for a in state.get("account_profiles", {}).values() if a.get("enabled", True)]
    agents = [a for a in state["agents"].values() if a.get("enabled", True)]
    ts = team_settings(state)
    bound = {}
    for a in agents:
        b = current_binding(state, a["agent_id"])
        if b:
            bound[a["agent_id"]] = b["account_profile_id"]
    return {"accounts": sorted(accs, key=lambda a: a["account_profile_id"]), "agents": sorted(agents, key=lambda a: a["agent_id"]),
            "bindings": bound, "max_parallel_chats": ts["max_parallel_chats"], "pm_agent_id": ts["pm_agent_id"],
            "priority": ts["priority"]}


TEAM_FORMAT = """Return your analysis in plain text, then exactly ONE block:
<<<AIWB_MANAGER_PROPOSAL>>>
{"schema_version": "1.0", "proposal_type": "team_plan", "base_state_revision": <the state_revision above>,
 "summary": "…", "assumptions": ["…"],
 "team": {"pm_counted": true, "total_agents": 3, "additional_workers": 2,
          "size_rationale": "why this team size fits the work and the parallel-chat limit",
          "simpler_alternative": "a smaller/lower-risk option and its trade-off", "confidence": "low|medium|high"},
 "operations": [
  {"operation": "create_agent", "agent_id": "agent-implementer-2", "role": "implementer", "name": "Implementer 2",
   "purpose": "…", "reason": "…"},
  {"operation": "assign_account", "agent_id": "agent-implementer-2", "account_profile_id": "ACC-0002", "reason": "…"},
  {"operation": "create_task", "temporary_ref": "new-1", "title": "…", "objective": "…", "owner_agent_id": "agent-implementer",
   "reviewer_agent_id": "agent-reviewer", "parallel_group": "A", "depends_on_refs": [],
   "acceptance_criteria": ["…"], "scope": {"include": ["path/**"], "exclude": []}, "priority": "medium"},
  {"operation": "report_risk", "description": "…"}],
 "risks": ["…"], "questions_for_user": ["…"]}
<<<AIWB_END_MANAGER_PROPOSAL>>>
Rules:
- Use ONLY the account profile IDs listed above (ACC-…); never invent accounts or claim quotas. If none fit, leave the
  agent without assign_account and ask the user.
- State explicitly whether you (the project manager) are counted in total_agents (pm_counted).
- Tasks in the same parallel_group run at the same time: never put more groups' work in parallel than the parallel-chat
  limit, and never put tasks with overlapping file scope in the same group.
- Prefer a small team; propose a bigger one only with its benefit, risk and management cost.
- Every task needs owner, scope, acceptance criteria and dependencies — or say what is missing.
- Never mark tasks done; Workbench assigns task IDs (use temporary_ref)."""


def team_planning_prompt(project: dict[str, Any], state: dict[str, Any]) -> str:
    """Planning prompt with registered resources and an explicit team-size question (spec §7.2, stage 4)."""
    r = resources_summary(state)
    lines = ["# AI Workbench — Team planning", "You are the Project Manager for this project. You cannot read files, "
             "run anything or contact other chats; the user copies every prompt by hand.", "",
             f"State revision: {int(state.get('state_revision', 0))}", "", "## Project",
             f"- Goal: {project.get('goal', '')}"]
    for k, label in (("non_goals", "Non-goals"), ("success", "Success criteria"), ("platform", "Platform / technology"),
                     ("constraints", "Constraints"), ("limits", "Time / cost limits")):
        if project.get(k):
            lines.append(f"- {label}: {project[k]}")
    lines.append(f"- Priority: {r['priority']}")
    lines += ["", "## Resources registered by the user (self-declared labels, NOT verified)"]
    if r["accounts"]:
        for a in r["accounts"]:
            lines.append(f"- {a['account_profile_id']}: {a['display_name']} ({a['provider']}, plan {a['plan']})"
                         + (f" — used for: {', '.join(a['usage_tags'])}" if a.get("usage_tags") else ""))
    else:
        lines.append("- (no account profiles registered — plan for one chat at a time and ask the user)")
    lines += [f"- Maximum chats the user will follow at the same time: {r['max_parallel_chats']}", "",
              "## Existing agents (roles)"]
    for a in r["agents"]:
        acc = r["bindings"].get(a["agent_id"])
        pm = " — project manager (you)" if a["agent_id"] == r["pm_agent_id"] else ""
        lines.append(f"- {a['agent_id']} ({a['role']}){pm}: {a['purpose']}" + (f" [uses {acc}]" if acc else ""))
    lines += ["", "## Your task",
              "1. Propose the team: how many logical agents, their roles and responsibilities, and which registered "
              "account each one uses. Explain why this size is right and give a simpler alternative.",
              "2. Propose the first tasks (3–8) with owner, reviewer if needed, scope, acceptance criteria, "
              "dependencies and parallel groups that respect the parallel-chat limit.",
              "3. List risks, assumptions and the questions only the user can answer.", "", TEAM_FORMAT]
    return "\n".join(lines)


def _norm_team(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    if isinstance(raw.get("pm_counted"), bool):
        out["pm_counted"] = raw["pm_counted"]
    for k in ("total_agents", "additional_workers"):
        try:
            if raw.get(k) is not None:
                out[k] = int(raw[k])
        except (TypeError, ValueError):
            out[k + "_invalid"] = str(raw.get(k))[:40]
    for k, n in (("size_rationale", 2000), ("simpler_alternative", 2000), ("confidence", 20)):
        if raw.get(k):
            out[k] = str(raw[k])[:n]
    return out


def normalize_team(raw: Any) -> dict[str, Any]:
    return _norm_team(raw)


def _scope_key(p: str) -> str:
    return re.sub(r"(/\*\*|/\*|\*\*|\*)$", "", str(p).strip().strip("/"))


def scopes_overlap(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    out = []
    for x in (a or {}).get("include", []) or []:
        for y in (b or {}).get("include", []) or []:
            kx, ky = _scope_key(x), _scope_key(y)
            if not kx or not ky or kx == ky or kx.startswith(ky + "/") or ky.startswith(kx + "/"):
                out.append(f"{x} ↔ {y}")
    return out


def check_team(data: dict[str, Any], ops: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    """Validate a (team) proposal against real agents, registered resources and the parallel limit.

    Returns ``{"team": normalized, "issues": [{"level", "code", "message", "op_index"}], "op_errors": {index: msg},
    "counts": {...}}``. Pure: never writes.
    """
    team = _norm_team(data.get("team"))
    issues: list[dict[str, Any]] = []
    op_errors: dict[int, str] = {}
    ts = team_settings(state)

    def add(level: str, code: str, msg: str, idx: int | None = None) -> None:
        issues.append({"level": level, "code": code, "message": msg, "op_index": idx})
        if level == "error" and idx is not None:
            op_errors.setdefault(idx, msg)

    accs = state.get("account_profiles", {})
    new_agents: dict[str, str] = {}
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            continue
        name = op.get("operation")
        if name == "create_agent":
            aid = op.get("agent_id")
            if not valid_id("agent", aid):
                add("error", "bad_agent_id", f"#{i + 1} create_agent: agent_id must look like 'agent-implementer-2'", i)
            elif aid in state["agents"] or aid in new_agents:
                add("error", "agent_exists", f"#{i + 1} create_agent: agent {aid} already exists", i)
            elif op.get("role") not in ROLES:
                add("error", "bad_role", f"#{i + 1} create_agent: role must be one of {', '.join(ROLES)}", i)
            else:
                new_agents[aid] = op["role"]
    agent_ids = set(state["agents"]) | set(new_agents)
    used_accounts: dict[str, list[str]] = {}
    groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            continue
        name = op.get("operation")
        if name == "assign_account":
            aid, acc = op.get("agent_id"), op.get("account_profile_id")
            if aid not in agent_ids:
                add("error", "unknown_agent", f"#{i + 1} assign_account: agent {aid} does not exist and is not created here", i)
            elif acc not in accs:
                add("error", "unknown_account", f"#{i + 1} assign_account: account profile {acc} is not registered; "
                    "the manager cannot invent resources", i)
            elif not accs[acc].get("enabled", True):
                add("error", "account_disabled", f"#{i + 1} assign_account: account profile {acc} is disabled", i)
            else:
                used_accounts.setdefault(acc, []).append(aid)
        if name in ("create_task", "split_task"):
            owner = op.get("owner_agent_id", "")
            if owner and owner not in agent_ids:
                add("error", "unknown_owner", f"#{i + 1} {name}: owner {owner} does not exist and is not created here", i)
            rev = op.get("reviewer_agent_id", "")
            if rev and rev not in agent_ids:
                add("error", "unknown_reviewer", f"#{i + 1} {name}: reviewer {rev} does not exist", i)
            missing = [k for k, ok in (("owner", owner or op.get("owner_role")), ("scope", (op.get("scope") or {}).get("include")),
                                       ("acceptance criteria", op.get("acceptance_criteria"))) if not ok]
            if missing:
                add("warning", "incomplete_task", f"#{i + 1} {op.get('title', name)}: missing {', '.join(missing)}", i)
            g = str(op.get("parallel_group") or "").strip()
            if g:
                groups.setdefault(g[:20], []).append((i, op))
    for acc, users in used_accounts.items():
        if len(users) > 1:
            add("info", "account_reused", f"account profile {acc} ({accs[acc]['display_name']}) is reused by "
                f"{', '.join(users)} — each agent still needs its own chat")
    if groups:
        # tasks in different groups may be parallel only if independent; we can only check the explicit limit:
        widest = max(len(v) for v in groups.values())
        if widest > ts["max_parallel_chats"]:
            g = max(groups, key=lambda k: len(groups[k]))
            add("warning", "parallel_limit", f"parallel group {g} has {widest} tasks at once but you follow at most "
                f"{ts['max_parallel_chats']} chat(s); run them in turns or raise the limit")
        for g, items in groups.items():
            for x in range(len(items)):
                for y in range(x + 1, len(items)):
                    ov = scopes_overlap(items[x][1].get("scope") or {}, items[y][1].get("scope") or {})
                    if ov:
                        add("warning", "scope_overlap", f"parallel group {g}: #{items[x][0] + 1} and #{items[y][0] + 1} "
                            f"touch the same files ({ov[0]}); do not run them at the same time")
    is_team = data.get("proposal_type") == "team_plan" or bool(data.get("team")) or bool(new_agents)
    enabled_agents = [a for a in state["agents"].values() if a.get("enabled", True)]
    total_after = len(enabled_agents) + len(new_agents)
    if is_team:
        if "pm_counted" not in team:
            add("warning", "pm_count_unclear", "the manager did not say whether it is counted in the team size")
        if "total_agents" in team:
            pm_in = team.get("pm_counted", True)
            workers = team.get("additional_workers")
            if workers is not None and pm_in and team["total_agents"] != workers + 1:
                add("warning", "count_mismatch", f"total_agents {team['total_agents']} with the manager counted should be "
                    f"additional_workers + 1 = {workers + 1}")
            if workers is not None and not pm_in and team["total_agents"] != workers:
                add("warning", "count_mismatch", f"total_agents {team['total_agents']} without the manager should equal "
                    f"additional_workers {workers}")
        if "total_agents" in team:
            actual = total_after if team.get("pm_counted", True) else total_after - 1
            if team["total_agents"] != actual:
                add("warning", "declared_vs_actual", f"the manager says {team['total_agents']} agent(s) but accepting every "
                    f"create_agent gives {actual} ({total_after} enabled incl. the manager); check the count")
        if not accs:
            add("warning", "no_resources", "no account profiles are registered; every agent will share whatever chat you use")
        if not team.get("size_rationale"):
            add("warning", "no_rationale", "the manager did not explain why this team size is appropriate")
    counts = {"agents_now": len(enabled_agents), "agents_new": len(new_agents), "agents_after": total_after,
              "accounts": sum(1 for a in accs.values() if a.get("enabled", True)),
              "max_parallel_chats": ts["max_parallel_chats"], "parallel_groups": len(groups),
              "widest_group": max((len(v) for v in groups.values()), default=0),
              "pm_counted": team.get("pm_counted"), "declared_total": team.get("total_agents"),
              "declared_workers": team.get("additional_workers")}
    return {"team": team, "issues": issues, "op_errors": op_errors, "counts": counts, "is_team": is_team}


def revision_request_prompt(proposal: dict[str, Any], user_note: str = "") -> str:
    """'Request changes' (spec §7.5): a prompt listing the issues; nothing is applied."""
    lines = ["# AI Workbench — please revise your proposal",
             f"Your proposal {proposal['proposal_id']} (base revision {proposal['base_state_revision']}) has status "
             f"'{proposal['status']}'" + (" — nothing was applied." if proposal["status"] in ("pending", "rejected") else
                                          "; only the operations the user accepted were applied."),
             "Fix the points below and return a complete new AIWB_MANAGER_PROPOSAL block (same format)."]
    issues = [i for i in proposal.get("team_issues", []) if i["level"] in ("error", "warning")]
    issues_txt = [f"- [{i['level']}] {i['message']}" for i in issues]
    issues_txt += [f"- [error] #{o['index'] + 1} {o['operation']}: {o['problem']}" for o in proposal["operations"]
                   if not o["valid"] and o.get("problem")]
    lines += ["", "## Issues found by Workbench"] + (issues_txt or ["- (none)"])
    if user_note.strip():
        lines += ["", "## User note", user_note.strip()[:2000]]
    return "\n".join(lines)
