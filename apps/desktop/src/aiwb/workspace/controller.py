"""Workspace application controller (roadmap 2.3.0, spec §16.1).

Read models for the Project Workbench shell — overview, tasks, team, timeline,
inspector — plus the actions the shell may call. Everything is computed from the
same ``ProjectsController`` / V2 services; this module never re-implements a
status rule, never writes state directly and keeps layout preferences outside
the project state (``ui.json``), so switching views creates no event.
"""
from __future__ import annotations

from typing import Any, Callable

from .. import i18n
from ..v2.controller import ProjectsController
from ..v2.models import ModelError
from ..v2.dashboard import attention_queue, filter_agents, summarize, team_overview
from ..v2.timeline import lanes, planned_items, progress
from ..v2.workflow import stage_label, task_stage
from ..v2.resources import binding_readiness, current_binding

# 5.11.0 (audit A7): three sections instead of seven. The 2.3.0–5.10.0 keys stay valid as aliases, so old ui.json
# files, attention links and callers keep working.
# 5.13.0 (owner audit B3): the Timeline section is gone — milestones and versions are on the Mission Map's columns
# (Home = now and next) and past events are in History (the past). "timeline" stays a valid alias.
SECTIONS = ("plan", "project")
SECTION_ALIASES = {"overview": "plan", "tasks": "plan", "timeline": "plan", "team": "project", "files": "project",
                   "versions": "project", "settings": "project"}
SECTION_LABELS = {
    "plan": ("Plan & Tasks", "برنامه و وظایف"), "project": ("Project settings", "تنظیمات پروژه"),
}
SHORT_LABELS = {"plan": ("Plan", "برنامه"), "project": ("Project", "پروژه")}


def canonical_section(key: str) -> str:
    """The 5.11.0 section of ``key`` (an old 2.3.0 key or a current one); unknown keys raise."""
    key = SECTION_ALIASES.get(key, key)
    if key not in SECTIONS:
        raise ModelError(f"unknown section {key!r}")
    return key


# Existing tools reachable from the workspace (no second implementation, spec §18 stage 3)
TOOLS = {
    "files": ("inbox", "context_request"),  # 5.14.0: "Classic prompt & response…" removed (Quick replaced it)
    "versions": ("build_center", "sync_build"),
    "settings": ("export_bundle", "import_bundle", "companion", "classic"),
}
TOOLS["project"] = TOOLS["files"] + TOOLS["versions"] + TOOLS["settings"]  # 5.11.0: one Tools menu
TOOL_LABELS = {
    "inbox": ("Response Inbox…", "صندوق پاسخ‌ها…"),
    "context_request": ("Context request…", "درخواست زمینه…"),
    "build_center": ("Build Center…", "مرکز Build…"),
    "sync_build": ("Sync & Build…", "همگام‌سازی و Build…"),
    "export_bundle": ("Export project for the phone…", "Export project for the phone…"),
    "import_bundle": ("Import project from the phone…", "Import project from the phone…"),
    "companion": ("Mobile Companion…", "همراه موبایل…"),
    "classic": ("Projects window (classic)…", "پنجرهٔ پروژه‌ها (کلاسیک)…"),
}
UI_KEYS = ("ws_section", "ws_inspector", "ws_sidebar", "ws_theme", "ws_seen")


