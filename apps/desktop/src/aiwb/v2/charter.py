"""Project Charter (roadmap 3.4.0, contract ``project-charter.v1``).

One prompt asks the project-manager chat to design the *whole* project at once:

* architecture and modules (with the paths each module owns),
* how many AI chats work in parallel and why (plus a simpler alternative),
* the coordination protocol: file/path ownership, shared contracts, sync points, conflict resolution,
* a roadmap of milestones, each with a version label,
* the tasks of every AI and a ready start prompt for every AI.

The answer is one ``AIWB_PROJECT_CHARTER`` block. :func:`parse_charter` normalizes chat-copy damage
(via :mod:`aiwb.intake.normalize`), validates every required section and returns precise, path-like
error messages; a rejected charter gets a ready :func:`charter_fix_prompt`. A valid charter is converted
by :func:`charter_to_proposal` into an ordinary manager proposal (``create_agent``, ``create_task``,
``create_milestone``) so it goes through the existing per-operation review — nothing is applied by
import alone. The non-operational parts (architecture, coordination, start prompts) are stored in
``settings.charter`` once the user accepts at least one operation.
"""
from __future__ import annotations

import re
from typing import Any

from .models import ROLES, ModelError, valid_id

CHARTER_RE = re.compile(r"(?s)<<<AIWB_PROJECT_CHARTER>>>\s*(.*?)\s*<<<AIWB_END_PROJECT_CHARTER>>>")
OPEN_MARK = "<<<AIWB_PROJECT_CHARTER>>>"
SEMVER = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
REQUIRED_SECTIONS = ("architecture", "team", "coordination", "roadmap", "tasks", "start_prompts")
MAX_TASKS = 40
MAX_MILESTONES = 12
MAX_AGENTS = 12

CHARTER_FORMAT = """Return your reasoning in plain text first, then exactly ONE block (valid JSON, no comments):
<<<AIWB_PROJECT_CHARTER>>>
{"schema_version": "1.0", "charter_type": "project_charter", "base_state_revision": <the state_revision above>,
 "project": {"name": "…", "goal": "…", "summary": "two or three sentences"},
 "architecture": {"summary": "…", "modules": [
   {"id": "core", "name": "Core logic", "purpose": "…", "paths": ["src/core/**"], "depends_on": []},
   {"id": "ui", "name": "User interface", "purpose": "…", "paths": ["src/ui/**"], "depends_on": ["core"]}]},
 "team": {"pm_counted": true, "total_agents": 3, "parallel_chats": 2,
          "rationale": "why this many AI chats work in parallel", "simpler_alternative": "a smaller option and its trade-off",
          "agents": [
   {"agent_id": "agent-project-manager", "role": "project_manager", "name": "Project manager", "purpose": "…", "owns_modules": []},
   {"agent_id": "agent-core-dev", "role": "implementer", "name": "Core developer", "purpose": "…", "owns_modules": ["core"]},
   {"agent_id": "agent-ui-dev", "role": "implementer", "name": "UI developer", "purpose": "…", "owns_modules": ["ui"]}]},
 "coordination": {
   "file_ownership": [{"agent_id": "agent-core-dev", "paths": ["src/core/**"]}, {"agent_id": "agent-ui-dev", "paths": ["src/ui/**"]}],
   "shared_contracts": [{"name": "Core API", "path": "docs/contracts/core-api.md", "owner_agent_id": "agent-core-dev",
                         "consumers": ["agent-ui-dev"]}],
   "sync_points": [{"after_milestone": "m1", "description": "UI starts only after the core API contract is frozen"}],
   "conflict_resolution": "who decides when two AIs need the same file or disagree"},
 "roadmap": {"milestones": [
   {"ref": "m1", "title": "Core ready", "version": "0.1.0", "criteria": ["…"], "task_refs": ["t1"]},
   {"ref": "m2", "title": "First usable app", "version": "0.2.0", "criteria": ["…"], "task_refs": ["t2"]}]},
 "tasks": [
   {"ref": "t1", "title": "…", "objective": "…", "owner_agent_id": "agent-core-dev", "milestone_ref": "m1",
    "depends_on_refs": [], "parallel_group": "A", "scope": {"include": ["src/core/**"], "exclude": []},
    "acceptance_criteria": ["…"], "priority": "high"},
   {"ref": "t2", "title": "…", "objective": "…", "owner_agent_id": "agent-ui-dev", "milestone_ref": "m2",
    "depends_on_refs": ["t1"], "parallel_group": "B", "scope": {"include": ["src/ui/**"], "exclude": []},
    "acceptance_criteria": ["…"], "priority": "medium"}],
 "start_prompts": [{"agent_id": "agent-core-dev", "prompt": "the complete first message for this AI's own chat"},
                   {"agent_id": "agent-ui-dev", "prompt": "…"}],
 "risks": ["…"], "questions_for_user": ["…"]}
<<<AIWB_END_PROJECT_CHARTER>>>
Rules:
- Every section above is required: architecture, team, coordination, roadmap, tasks, start_prompts.
- agent_id looks like agent-<lowercase-words>; role is one of: """ + ", ".join(ROLES) + """.
- Every task has exactly one owner from team.agents, a milestone_ref, a file scope inside that owner's file_ownership,
  and acceptance criteria. Use refs (t1, m1, …); Workbench assigns the real IDs.
- Never give two AIs ownership of the same path. Shared files go into shared_contracts with one owner.
- Tasks in the same parallel_group run at the same time: never more groups' tasks at once than parallel_chats.
- Every milestone has a semantic version (e.g. 0.1.0); versions grow along the roadmap.
- Every AI except the project manager gets a start prompt that stands on its own: that chat has NO access to this
  conversation, the files or other chats; the user copies every prompt by hand.
- Prefer a small team; propose more parallel AIs only with the benefit, the risk and the coordination cost."""


