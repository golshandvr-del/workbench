# Release Gate — Project Workbench و تیم چند Agent (Roadmap 2.3.0 → 2.6.0، مرحله 9)

**تاریخ:** 2026-10-18 · **نسخه:** `desktop-v2.6.0` · **مرجع:** `docs/specs/AI_Workbench_GUI_Team_Orchestration_Roadmap_FA.md` §۲۰، §۲۴

این سند فقط چیزی را «پاس» می‌نامد که شاهد اجرایی دارد. هر چیزی که در محیط واقعی (Windows فیزیکی، DPI متفاوت، دو چت واقعی مدل) اجرا نشده **NOT RUN** است.

## ۱. شواهد خودکار (Linux sandbox، Python 3.13، Xvfb)

| مورد | نتیجه |
|---|---|
| Unit/Integration (`unittest discover`) | **475 تست — OK** |
| GUI smoke (`tests/gui/run_all.py`) | **28/28 PASS** (شامل `gui_workflow_timeline_smoke`، `gui_dashboard_smoke`، `gui_team_planner_smoke`، `gui_workspace_*`) |
| Undefined names / pyflakes | PASS (0) |
| Contracts (`validate_contracts.py`) | PASS: 8 schema، 18 fixture، capabilities (35)، manifest، build metadata |
| V2 schema ↔ models | PASS (3) |
| Windows CI (installer clean + **upgrade از آخرین Release با حفظ settings و app data**) | در CI این PR اجرا می‌شود؛ تصمیم انتشار مشروط به سبز بودن آن است |

## ۲. Gateها

| Gate | وضعیت | شواهد |
|---|---|---|
| A — Team Planner و پذیرش انتخابی | PASS | `test_team_planner.py`، `gui_team_planner_smoke.py` (2.4.0) |
| B — وضعیت‌های بیرونی فقط از عمل کاربر/رویداد واقعی | PASS | `test_workflow_timeline.py`: copy ≠ sent، `user_confirmed_sent` با `time_source: user_confirmed`، هشدار Start تکراری |
| C — ده Agent و Failure Triage | PASS (Dataset ساختگی) | `fixtures_ten_agents.py` + `test_dashboard.py`: پاسخ ناقص، stale، parse-failed، منتظر کاربر و Agentهای آماده جدا؛ هر مورد صف «چرا» و ref دارد؛ «فقط نیازمند اقدام» پیش‌فرض برای 7–10 Agent؛ Workbench هرگز «مدل در حال کار است» نمی‌گوید |
| D — Timeline و Progress | PASS | Milestone/Version مستقل؛ Task جدید Version نمی‌سازد؛ released فقط با run id/artifact؛ پیشرفت شمارشی جدا از وزنی «تخمینی»؛ فیلتر/زبان تاریخچه را تغییر نمی‌دهد |
| E — Responsive UI و Windows | PARTIAL | smoke در 1024×640 تا 1920×1080، RTL/LTR، جمع‌شدن Sidebar/Inspector، Light/Dark: PASS. **ویندوز فیزیکی با DPI 125/150/200٪: NOT RUN** |
| F — Performance و Installer | PASS با یادداشت | جدول ۳؛ Regressionها توضیح داده و پذیرفته شده‌اند |
| G — امنیت و داده | PASS | Account Profile بدون credential (validation رد می‌کند)؛ Ledger متن را کوتاه و موارد شبه‌secret را `[redacted]` می‌کند؛ Context Request همان parser/اعتبارسنجی مسیر قبلی؛ migration نسخه‌دار با backup |

## ۳. Performance در برابر Baseline (همان اسکریپت `tools/measure_baseline.py`، همان دستگاه، 200 Task / 2000 Event)

| شاخص | Baseline (2.3.0 مرحله 0) | 2.6.0 | توضیح |
|---|---|---|---|
| import ماژول اصلی | 165 ms | 143 ms | بهتر |
| ساخت پنجرهٔ اصلی تا idle | 167 ms | 260 ms | +93 ms: Workspace با Dashboard، صف و Timeline Lane ساخته می‌شود؛ زیر 0.5 s — **پذیرفته شد** |
| Open project، میانه | 123 ms | 150 ms | +27 ms به‌خاطر projection مرحلهٔ workflow برای هر Task — پذیرفته شد |
| Read models (میانه) | — | overview 104 · tasks 55 · timeline page 18 · lanes 46 · team 28 · attention 29 · dashboard 30 ms | همه زیر 150 ms در Dataset بزرگ |
| Max RSS | 50 MiB | 56 MiB | +6 MiB |
| Payload نصب | 92 فایل / 1.92 MB | 104 فایل / 2.12 MB | ماژول‌های جدید؛ بدون وابستگی جدید (Tkinter حفظ شد، ADR-007) |
| اعداد روی دستگاه ویندوز مرجع | — | **NOT RUN** | |

UI thread: Publish و Build در پس‌زمینه می‌مانند (رفتار قبلی، smokeهای publish)؛ read modelها خالص و بدون IO شبکه هستند.

## ۴. NOT RUN (صریح)

1. **Manual End-to-End با دو چت مستقل واقعی مدل** (§۲۴) — نیازمند مالک محصول.
2. **Windows فیزیکی با DPI متفاوت و Taskbar در موقعیت‌های مختلف** — فقط Windows CI (runner مجازی) اجرا می‌شود.
3. **Mobile Companion 0.3.0 روی گوشی واقعی** (از 2.2.0 باقی مانده).
4. Downgrade: `v2/store.migrate_state` state با `db_version` بالاتر را رد می‌کند و فایل را تغییر نمی‌دهد (تست‌شده در unit tests)، backup قبل از migration حفظ می‌شود؛ rollback انتشار طبق `docs/release/ROLLBACK_PLAN.md`. نصب دستی نسخهٔ قدیمی روی دادهٔ جدید: NOT RUN.

## ۵. تصمیم انتشار

انتشار `desktop-v2.6.0`: **تأیید شد**، به شرط سبز بودن CI روی Linux و Windows و Release workflow. Roadmap از نظر کد و تست خودکار کامل است؛ مطابق §۲۴ موارد بخش ۴ تا اجرای مالک محصول NOT RUN می‌مانند و Roadmap صرفاً بر اساس تست سبز «کامل در محیط واقعی» اعلام نمی‌شود.
