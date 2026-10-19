# AI Workbench — نقشه‌راه اصلی (Master Roadmap) — بازطراحی رابط کاربری (GUI-only)

> **وضعیت: superseded (2026-10-19)** — فقط 2.7.0 (سند و توکن) منتشر شد؛ 2.8–2.10 لغو و با [`ROADMAP.md`](../../../ROADMAP.md) (Roadmap 3.x — بازسازی محصول) جایگزین شد.

> **این فایل تنها مرجع اجرایی ترتیب توسعه است.** هر کار توسعه باید به یکی از گام‌های همین فایل اشاره کند.
> منبع جزئیات، معیارها و Gateها: [`docs/specs/AI_Workbench_GUI_Only_Roadmap_FA_v1.0.md`](docs/specs/AI_Workbench_GUI_Only_Roadmap_FA_v1.0.md) (نسخه 1.0، 2026-10-19).
> Roadmapهای قبلی بایگانی شده‌اند: [`ROADMAP_v2.3-v2.6_FA.md`](docs/roadmap/archive/ROADMAP_v2.3-v2.6_FA.md) (Project Workbench و تیم چند Agent، کامل‌شده) و [`ROADMAP_v1.14-v2.2_FA.md`](docs/roadmap/archive/ROADMAP_v1.14-v2.2_FA.md).
> تعارض بین این فایل و سند مرجع با ADR در `docs/adr/` حل می‌شود.

**آخرین به‌روزرسانی:** 2026-10-19 · **نسخهٔ Desktop منتشرشده:** `desktop-v2.6.0` · **نسخهٔ Mobile منتشرشده:** `mobile-v0.3.0`
**گام فعال بعدی:** 2.8.0 — مرحلهٔ 5 (پوسته و کامپوننت‌های مشترک)

راهنمای وضعیت: ✅ کامل (دروازه پاس شده) · 🟡 بخشی · ⬜ شروع‌نشده · ⏭ خارج از دامنه · NOT RUN = اجرا نشده

---

## ۰. قواعد استفاده

1. یک گام در هر زمان؛ ✅ فقط با شواهد (تست، Run، Release، سند). شمارهٔ نسخه به‌تنهایی مدرک تکمیل نیست.
2. وضعیت در همان PR به‌روز می‌شود.
3. **دامنه فقط GUI است** (سند مرجع §10): بدون تغییر Store/State Schema، Event Ledger، workflow، Publisher، Build یا Installer. اگر View به Action تازه نیاز داشت، به‌عنوان «وابستگی» ثبت می‌شود.
4. Tkinter/ttk می‌ماند (ADR-007). تغییر Toolkit فقط با ADR تازه و اندازه‌گیری.
5. «NOT RUN» صریح می‌ماند: آزمون کاربر مستقل، Windows فیزیکی با DPI مختلف و چت واقعی مدل که اجرا نشده‌اند PASS اعلام نمی‌شوند. CI مجازی معادل DPI فیزیکی نیست.
6. قرارداد PR مربوط به UI (سند مرجع §7.3) و قواعد ضدوصله‌پینه (§7.1) برای هر PR الزامی است.
7. تغییر View/Theme/Inspector هرگز Revision یا Event دامنه نمی‌سازد (UX-18).

## ۱. نسخه‌بندی

شماره‌های مراحل، مراحل طراحی‌اند نه تضمین نسخهٔ نرم‌افزار (سند مرجع §5). نگاشت اجرایی:

| نسخه | مراحل سند مرجع | محتوا |
|---|---|---|
| 2.7.0 | 0، 1، 2، 3، 4 | Audit و Screenshotهای Baseline، تحقیق، IA و ۱۰ جریان کار، Wireframe، Design System (سند + توکن‌های معنایی) |
| 2.8.0 | 5 | پوستهٔ تازه و کامپوننت‌های مشترک، Component gallery |
| 2.9.0 | 6 | بازطراحی Overview، Tasks، Team، Timeline، Deliveries، Files & Context، Settings |
| 2.10.0 | 7، 8، 9 | ماتریس Responsive/RTL/Contrast/Keyboard، ارزیابی Heuristic و بازنگری، Release Gate GUI |

## ۲. وضعیت مراحل

| مرحله | نام | وضعیت | شواهد |
|---|---|---|---|
| 0 | Baseline و Audit | ✅ | `docs/audit/GUI_AUDIT_FA.md`، `docs/audit/screens/v2.6.0/`، `tools/gui_screenshots.py` |
| 1 | تحقیق موج اول | ✅ | `docs/specs/GUI_RESEARCH_FA.md` §۱–۳ |
| 2 | UX/IA و تحقیق موج دوم | ✅ | `docs/specs/GUI_INFORMATION_ARCHITECTURE_FA.md` (آزمون کاربر: NOT RUN) |
| 3 | Wireframe و Layout | ✅ | `docs/specs/GUI_WIREFRAMES_FA.md` (آزمون وظیفه: NOT RUN) |
| 4 | تحقیق نهایی و Visual system | ✅ | `docs/specs/GUI_DESIGN_SYSTEM_FA.md`، `workspace/theme.py`، `test_gui_design_system.py` |
| 5 | Core shell و کامپوننت‌ها | ⬜ | |
| 6 | بازطراحی نماها (6A–6E) | ⬜ | |
| 7 | Responsive، RTL/LTR، Accessibility | ⬜ | |
| 8 | ارزیابی استفاده‌پذیری و بازنگری | ⬜ | |
| 9 | یکپارچه‌سازی و انتشار کنترل‌شده | ⬜ | |

## ۳. موارد NOT RUN که فقط مالک محصول می‌تواند اجرا کند

- آزمون وظیفه با ۵ کاربر مستقل (Gate 2، 3، 8؛ معیارهای §1.3).
- Windows فیزیکی با DPI 100/125/150/200٪ و دو مانیتور (Gate 7، UX-16).
- سناریوهای دستی UX-03 تا UX-10 با چت واقعی مدل (Gate انتشار §9.2).
- از Roadmap قبلی: E2E با دو چت واقعی، Companion روی گوشی واقعی.

## ۴. اسناد

| سند | نقش |
|---|---|
| `docs/specs/AI_Workbench_GUI_Only_Roadmap_FA_v1.0.md` | منبع جزئیات این Roadmap |
| `docs/roadmap/archive/` | Roadmapهای کامل‌شدهٔ قبلی (superseded) |
| `docs/adr/ADR-007-workspace-gui-technology-v2.3.0.md` | تصمیم Tkinter/ttk |
| `docs/specs/*` دیگر | مشخصات رفتار موجود (مرجع، تغییر نمی‌کند) |