# Charter v2 (roadmap 5.10.0): the team comes from the New Project wizard, so the model returns only what it alone can
# decide — architecture, file ownership, roadmap and tasks on the user's agent_ids. Workbench adds the team and writes
# every start prompt itself (shorter answer → fewer cut-off answers and fewer JSON mistakes).
CHARTER_FORMAT_V2 = """Return a short explanation first, then exactly ONE block (valid JSON, no comments):
<<<AIWB_PROJECT_CHARTER>>>
{"schema_version": "1.0", "base_state_revision": <the state_revision above>,
 "project": {"name": "…", "goal": "…", "summary": "two or three sentences"},
 "architecture": {"summary": "…", "modules": [
   {"id": "core", "purpose": "…", "paths": ["src/core/**"], "depends_on": [], "owner_agent_id": "<one agent_id>"}]},
 "coordination": {"file_ownership": [{"agent_id": "<agent_id>", "paths": ["src/core/**"]}],
                  "sync_points": [{"after_milestone": "m1", "description": "…"}]},
 "roadmap": {"milestones": [{"ref": "m1", "title": "…", "version": "0.1.0", "criteria": ["…"]}]},
 "tasks": [{"ref": "t1", "title": "…", "objective": "…", "owner_agent_id": "<agent_id>", "milestone_ref": "m1",
            "depends_on_refs": [], "scope": {"include": ["src/core/**"]}, "acceptance_criteria": ["…"]}],
 "risks": ["…"], "questions_for_user": ["…"]}
<<<AIWB_END_PROJECT_CHARTER>>>
Rules:
- Use ONLY the agent_ids of the team above; every task has exactly one owner from that list.
- Do NOT write team or start prompts — Workbench builds them from your plan.
- One AI per path; a task's scope stays inside its owner's paths. Refs: t1, t2 … and m1, m2 …
- Versions grow along the roadmap (0.1.0, 0.2.0 …).
- If the project is big, plan only the first two milestones in detail (at most 15 tasks); later ones may have no tasks
  yet. Keep the whole answer short."""

PROFILE_LABELS = (("target_platform", "Target platform"), ("languages", "Language(s)"),
                  ("gui_framework", "GUI / application framework"), ("runtime_toolchain", "Runtime / build toolchain"),
                  ("target_ui_language", "Language of the app's own UI"), ("architecture", "Architecture preference"),
                  ("dependency_policy", "Dependency policy"), ("packaging", "Packaging / delivery"),
                  ("testing", "Testing expectations"), ("coding_style", "Coding style"), ("constraints", "Constraints"))
_NO_CHOICE = ("", "let ai recommend", "other / undecided", "not applicable", "recommend based on scope", "auto-detect")


def profile_lines(profile: Any) -> list[str]:
    """The Project Profile choices that say something (defaults such as 'Let AI recommend' are left out); pure."""
    if not isinstance(profile, dict):
        return []
    out = []
    for key, label in PROFILE_LABELS:
        v = str(profile.get(key) or "").strip()
        if v.lower() in _NO_CHOICE or v.lower().startswith("not applicable"):
            continue
        out.append(f"- {label}: {v[:400]}")
    return out


