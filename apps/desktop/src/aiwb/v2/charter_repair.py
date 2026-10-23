"""Turn the charter a chat model *actually* returned into the canonical ``project-charter.v1`` shape (roadmap 5.10.0).

Audit A12 tried 18 real answer shapes on the 3.4.0 parser and 13 were rejected for reasons a human reads past:
``schema_version: 1``, ``base_state_revision: "2"``, the role ``developer``, the version ``v0.1``, the id ``core_dev``,
``start_prompts`` as a dictionary, a string where a list was expected, ``sync_points`` left out, … :func:`repair`
rewrites exactly those things and returns every change as a short, human-readable line — a fix is never hidden: the
caller shows the list to the user and writes it to the project history.

What is repaired (only where the meaning is unambiguous):

* wrapper objects (``{"charter": {...}}``), top-level ``milestones`` and tasks nested inside milestones;
* ``schema_version`` / ``charter_type`` / ``base_state_revision`` (number ↔ text, missing → the current revision);
* key synonyms (``id`` → ``ref``, ``owner`` / ``assignee`` → ``owner_agent_id``, ``depends_on`` → ``depends_on_refs``…);
* role synonyms (developer / engineer / coder → implementer, qa / tester → reviewer, pm / lead → project_manager…);
* agent ids (``core_dev`` / ``Core dev`` / ``CoreDev`` → ``agent-core-dev``; a name of the user's team → its id);
* versions (``v0.1`` → ``0.1.0``, ``1`` → ``1.0.0``) and refs (``Task 1`` → ``Task-1``) everywhere they are used;
* text ↔ list and dictionary ↔ list (``start_prompts: {id: prompt}``, ``file_ownership: {id: [paths]}``…);
* Charter v2 (5.10.0): the team the user defined in the New Project wizard is the team — when the model leaves
  ``team`` or ``start_prompts`` out (the v2 prompt asks it to), Workbench fills them from the user's team and writes
  every start prompt itself from the charter;
* missing coordination parts that have one obvious answer (ownership from module ownership or task scopes, the
  conflict rule "the project manager decides", an empty ``sync_points`` list).

Anything genuinely ambiguous (a task whose owner cannot be told, a dependency on an unknown task, too many tasks…)
is left for :func:`aiwb.v2.charter.validate_charter`, whose message goes into the one-click fix prompt.

Pure: no I/O, no Tk; the input is never mutated.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from .models import ROLES, valid_id

PM_ID = "agent-project-manager"

# Role words → model role. Checked in order; the first rule whose word appears in the text wins.
_ROLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("project_manager", ("project_manager", "project manager", "project-manager", "pm", "manager", "coordinator",
                         "lead", "orchestrator", "planner", "scrum", "owner")),
    ("reviewer", ("reviewer", "review", "qa", "tester", "test", "testing", "quality", "auditor", "verifier",
                  "validator")),
    ("architect", ("architect", "architecture", "designer", "design")),
    ("researcher", ("researcher", "research", "analyst", "analysis", "investigator")),
    ("implementer", ("implementer", "developer", "dev", "engineer", "coder", "programmer", "builder", "frontend",
                     "backend", "fullstack", "full-stack", "full stack", "implementation", "worker", "maker",
                     "mobile", "desktop", "ui", "core")),
)
_PRIORITY = {"p0": "critical", "p1": "high", "p2": "medium", "p3": "low", "urgent": "critical", "blocker": "critical",
             "critical": "critical", "highest": "critical", "high": "high", "important": "high", "medium": "medium",
             "normal": "medium", "mid": "medium", "moderate": "medium", "low": "low", "minor": "low", "lowest": "low"}
_REF_BAD = re.compile(r"[^A-Za-z0-9_.-]+")

# key synonyms per object kind: canonical key → accepted alternatives (first present one wins)
_TASK_KEYS = {
    "ref": ("ref", "id", "task_ref", "task_id", "key", "temporary_ref"),
    "title": ("title", "name", "summary", "task"),
    "objective": ("objective", "description", "details", "goal", "what", "detail", "body"),
    "owner_agent_id": ("owner_agent_id", "owner", "assignee", "agent_id", "agent", "assigned_to", "owner_agent",
                       "owner_id", "responsible"),
    "milestone_ref": ("milestone_ref", "milestone", "milestone_id", "milestone_ref_id", "phase"),
    "depends_on_refs": ("depends_on_refs", "depends_on", "dependencies", "deps", "after", "blocked_by", "requires"),
    "acceptance_criteria": ("acceptance_criteria", "acceptance", "criteria", "done_when", "definition_of_done",
                            "acceptance_tests", "success_criteria"),
    "scope": ("scope", "files", "paths", "file_scope", "allowed_paths", "include"),
    "parallel_group": ("parallel_group", "group", "wave", "parallel"),
    "priority": ("priority", "prio", "importance"),
    "reviewer_agent_id": ("reviewer_agent_id", "reviewer"),
}
_MILESTONE_KEYS = {
    "ref": ("ref", "id", "milestone_ref", "milestone_id", "key"),
    "title": ("title", "name", "summary", "goal"),
    "version": ("version", "release", "semver", "tag"),
    "criteria": ("criteria", "acceptance_criteria", "exit_criteria", "done_when", "definition_of_done",
                 "success_criteria", "acceptance"),
    "task_refs": ("task_refs", "tasks_refs", "task_ids", "tasks_ids", "task_list"),
}
_AGENT_KEYS = {
    "agent_id": ("agent_id", "id", "agent", "key"),
    "role": ("role", "type", "kind", "position"),
    "name": ("name", "display_name", "title", "label"),
    "purpose": ("purpose", "description", "responsibilities", "responsibility", "focus", "mission", "job"),
    "owns_modules": ("owns_modules", "modules", "owns", "owned_modules"),
}
_MODULE_KEYS = {
    "id": ("id", "module_id", "key", "ref", "slug"),
    "name": ("name", "title", "label"),
    "purpose": ("purpose", "description", "responsibility", "responsibilities", "summary", "role"),
    "paths": ("paths", "path", "files", "folders", "directories", "include", "globs"),
    "depends_on": ("depends_on", "dependencies", "deps", "uses", "requires"),
}


# --------------------------------------------------------------------------- small helpers

def _pick(d: dict[str, Any], names: tuple[str, ...]) -> tuple[str, Any]:
    for n in names:
        if n in d and d[n] not in (None, "", [], {}):
            return n, d[n]
    return "", None


def _canon(d: dict[str, Any], table: dict[str, tuple[str, ...]], where: str, fixes: list[str]) -> dict[str, Any]:
    """Copy of ``d`` with synonyms renamed to the canonical keys (each rename reported once per key/where)."""
    out = dict(d)
    for canon, names in table.items():
        if out.get(canon) not in (None, "", [], {}):
            continue
        key, val = _pick(out, names[1:]) if names and names[0] == canon else _pick(out, names)
        if key and key != canon:
            out[canon] = val
            out.pop(key, None)
            _fix(fixes, f"{where}: used \"{key}\" as \"{canon}\"")
    return out


def _fix(fixes: list[str], msg: str) -> None:
    if msg not in fixes:
        fixes.append(msg)


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, list):
        return "; ".join(_text(x) for x in v if _text(x))
    if isinstance(v, dict):
        for k in ("text", "description", "value", "name", "title"):
            if isinstance(v.get(k), str):
                return v[k].strip()
    return ""


def _text_list(v: Any) -> tuple[list[str], bool]:
    """A list of non-empty texts; ``True`` when the shape had to be changed (string → list, objects → text)."""
    if v is None:
        return [], False
    if isinstance(v, str):
        lines = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", x).strip() for x in v.split("\n")]
        lines = [x for x in lines if x]
        return lines, True
    if isinstance(v, dict):
        return [x for x in (_text(val) if not isinstance(val, str) else f"{k}: {val}".strip() for k, val in v.items())
                if x], True
    if isinstance(v, list):
        out, changed = [], False
        for x in v:
            if isinstance(x, str):
                if x.strip():
                    out.append(x.strip())
                else:
                    changed = True
            else:
                t = _text(x)
                changed = True
                if t:
                    out.append(t)
        return out, changed
    t = _text(v)
    return ([t] if t else []), True


def _token_list(v: Any) -> tuple[list[str], bool]:
    """Paths / refs / ids: a list; a string may hold several separated by commas, semicolons or new lines."""
    if v is None:
        return [], False
    if isinstance(v, (str, int)) and not isinstance(v, bool):
        parts = [x.strip().strip("`'\"") for x in re.split(r"[,;\n]+", str(v))]
        return [x for x in parts if x], True
    if isinstance(v, dict):
        return _token_list(list(v.keys()) if all(isinstance(x, (dict, list)) for x in v.values()) else list(v.values()))[0], True
    if isinstance(v, list):
        out, changed = [], False
        for x in v:
            if isinstance(x, (str, int)) and not isinstance(x, bool):
                s = str(x).strip().strip("`'\"")
                if s:
                    out.append(s)
                if not isinstance(x, str) or s != x:
                    changed = True
            elif isinstance(x, dict):
                t = _text(x.get("ref") or x.get("id") or x.get("path") or x.get("agent_id") or x.get("name"))
                changed = True
                if t:
                    out.append(t)
            else:
                changed = True
        return out, changed
    return [], True


def _set_list(obj: dict[str, Any], key: str, where: str, fixes: list[str], *, tokens: bool = False) -> list[str]:
    if key not in obj:
        return []
    vals, changed = (_token_list if tokens else _text_list)(obj[key])
    if changed:
        _fix(fixes, f"{where}.{key}: turned into a list")
    obj[key] = vals
    return vals


def _dict_to_list(v: Any, key_name: str, value_name: str | None = None) -> list[Any] | None:
    """``{k: {...}}`` → ``[{key_name: k, ...}]``; ``{k: "x"}`` → ``[{key_name: k, value_name: "x"}]``; else None."""
    if not isinstance(v, dict) or not v:
        return None
    out = []
    for k, val in v.items():
        if isinstance(val, dict):
            item = dict(val)
            item.setdefault(key_name, k)
            out.append(item)
        elif value_name is not None:
            out.append({key_name: k, value_name: val})
        else:
            return None
    return out


def role_of(value: Any, *, name: str = "") -> str:
    """The model role for a role text such as ``"Senior developer"`` or ``"QA"``; ``""`` when nothing matches."""
    v = str(value or "").strip().lower()
    if v in ROLES:
        return v
    words = " " + re.sub(r"[^a-z0-9]+", " ", (v or str(name).lower())) + " "
    for role, keys in _ROLE_RULES:
        for k in keys:
            if (" " + k + " ") in words or (len(k) > 3 and k in words):
                return role
    return ""


def norm_version(v: Any) -> str:
    """``v0.1`` → ``0.1.0``; ``1`` → ``1.0.0``; ``0.2.0-beta`` stays; ``""`` when no number is present."""
    s = _text(v).strip().lstrip("vV").strip()
    m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?([-+][0-9A-Za-z.-]+)?$", s)
    if not m:
        m2 = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", s)
        if not m2:
            return ""
        return f"{m2.group(1)}.{m2.group(2) or 0}.{m2.group(3) or 0}"
    return f"{m.group(1)}.{m.group(2) or 0}.{m.group(3) or 0}{m.group(4) or ''}"


def norm_ref(v: Any) -> str:
    s = _REF_BAD.sub("-", _text(v)).strip("-._")
    return s[:40]


def _slug(s: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", str(s or ""))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# --------------------------------------------------------------------------- agent ids

class _Agents:
    """Resolves whatever the model used to name an AI (id, name, snake_case…) to one agent id."""

    def __init__(self, state: dict[str, Any] | None) -> None:
        st = state or {}
        self.known: dict[str, dict[str, Any]] = {aid: a for aid, a in (st.get("agents") or {}).items()
                                                 if a.get("enabled", True)}
        self.by_name: dict[str, str] = {}
        for aid, a in self.known.items():
            for label in (a.get("name"), aid, aid.removeprefix("agent-")):
                if label:
                    self.by_name.setdefault(_slug(str(label)), aid)
        self.map: dict[str, str] = {}

    def learn(self, raw: Any, name: Any = "") -> str:
        """Register an agent the charter declares (its id and/or name) and return the resolved id."""
        aid = self.resolve(raw) or self.resolve(name)
        if not aid:
            base = _slug(_text(raw)) or _slug(_text(name))
            base = base.removeprefix("agent-")
            aid = f"agent-{base}" if base else ""
            if aid and not valid_id("agent", aid):
                aid = ("agent-" + base[:56]).rstrip("-")
        for k in (_text(raw), _text(name)):
            if k and aid:
                self.map.setdefault(k, aid)
                self.map.setdefault(_slug(k), aid)
        return aid

    def resolve(self, raw: Any) -> str:
        s = _text(raw)
        if not s:
            return ""
        if s in self.map:
            return self.map[s]
        if s in self.known:
            return s
        sl = _slug(s)
        if sl in self.map:
            return self.map[sl]
        cand = sl if sl.startswith("agent-") else f"agent-{sl}"
        if cand in self.known:
            return cand
        for key in (sl, sl.removeprefix("agent-")):
            if key in self.by_name:
                return self.by_name[key]
        if sl in ("pm", "manager", "project-manager", "agent-pm", "lead", "project-lead"):
            return PM_ID
        if valid_id("agent", cand):
            return cand if cand in self.map.values() else ""
        return ""

    def fix(self, raw: Any, where: str, fixes: list[str]) -> Any:
        """The resolved id for ``raw`` (unchanged when nothing better is known), reporting a rename."""
        s = _text(raw)
        aid = self.resolve(s)
        if not aid:
            sl = _slug(s)
            cand = sl if sl.startswith("agent-") else f"agent-{sl}" if sl else ""
            aid = cand if cand and valid_id("agent", cand) else ""
        if aid and aid != s:
            _fix(fixes, f"{where}: {s!r} → {aid}")
            return aid
        return raw if aid == "" else aid


# --------------------------------------------------------------------------- the repair

def is_wizard_team(state: dict[str, Any] | None) -> bool:
    return ((state or {}).get("settings") or {}).get("team_source") == "wizard"


def repair(data: Any, state: dict[str, Any] | None = None) -> tuple[Any, list[str]]:  # noqa: C901 — one pass, in order
    """``(charter, fixes)``: the canonical charter and the list of every change made. Never raises."""
    fixes: list[str] = []
    if not isinstance(data, dict):
        return data, fixes
    d = copy.deepcopy(data)
    st = state or {"agents": {}, "settings": {}}

    # 0. wrappers
    for wrap in ("project_charter", "charter", "AIWB_PROJECT_CHARTER", "data", "result"):
        inner = d.get(wrap)
        if isinstance(inner, dict) and len(d) <= 2 and any(k in inner for k in ("tasks", "roadmap", "architecture")):
            d = copy.deepcopy(inner)
            _fix(fixes, f"the charter was wrapped in \"{wrap}\" — unwrapped")
            break

    # 1. header fields
    sv = d.get("schema_version")
    if sv != "1.0":
        if sv in (1, 1.0, "1", "1.0.0", "v1", "v1.0", None, "") or (isinstance(sv, str) and sv.strip().startswith("1")):
            d["schema_version"] = "1.0"
            _fix(fixes, f"schema_version: {sv!r} → \"1.0\"" if sv not in (None, "") else "schema_version: added \"1.0\"")
    if d.get("charter_type") != "project_charter":
        if d.get("charter_type") not in (None, ""):
            _fix(fixes, f"charter_type: {d.get('charter_type')!r} → \"project_charter\"")
        d["charter_type"] = "project_charter"
    rev = d.get("base_state_revision", d.pop("state_revision", None) if "state_revision" in d else None)
    if not isinstance(rev, int) or isinstance(rev, bool):
        cur = int(st.get("state_revision") or 0)
        m = re.search(r"\d+", str(rev)) if rev not in (None, "") and not isinstance(rev, bool) else None
        if m:
            d["base_state_revision"] = int(m.group(0))
            _fix(fixes, f"base_state_revision: {rev!r} → {int(m.group(0))}")
        else:
            d["base_state_revision"] = cur
            _fix(fixes, f"base_state_revision: missing — used the current state revision {cur}")
    else:
        d["base_state_revision"] = rev
    if "project" in d and not isinstance(d["project"], dict):
        d["project"] = {"summary": _text(d["project"])}
        _fix(fixes, "project: turned into an object")

    # 2. roadmap shape (+ tasks nested in milestones)
    rm = d.get("roadmap")
    if rm is None and isinstance(d.get("milestones"), (list, dict)):
        rm = {"milestones": d.pop("milestones")}
        _fix(fixes, "roadmap: the top-level \"milestones\" list was used as roadmap.milestones")
    if isinstance(rm, list):
        rm = {"milestones": rm}
        _fix(fixes, "roadmap: a list of milestones was wrapped as roadmap.milestones")
    if isinstance(rm, dict):
        ms = rm.get("milestones")
        if ms is None:
            k, v = _pick(rm, ("phases", "stages", "releases", "versions", "items"))
            if k:
                ms = v
                _fix(fixes, f"roadmap: used \"{k}\" as \"milestones\"")
        conv = _dict_to_list(ms, "ref")
        if conv is not None:
            ms = conv
            _fix(fixes, "roadmap.milestones: a dictionary was turned into a list")
        rm["milestones"] = ms if isinstance(ms, list) else ([] if ms is None else ms)
        d["roadmap"] = rm
    tasks = d.get("tasks")
    conv = _dict_to_list(tasks, "ref")
    if conv is not None:
        tasks = conv
        _fix(fixes, "tasks: a dictionary was turned into a list")
    if tasks is None:
        tasks = []
    nested = 0
    if isinstance(rm, dict) and isinstance(rm.get("milestones"), list):
        for mi, m in enumerate(rm["milestones"]):
            if isinstance(m, dict) and isinstance(m.get("tasks"), list) and any(isinstance(t, dict) for t in m["tasks"]):
                mref = m.get("ref") or m.get("id") or f"m{mi + 1}"
                refs = []
                for t in m.pop("tasks"):
                    if isinstance(t, dict):
                        t = dict(t)
                        t.setdefault("milestone_ref", mref)
                        tasks.append(t) if isinstance(tasks, list) else None
                        refs.append(t.get("ref") or t.get("id"))
                        nested += 1
                    elif isinstance(t, (str, int)):
                        refs.append(t)
                m.setdefault("task_refs", [r for r in refs if r not in (None, "")])
    if nested:
        _fix(fixes, f"tasks: {nested} task(s) written inside milestones were moved to the task list")
    if "tasks" in d or tasks:
        d["tasks"] = tasks

    # 3. milestones: keys, refs, versions
    ms_ref_map: dict[str, str] = {}
    ms_title_map: dict[str, str] = {}
    milestones = d["roadmap"]["milestones"] if isinstance(d.get("roadmap"), dict) and isinstance(
        d["roadmap"].get("milestones"), list) else []
    seen_ms: set[str] = set()
    for i, m in enumerate(milestones):
        if not isinstance(m, dict):
            continue
        where = f"roadmap.milestones[{i}]"
        m = _canon(m, _MILESTONE_KEYS, where, fixes)
        raw = m.get("ref")
        ref = norm_ref(raw) or f"m{i + 1}"
        if ref in seen_ms:
            ref = f"{ref}-{i + 1}"
        seen_ms.add(ref)
        if _text(raw) != ref:
            _fix(fixes, f"{where}.ref: {raw!r} → {ref}" if raw not in (None, "") else f"{where}.ref: added {ref}")
        if raw not in (None, ""):
            ms_ref_map[_text(raw)] = ref
        m["ref"] = ref
        if _text(m.get("title")):
            m["title"] = _text(m["title"])
            ms_title_map[_slug(m["title"])] = ref
        else:
            m["title"] = f"Milestone {i + 1}"
            _fix(fixes, f"{where}.title: missing — named \"{m['title']}\"")
        v = m.get("version")
        nv = norm_version(v)
        if not nv:
            nv = f"0.{i + 1}.0"
            _fix(fixes, f"{where}.version: missing — set to {nv}" if v in (None, "") else f"{where}.version: {v!r} → {nv}")
        elif nv != _text(v):
            _fix(fixes, f"{where}.version: {v!r} → {nv}")
        m["version"] = nv
        if "criteria" in m:
            _set_list(m, "criteria", where, fixes)
        if not m.get("criteria"):
            m["criteria"] = [f"{m['title']} is reached"]
            _fix(fixes, f"{where}.criteria: missing — used the milestone title")
        if "task_refs" in m:
            _set_list(m, "task_refs", where, fixes, tokens=True)
        milestones[i] = m

    def ms_ref(v: Any) -> str:
        s = _text(v)
        if not s:
            return ""
        if s in seen_ms:
            return s
        if s in ms_ref_map:
            return ms_ref_map[s]
        if _slug(s) in ms_title_map:
            return ms_title_map[_slug(s)]
        n = norm_ref(s)
        if n in seen_ms:
            return n
        m = re.fullmatch(r"(?:m|milestone|ms|phase)[-_ ]?(\d+)", s, re.I)
        if m and f"m{m.group(1)}" in seen_ms:
            return f"m{m.group(1)}"
        if s.isdigit() and 0 < int(s) <= len(milestones):
            mm = milestones[int(s) - 1]
            return mm["ref"] if isinstance(mm, dict) else n
        return n

    # 4. tasks: keys, refs
    task_list = d.get("tasks") if isinstance(d.get("tasks"), list) else []
    task_ref_map: dict[str, str] = {}
    seen_t: set[str] = set()
    for i, t in enumerate(task_list):
        if not isinstance(t, dict):
            continue
        where = f"tasks[{i}]"
        t = _canon(t, _TASK_KEYS, where, fixes)
        raw = t.get("ref")
        ref = norm_ref(raw) or f"t{i + 1}"
        if ref in seen_t:
            ref = f"{ref}-{i + 1}"
        seen_t.add(ref)
        if _text(raw) != ref:
            _fix(fixes, f"{where}.ref: {raw!r} → {ref}" if raw not in (None, "") else f"{where}.ref: added {ref}")
        if raw not in (None, ""):
            task_ref_map[_text(raw)] = ref
        t["ref"] = ref
        task_list[i] = t

    def t_ref(v: Any) -> str:
        s = _text(v)
        if s in seen_t:
            return s
        if s in task_ref_map:
            return task_ref_map[s]
        n = norm_ref(s)
        if n in seen_t:
            return n
        m = re.fullmatch(r"(?:t|task)[-_ ]?(\d+)", s, re.I)
        if m and f"t{m.group(1)}" in seen_t:
            return f"t{m.group(1)}"
        return n

    for i, m in enumerate(milestones):
        if isinstance(m, dict) and m.get("task_refs"):
            new = [t_ref(r) for r in m["task_refs"]]
            if new != m["task_refs"]:
                _fix(fixes, f"roadmap.milestones[{i}].task_refs: refs matched to the task list")
            m["task_refs"] = new

    # 5. team
    agents = _Agents(st)
    wizard = is_wizard_team(st)
    team = d.get("team")
    if isinstance(team, list):
        team = {"agents": team}
        _fix(fixes, "team: a list of agents was wrapped as team.agents")
    if team is None and isinstance(d.get("agents"), (list, dict)):
        team = {"agents": d.pop("agents")}
        _fix(fixes, "team: the top-level \"agents\" list was used as team.agents")
    if isinstance(team, dict):
        team = dict(team)
        ags = team.get("agents")
        if ags is None:
            k, v = _pick(team, ("members", "ais", "roles", "chats", "team"))
            if k:
                ags = v
                _fix(fixes, f"team: used \"{k}\" as \"agents\"")
        conv = _dict_to_list(ags, "agent_id", "purpose")
        if conv is not None:
            ags = conv
            _fix(fixes, "team.agents: a dictionary was turned into a list")
        out_agents = []
        for i, a in enumerate(ags if isinstance(ags, list) else []):
            where = f"team.agents[{i}]"
            if isinstance(a, str):
                a = {"agent_id": a}
                _fix(fixes, f"{where}: a name was turned into an agent")
            if not isinstance(a, dict):
                out_agents.append(a)
                continue
            a = _canon(a, _AGENT_KEYS, where, fixes)
            raw = a.get("agent_id")
            aid = agents.learn(raw, a.get("name"))
            if aid and aid != _text(raw):
                _fix(fixes, f"{where}.agent_id: {raw!r} → {aid}" if raw not in (None, "") else f"{where}.agent_id: added {aid}")
            a["agent_id"] = aid or raw
            known = agents.known.get(aid)
            role = role_of(a.get("role"), name=_text(a.get("name")) or aid)
            if known is not None and role != known["role"] and (wizard or not role or a.get("role") not in ROLES):
                if a.get("role") not in (None, ""):
                    _fix(fixes, f"{where}.role: {a.get('role')!r} → {known['role']} (as in your team)")
                role = known["role"]
            if not role and aid == PM_ID:
                role = "project_manager"
            if role and role != a.get("role"):
                if known is None or a.get("role") not in (None, ""):
                    _fix(fixes, f"{where}.role: {a.get('role')!r} → {role}" if a.get("role") not in (None, "")
                         else f"{where}.role: added {role}")
                a["role"] = role
            if not _text(a.get("name")) and known is not None:
                a["name"] = known.get("name") or aid
            if not _text(a.get("purpose")):
                a["purpose"] = (known or {}).get("purpose") or f"{_text(a.get('name')) or aid} — work assigned in the tasks"
                _fix(fixes, f"{where}.purpose: missing — filled in")
            elif not isinstance(a.get("purpose"), str):
                a["purpose"] = _text(a["purpose"])
            if "owns_modules" in a:
                _set_list(a, "owns_modules", where, fixes, tokens=True)
            out_agents.append(a)
        team["agents"] = out_agents
        d["team"] = team

    # 5b. Charter v2: the user's team from the wizard is the team
    if wizard:
        mine = [a for a in agents.known.values()]
        order = {aid: i for i, aid in enumerate((st.get("settings") or {}).get("team_order") or [])}
        mine.sort(key=lambda a: (a["agent_id"] != PM_ID, order.get(a["agent_id"], len(order)), a["agent_id"]))
        if not isinstance(d.get("team"), dict):
            d["team"] = {"agents": []}
            _fix(fixes, "team: taken from the team you defined (Charter v2)")
        team = d["team"]
        have = {a.get("agent_id") for a in team.get("agents", []) if isinstance(a, dict)}
        added = []
        for a in mine:
            if a["agent_id"] not in have:
                team.setdefault("agents", []).append({"agent_id": a["agent_id"], "role": a["role"],
                                                      "name": a.get("name") or a["agent_id"],
                                                      "purpose": a.get("purpose") or f"{a.get('name')} ({a['role']})",
                                                      "owns_modules": []})
                added.append(a["agent_id"])
        if added and len(added) < len(mine):
            _fix(fixes, "team.agents: added from your team: " + ", ".join(added))
        elif added and "team: taken from the team you defined (Charter v2)" not in fixes:
            _fix(fixes, "team.agents: taken from the team you defined (Charter v2)")
    team = d.get("team") if isinstance(d.get("team"), dict) else None
    if team is not None:
        ags = [a for a in team.get("agents", []) if isinstance(a, dict)]
        workers = [a for a in ags if a.get("role") != "project_manager"]
        if not isinstance(team.get("pm_counted"), bool):
            team["pm_counted"] = any(a.get("role") == "project_manager" for a in ags) or not ags
            _fix(fixes, f"team.pm_counted: set to {str(team['pm_counted']).lower()}")
        for k, val in (("total_agents", len(ags) if team["pm_counted"] else len(workers)),
                       ("parallel_chats", max(1, len(workers)))):
            cur = team.get(k)
            if isinstance(cur, str) and cur.strip().isdigit():
                team[k] = int(cur.strip())
                _fix(fixes, f"team.{k}: {cur!r} → {team[k]}")
            elif not isinstance(cur, int) or isinstance(cur, bool) or cur < 1:
                team[k] = max(1, val)
                _fix(fixes, f"team.{k}: set to {team[k]}")
        if not _text(team.get("rationale")):
            team["rationale"] = ("The user chose this team in the New Project wizard." if wizard
                                 else "Not explained by the project manager.")
            _fix(fixes, "team.rationale: missing — filled in")
        elif not isinstance(team.get("rationale"), str):
            team["rationale"] = _text(team["rationale"])
        if team.get("simpler_alternative") is not None and not isinstance(team["simpler_alternative"], str):
            team["simpler_alternative"] = _text(team["simpler_alternative"])

    # 6. architecture
    arch = d.get("architecture")
    if isinstance(arch, str):
        arch = {"summary": arch}
        _fix(fixes, "architecture: a text was turned into {summary}")
    if isinstance(arch, list):
        arch = {"modules": arch}
        _fix(fixes, "architecture: a list was used as architecture.modules")
    if isinstance(arch, dict):
        arch = dict(arch)
        mods = arch.get("modules")
        if mods is None:
            k, v = _pick(arch, ("components", "parts", "packages", "layers", "services"))
            if k:
                mods = v
                _fix(fixes, f"architecture: used \"{k}\" as \"modules\"")
        conv = _dict_to_list(mods, "id", "purpose")
        if conv is not None:
            mods = conv
            _fix(fixes, "architecture.modules: a dictionary was turned into a list")
        out_mods, seen_mod = [], set()
        for i, mo in enumerate(mods if isinstance(mods, list) else []):
            where = f"architecture.modules[{i}]"
            if not isinstance(mo, dict):
                out_mods.append(mo)
                continue
            mo = _canon(mo, _MODULE_KEYS, where, fixes)
            if not _text(mo.get("id")):
                mo["id"] = _slug(_text(mo.get("name"))) or f"module-{i + 1}"
                _fix(fixes, f"{where}.id: added {mo['id']}")
            else:
                mo["id"] = _text(mo["id"])
            if mo["id"] in seen_mod:
                mo["id"] = f"{mo['id']}-{i + 1}"
            seen_mod.add(mo["id"])
            if not _text(mo.get("purpose")):
                mo["purpose"] = _text(mo.get("name")) or mo["id"]
                _fix(fixes, f"{where}.purpose: missing — used the module name")
            elif not isinstance(mo.get("purpose"), str):
                mo["purpose"] = _text(mo["purpose"])
            if "paths" in mo:
                _set_list(mo, "paths", where, fixes, tokens=True)
            if "depends_on" in mo:
                _set_list(mo, "depends_on", where, fixes, tokens=True)
            out_mods.append(mo)
        arch["modules"] = out_mods if isinstance(mods, list) or out_mods else mods
        if not _text(arch.get("summary")):
            arch["summary"] = _text((d.get("project") or {}).get("summary")) or "See the modules."
            _fix(fixes, "architecture.summary: missing — filled in")
        elif not isinstance(arch.get("summary"), str):
            arch["summary"] = _text(arch["summary"])
        d["architecture"] = arch
        # module dependency ids that use a name instead of the id
        ids = {mo["id"]: mo["id"] for mo in arch.get("modules", []) if isinstance(mo, dict)}
        names = {_slug(_text(mo.get("name"))): mo["id"] for mo in arch.get("modules", []) if isinstance(mo, dict)}
        for i, mo in enumerate(arch.get("modules", [])):
            if isinstance(mo, dict) and mo.get("depends_on"):
                new = [ids.get(x) or names.get(_slug(x)) or x for x in mo["depends_on"]]
                if new != mo["depends_on"]:
                    _fix(fixes, f"architecture.modules[{i}].depends_on: module names matched to ids")
                mo["depends_on"] = new
        if isinstance(d.get("team"), dict):
            # Charter v2: a module names its owner → that AI's owns_modules
            by_id = {a.get("agent_id"): a for a in d["team"].get("agents", []) if isinstance(a, dict)}
            for i, mo in enumerate(arch.get("modules", [])):
                if isinstance(mo, dict) and mo.get("owner_agent_id") not in (None, ""):
                    owner = agents.fix(mo.pop("owner_agent_id"), f"architecture.modules[{i}].owner_agent_id", fixes)
                    if owner in by_id:
                        own = by_id[owner].setdefault("owns_modules", [])
                        if mo["id"] not in own:
                            own.append(mo["id"])
            for i, a in enumerate(d["team"].get("agents", [])):
                if isinstance(a, dict) and a.get("owns_modules"):
                    new = [ids.get(x) or names.get(_slug(x)) or x for x in a["owns_modules"]]
                    if new != a["owns_modules"]:
                        _fix(fixes, f"team.agents[{i}].owns_modules: module names matched to ids")
                    a["owns_modules"] = new

    # 7. tasks: owners, milestones, lists, scope (needs agents + milestones)
    worker_ids = [a["agent_id"] for a in (d.get("team") or {}).get("agents", []) if isinstance(a, dict)
                  and a.get("role") != "project_manager" and isinstance(a.get("agent_id"), str)]
    for i, t in enumerate(task_list):
        if not isinstance(t, dict):
            continue
        where = f"tasks[{i}]"
        if t.get("owner_agent_id") not in (None, ""):
            t["owner_agent_id"] = agents.fix(t["owner_agent_id"], f"{where}.owner_agent_id", fixes)
        elif len(worker_ids) == 1:
            t["owner_agent_id"] = worker_ids[0]
            _fix(fixes, f"{where}.owner_agent_id: missing — the only working AI {worker_ids[0]}")
        if t.get("reviewer_agent_id") not in (None, ""):
            t["reviewer_agent_id"] = agents.fix(t["reviewer_agent_id"], f"{where}.reviewer_agent_id", fixes)
        mr = t.get("milestone_ref")
        if mr not in (None, ""):
            new = ms_ref(mr)
            if new != _text(mr):
                _fix(fixes, f"{where}.milestone_ref: {mr!r} → {new}")
            t["milestone_ref"] = new
        else:
            owners = [m["ref"] for m in milestones if isinstance(m, dict) and t["ref"] in (m.get("task_refs") or [])]
            if len(owners) == 1 or (not owners and len(milestones) == 1 and isinstance(milestones[0], dict)):
                t["milestone_ref"] = owners[0] if owners else milestones[0]["ref"]
                _fix(fixes, f"{where}.milestone_ref: missing — {t['milestone_ref']}")
        if "depends_on_refs" in t:
            _set_list(t, "depends_on_refs", where, fixes, tokens=True)
            new = [t_ref(x) for x in t["depends_on_refs"]]
            if new != t["depends_on_refs"]:
                _fix(fixes, f"{where}.depends_on_refs: refs matched to the task list")
            t["depends_on_refs"] = new
        if not _text(t.get("title")):
            t["title"] = (_text(t.get("objective"))[:80] or f"Task {t['ref']}")
            _fix(fixes, f"{where}.title: missing — filled in")
        elif not isinstance(t.get("title"), str):
            t["title"] = _text(t["title"])
        if len(t["title"]) > 200:
            t["title"] = t["title"][:197] + "…"
            _fix(fixes, f"{where}.title: shortened to 200 characters")
        if not _text(t.get("objective")):
            t["objective"] = t["title"]
            _fix(fixes, f"{where}.objective: missing — used the title")
        elif not isinstance(t.get("objective"), str):
            t["objective"] = _text(t["objective"])
        if "acceptance_criteria" in t:
            _set_list(t, "acceptance_criteria", where, fixes)
        if not t.get("acceptance_criteria"):
            t["acceptance_criteria"] = [f"{t['title']}: done as described in the objective"]
            _fix(fixes, f"{where}.acceptance_criteria: missing — derived from the title (check it)")
        sc = t.get("scope")
        if isinstance(sc, (str, list)):
            inc, _c = _token_list(sc)
            t["scope"] = {"include": inc, "exclude": []}
            _fix(fixes, f"{where}.scope: a path list was turned into {{include}}")
        elif isinstance(sc, dict):
            sc = dict(sc)
            if "include" not in sc:
                k, v = _pick(sc, ("paths", "files", "allowed", "write", "includes"))
                if k:
                    sc["include"] = v
                    _fix(fixes, f"{where}.scope: used \"{k}\" as \"include\"")
            for k in ("include", "exclude"):
                if k in sc:
                    vals, changed = _token_list(sc[k])
                    if changed:
                        _fix(fixes, f"{where}.scope.{k}: turned into a list")
                    sc[k] = vals
            sc.setdefault("exclude", [])
            t["scope"] = sc
        if t.get("priority") not in (None, ""):
            p = _PRIORITY.get(_text(t["priority"]).lower().replace(" ", ""))
            if p is None:
                _fix(fixes, f"{where}.priority: {t['priority']!r} is not low/medium/high/critical — dropped")
                t.pop("priority")
            elif p != t["priority"]:
                _fix(fixes, f"{where}.priority: {t['priority']!r} → {p}")
                t["priority"] = p
        if t.get("parallel_group") not in (None, ""):
            g = _text(t["parallel_group"])[:20]
            if g != t["parallel_group"]:
                _fix(fixes, f"{where}.parallel_group: written as text")
            t["parallel_group"] = g
        else:
            t.pop("parallel_group", None)

    # 8. coordination
    co = d.get("coordination")
    if co is None and any(k in d for k in ("file_ownership", "ownership", "conflict_resolution", "sync_points")):
        co = {k: d.pop(k) for k in ("file_ownership", "ownership", "shared_contracts", "sync_points",
                                    "conflict_resolution") if k in d}
        _fix(fixes, "coordination: top-level coordination keys were grouped into coordination")
    if co is None and (d.get("team") is not None or wizard):
        co = {}
        _fix(fixes, "coordination: missing — built from the modules and tasks")
    if isinstance(co, dict):
        co = dict(co)
        fo = co.get("file_ownership")
        if fo is None:
            k, v = _pick(co, ("ownership", "files", "owners", "path_ownership", "file_owners"))
            if k:
                fo = v
                co.pop(k, None)
                _fix(fixes, f"coordination: used \"{k}\" as \"file_ownership\"")
        conv = _dict_to_list(fo, "agent_id", "paths")
        if conv is not None:
            fo = conv
            _fix(fixes, "coordination.file_ownership: a dictionary was turned into a list")
        out_fo: list[Any] = []
        for i, o in enumerate(fo if isinstance(fo, list) else []):
            where = f"coordination.file_ownership[{i}]"
            if not isinstance(o, dict):
                out_fo.append(o)
                continue
            o = dict(o)
            if "agent_id" not in o:
                k, v = _pick(o, ("owner", "agent", "owner_agent_id", "ai"))
                if k:
                    o["agent_id"] = v
                    o.pop(k, None)
            if "paths" not in o:
                k, v = _pick(o, ("path", "files", "globs", "folders", "include"))
                if k:
                    o["paths"] = v
                    o.pop(k, None)
            if o.get("agent_id") not in (None, ""):
                o["agent_id"] = agents.fix(o["agent_id"], f"{where}.agent_id", fixes)
            _set_list(o, "paths", where, fixes, tokens=True)
            out_fo.append(o)
        if not out_fo:
            out_fo = _derive_ownership(d)
            if out_fo:
                _fix(fixes, "coordination.file_ownership: missing — derived from module ownership / task scopes")
        co["file_ownership"] = out_fo
        sc_list = co.get("shared_contracts")
        conv = _dict_to_list(sc_list, "name", "path")
        if conv is not None:
            sc_list = conv
            _fix(fixes, "coordination.shared_contracts: a dictionary was turned into a list")
        if isinstance(sc_list, str):
            sc_list = [{"name": sc_list, "owner_agent_id": PM_ID}]
            _fix(fixes, "coordination.shared_contracts: a text was turned into one contract owned by the project manager")
        if isinstance(sc_list, list):
            for i, c in enumerate(sc_list):
                if isinstance(c, dict):
                    where = f"coordination.shared_contracts[{i}]"
                    if "owner_agent_id" not in c:
                        k, v = _pick(c, ("owner", "agent_id", "agent"))
                        if k:
                            c["owner_agent_id"] = v
                            c.pop(k, None)
                    if c.get("owner_agent_id") not in (None, ""):
                        c["owner_agent_id"] = agents.fix(c["owner_agent_id"], f"{where}.owner_agent_id", fixes)
                    if not _text(c.get("name")):
                        c["name"] = _text(c.get("path")) or f"Contract {i + 1}"
                        _fix(fixes, f"{where}.name: missing — filled in")
                    if "consumers" in c:
                        _set_list(c, "consumers", where, fixes, tokens=True)
                        c["consumers"] = [agents.fix(x, f"{where}.consumers", fixes) for x in c["consumers"]]
            co["shared_contracts"] = sc_list
        sp = co.get("sync_points")
        if sp is None:
            co["sync_points"] = []
            _fix(fixes, "coordination.sync_points: missing — none")
        else:
            if isinstance(sp, str):
                sp = [sp]
            if isinstance(sp, dict):
                sp = [{"after_milestone": k, "description": _text(v)} for k, v in sp.items()]
            out_sp = []
            for i, x in enumerate(sp if isinstance(sp, list) else []):
                if isinstance(x, str):
                    out_sp.append({"description": x})
                    _fix(fixes, f"coordination.sync_points[{i}]: a text was turned into {{description}}")
                elif isinstance(x, dict):
                    x = dict(x)
                    if "after_milestone" not in x:
                        k, v = _pick(x, ("milestone", "after", "milestone_ref", "when"))
                        if k:
                            x["after_milestone"] = v
                            x.pop(k, None)
                    if x.get("after_milestone") not in (None, ""):
                        new = ms_ref(x["after_milestone"])
                        if new != _text(x["after_milestone"]):
                            _fix(fixes, f"coordination.sync_points[{i}].after_milestone: {x['after_milestone']!r} → {new}")
                        x["after_milestone"] = new
                    else:
                        x.pop("after_milestone", None)
                    if not _text(x.get("description")):
                        k, v = _pick(x, ("rule", "what", "text", "note"))
                        x["description"] = _text(v) or "Wait for the previous milestone"
                        _fix(fixes, f"coordination.sync_points[{i}].description: filled in")
                    out_sp.append(x)
            co["sync_points"] = out_sp
        if not _text(co.get("conflict_resolution")):
            co["conflict_resolution"] = "The project manager decides; the user has the final say."
            _fix(fixes, "coordination.conflict_resolution: missing — \"the project manager decides\"")
        elif not isinstance(co.get("conflict_resolution"), str):
            co["conflict_resolution"] = _text(co["conflict_resolution"])
        d["coordination"] = co
        own = {o["agent_id"]: o.get("paths", []) for o in co["file_ownership"] if isinstance(o, dict)
               and isinstance(o.get("agent_id"), str)}
        for i, t in enumerate(task_list):
            if isinstance(t, dict) and not ((t.get("scope") or {}).get("include")):
                paths = own.get(str(t.get("owner_agent_id") or ""))
                if paths:
                    t["scope"] = {"include": list(paths), "exclude": []}
                    _fix(fixes, f"tasks[{i}].scope: missing — the files {t['owner_agent_id']} owns")
        mods = (d.get("architecture") or {}).get("modules") if isinstance(d.get("architecture"), dict) else None
        if isinstance(d.get("architecture"), dict) and not mods and co["file_ownership"]:
            d["architecture"]["modules"] = [
                {"id": (o["agent_id"].removeprefix("agent-") or f"module-{i + 1}"), "name": o["agent_id"],
                 "purpose": f"Files owned by {o['agent_id']}", "paths": list(o.get("paths") or []), "depends_on": []}
                for i, o in enumerate(co["file_ownership"]) if isinstance(o, dict) and o.get("paths")]
            if d["architecture"]["modules"]:
                _fix(fixes, "architecture.modules: missing — one module per AI's owned files")

    # 9. start prompts
    sps = d.get("start_prompts")
    conv = _dict_to_list(sps, "agent_id", "prompt")
    if conv is not None:
        sps = conv
        _fix(fixes, "start_prompts: a dictionary {agent: prompt} was turned into a list")
    if isinstance(sps, list):
        out_sp2 = []
        for i, x in enumerate(sps):
            where = f"start_prompts[{i}]"
            if isinstance(x, dict):
                x = dict(x)
                if "prompt" not in x:
                    k, v = _pick(x, ("text", "message", "content", "start_prompt", "first_message"))
                    if k:
                        x["prompt"] = v
                        x.pop(k, None)
                        _fix(fixes, f"{where}: used \"{k}\" as \"prompt\"")
                if "agent_id" not in x:
                    k, v = _pick(x, ("agent", "for", "owner", "ai", "name"))
                    if k:
                        x["agent_id"] = v
                        x.pop(k, None)
                if x.get("agent_id") not in (None, ""):
                    x["agent_id"] = agents.fix(x["agent_id"], f"{where}.agent_id", fixes)
                if not isinstance(x.get("prompt"), str):
                    x["prompt"] = _text(x.get("prompt"))
            out_sp2.append(x)
        sps = out_sp2
    elif sps is not None:
        sps = []
        _fix(fixes, "start_prompts: not a list — Workbench writes them")
    if isinstance(d.get("team"), dict):
        have = {x.get("agent_id") for x in (sps or []) if isinstance(x, dict) and len(_text(x.get("prompt"))) >= 40}
        sps = [x for x in (sps or []) if not (isinstance(x, dict) and len(_text(x.get("prompt"))) < 40
                                               and x.get("agent_id") in set(worker_ids))]
        written = []
        for a in d["team"].get("agents", []):
            if isinstance(a, dict) and a.get("role") != "project_manager" and isinstance(a.get("agent_id"), str) \
                    and a["agent_id"] not in have:
                sps.append({"agent_id": a["agent_id"], "prompt": build_start_prompt(d, a["agent_id"])})
                written.append(a["agent_id"])
        if written:
            _fix(fixes, "start_prompts: written by Workbench for " + ", ".join(written))
    if sps is not None or "start_prompts" in d:
        d["start_prompts"] = sps or []

    # 10. lists at the top
    for k in ("risks", "questions_for_user"):
        if k in d:
            vals, changed = _text_list(d[k])
            if changed:
                _fix(fixes, f"{k}: turned into a list")
            d[k] = vals

    # 11. Charter v2: what the v2 prompt told the model to leave out is by design, not a repair
    if wizard and "team" not in data:
        expected: tuple[str, ...] = ("team: taken from", "team.agents: taken from", "team.agents: added from",
                                     "team.pm_counted:", "team.total_agents: set", "team.parallel_chats: set",
                                     "team.rationale: missing", "start_prompts: written by Workbench",
                                     "coordination.conflict_resolution: missing", "coordination.sync_points: missing")
        if "coordination" not in data:
            expected += ("coordination: missing", "coordination.file_ownership: missing")
        fixes[:] = [f for f in fixes if not f.startswith(expected)]
        if isinstance(d.get("team"), dict) and not _text(d["team"].get("simpler_alternative")):
            d["team"]["simpler_alternative"] = "The user decided the team size."
    return d, fixes


def _derive_ownership(d: dict[str, Any]) -> list[dict[str, Any]]:
    """file_ownership from team.agents[].owns_modules → module paths, else from each owner's task scopes."""
    mods = {m.get("id"): m.get("paths") or [] for m in ((d.get("architecture") or {}).get("modules") or [])
            if isinstance(m, dict)} if isinstance(d.get("architecture"), dict) else {}
    out: dict[str, list[str]] = {}
    for a in ((d.get("team") or {}).get("agents") or []):
        if isinstance(a, dict) and a.get("role") != "project_manager" and isinstance(a.get("agent_id"), str):
            for m in a.get("owns_modules") or []:
                for p in mods.get(m, []):
                    if p not in out.setdefault(a["agent_id"], []):
                        out[a["agent_id"]].append(p)
    if not out:
        for t in d.get("tasks") or []:
            if isinstance(t, dict) and isinstance(t.get("owner_agent_id"), str):
                inc, _c = _token_list((t.get("scope") or {}).get("include") if isinstance(t.get("scope"), dict) else t.get("scope"))
                for p in inc:
                    if p not in out.setdefault(t["owner_agent_id"], []):
                        out[t["owner_agent_id"]].append(p)
    return [{"agent_id": k, "paths": v} for k, v in out.items() if v]


