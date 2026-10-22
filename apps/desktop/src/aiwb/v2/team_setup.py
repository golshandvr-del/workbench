"""The user's own AI team (roadmap 5.9.0, audit A1/A5/A8/A9).

Before 5.9.0 a new project silently received four template agents (project manager, architect, implementer,
reviewer), the "how many AIs" answer only changed a setting, and the AIs could not be named. Now the New Project
wizard collects one table — *name · role · model label · note* — and this module turns it into agents:

* the project manager is always the first row and keeps the stable id ``agent-project-manager`` (the guide and the
  team settings refer to it); only its name, model label and note are the user's;
* every other row gets an id derived from its name (``"Core developer"`` → ``agent-core-developer``); a name with no
  latin letters (for example Persian) gets ``agent-ai-<n>``; ids never collide and never change after creation;
* :func:`apply_wizard` records the brief through :func:`flow.start_project` (so the guide never asks the start
  questions again) and writes the team in one transaction; no template agent is installed for such a project;
* :func:`save_team` is the Agents page's team editor: rename, change role or model label, add rows, and remove rows —
  an AI that never received work is deleted, one with history is only disabled, so nothing recorded is lost;
* :func:`unused_template_agents` finds the template AIs an older project got automatically and never used, so the
  app can *offer* to remove them (opening an old project changes nothing by itself).

Pure apart from the store transactions; no Tk.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from .agents import BASE_TEMPLATE_IDS, TEMPLATES
from .models import ModelError, normalize_agent, now_utc, valid_id
from .store import emit

PM_ID = "agent-project-manager"
MAX_WORKERS = 12          # the same limit as team.MAX_PARALLEL_CHATS; the project manager comes on top
DEFAULT_WORKERS = 2

# Wizard role choices: (label shown to the user, model role)
ROLE_CHOICES: tuple[tuple[str, str], ...] = (
    ("Developer", "implementer"),
    ("Architect", "architect"),
    ("Reviewer / tester", "reviewer"),
    ("Researcher", "researcher"),
)
PM_ROLE_LABEL = "Project manager"
ROLE_LABEL = {role: label for label, role in ROLE_CHOICES} | {"project_manager": PM_ROLE_LABEL}
LABEL_ROLE = {label: role for label, role in ROLE_CHOICES} | {PM_ROLE_LABEL: "project_manager"}

ANSWER_FORMATS: tuple[tuple[str, str], ...] = (
    ("aiwb", "AIWB file blocks (recommended)"),
    ("json", "Strict JSON"),
    ("zip", "GPT ZIP"),
)
SUPPORTED_FORMATS = ("aiwb",)   # what the guided loop reads today; JSON and ZIP readers come with 5.10.0

_RESEARCHER = {
    "purpose": "Research one approved question and report findings, sources and open points.",
    "instructions": ["Separate facts with sources from your own inference", "Say what you could not find",
                     "Do not change project files unless the task asks for it"],
    "allowed_task_types": ["research", "analysis"], "output_contract": "aiwb-handoff-v1",
    "review_policy": "none", "escalation_rules": ["missing_information"],
}


def role_of(label_or_role: str) -> str:
    """A wizard label (``"Developer"``) or a model role (``"implementer"``) → the model role."""
    v = str(label_or_role or "").strip()
    if v in LABEL_ROLE:
        return LABEL_ROLE[v]
    if v in ROLE_LABEL:
        return v
    raise ModelError(f"unknown role {v!r}; choose one of: {', '.join(label for label, _r in ROLE_CHOICES)}")


def slug(name: str) -> str:
    """Latin letters and digits of ``name`` joined by '-', lowercase; '' if there are none."""
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    return s[:50].strip("-")


def agent_id_for(name: str, taken: set[str] | list[str] | tuple[str, ...], index: int = 1) -> str:
    """A new, unique, valid agent id for ``name`` (``agent-<slug>``, else ``agent-ai-<index>``)."""
    used = set(taken)
    base = slug(name)
    if not base or base == "project-manager":
        base = f"ai-{index}" if base != "project-manager" else "project-manager-2"
    cand, n = f"agent-{base}", 2
    while cand in used or not valid_id("agent", cand):
        cand = f"agent-{base}-{n}"
        n += 1
    return cand


def default_rows(workers: int = DEFAULT_WORKERS) -> list[dict[str, str]]:
    """The table the wizard starts with: the project manager plus ``workers`` developers."""
    rows = [{"name": "Project manager", "role": "project_manager", "model": "", "note": ""}]
    rows += [{"name": f"Developer {i}", "role": "implementer", "model": "", "note": ""} for i in range(1, workers + 1)]
    return rows


def resize_rows(rows: list[dict[str, str]], workers: int) -> list[dict[str, str]]:
    """Grow or shrink the table to ``workers`` AIs after the project manager, keeping what the user typed."""
    workers = max(1, min(MAX_WORKERS, int(workers)))
    pm = [dict(rows[0])] if rows and rows[0].get("role") == "project_manager" else default_rows(0)
    rest = [dict(r) for r in rows[1:]] if rows and rows[0].get("role") == "project_manager" else [dict(r) for r in rows]
    rest = rest[:workers]
    names = {r.get("name", "") for r in rest}
    i = 1
    while len(rest) < workers:
        while f"Developer {i}" in names:
            i += 1
        rest.append({"name": f"Developer {i}", "role": "implementer", "model": "", "note": ""})
        names.add(f"Developer {i}")
    return pm + rest


def check_rows(rows: list[dict[str, Any]]) -> list[str]:
    """Problems that block the table (empty list = fine). Pure."""
    errors: list[str] = []
    if not rows or role_of(rows[0].get("role", "")) != "project_manager":
        errors.append("the first row must be the project manager")
    workers = rows[1:] if rows else []
    if not workers:
        errors.append("add at least one AI besides the project manager")
    if len(workers) > MAX_WORKERS:
        errors.append(f"at most {MAX_WORKERS} AIs besides the project manager")
    seen: dict[str, int] = {}
    for i, r in enumerate(rows or [], start=1):
        name = str(r.get("name", "")).strip()
        if not name:
            errors.append(f"row {i}: give this AI a name")
            continue
        if len(name) > 120:
            errors.append(f"row {i}: the name is longer than 120 characters")
        key = name.casefold()
        if key in seen:
            errors.append(f"row {i}: the name {name!r} is already used in row {seen[key]}")
        seen.setdefault(key, i)
        try:
            role = role_of(r.get("role", ""))
        except ModelError as exc:
            errors.append(f"row {i}: {exc}")
            continue
        if i > 1 and role == "project_manager":
            errors.append(f"row {i}: only the first row is the project manager")
    return errors


def _agent_data(agent_id: str, row: dict[str, Any]) -> dict[str, Any]:
    role = role_of(row.get("role", ""))
    tpl_id = {"project_manager": PM_ID, "architect": "agent-architect", "implementer": "agent-implementer",
              "reviewer": "agent-reviewer"}.get(role)
    base = copy.deepcopy(TEMPLATES[tpl_id]) if tpl_id else copy.deepcopy(_RESEARCHER)
    base.pop("name", None)
    base.pop("role", None)
    note = str(row.get("note", "") or "").strip()
    if note:
        base["purpose"] = (note + " — " + base.get("purpose", ""))[:1000]
    return {**base, "agent_id": agent_id, "name": str(row.get("name", "")).strip()[:120], "role": role,
            "preferred_model_label": str(row.get("model", "") or "").strip()[:80], "template_id": ""}


def plan_ids(rows: list[dict[str, Any]], existing: set[str] | None = None) -> list[str]:
    """The agent id each row gets (existing ``agent_id`` kept; the first row is always the project manager)."""
    taken = set(existing or ())
    out: list[str] = []
    for i, r in enumerate(rows):
        if i == 0:
            aid = PM_ID
        elif r.get("agent_id") and valid_id("agent", r["agent_id"]):
            aid = str(r["agent_id"])
        else:
            aid = agent_id_for(str(r.get("name", "")), taken | set(out), index=i)
        out.append(aid)
        taken.add(aid)
    return out


def apply_wizard(project: Any, brief: dict[str, Any], rows: list[dict[str, Any]], answer_format: str = "aiwb") -> dict[str, Any]:
    """Record the wizard: the brief (goal, name, platform, constraints), the team and the answer format.

    ``project`` is a :class:`aiwb.v2.V2Project` whose store was **not** opened with templates (call this before the
    Workbench opens the project). Returns ``{"agents": [ids], "workers": n}``.
    """
    from .flow import start_project
    errors = check_rows(rows)
    if errors:
        raise ModelError("; ".join(errors))
    if answer_format not in dict(ANSWER_FORMATS):
        raise ModelError(f"answer format must be one of {', '.join(dict(ANSWER_FORMATS))}")
    store = project.store
    store.ensure_migrated()
    workers = len(rows) - 1
    start_project(store, {**{k: brief.get(k, "") for k in ("goal", "name", "platform", "constraints")},
                          "ais": str(workers)})
    with store.transaction("team from the New Project wizard") as s:
        existing = set(s["agents"])
        ids = plan_ids(rows, existing - {PM_ID})
        for aid, row in zip(ids, rows):
            if aid in s["agents"]:
                continue
            s["agents"][aid] = normalize_agent({**_agent_data(aid, row), "revision": 1})
        s["settings"]["team_source"] = "wizard"
        s["settings"]["answer_format"] = answer_format
        emit(s, "team_defined", agent_ids=ids, workers=workers, source="wizard", importance="major")
    return {"agents": ids, "workers": workers}


def _references(state: dict[str, Any]) -> set[str]:
    """Agent ids that something recorded points at (tasks, handoffs, attempts, chat bindings, proposals)."""
    refs: set[str] = set()
    for t in (state.get("tasks") or {}).values():
        refs.update(str(t.get(k) or "") for k in ("owner_agent_id", "reviewer_agent_id"))
    for coll in ("handoffs", "attempts", "chat_bindings"):
        for r in (state.get(coll) or {}).values():
            refs.update(str(r.get(k) or "") for k in ("agent_id", "from_agent_id", "to_agent_id", "owner_agent_id"))
    refs.discard("")
    return refs


def team_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The editable table of the current team (enabled agents; project manager first). Pure."""
    agents = [a for a in (state.get("agents") or {}).values() if a.get("enabled", True)]
    agents.sort(key=lambda a: (a["role"] != "project_manager", a["agent_id"] != PM_ID, a.get("created_at", ""),
                               a["agent_id"]))
    refs = _references(state)
    unused_tpl = set(unused_template_agents(state))
    return [{"agent_id": a["agent_id"], "name": a.get("name", ""), "role": a["role"],
             "model": a.get("preferred_model_label", ""), "note": "", "has_work": a["agent_id"] in refs,
             "unused_template": a["agent_id"] in unused_tpl} for a in agents]