def charter_prompt(project: dict[str, Any], state: dict[str, Any]) -> str:
    """The 'design the whole project' prompt (roadmap 3.4.0). Pure; the caller saves the goal."""
    from .team import resources_summary
    r = resources_summary(state)
    lines = ["# AI Workbench — Project Charter (design the whole project)",
             "You are the Project Manager and architect for this project. You cannot read files, run anything or "
             "contact other chats; the user copies every prompt by hand and pastes your answer back.", "",
             f"State revision: {int(state.get('state_revision', 0))}", "", "## Project"]
    if project.get("name"):
        lines.append(f"- Name: {project['name']}")
    lines.append(f"- Goal: {project.get('goal', '')}")
    for k, label in (("non_goals", "Non-goals"), ("success", "Success criteria"), ("platform", "Platform / technology"),
                     ("constraints", "Constraints"), ("limits", "Time / cost limits")):
        if project.get(k):
            lines.append(f"- {label}: {project[k]}")
    profile = profile_lines(project.get("profile"))
    if profile:
        lines += ["", "## Technical profile chosen by the user (binding unless you explain a better choice)"] + profile
    lines += ["", "## Resources registered by the user (self-declared labels, NOT verified)"]
    if r["accounts"]:
        for a in r["accounts"]:
            lines.append(f"- {a['account_profile_id']}: {a['display_name']} ({a['provider']}, plan {a['plan']})")
    else:
        lines.append("- (no account profiles registered)")
    lines.append(f"- Maximum chats the user will follow at the same time: {r['max_parallel_chats']}")
    from .team_setup import team_prompt_lines
    chosen = team_prompt_lines(state)  # 5.9.0: the team from the New Project wizard is binding
    if chosen:  # 5.10.0: Charter v2 — shorter; Workbench writes the team and the start prompts
        lines += [""] + chosen
        lines += ["", "## Your task — answer ALL of these",
                  "1. Architecture: the modules of the whole project, their purpose, the paths each owns, who owns it.",
                  "2. Coordination: which AI owns which paths, and when one AI must wait for another.",
                  "3. Roadmap: milestones in order, each with a version number and acceptance criteria.",
                  "4. Tasks: every AI's tasks with owner, milestone, dependencies, scope and acceptance criteria.",
                  "5. Risks and the questions only the user can answer.", "", CHARTER_FORMAT_V2]
        return "\n".join(lines)
    else:
        lines += ["", "## Existing agents (you may reuse them by agent_id)"]
        for a in r["agents"]:
            lines.append(f"- {a['agent_id']} ({a['role']}): {a['purpose']}")
    lines += ["", "## Your task — answer ALL of these",
              "1. Architecture: the modules of the whole project, their purpose, the paths each one owns and how they "
              "depend on each other.",
              "2. Team: how many AI chats work in parallel and WHY that number (and a simpler alternative).",
              "3. Coordination protocol: which AI owns which files/paths, the shared contracts between them, the sync "
              "points (when one AI must wait for another) and how conflicts are resolved.",
              "4. Roadmap: milestones in order, each with a version number and acceptance criteria.",
              "5. Tasks: the tasks of every AI, with owner, milestone, dependencies, scope and acceptance criteria.",
              "6. Start prompts: a complete first message for every AI's own chat.",
              "7. Risks and the questions only the user can answer.", "", CHARTER_FORMAT]
    return "\n".join(lines)


# --------------------------------------------------------------------------- parsing

def find_charter(text: str) -> str | None:
    """Raw JSON body of the charter block, or None when there is no block."""
    m = CHARTER_RE.search(text or "")
    if not m:
        return None
    body = m.group(1).strip()
    f = re.match(r"(?s)^`{3,}\s*(?:json)?\s*\n(.*?)\n`{3,}$", body)
    return f.group(1) if f else body


_OTHER_BLOCKS = ("AIWB_MANAGER_PROPOSAL", "AIWB_HANDOFF", "AIWB_FILE", "AIWB_CONTEXT_REQUEST")
_CHARTER_KEYS = ("tasks", "roadmap", "milestones", "architecture", "team", "start_prompts", "coordination")


def _marker_free_charter(text: str) -> bool:
    """5.10.0 (A12): a JSON object that looks like a charter (tasks + roadmap/architecture/team) without our markers."""
    s = text or ""
    if any(m in s for m in _OTHER_BLOCKS):
        return False
    hits = [k for k in _CHARTER_KEYS if re.search(r"[\"\u201c\u201d]" + k + r"[\"\u201c\u201d]\s*:", s)]
    return "tasks" in hits and len(hits) >= 3


def has_charter(text: str) -> bool:
    if CHARTER_RE.search(text or "") or "AIWB_PROJECT_CHARTER" in (text or "").replace("\\_", "_"):
        return True
    try:
        from ..intake.normalize import normalize
        if CHARTER_RE.search(normalize(text or "").text):
            return True
    except Exception:  # noqa: BLE001 - detection must never fail
        pass
    return _marker_free_charter(text)


