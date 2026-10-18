# AI Workbench — نقشه‌راه اصلی (Master Roadmap) — Project Workbench و تیم چند Agent

> **این فایل تنها مرجع اجرایی ترتیب توسعه است.** هر کار توسعه باید به یکی از گام‌های همین فایل اشاره کند.
> منبع جزئیات، معیارها و Gateها: [`docs/specs/AI_Workbench_GUI_Team_Orchestration_Roadmap_FA.md`](docs/specs/AI_Workbench_GUI_Team_Orchestration_Roadmap_FA.md) (نسخه 1.0، 2026-10-18).
> Roadmap قبلی (1.14.1 → 2.2.0، کامل‌شده) در [`docs/roadmap/archive/ROADMAP_v1.14-v2.2_FA.md`](docs/roadmap/archive/ROADMAP_v1.14-v2.2_FA.md) بایگانی شده است.
> تعارض بین این فایل و سند مرجع با ADR در `docs/adr/` حل می‌شود.

**آخرین به‌روزرسانی:** 2026-10-18 · **نسخهٔ Desktop منتشرشده:** `desktop-v2.5.0` · **نسخهٔ Mobile منتشرشده:** `mobile-v0.3.0`
**گام فعال بعدی:** 2.6.0 — Team Dashboard، یکپارچه‌سازی و Release Gate (مراحل 7، 8، 9)

راهنمای وضعیت: ✅ کامل (دروازه پاس شده) · 🟡 بخشی · ⬜ شروع‌نشده · ⏭ خارج از دامنه · NOT RUN = اجرا نشده

---

## ۰. قواعد استفاده

1. یک گام در هر زمان؛ ✅ فقط با شواهد (تست، Run، Release). شمارهٔ نسخه به‌تنهایی مدرک تکمیل نیست.
2. وضعیت در همان PR به‌روز می‌شود.
3. قابلیت موجود دوباره ساخته نمی‌شود: V2 Store/Services، Inbox، Repair، Context Request، Publisher، GitHub و Companion reuse می‌شوند.
4. «NOT RUN» صریح می‌ماند: آنچه روی ویندوز واقعی، با چت واقعی مدل یا گوشی واقعی اجرا نشده PASS اعلام نمی‌شود.
5. تغییر فناوری GUI هرگز در یک PR با تغییر پرخطر State Schema مخلوط نمی‌شود.

## ۱. اصول تغییرناپذیر (سند مرجع §۲)

- بدون API مدل، بدون API Key، بدون ورود به حساب مدل، بدون scraping و بدون ارسال خودکار پیام. مسیر دستی کپی/پیست حفظ می‌شود.
- Agent (نقش) ≠ Account Profile (برچسب محلی خوداظهاری) ≠ Chat Binding (یادداشت دستی چت) ≠ Task ≠ Attempt/Handoff ≠ Milestone ≠ Version.
- «پرامپت کپی شد» ≠ «کاربر ارسال را تأیید کرد» ≠ «پاسخ دریافت شد». Workbench هرگز ادعا نمی‌کند مدل «در حال کار» است.
- ادعای مدل Evidence نیست؛ Done فقط با سیاست پذیرش و شاهد.
- هیچ Proposal/پاسخ بدون بازبینی کاربر State یا فایل را تغییر نمی‌دهد. Merge خودکار Candidateهای متعارض ممنوع.
- Event Ledger تاریخچه است، نه منبع دوم وضعیت جاری؛ تاریخ حدسی ساخته نمی‌شود.

## ۲. نمای کلی مسیر

```text
2.3.0  مرحله 0–3  ADR + Spike + Event Ledger + Account/Chat data + پوستهٔ Workspace واکنش‌گرا   (Gate: نصب/مهاجرت/Responsive)
2.4.0  مرحله 4    Account/Chat UI + Team Planner + Team Proposal                                  (Gate A)
2.5.0  مرحله 5–6  Workflow tracking دستی + Timeline + Milestone/Version + Progress                (Gate B, D)
2.6.0  مرحله 7–9  Team Dashboard + Needs Attention + یکپارچه‌سازی/Polish + Release Gate          (Gate C, E, F, G)
```

---

## 2.3.0 — Foundation (مراحل 0، 1، 2، 3)

| گام | عنوان | وضعیت | شواهد / باقی‌مانده |
|---|---|---|---|
| 0 | Discovery، Audit، UX Flow، Baseline و ADR | ✅ | `docs/audit/WORKSPACE_STAGE0_AUDIT_FA.md`، `tools/measure_baseline.py` |
| 1 | UI Technology Spike و Design System | ✅ | ADR-007، `aiwb/workspace/theme.py` |
| 2 | Event Ledger، Account Profile و Chat Binding (داده) | ✅ | ADR-008، `v2/events.py`، `v2/resources.py`، `event-ledger.v1` |
| 3 | پوستهٔ Workspace و Responsive | ✅ | `aiwb/workspace/`، `gui_workspace_smoke.py`؛ DPI ویندوز واقعی NOT RUN |