def unused_template_agents(state: dict[str, Any]) -> list[str]:
    """Template AIs (architect, implementer, reviewer) added automatically before 5.9.0 and never given work."""
    refs = _references(state)
    out = []
    for aid in BASE_TEMPLATE_IDS:
        if aid == PM_ID:
            continue
        a = (state.get("agents") or {}).get(aid)
        if a and str(a.get("template_id", "")).startswith(aid + "@") and aid not in refs:
            out.append(aid)
    return out


def remove_unused_templates(store: Any) -> list[str]:
    """Delete the unused template AIs (only those; anything with history stays). Returns the removed ids."""
    with store.transaction("remove unused template AIs") as s:
        gone = unused_template_agents(s)
        for aid in gone:
            del s["agents"][aid]
        if gone:
            emit(s, "agents_removed", agent_ids=gone, reason="unused template AIs")
    return gone


def save_team(store: Any, rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Agents page › Edit team: make the enabled team equal to ``rows``.

    Rows with an ``agent_id`` update that AI (name, role, model label); rows without one are created; enabled AIs
    missing from ``rows`` are deleted when nothing points at them, otherwise disabled. The project manager stays.
    Returns ``{"created", "updated", "removed", "disabled"}`` id lists.
    """
    errors = check_rows(rows)
    if errors:
        raise ModelError("; ".join(errors))
    out: dict[str, list[str]] = {"created": [], "updated": [], "removed": [], "disabled": []}
    with store.transaction("edit team") as s:
        agents = s["agents"]
        ids = plan_ids(rows, set(agents))
        refs = _references(s)
        for aid, row in zip(ids, rows):
            if aid in agents:
                cur = agents[aid]
                role = "project_manager" if aid == PM_ID else role_of(row.get("role", ""))
                changes = {"name": str(row.get("name", "")).strip()[:120], "role": role,
                           "preferred_model_label": str(row.get("model", "") or "").strip()[:80], "enabled": True}
                if any(cur.get(k) != v for k, v in changes.items()):
                    merged = normalize_agent({**cur, **changes})
                    merged["revision"] = int(cur.get("revision", 1)) + 1
                    merged["created_at"] = cur.get("created_at", merged["created_at"])
                    merged["updated_at"] = now_utc()
                    agents[aid] = merged
                    out["updated"].append(aid)
            else:
                agents[aid] = normalize_agent({**_agent_data(aid, row), "revision": 1})
                out["created"].append(aid)
        keep = set(ids) | {PM_ID}
        for aid in [a for a, v in agents.items() if v.get("enabled", True) and a not in keep]:
            if aid in refs:
                agents[aid] = {**agents[aid], "enabled": False, "updated_at": now_utc(),
                               "revision": int(agents[aid].get("revision", 1)) + 1}
                out["disabled"].append(aid)
            else:
                del agents[aid]
                out["removed"].append(aid)
        workers = len([a for a in agents.values() if a.get("enabled", True) and a["role"] != "project_manager"])
        if workers:
            s["settings"].setdefault("team", {})["max_parallel_chats"] = min(MAX_WORKERS, workers)
        if any(out.values()):
            emit(s, "team_edited", **{k: v for k, v in out.items() if v})
    return out


def team_prompt_lines(state: dict[str, Any]) -> list[str]:
    """Charter prompt section for a team the user defined (empty for older projects). Pure."""
    if (state.get("settings") or {}).get("team_source") != "wizard":
        return []
    lines = ["## Team chosen by the user (binding)",
             "The user decided how many AIs work on this project and who they are. Use EXACTLY these agent_ids, "
             "names and roles in team.agents; give every task an owner from this list; do not add, rename or drop "
             "agents (explain in questions_for_user if you think the team should change)."]
    for a in sorted((state.get("agents") or {}).values(), key=lambda a: (a["role"] != "project_manager", a["agent_id"])):
        if not a.get("enabled", True):
            continue
        model = f", model: {a['preferred_model_label']}" if a.get("preferred_model_label") else ""
        lines.append(f"- {a['agent_id']} — \"{a.get('name', '')}\" (role {a['role']}{model})")
    return lines
