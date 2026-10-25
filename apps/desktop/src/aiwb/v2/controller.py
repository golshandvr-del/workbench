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

from .. import i18n
from . import V2Project, build_snapshot
from .handoff import BLOCK_RE as HANDOFF_RE
from .models import ModelError
from .proposals import BLOCK_RE as PROPOSAL_RE, manager_update_prompt, planning_prompt
from .snapshot import fallback_summary, render_status_md
from .team import normalize_team_settings, revision_request_prompt, team_planning_prompt, team_settings

# Plain-language labels come from the single FA/EN glossary (aiwb.i18n); English kept as module constants
# for callers that predate the language setting.
SIMPLE_STATUS = {k: (v[0], v[1]) for k, v in i18n.STATUS.items()}
SIMPLE_ACTION = {k: v[0] for k, v in i18n.ACTION.items() if k != "nothing"}

MODES = ("simple", "advanced")


@dataclass
class RouteResult:
    kind: str                       # proposal | charter_rejected | handoff | context_request | inbox_only | rejected
    #                                 | truncated (5.10.0: files found but the answer was cut off)
    response_id: str = ""
    message: str = ""
    reference_id: str = ""
    record: dict[str, Any] = field(default_factory=dict)
    text: str = ""                  # 5.10.0: the canonical answer text the loop read (files as AIWB blocks)


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
        # GitHub blue nodes (roadmap 4.5.0): manual until the app binds a token-backed client factory
        from .repo import RepoService
        self.repo = RepoService(self.project.store, root)
        self.ui_path = self.project.store.dir / "ui.json"
        self.mode = self._load_ui().get("mode") or str(self.project.store.load()["settings"].get("ui_mode", "simple"))
        if self.mode not in MODES:
            self.mode = "simple"
        self.lang = self._load_ui().get("lang") or i18n.DEFAULT_LANGUAGE
        if self.lang not in i18n.LANGUAGES:
            self.lang = i18n.DEFAULT_LANGUAGE

    # -- mode: a view preference kept OUTSIDE the project state (spec §19.5: switching views changes no data,
    #    does not bump state_revision and never triggers a publish)
    def _load_ui(self) -> dict[str, Any]:
        try:
            d = json.loads(self.ui_path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_ui(self, **kw: str) -> None:
        try:
            self.ui_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.ui_path.parent), prefix=".ui-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({**self._load_ui(), **kw}, fh)
            os.replace(tmp, self.ui_path)
        except OSError:
            pass  # a view preference that cannot be saved is not an error

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ModelError("mode must be simple or advanced")
        self.mode = mode
        self._save_ui(mode=mode)

    def set_language(self, lang: str) -> None:
        """Display language only; data and logic use keys, never translated text (§19.4)."""
        if lang not in i18n.LANGUAGES:
            raise ModelError("language must be one of " + ", ".join(i18n.LANGUAGES))
        self.lang = lang
        self._save_ui(lang=lang)

    def t(self, key: str) -> str:
        return i18n.term(key, self.lang)

    def next_action_view(self) -> dict[str, Any] | None:
        """The same next action in both views (§19.1): Simple gets the summary, Advanced also the reason,
        the referenced entity and the queue behind it."""
        a = self.next_action()
        if not a:
            return None
        v = {"type": a["type"], "reference_id": a.get("reference_id", ""), "needs_approval": bool(a.get("needs_approval")),
             "summary": i18n.action(a["type"], self.lang, a["label"])}
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
            return i18n.action("nothing", self.lang)
        base = i18n.action(a["type"], self.lang, a["label"])
        ref = f" ({a['reference_id']})" if a.get("reference_id") else ""
        return base + ref + ("" if self.mode == "simple" else f" — {a['reason']}")

    def task_rows(self) -> list[dict[str, Any]]:
        rows = []
        for t in self.project.tasks.list():
            sym, word = i18n.status(t["status"], self.lang)
            row = {"task_id": t["task_id"], "title": t["title"], "symbol": sym, "status_text": word,
                   "status": t["status"], "owner": t.get("owner_agent_id", ""), "reason": t.get("blocked_reason", "")}
            if self.mode == "advanced":
                row.update(revision=t["task_revision"], depends_on=", ".join(t["depends_on"]),
                           attempt=t.get("active_attempt_id", ""), policy=t.get("acceptance_policy", ""))
            rows.append(row)
        return rows

    def publish_status(self) -> dict[str, Any]:
        """Last Published vs Local Revision (§22.11), in both views."""
        local = self.project.store.revision
        if self.publisher is None:
            return {"state": "local_only", "local_revision": local, "published_revision": 0,
                    "text": self.t("local_only")}
        q = self.publisher.queue()
        pub = int(q.get("last_published_revision") or 0)
        pending = bool(getattr(self.publisher, "pending", False))
        state = "paused" if q.get("paused") else ("behind" if pending else "current")
        word = self.t("publish_paused") if state == "paused" else self.t("published_behind" if pending else "published_current")
        text = f"{word} · {self.t('local_revision')} {local} · {self.t('last_published')} {pub or '—'}"
        if self.mode == "advanced" and q.get("last_error"):
            text += f" · {q['last_error']}"
        return {"state": state, "local_revision": local, "published_revision": pub, "text": text,
                "commit": q.get("last_commit", "")}

    def tick_publisher(self) -> dict[str, Any] | None:
        """Timer trigger used by the window (event + timer, §17 2E); never raises."""
        if self.publisher is None:
            return None
        try:
            return self.publisher.tick()
        except Exception as exc:  # noqa: BLE001 - publishing never blocks local work
            return {"status": "error", "message": str(exc)}

    def warning_items(self) -> list[dict[str, str]]:
        """Prioritised, de-duplicated warnings (§19.2): blocking (stop) first, then actions, then info.
        Each item has a severity key, a text in the display language and a reference id."""
        st = self.state()
        items: list[dict[str, str]] = []
        if self.publisher is not None:
            q = self.publisher.queue()
            if q.get("paused"):
                items.append({"severity": "blocking", "ref": "publish", "text": f"{self.t('publish_paused')}: {q['paused']}"})
        for p in st["proposals"].values():
            if p["status"] == "pending" and p.get("stale"):
                items.append({"severity": "action", "ref": p["proposal_id"],
                              "text": f"{self.t('stale_proposal')} ({p['proposal_id']})"})
        for d in st["decisions"].values():
            if d["status"] == "proposed":
                items.append({"severity": "action", "ref": d["decision_id"],
                              "text": f"{self.t('decision_needed')}: {d['title']} ({d['decision_id']})"})
        for h in st["handoffs"].values():
            if h["status"] in ("stale", "reconciliation_required"):
                items.append({"severity": "action", "ref": h["handoff_id"],
                              "text": f"{self.t('stale_answer')} ({h['handoff_id']}, {h['task_id']})"})
        for t in st["tasks"].values():
            if t["status"] == "blocked":
                items.append({"severity": "action", "ref": t["task_id"],
                              "text": f"{self.t('blocked')}: {t['title']} — {t.get('blocked_reason') or self.t('see_details')}"})
        for t in st["tasks"].values():
            if t["status"] == "validation_pending":
                items.append({"severity": "info", "ref": t["task_id"], "text": f"{self.t('not_verified')}: {t['title']}"})
        seen, out = set(), []
        for it in sorted(items, key=lambda x: i18n.SEVERITY_ORDER.index(x["severity"])):
            if it["text"] not in seen:
                seen.add(it["text"])
                out.append(it)
        return out

    def warnings(self) -> list[str]:
        """Prioritised warning texts (blocking first, then decisions, then blockers)."""
        return [w["text"] for w in self.warning_items()]

    def task_details(self, task_id: str) -> str:
        st = self.state()
        t = st["tasks"].get(task_id)
        if not t:
            return ""
        lines = [f"{t['task_id']} · {t['title']}", f"Status: {' '.join(i18n.status(t['status'], self.lang))}",
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
                             f"({i18n.evidence_label(i18n.evidence_state(e), self.lang)}, {e['source']['kind']})")
            ev = t.get("evaluation") or {}
            if ev.get("reasons"):
                lines.append("Policy: " + "; ".join(ev["reasons"]))
        return "\n".join(lines)

    # -- prompts (Workbench prepares; the user copies)
    def planning_prompt(self, goal: str, constraints: list[str] | None = None) -> str:
        with self.project.store.transaction("project goal") as s:
            s["settings"]["goal"] = goal.strip()[:2000]
        return planning_prompt({"goal": goal, "constraints": constraints or []}, self.project.agents.list())

    # -- team planner (2.4.0, spec §7)
    def team_settings(self) -> dict[str, Any]:
        return team_settings(self.state())

    def set_team_settings(self, **changes: Any) -> dict[str, Any]:
        with self.project.store.transaction("team settings") as s:
            new = normalize_team_settings(s, changes)
            if s["settings"].get("team") != new:
                s["settings"]["team"] = new
                from .store import emit
                emit(s, "team_settings_changed", **{k: str(v) for k, v in new.items()})
        return new

    # -- Agents hub (5.6.0): per-AI memory note and load balancing; every write is one store transaction
    def agent_hub(self) -> dict[str, Any]:
        """Stats, alerts and balancing suggestions of the open project (reading only)."""
        from . import agent_hub
        st = self.state()
        return {"stats": agent_hub.agent_stats(st), "alerts": agent_hub.alerts(st),
                "moves": agent_hub.rebalance(st)}

    def set_agent_note(self, agent_id: str, text: str) -> str:
        """Save the owner's memory note of one AI; it rides along in every prompt that AI gets."""
        from . import agent_hub
        from .store import emit
        with self.project.store.transaction("agent note") as s:
            before = agent_hub.note(s, agent_id)
            clean = agent_hub.set_note(s, agent_id, text)
            if clean != before:
                emit(s, "agent_note_changed", agent_id=agent_id, length=str(len(clean)))
        return clean

    def agent_briefing(self, agent_id: str) -> str:
        from . import agent_hub
        return agent_hub.briefing(self.state(), agent_id, project_name=self.root.name)

    def apply_rebalance(self, task_id: str, to_agent_id: str) -> dict[str, Any]:
        """Move one not-yet-started task to another AI (a suggestion of :func:`agent_hub.rebalance`)."""
        from .models import ModelError
        t = self.project.tasks.get(task_id)
        if t is None:
            raise ModelError(f"task {task_id} does not exist")
        if t.get("active_attempt_id") or t["status"] != "ready":
            raise ModelError(f"{task_id} has already started; only ready, unstarted tasks can move")
        return self.project.tasks.update(task_id, {"owner_agent_id": to_agent_id},
                                         reason=f"rebalanced to {to_agent_id}")

    # -- Project Charter (3.4.0)
    def charter_prompt(self, project: dict[str, Any]) -> str:
        """'Design the whole project' prompt. Saves the goal/brief only; nothing else changes."""
        from .charter import charter_prompt
        goal = str(project.get("goal", "")).strip()
        if not goal:
            raise ModelError("describe the project goal first (one or two sentences are enough)")
        with self.project.store.transaction("project goal") as s:
            s["settings"]["goal"] = goal[:2000]
            for k in ("non_goals", "success", "platform", "constraints", "limits"):
                if project.get(k):
                    s["settings"].setdefault("brief", {})[k] = str(project[k]).strip()[:2000]
        return charter_prompt({"profile": self.project_profile(), **project, "goal": goal}, self.state())

    def project_profile(self) -> dict[str, Any]:
        """The Project Profile saved by the profile page (``.workbench/project.json``); read only, {} if absent."""
        try:
            data = json.loads((self.root / ".workbench" / "project.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        prof = data.get("profile") if isinstance(data, dict) else None
        return prof if isinstance(prof, dict) else {}

    def import_charter(self, text: str, *, response_id: str = "") -> dict[str, Any]:
        """Parse + validate a charter answer; a valid one becomes a pending proposal (nothing applied)."""
        from .charter import charter_fix_prompt, charter_record, charter_to_proposal, parse_charter
        st = self.state()
        res = parse_charter(text, st)
        if not res["ok"]:
            return {**res, "proposal": None, "fix_prompt": charter_fix_prompt(res)}
        p = self.project.proposals.import_data(charter_to_proposal(res["data"], st), response_id=response_id,
                                               kind="charter", charter=charter_record(res["data"]),
                                               fixes=res.get("fixes") or [])
        self._dirty("charter imported")
        return {**res, "proposal": p, "fix_prompt": ""}

    def charter(self) -> dict[str, Any] | None:
        return self.state()["settings"].get("charter")

    def charter_start_prompt(self, agent_id: str) -> str:
        from .charter import start_prompt
        ch = self.charter()
        if not ch:
            raise ModelError("no Project Charter has been accepted yet")
        st = self.state()
        tasks = [f"{t['task_id']} {t['title']} ({t['status']})" for t in sorted(st["tasks"].values(), key=lambda t: t["task_id"])
                 if t.get("owner_agent_id") == agent_id and t["status"] not in ("cancelled", "superseded")]
        return start_prompt(ch, agent_id, task_lines=tasks)

    def team_planning_prompt(self, project: dict[str, Any]) -> str:
        """Planning prompt with registered resources + explicit team-size question. Saves goal only."""
        goal = str(project.get("goal", "")).strip()
        if not goal:
            raise ModelError("describe the project goal first (one or two sentences are enough)")
        with self.project.store.transaction("project goal") as s:
            s["settings"]["goal"] = goal[:2000]
            for k in ("non_goals", "success", "platform", "constraints", "limits"):
                if project.get(k):
                    s["settings"].setdefault("brief", {})[k] = str(project[k]).strip()[:2000]
        return team_planning_prompt({**project, "goal": goal}, self.state())

    def proposal_revision_prompt(self, proposal_id: str, note: str = "") -> str:
        p = self.project.proposals.get(proposal_id)
        if p is None:
            raise ModelError(f"proposal {proposal_id} does not exist")
        return revision_request_prompt(p, note)

    def start_task(self, task_id: str, agent_id: str = "") -> dict[str, Any]:
        t = self.project.tasks.get(task_id)
        if t is None:
            raise ModelError(f"task {task_id} does not exist")
        agent = agent_id or t.get("owner_agent_id") or "agent-implementer"
        h = self.project.handoffs.prepare(task_id, agent, base_commit_sha=self.base_commit())
        self._dirty("handoff prepared")
        return h

    def mark_copied(self, handoff_id: str) -> None:
        h = self.project.handoffs.get(handoff_id)
        if h and h["status"] == "prepared":
            self.project.handoffs.mark_exported(handoff_id)
        if h:
            self.project.workflow.mark_copied(h["attempt_id"])
        self._dirty("prompt copied")

    # -- manual workflow (2.5.0, spec §9)
    def start_warning(self, task_id: str) -> str:
        return self.project.workflow.open_attempt_warning(task_id)

    def confirm_sent(self, handoff_id: str, chat_binding_id: str = "") -> dict[str, Any]:
        h = self.project.handoffs.get(handoff_id)
        if h is None:
            raise ModelError(f"handoff {handoff_id} does not exist")
        out = self.project.workflow.confirm_sent(h["attempt_id"], chat_binding_id=chat_binding_id)
        self._dirty("user confirmed sent")
        return out

    def suggest_change_route(self, task_id: str, request: str) -> dict[str, Any]:
        from .changes import suggest_route
        return suggest_route(self.state(), task_id, request)

    def apply_change_route(self, task_id: str, route: str, request: str, title: str = "") -> dict[str, Any]:
        from .changes import apply_route
        out = apply_route(self.project, task_id, route, request, title=title)
        if route != "replan":
            self._dirty("change request")
        return out

    def workflow_stages(self) -> list[dict[str, Any]]:
        return self.project.workflow.stages()

    def manager_update(self) -> str:
        st = self.state()
        snap = build_snapshot(st, source={"commit_sha": self.base_commit()})
        return manager_update_prompt(snap, state_url=self.state_url(), fallback=fallback_summary(snap, st))

    def status_markdown(self) -> str:
        st = self.state()
        return render_status_md(build_snapshot(st), st)

    # -- one paste box for every answer
    def route_answer(self, text: str, *, file_hashes: dict[str, str] | None = None,
                     handoff_hint: str = "") -> RouteResult:
        """Read one pasted answer. ``handoff_hint``: the handoff the user pasted it for (a guide step), used when
        the answer itself does not say (5.10.0: Markdown / JSON / ZIP answers often carry no manifest)."""
        if not text.strip():
            return RouteResult("rejected", message="The answer is empty.")
        rid = ""
        if self.make_pipeline is not None:
            cap = self.make_pipeline(self.root).capture_text(text, source="v2-projects")
            rid = cap.response.response_id if cap.response else ""
        rid = rid or "resp-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        try:
            from .charter import has_charter
            if has_charter(text):
                out = self.import_charter(text, response_id=rid)
                if out["proposal"] is None:
                    if any("cut off" in e for e in out["errors"]):
                        # 5.10.0: a charter cannot be continued mid-JSON — the prompt asks for it again, shorter
                        out["cut_off"] = True
                        return RouteResult("charter_rejected", rid, "The Project Charter was cut off before its end "
                                           "and was not imported. A prompt that asks for the complete charter again, "
                                           "shorter, is ready to copy.", "", out)
                    return RouteResult("charter_rejected", rid, "The Project Charter is incomplete and was not imported: "
                                       + "; ".join(out["errors"][:3]) + (" …" if len(out["errors"]) > 3 else "")
                                       + " A fix prompt is ready to copy.", "", out)
                p = out["proposal"]
                data = out["data"] or {}
                n_ai = len([a for a in (data.get("team") or {}).get("agents", []) if isinstance(a, dict)])
                n_fix = len(out.get("fixes") or [])
                msg = (f"Charter ✓ · {n_ai} AIs · {len(data.get('tasks') or [])} tasks · "
                       f"{len((data.get('roadmap') or {}).get('milestones') or [])} milestones"
                       + (f" · {n_fix} auto-fix{'es' if n_fix != 1 else ''}" if n_fix else "")
                       + f". Imported as {p['proposal_id']} with {len(p['operations'])} change(s) — review and accept them.")
                if n_fix:
                    msg += " Fixed automatically: " + "; ".join(out["fixes"][:3]) + (" …" if n_fix > 3 else "") + "."
                if out["warnings"]:
                    msg += f" {len(out['warnings'])} warning(s) to check."
                return RouteResult("proposal", rid, msg, p["proposal_id"], p)
            if PROPOSAL_RE.search(text):
                p = self.project.proposals.import_text(text, response_id=rid)
                msg = f"Manager proposal {p['proposal_id']} with {len(p['operations'])} change(s) is ready for review."
                if p.get("stale"):
                    msg += " It was written for an older project state: review carefully."
                return RouteResult("proposal", rid, msg, p["proposal_id"], p)
            from ..intake.answer_files import canonical
            canon, ex = canonical(text)   # 5.10.0 (A13): Markdown, Strict JSON, ZIP, damaged markers → AIWB blocks
            if ex.truncated and not HANDOFF_RE.search(canon):
                # cut off before the end and nothing says what was finished: ask to continue, link nothing yet
                return RouteResult("truncated", rid, f"The answer was cut off ({len(ex.files)} file(s) so far, "
                                   f"{ex.label}). Nothing was linked; a continue prompt is ready.", text=canon)
            if ex.files or HANDOFF_RE.search(canon):
                text = canon
                hid = self._match_handoff(text, attempt_id=ex.attempt_id, hint=handoff_hint)
                if not hid and not HANDOFF_RE.search(text) and not ex.attempt_id:
                    return RouteResult("rejected", rid, f"{len(ex.files)} file(s) found ({ex.label}), but this "
                                       "project is not waiting for an answer they belong to. Copy a task prompt "
                                       "first. The answer is kept in the Inbox; nothing was changed.", text=text)
                if not hid:
                    return RouteResult("rejected", rid, "This answer names a task/attempt this project is not waiting "
                                       "for. It is kept in the Inbox; nothing was changed.", text=text)
                h = self.project.handoffs.ingest(hid, rid, text, file_hashes=file_hashes,
                                                 declared_attempt=ex.attempt_id if ex.attempt_id else "")
                self._dirty("handoff answer")
                msg = f"Answer linked to {hid} ({h['status']}, {h['outcome'] or 'no outcome'})."
                if ex.files:
                    msg += f" {len(ex.files)} file(s) read from {ex.label}."
                if ex.fixes:
                    msg += " Fixed automatically: " + "; ".join(ex.fixes[:3]) + (" …" if len(ex.fixes) > 3 else "") + "."
                if ex.problems:
                    msg += " Skipped: " + "; ".join(ex.problems[:3]) + (" …" if len(ex.problems) > 3 else "") + "."
                if h["unresolved_items"]:
                    msg += " Still open: " + "; ".join(h["unresolved_items"][:5])
                return RouteResult("handoff", rid, msg, hid, h, text=text)
        except ModelError as exc:
            return RouteResult("rejected", rid, f"{exc} The raw answer is kept in the Inbox.")
        from .changes import detect_context_request, note_context_request
        cr = detect_context_request(text)
        if cr is not None:
            if not cr["ok"]:
                return RouteResult("rejected", rid, f"Context request could not be read: {cr['error']} Nothing changed.")
            aid = note_context_request(self.project.store, self.project.workflow, cr)
            # 5.12.0 (owner audit B2): keep the request on its handoff → the Next-step card turns into
            # "<AI> asked for N file(s)" with [Copy the files for the chat]. Before, this was a dead end.
            from ..context_request import parse_request
            from . import context_step
            req = parse_request(text)
            hid = self._match_handoff(text, attempt_id=req.attempt_id, hint=handoff_hint)
            if not hid and aid:
                hid = next((h["handoff_id"] for h in self.state()["handoffs"].values()
                            if h.get("attempt_id") == aid and h["status"] in self.WAITING), "")
            self._dirty("context request")
            what = context_step.summary_line(context_step.to_record(req))
            if not hid:
                return RouteResult("context_request", rid, f"The model asks for: {what}. This project is not waiting "
                                   "for an answer it belongs to (copy the task prompt from the card first); nothing "
                                   "was prepared.", aid, cr)
            context_step.record(self.project.store, hid, req)
            cr["handoff_id"] = hid
            n_fix = len(req.fixes)
            return RouteResult("context_request", rid, f"The model asks for {what}. The next step shows them: "
                               "Copy the files for the chat, paste them into the same chat, then paste its answer."
                               + (f" {n_fix} auto-fix{'es' if n_fix != 1 else ''} in the request." if n_fix else ""),
                               hid, cr)
        return RouteResult("inbox_only", rid, "No manager proposal or handoff block found. If it contains files, "
                           "use the normal Analyze / preview flow on the Response tab.")

    WAITING = ("prepared", "prompt_exported", "response_received")

    def _match_handoff(self, text: str, *, attempt_id: str = "", hint: str = "") -> str:
        """The handoff an answer belongs to: its manifest, its ``AIWB_ATTEMPT_ID`` line, the guide step it was
        pasted for, or — 5.10.0 — the only handoff the project is waiting for."""
        from .handoff import find_manifest
        try:
            data = find_manifest(text) or {}
        except ModelError:
            data = {}
        st = self.state()
        hid = str(data.get("handoff_id", ""))
        if hid in st["handoffs"]:
            return hid
        for att in (str(data.get("attempt_id", "")), attempt_id):
            for h in st["handoffs"].values():
                if att and h["attempt_id"] == att:
                    return h["handoff_id"]
        if data.get("handoff_id") or data.get("attempt_id") or attempt_id:
            return ""   # the answer names another task/attempt: never guess
        if hint in st["handoffs"] and st["handoffs"][hint]["status"] in self.WAITING:
            return hint
        waiting = [h["handoff_id"] for h in st["handoffs"].values() if h["status"] in self.WAITING]
        return waiting[0] if len(waiting) == 1 else ""

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

    # -- project bundle (aiwb-bundle.v1, roadmap 3.8.0): move the project to/from the phone
    def export_bundle(self, *, version: str = "") -> str:
        """The whole project as one ``aiwb-bundle.v1`` JSON text (nothing local changes)."""
        from . import bundle
        if not version:
            from .. import __version__ as version
        return bundle.dumps(bundle.export_bundle(self.state(), name=self.root.name, version=version))

    def plan_bundle_import(self, data: str | bytes) -> dict[str, Any]:
        """What importing this bundle would do (new / same / newer / older / diverged / other_project)."""
        from . import bundle
        _b, incoming = bundle.read_bundle(data)
        local = self.project.store.load() if self.project.store.path.exists() else None
        return bundle.plan_import(local, incoming)

    def import_bundle(self, data: str | bytes, *, force: bool = False) -> dict[str, Any]:
        """Replace the project state with the bundle (backup first; unsafe kinds need ``force``)."""
        from . import bundle
        out = bundle.import_into(self.project.store, data, force=force)
        if out.get("imported"):
            self._dirty("project bundle imported")
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