**معیارهای پذیرش (خلاصه):**
- [x] ADR فناوری GUI و ADR Event Ledger/Data Model ثبت شده‌اند.
- [x] Audit موجود/جدید/حذف‌شدنی UI و نقشهٔ جریان UX با ۵ سناریو.
- [x] Baseline عملکرد (start، open project، حافظه، اندازهٔ Payload) با اعداد واقعی ثبت شده.
- [x] Event Ledger append-only نسخه‌دار، idempotent، بدون Prompt/Response خام؛ تغییر نما Event نمی‌سازد.
- [x] Account Profile / Chat Binding بدون هیچ Credential؛ پروژه‌های قدیمی بدون آن باز می‌شوند؛ `preferred_model_label` حفظ می‌شود.
- [x] Workspace: Project Bar، Sidebar، Workspace، Inspector جمع‌شونده، Next Action، Status Footer؛ همهٔ مسیرهای موجود در دسترس.
- [x] تنظیم Layout بیرون از State پروژه؛ RTL فارسی/LTR انگلیسی در پوسته.
- [x] تست‌های واحد + GUI smoke (اندازه‌های 1280×720، 1366×768، 1920×1080) و Installer ویندوز در CI سبز.

## 2.4.0 — Team Planner (مرحله 4، Gate A)

| گام | عنوان | وضعیت | شواهد / باقی‌مانده |
|---|---|---|---|
| 4.1 | Account Profile manager و Chat Binding UI | ✅ | نمای Team در Workspace |
| 4.2 | Planning Prompt با منابع، سقف چت هم‌زمان و سؤال اندازهٔ تیم | ✅ | `v2/team.py` `team_planning_prompt` |
| 4.3 | قرارداد Team Proposal (نسخه‌دار، سازگار با قبلی) + اعتبارسنجی منابع | ✅ | `team-proposal.v1`، `check_team` |
| 4.4 | Review UI تیم: پذیرش کل/انتخابی/رد | ✅ | + Request changes؛ `gui_team_planner_smoke.py`؛ چت واقعی مدل NOT RUN |

- [x] PM نمی‌تواند Account Profile ناموجود را منبع واقعی معرفی کند؛ شمارش PM داخل/خارج تیم صریح است.
- [x] Taskها Owner/Scope/Acceptance/Dependencies دارند یا کمبودها روشن نمایش داده می‌شوند.
- [x] محدودیت منابع/هم‌زمانی در اعتبارسنجی لحاظ می‌شود؛ قرارداد قدیمی Proposal کار می‌کند.

## 2.5.0 — Workflow tracking، Timeline و Progress (مراحل 5، 6؛ Gate B، D)

| گام | عنوان | وضعیت | شواهد / باقی‌مانده |
|---|---|---|---|
| 5.1 | Workflow projection: prompt_prepared / copied / user_confirmed_sent / waiting / received / parse_failed / partial / stale … | ✅ | `v2/workflow.py` `task_stage` |
| 5.2 | «I sent this prompt»، هشدار Start تکراری، اتصال Attempt به Account/Chat | ✅ | `WorkflowService`، `gui_workflow_timeline_smoke.py` |
| 6.1 | Timeline از Event Ledger با فیلتر، Lane و legacy برچسب‌دار | ✅ | `timeline.lanes`، نمای Timeline |
| 6.2 | Milestone و Version مستقل، اتصال به Commit/Build/Artifact | ✅ | `TimelineService` |
| 6.3 | Progress: «n از m Task تأییدشده» + شاخص‌های جدا؛ وزن فقط با برچسب «تخمینی» | ✅ | `timeline.progress` |

## 2.6.0 — Team Dashboard، یکپارچه‌سازی و Release Gate (مراحل 7، 8، 9؛ Gate C، E، F، G)

| گام | عنوان | وضعیت | شواهد / باقی‌مانده |
|---|---|---|---|
| 7 | Team Dashboard و صف Needs Attention (اولویت قطعی و توضیح‌پذیر) | ⬜ | |
| 8 | یکپارچه‌سازی ورودی‌ها (اصلاح همین Task / Task جدید / Re-plan)، Polish، Light/Dark | ⬜ | |
| 9 | Release Gate: Dataset ده Agent، Performance در برابر Baseline، Installer upgrade، NOT RUNها | ⬜ | |

---

## Definition of Done (سند مرجع §۲۴)

Roadmap فقط وقتی کامل اعلام می‌شود که همهٔ موارد §۲۴ سند مرجع با شواهد پاس شده باشند. آزمون Manual End-to-End با دو چت واقعی مدل و آزمون روی Windows واقعی با DPI متفاوت تا اجرای مالک محصول **NOT RUN** می‌مانند و در Release Gate صریحاً ثبت می‌شوند.

## اسناد

| سند | نقش |
|---|---|
| `docs/specs/AI_Workbench_GUI_Team_Orchestration_Roadmap_FA.md` | منبع جزئیات این Roadmap |
| `docs/roadmap/archive/ROADMAP_v1.14-v2.2_FA.md` | Roadmap کامل‌شدهٔ قبلی (1.14.1 → 2.2.0) |
| `docs/specs/*` دیگر | مشخصات V2، GitHub Hub و Integration (مرجع رفتار موجود) |
| `docs/adr/` | تصمیم‌های معماری |