class WorkspaceController:
    def __init__(self, ctl: ProjectsController, *, tools: dict[str, Callable[[], Any]] | None = None,
                 prefs: Any = None) -> None:
        self.ctl = ctl
        self.tools = tools or {}
        # 3.0.0: theme / language / mode are application-wide (aiwb.ui.prefs.AppPrefs) when the
        # workspace is embedded in the main window; the project only keeps its own view state.
        self.prefs = prefs
        if prefs is not None:
            if ctl.lang != prefs.lang:
                ctl.set_language(prefs.lang)
            if ctl.mode != prefs.mode:
                ctl.set_mode(prefs.mode)
        ui = ctl._load_ui()
        try:
            self.section = canonical_section(str(ui.get("ws_section") or "plan"))
        except ModelError:
            self.section = "plan"
        self.inspector_open = ui.get("ws_inspector", True) is not False
        self.sidebar_open = ui.get("ws_sidebar", True) is not False
        self._theme = ui.get("ws_theme") if ui.get("ws_theme") in ("light", "dark") else "light"
        self.selection: tuple[str, str] = ("", "")  # (kind, id)

    # -- language / view preferences (ui.json only; never project state)
    @property
    def lang(self) -> str:
        return self.prefs.lang if self.prefs is not None else self.ctl.lang

    @property
    def theme(self) -> str:
        return self.prefs.theme if self.prefs is not None else self._theme

    @property
    def mode(self) -> str:
        return self.prefs.mode if self.prefs is not None else self.ctl.mode

    @property
    def rtl(self) -> bool:
        return self.lang == "fa"

    def tr(self, pair: tuple[str, str]) -> str:
        return pair[1] if self.lang == "fa" else pair[0]

    def section_label(self, key: str, compact: bool = False) -> str:
        return self.tr((SHORT_LABELS if compact else SECTION_LABELS)[key])

    def set_section(self, key: str) -> None:
        key = canonical_section(key)
        self.section = key
        self.ctl._save_ui(ws_section=key)

    def set_inspector(self, open_: bool) -> None:
        self.inspector_open = bool(open_)
        self.ctl._save_ui(ws_inspector=self.inspector_open)

    def set_sidebar(self, open_: bool) -> None:
        self.sidebar_open = bool(open_)
        self.ctl._save_ui(ws_sidebar=self.sidebar_open)

    def set_theme(self, theme: str) -> None:
        if theme not in ("light", "dark"):
            raise ModelError("theme must be light or dark")
        self._theme = theme
        self.ctl._save_ui(ws_theme=theme)
        if self.prefs is not None:
            self.prefs.set_theme(theme)

    def set_language(self, lang: str) -> None:
        self.ctl.set_language(lang)
        if self.prefs is not None:
            self.prefs.set_lang(lang)

    def set_mode(self, mode: str) -> None:
        self.ctl.set_mode(mode)
        if self.prefs is not None:
            self.prefs.set_mode(mode)

    def select(self, kind: str, ref: str) -> None:
        self.selection = (kind, ref)

    # -- tools
    def tool_items(self, section: str) -> list[tuple[str, str]]:
        return [(k, self.tr(TOOL_LABELS[k])) for k in TOOLS.get(section, ()) if k in self.tools]

    def open_tool(self, key: str) -> Any:
        fn = self.tools.get(key)
        if fn is None:
            raise ModelError(f"tool {key!r} is not available here")
        return fn()

    # -- project bar / footer
    def project_bar(self) -> dict[str, Any]:
        st = self.ctl.state()
        pub = self.ctl.publish_status()
        return {"name": self.ctl.root.name, "goal": str(st["settings"].get("goal", "")),
                "revision": int(st.get("state_revision", 0)), "publish": pub["text"], "publish_state": pub["state"]}

    # -- overview
    def overview(self) -> dict[str, Any]:
        st = self.ctl.state()
        tasks = list(st["tasks"].values())
        counts: dict[str, int] = {}
        for t in tasks:
            counts[t["status"]] = counts.get(t["status"], 0) + 1
        nv = self.ctl.next_action_view() or {"type": "nothing", "summary": i18n.action("nothing", self.lang),
                                             "reference_id": ""}
        return {"goal": str(st["settings"].get("goal", "")), "next": nv,
                "progress": progress(st),
                "counts": counts, "warnings": self.ctl.warning_items()[:5],
                "agents": sum(1 for a in st["agents"].values() if a.get("enabled", True)),
                "accounts": sum(1 for a in st["account_profiles"].values() if a.get("enabled", True)),
                "recent": self.ctl.project.store.ledger.query(page_size=8)["items"]}

    def progress_text(self, pr: dict[str, Any]) -> str:
        if not pr["total"]:
            return self.tr(("No tasks yet", "هنوز Taskی وجود ندارد"))
        if self.lang == "fa":
            return f"{pr['done']} از {pr['total']} Task تأیید شده؛ {pr['percent']}٪ از تعداد Taskها (نه حجم کار)"
        return f"{pr['done']} of {pr['total']} tasks verified; {pr['percent']}% of tasks by count (not of effort)"

    def progress_details(self, pr: dict[str, Any]) -> list[str]:
        """Separate indicators (spec §6.2); the weighted figure only when weights exist, labelled estimated."""
        fa = self.lang == "fa"
        lines = [(f"در انتظار تست/Build: {pr['validation_pending']} · در انتظار بازبینی: {pr['in_review']} · "
                  f"مسدود: {pr['blocked']} · نیازمند تصمیم: {pr['needs_decision']} · در حال انجام: {pr['in_progress']}")
                 if fa else
                 (f"Waiting for test/build: {pr['validation_pending']} · waiting for review: {pr['in_review']} · "
                  f"blocked: {pr['blocked']} · needs decision: {pr['needs_decision']} · in progress: {pr['in_progress']}")]
        if pr.get("excluded"):
            lines.append(f"{pr['excluded']} Task لغو/جایگزین‌شده از مخرج خارج است" if fa
                         else f"{pr['excluded']} cancelled/superseded task(s) excluded from the count")
        if pr.get("weighted"):
            lines.append(f"پیشرفت وزنی (تخمینی، بر اساس وزن‌های شما): {pr['weighted']['percent']}٪" if fa
                         else f"Weighted progress (estimated, from your task weights): {pr['weighted']['percent']}%")
        return lines

    # -- tasks
    def task_rows(self, *, status: str = "", agent_id: str = "", text: str = "") -> list[dict[str, Any]]:
        rows = self.ctl.task_rows()
        st = self.ctl.state()
        for r in rows:
            if r["task_id"] in st["tasks"]:
                ts = task_stage(st, r["task_id"])
                r["stage"], r["stage_text"], r["user_action"] = ts["stage"], stage_label(ts["stage"], self.lang), ts["user_action"]
        needle = text.lower().strip()
        return [r for r in rows if (not status or r["status"] == status) and (not agent_id or r["owner"] == agent_id)
                and (not needle or needle in (r["task_id"] + " " + r["title"]).lower())]

    # -- team (2.3.0: registry view; planner/dashboard extend this in 2.4/2.6)
    def team_rows(self) -> list[dict[str, Any]]:
        st = self.ctl.state()
        rows = []
        for a in sorted(st["agents"].values(), key=lambda a: a["agent_id"]):
            b = current_binding(st, a["agent_id"])
            acc = st["account_profiles"].get(b["account_profile_id"]) if b else None
            owned = [t for t in st["tasks"].values() if t.get("owner_agent_id") == a["agent_id"]
                     and t["status"] not in ("done", "cancelled", "superseded")]
            ready = binding_readiness(st, a["agent_id"])
            rows.append({"agent_id": a["agent_id"], "name": a["name"], "role": a["role"],
                         "enabled": a.get("enabled", True), "account": acc["display_name"] if acc else "",
                         "chat": (b or {}).get("chat_name", ""), "binding_id": (b or {}).get("chat_binding_id", ""),
                         "open_tasks": len(owned), "readiness": ready["code"], "readiness_text": ready["message"],
                         "model_label": a.get("preferred_model_label", "")})
        return rows

    def account_rows(self) -> list[dict[str, Any]]:
        st = self.ctl.state()
        uses: dict[str, int] = {}
        for b in st["chat_bindings"].values():
            if b.get("enabled", True):
                uses[b["account_profile_id"]] = uses.get(b["account_profile_id"], 0) + 1
        return [{**a, "bindings": uses.get(a["account_profile_id"], 0)} for a in
                sorted(st["account_profiles"].values(), key=lambda a: a["account_profile_id"])]

    def add_account(self, data: dict[str, Any]) -> dict[str, Any]:
        out = self.ctl.project.resources.add_account(data)
        self.ctl._dirty("account profile")
        return out

    def set_account_enabled(self, account_id: str, enabled: bool) -> dict[str, Any]:
        return self.ctl.project.resources.set_account_enabled(account_id, enabled)

    def bind_chat(self, agent_id: str, account_id: str, chat_name: str = "", link: str = "", note: str = "") -> dict[str, Any]:
        return self.ctl.project.resources.bind_chat(agent_id, account_id, chat_name=chat_name, link=link, note=note)

    def update_account(self, account_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return self.ctl.project.resources.update_account(account_id, changes)

    def update_binding(self, binding_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return self.ctl.project.resources.update_binding(binding_id, changes)

    # -- team planner (2.4.0, spec §7, Gate A)
    def team_settings(self) -> dict[str, Any]:
        return self.ctl.team_settings()

    def set_team_settings(self, **changes: Any) -> dict[str, Any]:
        return self.ctl.set_team_settings(**changes)

    def pm_choices(self) -> list[tuple[str, str]]:
        st = self.ctl.state()
        return [(a["agent_id"], a["name"]) for a in sorted(st["agents"].values(), key=lambda a: a["agent_id"])
                if a["role"] == "project_manager" and a.get("enabled", True)]

    def plan_team(self, project: dict[str, Any]) -> str:
        return self.ctl.team_planning_prompt(project)

    def pending_proposals(self) -> list[dict[str, Any]]:
        return self.ctl.project.proposals.list("pending")

    def proposal_review(self, proposal_id: str) -> dict[str, Any]:
        """Preview model for Team/Plan Proposal review (spec §7.5). Pure read."""
        p = self.ctl.project.proposals.get(proposal_id)
        if p is None:
            raise ModelError(f"proposal {proposal_id} does not exist")
        st = self.ctl.state()
        c = p.get("team_counts") or {}
        team = p.get("team") or {}
        pm_txt = {True: self.tr(("manager counted", "مدیر پروژه شمرده شده")),
                  False: self.tr(("manager not counted", "مدیر پروژه شمرده نشده")),
                  None: self.tr(("manager count not stated", "شمارش مدیر پروژه نامشخص"))}[team.get("pm_counted")]
        head = []
        if p.get("is_team"):
            head.append(self.tr(("Team: ", "تیم: ")) + f"{c.get('agents_now', 0)} → {c.get('agents_after', 0)} "
                        + self.tr(("agents", "Agent")) + f" ({pm_txt})")
            if c.get("declared_total") is not None:
                head.append(self.tr(("Manager says: ", "ادعای مدیر: ")) + f"{c['declared_total']} "
                            + self.tr(("in total", "کل")) + (f", {c['declared_workers']} " + self.tr(("extra workers", "کارگر اضافه"))
                                                             if c.get("declared_workers") is not None else ""))
            head.append(self.tr(("Registered accounts: ", "اکانت‌های ثبت‌شده: ")) + str(c.get("accounts", 0)) + " · "
                        + self.tr(("parallel chats you follow: ", "چت هم‌زمان: ")) + str(c.get("max_parallel_chats", 1)))
            if team.get("size_rationale"):
                head.append(self.tr(("Why this size: ", "دلیل اندازه: ")) + team["size_rationale"])
            if team.get("simpler_alternative"):
                head.append(self.tr(("Simpler option: ", "گزینهٔ ساده‌تر: ")) + team["simpler_alternative"])
        rows = []
        for op in p["operations"]:
            raw = op.get("raw", {})
            label = raw.get("title") or raw.get("name") or raw.get("agent_id") or raw.get("task_id") or raw.get("description", "")
            detail = []
            if op["operation"] in ("create_task", "split_task"):
                detail = [f"owner {raw.get('owner_agent_id') or raw.get('owner_role') or '?'}",
                          f"scope {', '.join((raw.get('scope') or {}).get('include', []) or []) or '?'}",
                          f"{len(raw.get('acceptance_criteria') or [])} criteria"]
                if raw.get("parallel_group"):
                    detail.append(f"group {raw['parallel_group']}")
                if raw.get("depends_on_refs"):
                    detail.append("after " + ", ".join(raw["depends_on_refs"]))
            if op["operation"] == "assign_account":
                acc = st["account_profiles"].get(raw.get("account_profile_id", ""), {})
                detail = [f"→ {acc.get('display_name') or raw.get('account_profile_id')}"]
            rows.append({"index": op["index"], "operation": op["operation"], "label": str(label)[:120],
                         "detail": " · ".join(detail), "valid": op["valid"], "problem": op.get("problem", ""),
                         "decision": op.get("decision", "pending")})
        issues = list(p.get("team_issues") or [])
        if p.get("stale"):
            issues.insert(0, {"level": "warning", "code": "stale", "op_index": None,
                              "message": "written for an older state; tasks changed: " + ", ".join(p["stale_task_ids"])})
        return {"proposal_id": proposal_id, "summary": p.get("summary", ""), "head": head, "rows": rows,
                "issues": issues, "risks": p.get("risks", []), "questions": p.get("questions_for_user", []),
                "assumptions": p.get("assumptions", []), "stale": p.get("stale", False), "status": p["status"],
                "valid_indices": [r["index"] for r in rows if r["valid"]]}

    def preview_proposal(self, proposal_id: str, indices: list[int]) -> dict[str, Any]:
        return self.ctl.project.proposals.preview(proposal_id, indices)

    def accept_proposal(self, proposal_id: str, indices: list[int], confirm_stale: bool = False) -> dict[str, Any]:
        return self.ctl.accept_proposal(proposal_id, indices, confirm_stale=confirm_stale)

    def reject_proposal(self, proposal_id: str) -> dict[str, Any]:
        return self.ctl.accept_proposal(proposal_id, [])

    def proposal_revision_prompt(self, proposal_id: str, note: str = "") -> str:
        return self.ctl.proposal_revision_prompt(proposal_id, note)

    def route_answer(self, text: str) -> Any:
        return self.ctl.route_answer(text)

    # -- team dashboard & needs-attention queue (2.6.0, spec §10, Gate C)
    def _publish_paused(self) -> str:
        pub = self.ctl.publisher
        if pub is None:
            return ""
        try:
            return str(pub.queue().get("paused") or "")
        except Exception:  # noqa: BLE001 - dashboard never fails because of publishing
            return ""

    def seen_keys(self) -> set[str]:
        return set(self.ctl._load_ui().get("ws_seen") or [])

    def mark_seen(self, keys: list[str]) -> set[str]:
        """'Mark as read' for queue items: user preference in app data; history is never removed."""
        cur = self.seen_keys() | set(keys)
        self.ctl._save_ui(ws_seen=sorted(cur)[-500:])
        return cur

    def clear_seen(self) -> None:
        self.ctl._save_ui(ws_seen=[])

    def attention(self, *, include_info: bool = False, hide_seen: bool = False, collapse: bool = True,
                  agent_id: str = "") -> list[dict[str, Any]]:
        items = attention_queue(self.ctl.state(), lang=self.lang, publish_paused=self._publish_paused(),
                                include_info=include_info, seen=self.seen_keys())
        if agent_id:
            items = [i for i in items if i["agent_id"] == agent_id]
        if hide_seen:
            items = [i for i in items if not i["seen"]]
        return summarize(items) if collapse else items

    def dashboard(self, *, role: str = "", text: str = "", attention_only: bool = False) -> dict[str, Any]:
        ov = team_overview(self.ctl.state(), lang=self.lang)
        ov["agents"] = filter_agents(ov["agents"], role=role, text=text, attention_only=attention_only)
        ov.pop("queue", None)
        return ov

    def attention_text(self, item: dict[str, Any]) -> str:
        if item["kind"] == "more":
            return self.tr(("… and ", "… و ")) + item["why"].split()[0] + self.tr((" more in this group", " مورد دیگر در این گروه"))
        who = f" · {item['agent_id']}" if item["agent_id"] else ""
        return f"{item['ref']}{who} — {item['ask']} ({self.tr(('why: ', 'چرا: '))}{item['why']})"

    def open_attention(self, item: dict[str, Any]) -> tuple[str, str]:
        """Where a queue item leads: (section, selection). Selection reuses the Inspector (no second logic)."""
        if item.get("task_id"):
            self.select("task", item["task_id"])
            return ("tasks", item["task_id"])
        if item["kind"] == "proposal":
            return ("team", item["ref"])
        if item["kind"] == "decision":
            return ("tasks", item["ref"])
        if item["kind"] == "publish":
            return ("settings", "")
        return (self.section, "")

    # -- timeline (2.3.0: ledger list; lanes/milestones in 2.5.0)
    def timeline_page(self, page: int = 0, **filters: Any) -> dict[str, Any]:
        return self.ctl.project.store.ledger.query(page=page, **filters)

    def timeline_lanes(self, limit: int = 400) -> dict[str, list[dict[str, Any]]]:
        """Per-agent lanes, oldest first (spec §5.4). A lane is a work stream, not a git branch."""
        recs = self.ctl.project.store.ledger.all()[-limit:]
        return lanes(recs, self.ctl.state())

    def timeline_model(self, limit: int = 5000) -> dict[str, Any]:
        """Drawable model for the visual timeline (3.6.0): the latest ``limit`` ledger events + versions."""
        from ..ui.timeline_canvas import build_model
        return build_model(self.ctl.project.store.ledger.all()[-limit:], self.ctl.state())

    def planned(self) -> list[dict[str, Any]]:
        return planned_items(self.ctl.state())

    def milestone_rows(self) -> list[dict[str, Any]]:
        st = self.ctl.state()
        out = []
        for m in self.ctl.project.timeline.milestones():
            pr = progress(st, task_ids=m["task_ids"])
            out.append({**m, "progress_text": f"{pr['done']}/{pr['total']}"})
        return out

    def version_rows(self) -> list[dict[str, Any]]:
        labels = {"proposed": ("proposed", "پیشنهادی"), "local": ("local (commit)", "محلی (Commit)"),
                  "tagged": ("tag created", "Tag ساخته شد"), "released": ("released", "منتشرشده"),
                  "withdrawn": ("withdrawn", "کنار گذاشته شد")}
        return [{**v, "status_text": self.tr(labels.get(v["status"], (v["status"], v["status"])))}
                for v in self.ctl.project.timeline.versions()]

    def create_milestone(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.ctl.project.timeline.create_milestone(data)

    def accept_milestone(self, milestone_id: str, force: bool = False) -> dict[str, Any]:
        return self.ctl.project.timeline.accept_milestone(milestone_id, force=force)

    def propose_version(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.ctl.project.timeline.propose_version(data)

    def advance_version(self, version_id: str, status: str, **facts: Any) -> dict[str, Any]:
        return self.ctl.project.timeline.advance_version(version_id, status, **facts)

    def event_text(self, rec: dict[str, Any]) -> str:
        refs = rec.get("refs", {})
        ref = refs.get("task_id") or refs.get("handoff_id") or refs.get("proposal_id") or refs.get("decision_id") \
            or refs.get("evidence_id") or refs.get("attempt_id") or refs.get("account_profile_id") \
            or refs.get("chat_binding_id") or refs.get("milestone_id") or refs.get("version_id") or ""
        change = ""
        if rec.get("before") or rec.get("after", {}).get("new"):
            change = f"{rec.get('before', {}).get('status', '')} → {rec.get('after', {}).get('new', '')}".strip()
        elif rec.get("after", {}).get("status"):
            change = str(rec["after"]["status"])
        when = rec.get("timestamp_utc") or self.tr(("time unknown (legacy)", "زمان نامعلوم (قدیمی)"))
        legacy = " · " + self.tr(("imported history", "تاریخچهٔ واردشده")) if rec.get("legacy_import") else ""
        return f"{when} · {rec['event_type']} {ref} {change}".rstrip() + legacy

    # -- inspector
    def inspector(self) -> dict[str, Any]:
        kind, ref = self.selection
        if kind == "task" and ref:
            text = self.ctl.task_details(ref)
            if not text:
                return {"title": "", "text": "", "actions": []}
            t = self.ctl.project.tasks.get(ref) or {}
            acts = []
            if t.get("status") in ("ready", "in_progress", "blocked", "needs_decision"):
                acts.append(("start_task", self.tr(("Prepare prompt for this task", "آماده‌سازی پرامپت این Task"))))
            if t.get("status") in ("in_review", "validation_pending"):
                acts += [("approve_review", self.tr(("Approve review", "تأیید بازبینی"))),
                         ("reject_review", self.tr(("Reject review", "رد بازبینی")))]
            if t.get("status") not in ("cancelled", "superseded"):
                acts.append(("change_request", self.tr(("Request a change…", "درخواست تغییر…"))))
            ts = task_stage(self.ctl.state(), ref)
            text += "\n\n" + self.tr(("Workflow: ", "گردش کار: ")) + stage_label(ts["stage"], self.lang) + f" ({ts['why']})"
            if ts["stage"] in ("prompt_prepared", "prompt_copied") and ts["handoff_id"]:
                acts.append(("confirm_sent", self.tr(("I sent this prompt", "این پرامپت را ارسال کردم"))))
            owner = t.get("owner_agent_id", "")
            if owner:
                r = binding_readiness(self.ctl.state(), owner)
                text += "\n\n" + self.tr(("Account / chat: ", "اکانت / چت: ")) + r["message"]
            return {"title": f"{ref} · {t.get('title', '')}", "text": text, "actions": acts}
        if kind == "agent" and ref:
            row = next((r for r in self.team_rows() if r["agent_id"] == ref), None)
            if not row:
                return {"title": "", "text": "", "actions": []}
            lines = [f"{row['name']} ({row['role']})", self.tr(("Account / chat: ", "اکانت / چت: ")) + row["readiness_text"],
                     self.tr(("Open tasks: ", "Taskهای باز: ")) + str(row["open_tasks"])]
            if row["model_label"]:
                lines.append(self.tr(("Model label (legacy): ", "برچسب مدل (قدیمی): ")) + row["model_label"])
            return {"title": row["name"], "text": "\n".join(lines),
                    "actions": [("bind_chat", self.tr(("Choose account / chat…", "انتخاب اکانت / چت…")))]}
        if kind == "event" and ref:
            rec = next((r for r in self.ctl.project.store.ledger.all() if r["event_id"] == ref), None)
            if not rec:
                return {"title": "", "text": "", "actions": []}
            lines = [self.event_text(rec), f"{self.tr(('Source', 'منبع'))}: {rec['source']} · "
                     f"{self.tr(('time', 'زمان'))}: {rec['time_source']} · revision {rec['state_revision']}"]
            lines += [f"{k}: {v}" for k, v in rec.get("refs", {}).items()]
            acts = [("open_task", self.tr(("Open task", "بازکردن Task")))] if rec.get("refs", {}).get("task_id") else []
            return {"title": rec["event_type"], "text": "\n".join(lines), "actions": acts, "task_id": rec["refs"].get("task_id", "")}
        return {"title": self.tr(("Nothing selected", "چیزی انتخاب نشده")),
                "text": self.tr(("Select a task, agent or event to see details and the actions that apply to it.",
                                 "یک Task، Agent یا رویداد را انتخاب کنید تا جزئیات و اقدام‌های مجاز آن نمایش داده شود.")),
                "actions": []}

    ROUTE_LABELS = {"revise": ("Change this task (new revision)", "اصلاح همین Task (Revision جدید)"),
                    "new_task": ("New task", "Task جدید"),
                    "replan": ("Ask the project manager to re-plan", "درخواست Re-plan از مدیر پروژه")}

    def suggest_change(self, task_id: str, request: str) -> dict[str, Any]:
        sug = self.ctl.suggest_change_route(task_id, request)
        sug["label"] = self.tr(self.ROUTE_LABELS[sug["route"]])
        sug["choices"] = [(k, self.tr(v)) for k, v in self.ROUTE_LABELS.items()]
        return sug

    def apply_change(self, task_id: str, route: str, request: str, title: str = "") -> dict[str, Any]:
        return self.ctl.apply_change_route(task_id, route, request, title)

    def start_warning(self, task_id: str) -> str:
        return self.ctl.start_warning(task_id)

    # -- guided loop (3.5.0)
    def guide(self) -> Any:
        from ..v2.guide import Guide
        return Guide(self.ctl)

    def guide_steps(self) -> list[dict[str, Any]]:
        return self.guide().steps()

    def flow_position(self) -> dict[str, Any]:
        """Where the project is in the owner's flowchart (roadmap 4.0.0), for the phase bar."""
        return self.guide().flow()

    def flow_text(self) -> str:
        """5.13.0 (owner audit B4): where the project is, in the user's words — no flowchart node, no "wave"."""
        f = self.flow_position()
        who = {"app": "Workbench", "user": "you", "github": "GitHub"}[f["kind"]]
        text = f"Now: {f['title']} ({who})" + (f" · round {f['cycle']}" if f["cycle"] > 1 else "")
        from aiwb.v2.waves import dispatch, waves
        st = self.ctl.state()
        w, d = waves(st), dispatch(st)
        if st.get("tasks"):
            text += f" · {len(d['active'])} of {d['limit']} chats busy"
            if w["cycle"]:
                text += f" · tasks wait for each other: {', '.join(w['cycle'][:4])}"
        return text

    def guide_queues(self) -> dict[str, list[dict[str, Any]]]:
        return self.guide().queues()

    def guide_perform(self, key: str, action: str, **inputs: Any) -> dict[str, Any]:
        return self.guide().perform(key, action, **inputs)

    def run_action(self, action: str, ref: str = "") -> Any:
        """Inspector / next-action buttons; every one delegates to the existing controller."""
        kind, sel = self.selection
        ref = ref or sel
        if action == "start_task":
            return self.ctl.start_task(ref)
        if action == "confirm_sent":
            ts = task_stage(self.ctl.state(), ref)
            if not ts["handoff_id"]:
                raise ModelError("there is no prepared prompt for this task")
            return self.ctl.confirm_sent(ts["handoff_id"])
        if action == "approve_review":
            return self.ctl.review_task(ref, True)
        if action == "reject_review":
            return self.ctl.review_task(ref, False)
        if action == "open_task":
            rec = self.inspector()
            self.select("task", rec.get("task_id", ""))
            return self.selection
        raise ModelError(f"unknown action {action!r}")
