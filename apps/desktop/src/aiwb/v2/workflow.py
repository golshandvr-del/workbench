"""Manual workflow tracking (roadmap 2.5.0 / stage 5, spec §9, Gate B).

The conceptual workflow stages of spec §9.1 are a *projection* over the existing
task / attempt / handoff state machines plus a few explicit user facts; no new
status is added to the central machines (spec §9.1, last paragraph).

User facts recorded here (each is a self-declaration and reported as such):

* ``prompt_copied``        — the prompt was put on the clipboard (NOT sent);
* ``user_confirmed_sent``  — the user says they pasted it into the chat; the
  timestamp is the time of the confirmation, not of the real send (§9.2);
* ``context_prepared`` / ``context_marked_sent`` — a context pack exists vs. the
  user says they pasted it.

Workbench never claims a model is "working": the furthest it says is
"waiting for you to paste the answer".
"""
from __future__ import annotations

from typing import Any

from .models import ModelError, now_utc
from .resources import binding_readiness, current_binding
from .store import ProjectStore, emit, require

# Ordered conceptual stages (spec §9.1). Labels are plain words; nothing implies model activity.
STAGES = {
    "planned": ("Planned", "برنامه‌ریزی‌شده"),
    "ready_to_prepare": ("Ready — prepare the prompt", "آماده — پرامپت را بسازید"),
    "prompt_prepared": ("Prompt prepared, not copied", "پرامپت ساخته شد، کپی نشده"),
    "prompt_copied": ("Copied — not confirmed as sent", "کپی شد — ارسال تأیید نشده"),
    "waiting_for_response": ("You confirmed sending — paste the answer when you have it",
                             "ارسال را تأیید کردید — پاسخ را وقتی گرفتید Paste کنید"),
    "response_received": ("Answer received", "پاسخ دریافت شد"),
    "parse_failed": ("Answer could not be read — repair needed", "پاسخ خوانده نشد — اصلاح لازم است"),
    "partial_response": ("Partial answer — some items missing", "پاسخ ناقص — بخشی گم شده"),
    "needs_user_review": ("Waiting for your review", "در انتظار بازبینی شما"),
    "repair_ready": ("Repair prompt prepared", "پرامپت اصلاح آماده است"),
    "context_request_pending": ("Model asked for more context", "مدل زمینهٔ بیشتر خواسته"),
    "context_prepared": ("Context prepared — not sent", "زمینه آماده شد — ارسال نشده"),
    "blocked": ("Blocked", "مسدود"),
    "needs_decision": ("Needs your decision", "نیازمند تصمیم شما"),
    "stale": ("Answer is for an older attempt — reconcile", "پاسخ برای تلاش قدیمی است — تطبیق لازم"),
    "validation_pending": ("Accepted — validation pending", "پذیرفته شد — در انتظار اعتبارسنجی"),
    "verified_done": ("Done (verified)", "انجام شد (تأییدشده)"),
    "rejected": ("Rejected", "رد شد"),
    "abandoned": ("Cancelled / abandoned", "لغو / کنار گذاشته شد"),
}
# Stages where the next step is the user's (used by the dashboard; 2.6.0)
USER_ACTION_STAGES = ("ready_to_prepare", "prompt_prepared", "prompt_copied", "waiting_for_response", "parse_failed",
                      "partial_response", "needs_user_review", "repair_ready", "context_request_pending",
                      "context_prepared", "needs_decision", "stale", "validation_pending")


def _active_handoff(state: dict[str, Any], task: dict[str, Any]) -> dict[str, Any] | None:
    aid = task.get("active_attempt_id")
    if not aid:
        return None
    hs = [h for h in state["handoffs"].values() if h.get("attempt_id") == aid]
    return max(hs, key=lambda h: h["handoff_id"]) if hs else None