def _load(text: str) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    """(data, errors, fixes). Our block first (raw, then normalized); 5.10.0: then an unmarked JSON object in a
    ```json fence or in the prose, an opening marker without the end marker, and lenient JSON (comments, commas…)."""
    from ..intake import lenient
    fixes: list[str] = []
    raw = text or ""
    candidates = [(raw, [])]
    try:
        from ..intake.normalize import normalize
        n = normalize(raw)
        if n.changed:
            candidates.append((n.text, list(n.fixes)))
    except Exception:  # noqa: BLE001
        pass
    last_error = ""
    bodies: list[tuple[str, list[str]]] = []
    for cand, cf in candidates:
        body = find_charter(cand)
        if body is not None:
            bodies.append((body, cf))
    if not bodies:
        for cand, cf in candidates:
            k = cand.find("AIWB_PROJECT_CHARTER")
            if k >= 0 and "AIWB_END_PROJECT_CHARTER" not in cand:  # opened, never closed: is the JSON complete?
                f = lenient.find_object(cand, start=k)
                if f.text:
                    bodies.append((f.text, cf + ["end marker <<<AIWB_END_PROJECT_CHARTER>>> was missing"]))
                    break
                return None, ["the charter block is not closed: <<<AIWB_END_PROJECT_CHARTER>>> is missing "
                              "(the answer was probably cut off)"], fixes
    if not bodies and _marker_free_charter(raw):
        for cand, cf in candidates:
            for fb in lenient.fenced_json_blocks(cand):
                if _marker_free_charter(fb):
                    bodies.append((fb, cf + ["the charter JSON had no AIWB markers (read from a ```json block)"]))
            if bodies:
                break
            f = lenient.find_object(cand, keys=("tasks",))
            if f.text:
                bodies.append((f.text, cf + ["the charter JSON had no AIWB markers (read from the answer text)"]))
                break
            if f.truncated:
                return None, ["the charter JSON was opened but never closed (the answer was probably cut off)"], fixes
    for body, cf in bodies:
        b = body.strip()
        fm = re.match(r"(?s)^(`{3,}|~{3,})[^\n]*\n(.*?)\n?\1\s*$", b)
        if fm:
            b = fm.group(2)
        if not b.lstrip().startswith("{"):
            f = lenient.find_object(b)
            if f.text:
                b = f.text
        data, lf, err = lenient.loads(b)
        if data is None:
            last_error = f"the charter block is {err}"
            continue
        if not isinstance(data, dict):
            return None, ["the charter block must be one JSON object"], cf + lf
        return data, [], cf + lf
    if last_error:
        return None, [last_error], fixes
    return None, ["no AIWB_PROJECT_CHARTER block found"], fixes


def _list(d: dict[str, Any], key: str, path: str, errors: list[str], *, required: bool = True) -> list[Any]:
    v = d.get(key)
    if v is None:
        if required:
            errors.append(f"{path}.{key}: missing (a non-empty list is required)")
        return []
    if not isinstance(v, list):
        errors.append(f"{path}.{key}: must be a list")
        return []
    if required and not v:
        errors.append(f"{path}.{key}: is empty")
    return v


def _str(d: dict[str, Any], key: str, path: str, errors: list[str], *, required: bool = True, limit: int = 4000) -> str:
    v = d.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            errors.append(f"{path}.{key}: missing")
        return ""
    if not isinstance(v, str):
        errors.append(f"{path}.{key}: must be text")
        return ""
    if len(v) > limit:
        errors.append(f"{path}.{key}: longer than {limit} characters")
    return v.strip()


