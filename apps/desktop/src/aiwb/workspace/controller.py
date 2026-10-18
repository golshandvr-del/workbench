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
from ..v2.resources import binding_readiness, current_binding

SECTIONS = ("overview", "timeline", "tasks", "team", "files", "versions", "settings")
SECTION_LABELS = {
    "overview": ("Overview", "نمای کلی"), "timeline": ("Timeline", "تاریخچه"), "tasks": ("Tasks", "وظایف"),
    "team": ("Team", "تیم AI"), "files": ("Files & Context", "فایل‌ها و زمینه"),
    "versions": ("Versions & Builds", "نسخه‌ها و ساخت‌ها"), "settings": ("Settings", "تنظیمات"),
}
SHORT_LABELS = {"overview": ("Home", "خانه"), "timeline": ("Time", "زمان"), "tasks": ("Tasks", "وظایف"),
                "team": ("Team", "تیم"), "files": ("Files", "فایل"), "versions": ("Ver.", "نسخه"),
                "settings": ("Set.", "تنظیم")}
# Existing tools reachable from the workspace (no second implementation, spec §18 stage 3)
TOOLS = {
    "files": ("response", "inbox", "context_request"),
    "versions": ("build_center", "sync_build"),
    "settings": ("companion", "classic"),
}
TOOL_LABELS = {
    "response": ("Classic prompt & response…", "پرامپت و پاسخ کلاسیک…"),
    "inbox": ("Response Inbox…", "صندوق پاسخ‌ها…"),
    "context_request": ("Context request…", "درخواست زمینه…"),
    "build_center": ("Build Center…", "مرکز Build…"),
    "sync_build": ("Sync & Build…", "همگام‌سازی و Build…"),
    "companion": ("Mobile Companion…", "همراه موبایل…"),
    "classic": ("Projects window (classic)…", "پنجرهٔ پروژه‌ها (کلاسیک)…"),
}
UI_KEYS = ("ws_section", "ws_inspector", "ws_sidebar", "ws_theme")


class WorkspaceController:
    def __init__(self, ctl: ProjectsController, *, tools: dict[str, Callable[[], Any]] | None = None) -> None:
        self.ctl = ctl
        self.tools = tools or {}
        ui = ctl._load_ui()
        self.section = ui.get("ws_section") if ui.get("ws_section") in SECTIONS else "overview"
        self.inspector_open = ui.get("ws_inspector", True) is not False
        self.sidebar_open = ui.get("ws_sidebar", True) is not False
        self.theme = ui.get("ws_theme") if ui.get("ws_theme") in ("light", "dark") else "light"
        self.selection: tuple[str, str] = ("", "")  # (kind, id)

    # -- language / view preferences (ui.json only; never project state)
    @property
    def lang(self) -> str:
        return self.ctl.lang

    @property
    def rtl(self) -> bool:
        return self.ctl.lang == "fa"

    def tr(self, pair: tuple[str, str]) -> str:
        return pair[1] if self.lang == "fa" else pair[0]

    def section_label(self, key: str, compact: bool = False) -> str:
        return self.tr((SHORT_LABELS if compact else SECTION_LABELS)[key])

    def set_section(self, key: str) -> None:
        if key not in SECTIONS:
            raise ModelError(f"unknown section {key!r}")
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
        self.theme = theme
        self.ctl._save_ui(ws_theme=theme)

    def set_language(self, lang: str) -> None:
        self.ctl.set_language(lang)

    def set_mode(self, mode: str) -> None:
        self.ctl.set_mode(mode)

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
        in_scope = [t for t in tasks if t["status"] not in ("cancelled", "superseded")]
        done = sum(1 for t in in_scope if t["status"] == "done")
        nv = self.ctl.next_action_view() or {"type": "nothing", "summary": i18n.action("nothing", self.lang),
                                             "reference_id": ""}
        return {"goal": str(st["settings"].get("goal", "")), "next": nv,
                "progress": {"done": done, "total": len(in_scope),
                             "percent": round(100 * done / len(in_scope)) if in_scope else 0},
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

    # -- tasks
    def task_rows(self, *, status: str = "", agent_id: str = "", text: str = "") -> list[dict[str, Any]]:
        rows = self.ctl.task_rows()
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

    # -- timeline (2.3.0: ledger list; lanes/milestones in 2.5.0)
    def timeline_page(self, page: int = 0, **filters: Any) -> dict[str, Any]:
        return self.ctl.project.store.ledger.query(page=page, **filters)

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

    def run_action(self, action: str, ref: str = "") -> Any:
        """Inspector / next-action buttons; every one delegates to the existing controller."""
        kind, sel = self.selection
        ref = ref or sel
        if action == "start_task":
            return self.ctl.start_task(ref)
        if action == "approve_review":
            return self.ctl.review_task(ref, True)
        if action == "reject_review":
            return self.ctl.review_task(ref, False)
        if action == "open_task":
            rec = self.inspector()
            self.select("task", rec.get("task_id", ""))
            return self.selection
        raise ModelError(f"unknown action {action!r}")
