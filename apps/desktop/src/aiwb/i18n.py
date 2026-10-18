"""Single FA/EN glossary for Workbench terms (Future Roadmap §19.3/§19.4, roadmap 2.1.x).

One key = one concept = one translation per language. Program logic never compares
against translated strings; it works with keys and asks this module for text.
Every status carries a symbol so colour never carries meaning alone.
"""
from __future__ import annotations

from typing import Any

LANGUAGES = ("en", "fa")
DEFAULT_LANGUAGE = "en"

# key: (symbol, English, Persian)
STATUS = {
    "draft": ("○", "Not planned yet", "هنوز برنامه‌ریزی نشده"),
    "proposed": ("○", "Proposed", "پیشنهادشده"),
    "ready": ("▶", "Ready to start", "آمادهٔ شروع"),
    "in_progress": ("…", "Waiting for the model", "در انتظار پاسخ مدل"),
    "blocked": ("■", "Blocked", "مسدود"),
    "needs_decision": ("?", "Needs your decision", "نیازمند تصمیم شما"),
    "in_review": ("◆", "Needs your review", "نیازمند بازبینی شما"),
    "validation_pending": ("◇", "Needs a real test/build", "نیازمند تست/Build واقعی"),
    "done": ("✓", "Done (verified)", "انجام‌شده (تأییدشده)"),
    "cancelled": ("✕", "Cancelled", "لغوشده"),
    "superseded": ("↷", "Replaced", "جایگزین‌شده"),
}

# Evidence words must be distinguishable from each other (§19.3).
EVIDENCE = {
    "verified": ("✓", "Verified", "تأییدشده"),
    "reported": ("≈", "Reported (not verified)", "گزارش‌شده (تأییدنشده)"),
    "not_run": ("–", "Not run", "اجرا نشده"),
    "failed": ("✗", "Failed", "ناموفق"),
}

SEVERITY = {  # ordered: blocking first
    "blocking": ("⛔", "Stop", "توقف"),
    "action": ("⚠", "Action needed", "اقدام لازم"),
    "info": ("ℹ", "Info", "اطلاع"),
}
SEVERITY_ORDER = tuple(SEVERITY)

ACTION = {
    "plan_project": ("Write the project goal and copy the planning prompt to your project-manager chat",
                     "هدف پروژه را بنویسید و پرامپت برنامه‌ریزی را در چت مدیر پروژه کپی کنید"),
    "review_proposal": ("Review the manager's proposal and accept the parts you agree with",
                        "پیشنهاد مدیر پروژه را بازبینی کنید و بخش‌هایی را که قبول دارید بپذیرید"),
    "resolve_decision": ("Make a decision the work is waiting for", "تصمیمی را که کار منتظر آن است بگیرید"),
    "start_task": ("Start the next task: copy its prompt to the agent's chat",
                   "Task بعدی را شروع کنید: پرامپت آن را در چت Agent کپی کنید"),
    "copy_prompt": ("Copy the prepared prompt into the agent's chat", "پرامپت آماده را در چت Agent کپی کنید"),
    "import_response": ("Paste the model's answer here", "پاسخ مدل را اینجا Paste کنید"),
    "review_handoff": ("Review what the agent delivered", "تحویلی Agent را بازبینی کنید"),
    "run_validation": ("Run the tests/build so the result is verified", "تست/Build را اجرا کنید تا نتیجه تأیید شود"),
    "repair": ("Ask the model only for what is missing", "فقط بخش ناقص را از مدل بخواهید"),
    "publish_state": ("Publish the project state to GitHub", "وضعیت پروژه را در GitHub منتشر کنید"),
    "manager_update": ("Send the manager an update", "گزارش به‌روز را برای مدیر پروژه بفرستید"),
    "replan": ("Re-plan a blocked task", "Task مسدود را دوباره برنامه‌ریزی کنید"),
    "unblock_task": ("Unblock a task whose prerequisites changed", "Taskی را که پیش‌نیازهایش تغییر کرده آزاد کنید"),
    "approve_task": ("Approve finished work so the task can be closed", "کار تمام‌شده را تأیید کنید تا Task بسته شود"),
    "review_delivery": ("Review what the agent delivered", "تحویلی Agent را بازبینی کنید"),
    "prepare_handoff": ("Prepare the prompt for the next agent", "پرامپت Agent بعدی را آماده کنید"),
    "review_task": ("Review the finished task", "Task تمام‌شده را بازبینی کنید"),
    "nothing": ("Nothing is waiting. Add a task or ask the manager for the next step.",
                "کاری در انتظار نیست. یک Task اضافه کنید یا قدم بعدی را از مدیر پروژه بپرسید."),
}

