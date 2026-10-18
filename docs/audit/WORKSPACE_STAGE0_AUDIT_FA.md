# مرحله 0 — Audit، نقشهٔ جریان UX و Baseline (Roadmap 2.3.0)

**تاریخ:** 2026-10-18 · **مبنا:** `main` @ `591a9ed` (desktop 2.2.0، mobile 0.3.0) · **مرجع:** `docs/specs/AI_Workbench_GUI_Team_Orchestration_Roadmap_FA.md` §۳، §۱۸ مرحله 0

## ۱. Audit کد — reuse / جدید / حذف‌شدنی

| حوزه | فایل موجود | تصمیم |
|---|---|---|
| State و Transaction | `aiwb/v2/store.py` (`ProjectStore`, `MAX_EVENTS=2000`, migration نسخه‌دار) | **reuse**؛ events داخلی state با سقف 2000 برای تاریخچهٔ بلندمدت کافی نیست ← Event Ledger append-only جدا (ADR-008) |
| ماشین‌های وضعیت | `aiwb/v2/models.py` (Task/Attempt/Handoff/Decision) | **reuse**؛ وضعیت ارسال دستی (`user_confirmed_sent`) به‌صورت projection روی Attempt/Handoff، نه Status جدید Task |
| Agent | `aiwb/v2/agents.py` (`preferred_model_label`) | **reuse**؛ Label حفظ می‌شود؛ Account Profile و Chat Binding collection جدا |
| Task Graph | `aiwb/v2/tasks.py` (`parallel_candidates`, `scopes_overlap`, `readiness`) | **reuse** در Team Planner و Dashboard |
| Proposal | `aiwb/v2/proposals.py` | **گسترش افزایشی**: بخش اختیاری `team` در همان بلوک (سازگار با قبلی) |
| Handoff / Attempt | `aiwb/v2/handoff.py`, `attempts.py` | **reuse**؛ اتصال اختیاری `chat_binding_id` |
| Next Action / Warnings | `next_action.py`, `controller.py::warning_items` | **reuse** مستقیم در Next Action Strip و صف Needs Attention |
| Response Inbox / Repair | `aiwb/inbox/*` | **reuse**؛ Workspace فقط پنجرهٔ موجود را باز می‌کند |
| Context Request | `context_request.py`, `context_request_window.py` | **reuse** |
| Publisher / Snapshot | `publisher.py`, `snapshot.py` | **reuse**؛ Account/Chat هرگز در Snapshot منتشر نمی‌شوند |
| Companion | `aiwb/companion/*` | **بدون تغییر** |
| GUI | `AI_Workbench.py` (Notebook کلاسیک، ~10.9k خط)، `projects_window.py` | **حفظ**؛ Workspace یک پوستهٔ جدید (`aiwb/workspace/`) روی همان Controllerهاست. هیچ مسیری حذف نمی‌شود (حذف‌شدنی در این مرحله: هیچ) |

## ۲. نقشهٔ جریان فعلی (از ایجاد پروژه تا Version)

1. Workspace انتخاب → `set_workspace` (Baseline نسخه/Git در پس‌زمینه).
2. «Projects (multi-agent)…» → `ProjectsController` → Planning Prompt → کپی → چت PM.
3. پاسخ PM در یک جعبهٔ Paste → Inbox (raw-first) → `AIWB_MANAGER_PROPOSAL` → Review انتخابی → Taskها.
4. Start Task → Handoff + Attempt → Copy (`exported`) → چت Agent → پاسخ → Inbox → `AIWB_HANDOFF` → reconcile/stale.
5. Accept handoff → `in_review` → Review/Evidence → `done` فقط با سیاست پذیرش.
6. پاسخ ناقص → Inbox salvage → Repair Prompt (Attempt جدید). درخواست زمینه → Context Request → متن/ZIP.
7. فایل‌ها فقط از مسیر کلاسیک Analyze/Preview/Apply. Sync & Build → Evidence. Publish → شاخهٔ `aiwb-state`.