def task_stage(state: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Conceptual stage of one task with its source facts (pure)."""
    t = state["tasks"].get(task_id)
    if t is None:
        raise ModelError(f"task {task_id} does not exist")
    st = t["status"]
    att = state["attempts"].get(t.get("active_attempt_id") or "")
    h = _active_handoff(state, t)
    wf = (att or {}).get("workflow") or {}
    why, stage = "", "planned"
    if st == "done":
        stage, why = "verified_done", "task status done (acceptance policy)"
    elif st in ("cancelled", "superseded"):
        stage, why = "abandoned", f"task {st}"
    elif st == "validation_pending":
        stage, why = "validation_pending", "task waits for test/build evidence"
    elif st == "in_review":
        stage, why = "needs_user_review", "delivery accepted, task waits for review"
    elif st == "needs_decision":
        stage, why = "needs_decision", t.get("blocked_reason") or "a decision is open"
    elif st == "blocked":
        stage, why = "blocked", t.get("blocked_reason") or "prerequisites"
    elif st in ("draft", "proposed"):
        stage, why = "planned", f"task {st}"
    elif att is None:
        stage, why = ("ready_to_prepare", "no attempt yet") if st == "ready" else ("planned", f"task {st}")
    else:
        a = att["status"]
        if wf.get("context_request") and not wf.get("context_prepared_at"):
            stage, why = "context_request_pending", "the answer asks for context"
        elif wf.get("context_prepared_at") and not wf.get("context_sent_at"):
            stage, why = "context_prepared", "context pack prepared, not marked as sent"
        elif a == "stale" or (h and h["status"] in ("stale", "reconciliation_required")):
            stage, why = "stale", "answer based on an older attempt/revision"
        elif a == "parse_failed":
            stage, why = ("repair_ready", "repair prompt prepared") if wf.get("repair_prepared_at") else \
                ("parse_failed", "answer stored but not readable")
        elif h and h["status"] in ("parsed", "reconciled") and h.get("unresolved_items") and h.get("outcome") == "partial":
            stage, why = "partial_response", f"{len(h['unresolved_items'])} item(s) still open"
        elif a in ("parsed", "reconciliation_required", "ready_for_review") or (h and h["status"] in ("parsed", "reconciled")):
            stage, why = "needs_user_review", "answer parsed; your review decides"
        elif a == "response_received":
            stage, why = "response_received", "answer stored"
        elif a in ("exported", "waiting_response"):
            if wf.get("sent_confirmed_at"):
                stage, why = "waiting_for_response", f"you confirmed sending at {wf['sent_confirmed_at']}"
            else:
                stage, why = "prompt_copied", "copied to clipboard; sending not confirmed"
        elif a in ("created", "prompt_ready"):
            stage, why = "prompt_prepared", "prompt built, not copied"
        elif a == "rejected":
            stage, why = "rejected", "attempt rejected"
        elif a == "abandoned":
            stage, why = "abandoned", "attempt abandoned"
        elif a == "accepted":
            stage, why = "needs_user_review", "delivery accepted"
    b = current_binding(state, att["agent_id"]) if att and att.get("agent_id") else None
    return {"task_id": task_id, "stage": stage, "why": why, "task_status": st,
            "attempt_id": (att or {}).get("attempt_id", ""), "attempt_status": (att or {}).get("status", ""),
            "handoff_id": (h or {}).get("handoff_id", ""), "agent_id": (att or {}).get("agent_id") or t.get("owner_agent_id", ""),
            "account_profile_id": (wf.get("account_profile_id") or (b or {}).get("account_profile_id", "")),
            "chat_binding_id": (wf.get("chat_binding_id") or (b or {}).get("chat_binding_id", "")),
            "sent_confirmed_at": wf.get("sent_confirmed_at", ""), "user_action": stage in USER_ACTION_STAGES}


def stage_label(stage: str, lang: str = "en") -> str:
    pair = STAGES.get(stage, (stage, stage))
    return pair[1] if lang == "fa" else pair[0]


class WorkflowService:
    """User facts on attempts (copied / sent / context) — every one an explicit action."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def stage(self, task_id: str) -> dict[str, Any]:
        return task_stage(self.store.load(), task_id)

    def stages(self) -> list[dict[str, Any]]:
        st = self.store.load()
        return [task_stage(st, tid) for tid in sorted(st["tasks"])]

    def open_attempt_warning(self, task_id: str) -> str:
        """Non-empty when starting again would leave an attempt that may still get an answer (spec §11.4)."""
        st = self.store.load()
        t = require(st, "tasks", task_id)
        a = st["attempts"].get(t.get("active_attempt_id") or "")
        if a and a["status"] in ("created", "prompt_ready", "exported", "waiting_response", "response_received"):
            sent = (a.get("workflow") or {}).get("sent_confirmed_at")
            return (f"{task_id} already has attempt {a['attempt_id']} ({a['status']}"
                    + (f", you confirmed sending at {sent}" if sent else "") + "). Starting again keeps it, but a late "
                    "answer to it will be marked stale. Continue only if you really want a new attempt.")
        return ""

    def _wf(self, s: dict[str, Any], attempt_id: str) -> dict[str, Any]:
        a = require(s, "attempts", attempt_id)
        return a.setdefault("workflow", {})

    def bind_attempt(self, s: dict[str, Any], attempt_id: str) -> None:
        """Freeze the account/chat used for this attempt (changing it later never rewrites history)."""
        a = require(s, "attempts", attempt_id)
        wf = a.setdefault("workflow", {})
        if wf.get("chat_binding_id") or not a.get("agent_id"):
            return
        b = current_binding(s, a["agent_id"])
        if b:
            wf["chat_binding_id"] = b["chat_binding_id"]
            wf["account_profile_id"] = b["account_profile_id"]

    def mark_copied(self, attempt_id: str) -> dict[str, Any]:
        with self.store.transaction("prompt copied") as s:
            wf = self._wf(s, attempt_id)
            self.bind_attempt(s, attempt_id)
            wf["copied_at"] = now_utc()
            wf["copy_count"] = int(wf.get("copy_count", 0)) + 1
            a = s["attempts"][attempt_id]
            emit(s, "prompt_copied", attempt_id=attempt_id, task_id=a["task_id"], agent_id=a.get("agent_id", ""),
                 count=wf["copy_count"])
            return a

    def confirm_sent(self, attempt_id: str, *, chat_binding_id: str = "") -> dict[str, Any]:
        """'I sent this prompt' — a self-declaration; time = time of this confirmation (§9.2)."""
        with self.store.transaction("user confirmed sent") as s:
            a = require(s, "attempts", attempt_id)
            if a["status"] not in ("created", "prompt_ready", "exported", "waiting_response"):
                raise ModelError(f"attempt {attempt_id} is {a['status']}; there is nothing to send")
            task = s["tasks"].get(a["task_id"]) or {}
            if task.get("active_attempt_id") != attempt_id:
                raise ModelError(f"attempt {attempt_id} is not the active attempt of {a['task_id']}; "
                                 "confirm sending for the current prompt instead")
            wf = a.setdefault("workflow", {})
            if chat_binding_id:
                b = require(s, "chat_bindings", chat_binding_id)
                if b["agent_id"] != a.get("agent_id"):
                    raise ModelError(f"chat binding {chat_binding_id} belongs to {b['agent_id']}, not {a.get('agent_id')}")
                wf["chat_binding_id"], wf["account_profile_id"] = chat_binding_id, b["account_profile_id"]
            else:
                self.bind_attempt(s, attempt_id)
            if not wf.get("copied_at"):
                wf["copied_at"] = ""  # sent without a recorded copy (e.g. typed by hand) — kept explicit
            wf["sent_confirmed_at"] = now_utc()
            for step in ("prompt_ready", "exported", "waiting_response"):
                from .models import MACHINES
                if a["status"] != step and step in MACHINES["attempt"][a["status"]]:
                    old = a["status"]
                    a["status"] = step
                    emit(s, "attempt_status", attempt_id=attempt_id, old=old, new=step, why="user confirmed sending")
            emit(s, "user_confirmed_sent", attempt_id=attempt_id, task_id=a["task_id"], agent_id=a.get("agent_id", ""),
                 chat_binding_id=wf.get("chat_binding_id", ""), account_profile_id=wf.get("account_profile_id", ""))
            return a

    def note_context_request(self, attempt_id: str, request_id: str = "") -> dict[str, Any]:
        with self.store.transaction("context request received") as s:
            wf = self._wf(s, attempt_id)
            wf["context_request"] = request_id or "pending"
            wf.pop("context_prepared_at", None)
            wf.pop("context_sent_at", None)
            a = s["attempts"][attempt_id]
            emit(s, "context_request_received", attempt_id=attempt_id, task_id=a["task_id"])
            return a

    def mark_context_prepared(self, attempt_id: str, *, kind: str = "text") -> dict[str, Any]:
        with self.store.transaction("context prepared") as s:
            wf = self._wf(s, attempt_id)
            wf["context_prepared_at"] = now_utc()
            wf["context_kind"] = kind if kind in ("text", "zip") else "text"
            a = s["attempts"][attempt_id]
            emit(s, "context_pack_prepared", attempt_id=attempt_id, task_id=a["task_id"], kind=wf["context_kind"])
            return a

    def mark_context_sent(self, attempt_id: str) -> dict[str, Any]:
        with self.store.transaction("context marked sent") as s:
            wf = self._wf(s, attempt_id)
            if not wf.get("context_prepared_at"):
                raise ModelError("prepare the context pack first")
            wf["context_sent_at"] = now_utc()
            a = s["attempts"][attempt_id]
            emit(s, "context_marked_sent", attempt_id=attempt_id, task_id=a["task_id"])
            return a

    def mark_repair_prepared(self, attempt_id: str) -> dict[str, Any]:
        with self.store.transaction("repair prepared") as s:
            wf = self._wf(s, attempt_id)
            wf["repair_prepared_at"] = now_utc()
            a = s["attempts"][attempt_id]
            emit(s, "repair_prepared", attempt_id=attempt_id, task_id=a["task_id"])
            return a

    def readiness(self, agent_id: str) -> dict[str, Any]:
        return binding_readiness(self.store.load(), agent_id)