TERMS = {
    "decision_needed": ("Decision needed", "تصمیم لازم است"),
    "blocked": ("Blocked", "مسدود"),
    "not_verified": ("Not verified yet", "هنوز تأیید نشده"),
    "publish_paused": ("State publishing is paused", "انتشار وضعیت متوقف شده است"),
    "stale_proposal": ("Proposal written for an older project state", "پیشنهاد برای وضعیت قدیمی‌تر پروژه نوشته شده"),
    "stale_answer": ("Answer for an older task version", "پاسخ برای نسخهٔ قدیمی‌تر Task"),
    "view": ("View", "نما"),
    "simple": ("Simple", "ساده"),
    "advanced": ("Advanced", "پیشرفته"),
    "language": ("Language", "زبان"),
    "next_step": ("Next step", "قدم بعدی"),
    "then": ("Then", "سپس"),
    "see_details": ("see details", "جزئیات را ببینید"),
}


def _lang(lang: str) -> int:
    return 1 if lang == "fa" else 0


def status(key: str, lang: str = DEFAULT_LANGUAGE) -> tuple[str, str]:
    sym, en, fa = STATUS.get(key, ("·", key, key))
    return sym, (fa if lang == "fa" else en)


def evidence_label(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    sym, en, fa = EVIDENCE[key]
    return f"{sym} {fa if lang == 'fa' else en}"


def severity_label(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    sym, en, fa = SEVERITY[key]
    return f"{sym} {fa if lang == 'fa' else en}"


def action(key: str, lang: str = DEFAULT_LANGUAGE, default: str = "") -> str:
    pair = ACTION.get(key)
    return pair[_lang(lang)] if pair else (default or key)


def term(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    return TERMS[key][_lang(lang)]


def evidence_state(e: dict[str, Any]) -> str:
    if not e.get("verified"):
        return "reported"
    return "failed" if str(e.get("result", "")) in ("failed", "rejected", "failure") else "verified"


def check_glossary() -> list[str]:
    """Problems: missing translation, duplicate translation for different concepts, missing symbol."""
    problems = []
    for name, table, width in (("STATUS", STATUS, 3), ("EVIDENCE", EVIDENCE, 3), ("SEVERITY", SEVERITY, 3),
                               ("ACTION", ACTION, 2), ("TERMS", TERMS, 2)):
        seen: dict[tuple[int, str], str] = {}
        for k, v in table.items():
            if len(v) != width or any(not str(x).strip() for x in v):
                problems.append(f"{name}.{k}: incomplete entry")
                continue
            texts = v[1:] if width == 3 else v
            for i, txt in enumerate(texts):
                other = seen.get((i, txt))
                if other and not (name == "ACTION" and {other, k} == {"review_handoff", "review_delivery"}):
                    problems.append(f"{name}: '{txt}' used for both {other} and {k}")
                seen[(i, txt)] = k
    syms = [v[0] for v in STATUS.values()]
    for k, v in STATUS.items():
        if syms.count(v[0]) > 1 and k not in ("draft", "proposed"):
            problems.append(f"STATUS.{k}: symbol {v[0]} not unique")
    return problems