def build_start_prompt(charter: dict[str, Any], agent_id: str) -> str:
    """The first message for one AI's own chat, written by Workbench from the charter (Charter v2, 5.10.0)."""
    proj = charter.get("project") if isinstance(charter.get("project"), dict) else {}
    arch = charter.get("architecture") if isinstance(charter.get("architecture"), dict) else {}
    agent = next((a for a in ((charter.get("team") or {}).get("agents") or []) if isinstance(a, dict)
                  and a.get("agent_id") == agent_id), {})
    name = _text(agent.get("name")) or agent_id
    lines = [f"You are \"{name}\" ({agent_id}, role {agent.get('role') or 'implementer'}) in a project built by "
             "several AI chats that cannot see each other."]
    if _text(proj.get("name")) or _text(proj.get("goal")):
        lines.append(f"Project: {_text(proj.get('name'))} — {_text(proj.get('goal'))}".strip(" —"))
    if _text(arch.get("summary")):
        lines.append(f"Architecture: {_text(arch.get('summary'))[:600]}")
    if _text(agent.get("purpose")):
        lines.append(f"Your job: {_text(agent.get('purpose'))[:600]}")
    mods = [m for m in (arch.get("modules") or []) if isinstance(m, dict) and m.get("id") in (agent.get("owns_modules") or [])]
    if mods:
        lines.append("Your modules: " + "; ".join(f"{m.get('id')} ({', '.join(m.get('paths') or [])})" for m in mods))
    mine = [t for t in (charter.get("tasks") or []) if isinstance(t, dict) and t.get("owner_agent_id") == agent_id]
    if mine:
        lines.append("Your tasks, in order: " + "; ".join(f"{t.get('ref')} {t.get('title')}" for t in mine[:12]))
    lines.append("Workbench (the user's app) sends you one task prompt at a time; answer each with the files it asks for. "
                 "For now reply only with a short confirmation and any question you have.")
    return "\n".join(lines)