**شکاف‌های تأییدشده:** پنجره‌های جدا (Prompt کلاسیک، Inbox، Projects، Context، GitHub، Companion)؛ «Copy» همان «exported/waiting» ثبت می‌شود و تأیید صریح ارسال وجود ندارد؛ نبود Account/Chat؛ نبود Timeline/Milestone/Version مستقل؛ نبود داشبورد تیم.

## ۳. پنج سناریوی کاربر (مبنای GUI smoke و Gate)

| # | سناریو | مسیر در Workspace |
|---|---|---|
| S1 | پروژهٔ تازه | Overview → «Plan project» → Team Planner (منابع، سقف چت) → Prompt → پاسخ → Review تیم |
| S2 | پاسخ ناقص | Needs Attention «پاسخ ناقص» → Inspector → «Repair» (Inbox موجود) |
| S3 | گسترش قابلیت | Inspector Task → «Extend this task / New task / Ask manager to re-plan» |
| S4 | چت جدید / زمینه | Team → تغییر Chat Binding → «Prepare handoff» / Context Request |
| S5 | پروژهٔ چند Agent | Team Dashboard + صف Needs Attention + Timeline با Lane |

## ۴. وایرفریم Low-Fi

```text
┌ Project Bar: پروژه · Publish/Local revision · زبان · نما (Focused/Advanced) · ☰ ─────────────┐
├ Sidebar ┬ Next Action Strip: «مهم‌ترین اقدام بعدی» [اقدام]                       ┬ Inspector ┤
│Overview │ Workspace (نمای منتخب):                                              │ انتخاب   │
│Timeline │  Overview: هدف · Progress (n از m) · Needs Attention (۵ مورد اول)     │ جاری:     │
│Tasks    │  Timeline: فیلترها | فهرست/Lane صفحه‌بندی‌شده                        │ جزئیات +  │
│Team     │  Tasks: جدول با Status متن+نماد                                      │ فقط       │
│Files&Ctx│  Team: Agentها · Account Profiles · Chat Bindings · Team Planner      │ اقدام‌های │
│Versions │  Versions: Milestone · Version · Build/Evidence                       │ معتبر     │
│Settings │                                                                       │ [جمع‌شو] │
├─────────┴ Status Footer: عملیات پس‌زمینه · خطای اخیر ───────────────────────────────────────┤
```

عرض کم (< 1100px): Inspector به پایین می‌رود؛ (< 900px): Sidebar فقط نماد/نام کوتاه.

## ۵. مدل مفهومی و وضعیت ارسال دستی

Agent (نقش) · Account Profile (برچسب خوداظهاری، بدون Credential) · Chat Binding (Agent↔Account + نام/لینک اختیاری) · Task · Attempt · Handoff · Milestone · Version.
وضعیت Workflow هر Attempt projection است از: وضعیت Attempt/Handoff + Eventهای `prompt_copied` و `user_confirmed_sent` در Ledger. جزئیات در ADR-008.

## ۶. Baseline عملکرد و بسته‌بندی

اندازه‌گیری با `tools/measure_baseline.py` (پروژهٔ مصنوعی 200 Task، 2000 Event):

| شاخص | مقدار | محیط |
|---|---|---|
| import ماژول اصلی | 165 ms | Linux sandbox، Python 3.13، 2 CPU، Xvfb |
| ساخت پنجرهٔ اصلی تا idle | 167 ms | همان |
| Open project (Controller + next action + task rows)، میانه | 123 ms (state 580 KB) | همان |
| Max RSS | 50 MiB | همان |
| Payload نصب (92 فایل) | 1.92 MB | `release_manifest.json` |
| PySide6-Essentials + shiboken6 (win_amd64 wheel) | 83.4 MB | دانلود واقعی، 2026-10-18 |

اعداد روی دستگاه ویندوز مرجع: **NOT RUN** (در Release Gate روی Windows CI تکرار می‌شود).

## ۷. تصمیم‌ها

- فناوری GUI: ADR-007. Event Ledger و Data Model: ADR-008.
- Event history: Ledger append-only جدا؛ events قبلی state با برچسب `legacy` خوانده می‌شوند، تاریخ حدسی ساخته نمی‌شود.
- نسخه‌ها: 2.3.0 → 2.6.0 مطابق جدول `ROADMAP.md`.
