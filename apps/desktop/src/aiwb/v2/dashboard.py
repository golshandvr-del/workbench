"""Team Operations Dashboard and Needs Attention queue (roadmap 2.6.0 / stage 7, spec §10, Gate C).

Pure read models over the shared store + workflow projection; nothing here writes
except the per-user "seen" marks, which live in app data (never in project state,
never removing history).

Priority (spec §10.3) is a fixed, explainable rank — no opaque scores:

1. blocking / needs a human decision
2. stale answers or answers for the wrong task
3. broken / partial answers that have a repair path
4. handoff / proposal waiting for review
5. task ready to start that needs a prompt or an owner
6. pending validation / publish
7. information

Within a rank the order is: older first (by reference id), so nothing jumps around.
"""
from __future__ import annotations

from typing import Any

from .resources import binding_readiness, current_binding
from .workflow import stage_label, task_stage

RANKS = {
    1: ("Blocking or needs your decision", "مسدودکننده یا نیازمند تصمیم شما"),
    2: ("Stale or mismatched answer", "پاسخ قدیمی یا نامرتبط"),
    3: ("Broken or partial answer — repair", "پاسخ خراب یا ناقص — اصلاح"),
    4: ("Waiting for your review", "در انتظار بازبینی شما"),
    5: ("Ready to start", "آمادهٔ شروع"),
    6: ("Validation or publish pending", "اعتبارسنجی یا انتشار معوق"),
    7: ("Information", "اطلاع"),
}
STAGE_RANK = {"needs_decision": 1, "blocked": 1, "stale": 2, "parse_failed": 3, "partial_response": 3,
              "repair_ready": 3, "context_request_pending": 3, "needs_user_review": 4, "ready_to_prepare": 5,
              "prompt_prepared": 5, "validation_pending": 6, "context_prepared": 7, "prompt_copied": 7,
              "waiting_for_response": 7, "response_received": 4}
# What the user must do, per stage (plain words)
ASK = {
    "needs_decision": ("Decide", "تصمیم بگیرید"), "blocked": ("Remove the blocker", "مانع را برطرف کنید"),
    "stale": ("Reconcile or discard the old answer", "پاسخ قدیمی را تطبیق دهید یا کنار بگذارید"),
    "parse_failed": ("Prepare a repair prompt", "پرامپت اصلاح بسازید"),
    "partial_response": ("Ask for the missing items", "موارد گم‌شده را درخواست کنید"),
    "repair_ready": ("Copy the repair prompt to the chat", "پرامپت اصلاح را در چت کپی کنید"),
    "context_request_pending": ("Prepare the context pack", "بستهٔ زمینه را آماده کنید"),
    "needs_user_review": ("Review the delivery", "تحویل را بازبینی کنید"),
    "response_received": ("Check the stored answer", "پاسخ ذخیره‌شده را بررسی کنید"),
    "ready_to_prepare": ("Prepare the prompt", "پرامپت را آماده کنید"),
    "prompt_prepared": ("Copy the prompt", "پرامپت را کپی کنید"),
    "validation_pending": ("Run tests / build", "تست / Build را اجرا کنید"),
    "context_prepared": ("Paste the context, then mark it sent", "زمینه را Paste کنید و ارسال را ثبت کنید"),
    "prompt_copied": ("Paste it in the chat, then confirm sending", "در چت Paste کنید و ارسال را تأیید کنید"),
    "waiting_for_response": ("Paste the answer when you have it", "وقتی پاسخ را گرفتید Paste کنید"),
}
QUICK = {  # contextual quick actions that are valid for the stage
    "needs_decision": "open_task", "blocked": "open_task", "stale": "open_task", "parse_failed": "open_inbox",
    "partial_response": "open_task", "repair_ready": "open_tasks", "context_request_pending": "open_context",
    "needs_user_review": "open_task", "response_received": "open_inbox", "ready_to_prepare": "start_task",
    "prompt_prepared": "open_tasks", "validation_pending": "open_build", "context_prepared": "open_context",
    "prompt_copied": "confirm_sent", "waiting_for_response": "open_tasks",
}


def _tr(pair: tuple[str, str], lang: str) -> str:
    return pair[1] if lang == "fa" else pair[0]


