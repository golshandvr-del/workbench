# ADR-009 — پوستهٔ واحد و تم Fluent (desktop 3.0.0)

**وضعیت:** پذیرفته‌شده · **تاریخ:** 2026-10-19 · **جایگزین بخشی از:** ADR-007 (پنجرهٔ Workspace جدا)

## مسئله
در 2.6/2.7 «Project Workbench» یک `Toplevel` جدا با Style، زبان، تم و Mode خودش بود؛ پنجرهٔ اصلی ۵۴ رنگ hard-code و تم `clam` داشت.
نتیجه: حس «دو اپ»، تم/زبان ناهمگون، Simple/Advanced فقط در یک گوشه، و ظاهر ساده و غیرحرفه‌ای (P1، P3، P8 در ROADMAP).

## تصمیم
1. **یک پنجره** (`aiwb/ui/shell.py` → `AppShell`): Nav rail + نوار عنوان + Page stack (`ttk.Notebook` با تب‌های پنهان، تا `notebook.select(tab)`های موجود سالم بمانند) + Status bar.
   همهٔ تب‌های قبلی و Workbench «صفحه» هستند. `WorkspaceWindow(host=...)` داخل صفحهٔ Workbench جاسازی می‌شود؛ حالت Toplevel فقط برای ابزار/تست می‌ماند.
2. **یک تنظیمات** (`aiwb/ui/prefs.py` → `AppPrefs`): تم، زبان و Mode در `settings.json` برنامه (`ui_theme`/`ui_lang`/`ui_mode`)؛ با Observer همهٔ صفحات بلافاصله عوض می‌شوند.
   تنها محل تغییر: صفحهٔ Settings. تغییر نما هیچ State پروژه‌ای را عوض نمی‌کند (تست).
3. **Mode سراسری:** Simple = مسیر هدایت‌شده (Home، Workbench، Prompt، AI Response، Settings)؛ Advanced = + Profile، History، Run، Git. ناوبری صریح به صفحهٔ پیشرفته، Advanced را روشن می‌کند.
4. **یک ظاهر** (`aiwb/ui/appearance.py`): تم **Sun Valley 2.6.1** (Fluent، MIT، ~۹۰KB، فقط Tcl+PNG، بدون وابستگی pip) vendored در `aiwb/ui/sv_theme/` بدون تغییر.
   همهٔ Styleها (کلاسیک و `WS.*`) روی توکن‌های معنایی `workspace/theme.py` نگاشت می‌شوند؛ ویجت‌های کلاسیک Tk با پیمایش درخت رنگ می‌گیرند. اگر Tcl تم را بار نکند، `clam` + توکن (بدون خطا).
5. **ممنوعیت رنگ hard-code** در `AI_Workbench.py` و `aiwb/ui` (تست).

## پیامدها
- Workbench دیگر زبان/تم جدا ندارد؛ RTL نوار ناوبری را آینه می‌کند.
- ابعاد پنجره به Work area صفحه محدود است (`fit_to_screen`)؛ حداقل اندازه هرگز بزرگ‌تر از صفحه نیست. دیالوگ‌ها در 3.1.0 به `place_dialog` منتقل می‌شوند.
- Installer فایل‌های `.tcl`/`.png` را هم نصب می‌کند (manifest + install.ps1، بررسی با `check_installer_manifest.py`).

## آزمون
`test_single_shell.py` و `tests/gui/gui_single_shell_smoke.py` (Gate 3.0.0) + همهٔ smokeهای قبلی.
NOT RUN: Windows فیزیکی با DPI 125/150/200٪.