def _strs(v: Any) -> list[str]:
    return [str(x).strip() for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []


def _norm_path(p: str) -> str:
    p = p.replace("\\", "/").strip().lstrip("./")
    return re.sub(r"/?\*\*?$", "", p).rstrip("/")


def _paths_overlap(a: str, b: str) -> bool:
    a, b = _norm_path(a), _norm_path(b)
    if not a or not b:
        return True
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _inside(path: str, owned: list[str]) -> bool:
    p = _norm_path(path)
    return any(p == _norm_path(o) or p.startswith(_norm_path(o) + "/") or not _norm_path(o) for o in owned)


def validate_charter(data: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check every required part. Returns ``{"errors": [...], "warnings": [...]}``; pure."""
    errors: list[str] = []
    warnings: list[str] = []
    state = state or {"agents": {}}
    if data.get("schema_version") != "1.0":
        errors.append('schema_version: must be "1.0"')
    if not isinstance(data.get("base_state_revision"), int) or isinstance(data.get("base_state_revision"), bool):
        errors.append("base_state_revision: missing (an integer, copy the state_revision from the prompt)")
    for sec in REQUIRED_SECTIONS:
        if sec not in data:
            errors.append(f"{sec}: section missing")
    obj = {k: data.get(k) if isinstance(data.get(k), dict) else {} for k in ("architecture", "team", "coordination", "roadmap")}
    for k in obj:
        if k in data and not isinstance(data.get(k), dict):
            errors.append(f"{k}: must be an object")

    # architecture
    arch = obj["architecture"]
    if "architecture" in data:
        _str(arch, "summary", "architecture", errors)
    modules = _list(arch, "modules", "architecture", errors) if "architecture" in data else []
    module_ids: list[str] = []
    for i, m in enumerate(modules):
        p = f"architecture.modules[{i}]"
        if not isinstance(m, dict):
            errors.append(f"{p}: must be an object")
            continue
        mid = _str(m, "id", p, errors, limit=40)
        if mid and mid in module_ids:
            errors.append(f"{p}.id: duplicate module id {mid!r}")
        module_ids.append(mid)
        _str(m, "purpose", p, errors)
        if not _strs(m.get("paths")):
            errors.append(f"{p}.paths: missing (which files/folders belong to module {mid or i})")
    for i, m in enumerate(modules):
        if isinstance(m, dict):
            for dep in _strs(m.get("depends_on")):
                if dep not in module_ids:
                    errors.append(f"architecture.modules[{i}].depends_on: unknown module {dep!r}")

    # team
    team = obj["team"]
    agents = _list(team, "agents", "team", errors) if "team" in data else []
    if "team" in data:
        _str(team, "rationale", "team", errors)
        if not isinstance(team.get("pm_counted"), bool):
            errors.append("team.pm_counted: missing (true/false — is the project manager counted in total_agents?)")
        for k in ("total_agents", "parallel_chats"):
            v = team.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or v < 1:
                errors.append(f"team.{k}: missing (a whole number ≥ 1)")
        if not _str(team, "simpler_alternative", "team", [], required=False):
            warnings.append("team.simpler_alternative: no simpler alternative was given")
    if len(agents) > MAX_AGENTS:
        errors.append(f"team.agents: too many agents ({len(agents)} > {MAX_AGENTS})")
    agent_roles: dict[str, str] = {}
    for i, a in enumerate(agents):
        p = f"team.agents[{i}]"
        if not isinstance(a, dict):
            errors.append(f"{p}: must be an object")
            continue
        aid = a.get("agent_id")
        if not valid_id("agent", aid):
            errors.append(f"{p}.agent_id: {aid!r} must look like 'agent-core-dev' (lowercase letters, digits, '-')")
            continue
        if aid in agent_roles:
            errors.append(f"{p}.agent_id: duplicate agent {aid}")
        role = a.get("role")
        if role not in ROLES:
            errors.append(f"{p}.role: {role!r} must be one of {', '.join(ROLES)}")
        existing = state["agents"].get(aid)
        if existing is not None and role in ROLES and existing["role"] != role:
            errors.append(f"{p}: agent {aid} already exists with role {existing['role']}, not {role}")
        _str(a, "purpose", p, errors)
        for mod in _strs(a.get("owns_modules")):
            if mod not in module_ids:
                errors.append(f"{p}.owns_modules: unknown module {mod!r}")
        agent_roles[str(aid)] = str(role)
    if agents and isinstance(team.get("total_agents"), int):
        declared = team["total_agents"]
        actual = len(agent_roles) if team.get("pm_counted", True) else len([r for r in agent_roles.values() if r != "project_manager"])
        if declared != actual:
            warnings.append(f"team.total_agents: says {declared} but team.agents lists {actual} counted agent(s)")
    if agents and (state.get("settings") or {}).get("team_source") == "wizard":  # 5.9.0: the user chose the team
        mine = {aid for aid, ag in state["agents"].items() if ag.get("enabled", True)}
        extra = sorted(set(agent_roles) - mine)
        if extra:
            warnings.append(f"team.agents: {', '.join(extra)} not in the team you chose; accepting adds them")
        unused = sorted(aid for aid in mine - set(agent_roles) if state["agents"][aid]["role"] != "project_manager")
        if unused:
            warnings.append(f"team.agents: your AI(s) {', '.join(unused)} got no place in the charter")
    workers = [aid for aid, r in agent_roles.items() if r != "project_manager"]
    if agents and not workers:
        errors.append("team.agents: no AI besides the project manager does the work")
    owned_modules = {m for a in agents if isinstance(a, dict) for m in _strs(a.get("owns_modules"))}
    for mid in module_ids:
        if mid and mid not in owned_modules:
            warnings.append(f"architecture: module {mid!r} has no owner in team.agents[].owns_modules")

    # coordination
    co = obj["coordination"]
    ownership: dict[str, list[str]] = {}
    if "coordination" in data:
        fo = _list(co, "file_ownership", "coordination", errors)
        for i, o in enumerate(fo):
            p = f"coordination.file_ownership[{i}]"
            if not isinstance(o, dict):
                errors.append(f"{p}: must be an object")
                continue
            aid = str(o.get("agent_id") or "")
            if aid not in agent_roles:
                errors.append(f"{p}.agent_id: {aid or '(missing)'} is not in team.agents")
            paths = _strs(o.get("paths"))
            if not paths:
                errors.append(f"{p}.paths: missing")
            ownership.setdefault(aid, []).extend(paths)
        owners = sorted(ownership)
        for x in range(len(owners)):
            for y in range(x + 1, len(owners)):
                for pa in ownership[owners[x]]:
                    for pb in ownership[owners[y]]:
                        if _paths_overlap(pa, pb):  # 5.10.0: a warning with the fix, not a rejection (A12)
                            warnings.append(f"coordination.file_ownership: {owners[x]} ({pa}) and {owners[y]} ({pb}) own "
                                            "the same path — give it to one AI or make it a shared contract")
        for i, sc in enumerate(_list(co, "shared_contracts", "coordination", errors, required=False)):
            p = f"coordination.shared_contracts[{i}]"
            if not isinstance(sc, dict):
                errors.append(f"{p}: must be an object")
                continue
            _str(sc, "name", p, errors, limit=200)
            if str(sc.get("owner_agent_id") or "") not in agent_roles:
                errors.append(f"{p}.owner_agent_id: {sc.get('owner_agent_id') or '(missing)'} is not in team.agents")
            for c in _strs(sc.get("consumers")):
                if c not in agent_roles:
                    errors.append(f"{p}.consumers: {c} is not in team.agents")
        if not _list(co, "shared_contracts", "coordination", [], required=False) and len(workers) > 1:
            warnings.append("coordination.shared_contracts: several AIs work in parallel but no shared contract is defined")
        sync = _list(co, "sync_points", "coordination", errors, required=False)
        if not sync and len(workers) > 1:  # 5.10.0: missing coordination detail is a warning (A12)
            warnings.append("coordination.sync_points: several AIs work in parallel but no sync point is defined")
        _str(co, "conflict_resolution", "coordination", errors)
    else:
        sync = []
    for w in workers:
        if w not in ownership:
            warnings.append(f"coordination.file_ownership: {w} owns no files")

    # roadmap
    rm = obj["roadmap"]
    milestones = _list(rm, "milestones", "roadmap", errors) if "roadmap" in data else []
    if len(milestones) > MAX_MILESTONES:
        errors.append(f"roadmap.milestones: too many ({len(milestones)} > {MAX_MILESTONES})")
    ms_refs: list[str] = []
    versions: list[tuple[int, ...]] = []
    for i, m in enumerate(milestones):
        p = f"roadmap.milestones[{i}]"
        if not isinstance(m, dict):
            errors.append(f"{p}: must be an object")
            continue
        ref = str(m.get("ref") or "")
        if not REF.match(ref):
            errors.append(f"{p}.ref: missing or invalid (e.g. m1)")
        elif ref in ms_refs:
            errors.append(f"{p}.ref: duplicate {ref}")
        ms_refs.append(ref)
        _str(m, "title", p, errors, limit=200)
        ver = str(m.get("version") or "")
        if not SEMVER.match(ver):
            errors.append(f"{p}.version: {ver or '(missing)'} is not a semantic version like 0.1.0")
        else:
            nums = tuple(int(x) for x in re.findall(r"\d+", ver.lstrip("v"))[:3])
            if versions and nums <= versions[-1]:
                errors.append(f"{p}.version: {ver} does not grow along the roadmap")
            versions.append(nums)
        if not _strs(m.get("criteria")):
            errors.append(f"{p}.criteria: missing (how the user knows the milestone is reached)")
    for i, sp in enumerate(sync):
        if isinstance(sp, dict) and sp.get("after_milestone") and sp["after_milestone"] not in ms_refs:
            errors.append(f"coordination.sync_points[{i}].after_milestone: unknown milestone {sp['after_milestone']!r}")
        if isinstance(sp, dict) and not str(sp.get("description") or "").strip():
            errors.append(f"coordination.sync_points[{i}].description: missing")

    # tasks
    tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else []
    if "tasks" in data and not isinstance(data.get("tasks"), list):
        errors.append("tasks: must be a list")
    elif "tasks" in data and not tasks:
        errors.append("tasks: is empty")
    if len(tasks) > MAX_TASKS:
        errors.append(f"tasks: too many ({len(tasks)} > {MAX_TASKS}); plan the first milestones in detail only")
    task_refs: list[str] = []
    for i, t in enumerate(tasks):
        if isinstance(t, dict):
            ref = str(t.get("ref") or "")
            if not REF.match(ref):
                errors.append(f"tasks[{i}].ref: missing or invalid (e.g. t1)")
            elif ref in task_refs:
                errors.append(f"tasks[{i}].ref: duplicate {ref}")
            task_refs.append(ref)
    owners_with_tasks: set[str] = set()
    for i, t in enumerate(tasks):
        p = f"tasks[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{p}: must be an object")
            continue
        _str(t, "title", p, errors, limit=200)
        _str(t, "objective", p, errors)
        owner = str(t.get("owner_agent_id") or "")
        if owner not in agent_roles:
            errors.append(f"{p}.owner_agent_id: {owner or '(missing)'} is not in team.agents")
        owners_with_tasks.add(owner)
        msr = str(t.get("milestone_ref") or "")
        if msr not in ms_refs:
            errors.append(f"{p}.milestone_ref: {msr or '(missing)'} is not a roadmap milestone")
        for d in _strs(t.get("depends_on_refs")):
            if d not in task_refs:
                errors.append(f"{p}.depends_on_refs: unknown task {d!r}")
            if d == t.get("ref"):
                errors.append(f"{p}.depends_on_refs: a task cannot depend on itself")
        if not _strs(t.get("acceptance_criteria")):
            errors.append(f"{p}.acceptance_criteria: missing")
        scope = t.get("scope") if isinstance(t.get("scope"), dict) else {}
        inc = _strs(scope.get("include"))
        if not inc:
            errors.append(f"{p}.scope.include: missing (which files this task may change)")
        elif owner in ownership:
            outside = [x for x in inc if not _inside(x, ownership[owner])]
            if outside:
                warnings.append(f"{p}.scope: {', '.join(outside[:3])} is outside the files {owner} owns")
    for i, m in enumerate(milestones):
        if isinstance(m, dict):
            for r in _strs(m.get("task_refs")):
                if r not in task_refs:
                    errors.append(f"roadmap.milestones[{i}].task_refs: unknown task {r!r}")
    for w in workers:
        if w not in owners_with_tasks:
            warnings.append(f"tasks: {w} has no task")
    errors += _cycles(tasks)

    # start prompts
    sps = data.get("start_prompts") if isinstance(data.get("start_prompts"), list) else []
    if "start_prompts" in data and not isinstance(data.get("start_prompts"), list):
        errors.append("start_prompts: must be a list")
    have = set()
    for i, sp in enumerate(sps):
        p = f"start_prompts[{i}]"
        if not isinstance(sp, dict):
            errors.append(f"{p}: must be an object")
            continue
        aid = str(sp.get("agent_id") or "")
        if aid not in agent_roles:
            errors.append(f"{p}.agent_id: {aid or '(missing)'} is not in team.agents")
        if len(_str(sp, "prompt", p, errors, limit=20000)) < 40 and sp.get("prompt"):
            errors.append(f"{p}.prompt: too short to start a chat on its own (at least 40 characters)")
        have.add(aid)
    for w in workers:
        if "start_prompts" in data and w not in have:
            errors.append(f"start_prompts: no start prompt for {w}")
    return {"errors": list(dict.fromkeys(errors)), "warnings": list(dict.fromkeys(warnings))}


def _cycles(tasks: list[Any]) -> list[str]:
    graph = {str(t.get("ref")): _strs(t.get("depends_on_refs")) for t in tasks if isinstance(t, dict) and t.get("ref")}
    seen: dict[str, int] = {}
    out: list[str] = []

    def visit(n: str, path: list[str]) -> None:
        if seen.get(n) == 2 or n not in graph:
            return
        if seen.get(n) == 1:
            out.append("tasks: dependency cycle " + " → ".join(path[path.index(n):] + [n]))
            return
        seen[n] = 1
        for d in graph[n]:
            visit(d, path + [n])
        seen[n] = 2

    for n in graph:
        visit(n, [])
    return out[:1]


def parse_charter(text: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """``{"ok", "data", "errors", "warnings", "fixes"}``. Never raises for bad model output."""
    data, errors, fixes = _load(text)
    if data is None:
        return {"ok": False, "data": None, "errors": errors, "warnings": [], "fixes": fixes}
    from .charter_repair import repair  # 5.10.0: what models really return → the canonical shape (A12)
    data, repaired = repair(data, state)
    fixes = list(fixes) + repaired
    if not isinstance(data, dict):
        return {"ok": False, "data": None, "errors": ["the charter block must be one JSON object"], "warnings": [],
                "fixes": fixes}
    v = validate_charter(data, state)
    return {"ok": not v["errors"], "data": data, "errors": v["errors"], "warnings": v["warnings"], "fixes": fixes}


def charter_fix_prompt(result: dict[str, Any]) -> str:
    """Ready prompt that asks the same chat for a corrected, complete charter."""
    lines = ["# AI Workbench — please fix your Project Charter",
             "Workbench could not accept your charter; nothing was applied. Fix every point below and return the "
             "COMPLETE corrected charter as one <<<AIWB_PROJECT_CHARTER>>> … <<<AIWB_END_PROJECT_CHARTER>>> block "
             "(same format, valid JSON, every section present).", "", "## Problems found by Workbench"]
    lines += [f"- {e}" for e in result.get("errors", [])] or ["- (none)"]
    if result.get("warnings"):
        lines += ["", "## Also worth fixing"] + [f"- {w}" for w in result["warnings"]]
    if any("cut off" in e or "not closed" in e for e in result.get("errors", [])):
        lines += ["", "Your previous answer was cut off. If it is long, shorten the start prompts and plan only the first "
                  "milestones in detail."]
    return "\n".join(lines)


# --------------------------------------------------------------------------- conversion

def charter_to_proposal(data: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Convert a *valid* charter into a manager proposal (reviewed per operation, nothing applied here)."""
    v = validate_charter(data, state)
    if v["errors"]:
        raise ModelError("the charter is incomplete: " + "; ".join(v["errors"][:5]))
    team = data["team"]
    ops: list[dict[str, Any]] = []
    for a in team["agents"]:
        if a["agent_id"] in state["agents"]:
            continue
        ops.append({"operation": "create_agent", "agent_id": a["agent_id"], "role": a["role"],
                    "name": a.get("name") or a["agent_id"], "purpose": a.get("purpose", ""),
                    "reason": "Project Charter team"})
    for t in data["tasks"]:
        op = {"operation": "create_task", "temporary_ref": t["ref"], "title": t["title"], "objective": t["objective"],
              "owner_agent_id": t["owner_agent_id"], "depends_on_refs": _strs(t.get("depends_on_refs")),
              "scope": {"include": _strs((t.get("scope") or {}).get("include")),
                        "exclude": _strs((t.get("scope") or {}).get("exclude"))},
              "acceptance_criteria": _strs(t.get("acceptance_criteria")),
              "reason": f"Charter milestone {t['milestone_ref']}"}
        for k in ("parallel_group", "priority", "reviewer_agent_id", "risk_level"):
            if t.get(k):
                op[k] = t[k]
        ops.append(op)
    for m in data["roadmap"]["milestones"]:
        refs = _strs(m.get("task_refs")) or [t["ref"] for t in data["tasks"] if t.get("milestone_ref") == m["ref"]]
        ops.append({"operation": "create_milestone", "temporary_ref": "ms:" + m["ref"], "title": m["title"],
                    "version": m["version"], "criteria": _strs(m.get("criteria")), "task_refs": refs,
                    "reason": f"Charter roadmap {m['ref']} → {m['version']}"})
    for r in data.get("risks") or []:
        if isinstance(r, str) and r.strip():
            ops.append({"operation": "report_risk", "description": r.strip()[:500]})
    workers = len([a for a in team["agents"] if a["role"] != "project_manager"])
    proposal = {"schema_version": "1.0", "proposal_type": "team_plan", "base_state_revision": data["base_state_revision"],
                "summary": (data.get("project") or {}).get("summary") or data["architecture"]["summary"],
                "assumptions": [], "risks": _strs(data.get("risks")), "questions_for_user": _strs(data.get("questions_for_user")),
                "team": {"pm_counted": team["pm_counted"], "total_agents": team["total_agents"],
                         "additional_workers": workers, "size_rationale": team.get("rationale", ""),
                         "simpler_alternative": team.get("simpler_alternative", "")},
                "operations": ops}
    return proposal


def charter_record(data: dict[str, Any]) -> dict[str, Any]:
    """What is kept in ``settings.charter`` after the user accepted the charter."""
    return {"schema_version": "1.0", "project": data.get("project") or {}, "architecture": data["architecture"],
            "team": {k: data["team"].get(k) for k in ("pm_counted", "total_agents", "parallel_chats", "rationale",
                                                      "simpler_alternative", "agents")},
            "coordination": data["coordination"], "roadmap": data["roadmap"],
            "start_prompts": {sp["agent_id"]: sp["prompt"] for sp in data["start_prompts"] if isinstance(sp, dict)},
            "risks": _strs(data.get("risks")), "questions_for_user": _strs(data.get("questions_for_user"))}


def start_prompt(charter: dict[str, Any], agent_id: str, *, task_lines: list[str] | None = None) -> str:
    """The start prompt of one AI, framed with its ownership, contracts and sync points from the charter."""
    prompt = (charter.get("start_prompts") or {}).get(agent_id)
    if not prompt:
        raise ModelError(f"the charter has no start prompt for {agent_id}")
    co = charter.get("coordination") or {}
    own = [p for o in co.get("file_ownership", []) if o.get("agent_id") == agent_id for p in o.get("paths", [])]
    contracts = [c for c in co.get("shared_contracts", []) if c.get("owner_agent_id") == agent_id
                 or agent_id in (c.get("consumers") or [])]
    lines = [f"# AI Workbench — start prompt for {agent_id}",
             "You have NO access to earlier chats, the project files or other AIs; everything you need is below.", "",
             prompt.strip(), "", "## Coordination rules (from the Project Charter)",
             "- You may change only: " + (", ".join(own) or "(no files — ask the project manager)")]
    for c in contracts:
        role = "you own it" if c.get("owner_agent_id") == agent_id else f"owned by {c.get('owner_agent_id')}; do not change it"
        lines.append(f"- Shared contract {c.get('name')} ({c.get('path', '')}): {role}")
    for sp in co.get("sync_points", []):
        lines.append(f"- Sync point after {sp.get('after_milestone', '?')}: {sp.get('description', '')}")
    if co.get("conflict_resolution"):
        lines.append(f"- Conflicts: {co['conflict_resolution']}")
    if task_lines:
        lines += ["", "## Your tasks"] + [f"- {t}" for t in task_lines]
    return "\n".join(lines)