def attention_queue(state: dict[str, Any], *, lang: str = "en", publish_paused: str = "",
                    include_info: bool = False, seen: set[str] | None = None) -> list[dict[str, Any]]:
    """Deterministic, explainable queue. Each item: key, rank, why, ask, ref, kind, agent_id, action, seen."""
    seen = seen or set()
    items: list[dict[str, Any]] = []

    def add(rank: int, kind: str, ref: str, why: str, ask: str, agent: str = "", action: str = "open_task",
            task_id: str = "", trace: dict[str, str] | None = None) -> None:
        key = f"{kind}:{ref}:{rank}"
        items.append({"key": key, "rank": rank, "rank_text": _tr(RANKS[rank], lang), "kind": kind, "ref": ref,
                      "task_id": task_id or (ref if kind == "task" else ""), "why": why, "ask": ask,
                      "agent_id": agent, "action": action, "seen": key in seen, "trace": trace or {}})

    if publish_paused:
        add(1, "publish", "publish", f"publishing paused: {publish_paused}",
            _tr(("Fix the GitHub connection or resume", "اتصال GitHub را اصلاح یا ادامه دهید"), lang), action="open_settings")
    for d in sorted(state["decisions"].values(), key=lambda d: d["decision_id"]):
        if d["status"] == "proposed":
            add(1, "decision", d["decision_id"], f"open decision: {d['title']}", _tr(ASK["needs_decision"], lang),
                action="open_decision")
    for p in sorted(state["proposals"].values(), key=lambda p: p["proposal_id"]):
        if p["status"] == "pending":
            r = 2 if p.get("stale") else 4
            why = ("proposal written for an older state" if p.get("stale") else "manager proposal waiting") + \
                f" ({len(p['operations'])} change(s))"
            add(r, "proposal", p["proposal_id"], why, _tr(("Review the proposal", "پیشنهاد را بازبینی کنید"), lang),
                action="open_proposal")
    for tid in sorted(state["tasks"]):
        t = state["tasks"][tid]
        ts = task_stage(state, tid)
        stage = ts["stage"]
        rank = STAGE_RANK.get(stage)
        if rank is None or (rank == 7 and not include_info):
            continue
        agent = ts["agent_id"]
        why = f"{stage_label(stage, 'en')} — {ts['why']}"
        if stage == "ready_to_prepare":
            if not t.get("owner_agent_id"):
                why += "; no owner yet"
            elif not binding_readiness(state, agent).get("ok"):
                why += "; no account/chat chosen for the agent"
        add(rank, "task", tid, why, _tr(ASK.get(stage, ("Open", "باز کردن")), lang), agent=agent,
            action=QUICK.get(stage, "open_task"),
            trace={"attempt_id": ts["attempt_id"], "handoff_id": ts["handoff_id"],
                   "response_id": (state["handoffs"].get(ts["handoff_id"]) or {}).get("response_id", "")})
    items.sort(key=lambda i: (i["rank"], i["kind"] != "decision", i["ref"]))
    return items


def summarize(items: list[dict[str, Any]], *, max_per_rank: int = 5) -> list[dict[str, Any]]:
    """Collapse long ranks: show the first ``max_per_rank`` and one 'n more' row (no notification storm)."""
    out: list[dict[str, Any]] = []
    by: dict[int, list[dict[str, Any]]] = {}
    for i in items:
        by.setdefault(i["rank"], []).append(i)
    for rank in sorted(by):
        group = by[rank]
        out += group[:max_per_rank]
        if len(group) > max_per_rank:
            out.append({"key": f"more:{rank}", "rank": rank, "rank_text": group[0]["rank_text"], "kind": "more",
                        "ref": "", "task_id": "", "why": f"{len(group) - max_per_rank} more", "ask": "",
                        "agent_id": "", "action": "", "seen": False, "trace": {}, "hidden": group[max_per_rank:]})
    return out


def team_overview(state: dict[str, Any], *, lang: str = "en") -> dict[str, Any]:
    """Agents with role, binding, owned tasks, last event and attention count; project status bar counts."""
    stages = {tid: task_stage(state, tid) for tid in state["tasks"]}
    queue = attention_queue(state, lang=lang)
    per_agent: dict[str, int] = {}
    for i in queue:
        if i["agent_id"]:
            per_agent[i["agent_id"]] = per_agent.get(i["agent_id"], 0) + 1
    agents = []
    for a in sorted(state["agents"].values(), key=lambda a: (a["role"] != "project_manager", a["role"], a["agent_id"])):
        if not a.get("enabled", True):
            continue
        b = current_binding(state, a["agent_id"])
        acc = state["account_profiles"].get(b["account_profile_id"]) if b else None
        owned = [tid for tid, s in stages.items() if s["agent_id"] == a["agent_id"]
                 and state["tasks"][tid]["status"] not in ("done", "cancelled", "superseded")]
        current = sorted((stages[t] for t in owned), key=lambda s: STAGE_RANK.get(s["stage"], 9))
        agents.append({"agent_id": a["agent_id"], "name": a["name"], "role": a["role"],
                       "account": (acc or {}).get("display_name", ""), "chat": (b or {}).get("chat_name", ""),
                       "open_tasks": len(owned), "attention": per_agent.get(a["agent_id"], 0),
                       "stage": current[0]["stage"] if current else "",
                       "stage_text": stage_label(current[0]["stage"], lang) if current else "",
                       "task_ids": owned})
    counts = {"verified": 0, "working": 0, "waiting_answer": 0, "blocked": 0, "needs_action": len(queue)}
    for s in stages.values():
        if s["stage"] == "verified_done":
            counts["verified"] += 1
        elif s["stage"] in ("blocked", "needs_decision"):
            counts["blocked"] += 1
        elif s["stage"] in ("prompt_copied", "waiting_for_response"):
            counts["waiting_answer"] += 1
        elif s["task_status"] == "in_progress":
            counts["working"] += 1
    density = "cards" if len(agents) <= 3 else ("grouped" if len(agents) <= 6 else "compact")
    return {"agents": agents, "counts": counts, "density": density, "queue": queue}


def filter_agents(agents: list[dict[str, Any]], *, role: str = "", text: str = "", attention_only: bool = False
                  ) -> list[dict[str, Any]]:
    n = text.lower().strip()
    return [a for a in agents if (not role or a["role"] == role) and (not attention_only or a["attention"])
            and (not n or n in f"{a['agent_id']} {a['name']} {a['account']} {a['chat']}".lower())]
