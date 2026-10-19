# Design System رابط Workbench (GUI roadmap، مرحلهٔ 4)

**نسخهٔ Design System:** 1.0 (2026-10-19) · **منبع کد:** `apps/desktop/src/aiwb/workspace/theme.py` (توکن‌ها) و `workspace/components.py` (کامپوننت‌ها، از 2.8.0)
**قاعدهٔ اصلی:** هیچ View رنگ، فونت، فاصله یا شعاع خام تعریف نمی‌کند. تست `test_gui_design_system.py` این را بررسی می‌کند.

## ۱. جهت بصری

ابزار کاری خنثی و دقیق: سطوح خاکستری روشن/تیره، یک رنگ تأکیدی آبی برای انتخاب جاری و اقدام اصلی، رنگ‌های وضعیت فقط برای وضعیت واقعی و همیشه همراه نماد + متن. بدون سایه، گرادیان، انیمیشن تزئینی و کارت. سلسله‌مراتب با تایپوگرافی و فاصله.

## ۲. توکن‌های رنگ (معنایی)

| توکن | Light | Dark | کاربرد |
|---|---|---|---|
| `bg` | `#f5f6f8` | `#15181d` | پس‌زمینهٔ پنجره و ناحیهٔ محتوا |
| `surface` | `#ffffff` | `#1d2127` | جدول‌ها، Inspector، فیلدها |
| `surface_alt` | `#eef0f3` | `#242930` | سربرگ جدول، ردیف «قدم بعدی» |
| `sidebar` | `#eceef2` | `#191c21` | Sidebar |
| `field` | `#ffffff` | `#111418` | ورودی متن (Entry، Text، Listbox) |
| `text` | `#1b2129` | `#e5e8ed` | متن اصلی |
| `muted` | `#5a6472` | `#9da6b3` | متن ثانویه، توضیح، زمان |
| `border` | `#c9ced6` | `#3a414b` | جداکنندهٔ تزئینی (غیرالزامی برای فهم) |
| `border_strong` | `#7c8592` | `#7a8494` | مرز فیلد و کنترل (≥3:1، WCAG 1.4.11) |
| `divider` | `#e2e5ea` | `#2b3038` | خط بین بخش‌ها |
| `selected` / `selected_text` | `#dbe6fb` / `#10213f` | `#2a3b5e` / `#eef3ff` | ردیف و مقصد انتخاب‌شده |
| `focus` | `#2f5fd0` | `#86a8ff` | حلقهٔ Focus (≥3:1 روی bg/surface) |
| `accent` / `accent_text` / `accent_hover` | `#2456c4` / `#ffffff` / `#1d47a6` | `#7ea3ff` / `#0b1322` / `#9bb8ff` | فقط Primary و نشانگر مقصد فعال |
| `success` | `#1c6b35` | `#7ad295` | تأییدشده با شاهد |
| `warning` | `#8a5300` | `#f0bf5c` | نیاز به اقدام / ناقص / قدیمی |
| `danger` | `#b0201c` | `#ff8f8a` | مسدودکننده / خطا / Destructive |
| `info` | `#265f99` | `#8fc0ff` | اطلاع |
| `banner_{info,warning,danger,success}` | ‌پس‌زمینهٔ کم‌رنگ هم‌خانواده | پس‌زمینهٔ تیرهٔ هم‌خانواده | Banner درون‌صفحه؛ متن رنگ وضعیت روی آن ≥4.5:1 |

**کنتراست (تست خودکار):** هر `text|muted|success|warning|danger|info|accent` روی هر سطح (`bg, surface, surface_alt, sidebar, field, selected, banner_*`) ≥ 4.5:1 · `accent_text` روی `accent`/`accent_hover` ≥ 4.5:1 · `focus` و `border_strong` روی `bg`/`surface` ≥ 3:1.

## ۳. تایپوگرافی

| نقش | اندازه (pt) | وزن | کاربرد |
|---|---|---|---|
| `page_title` | 15 | bold | عنوان صفحه (یکی در هر نما) |
| `section_title` | 11 | bold | عنوان بخش داخل صفحه، عنوان Inspector |
| `body` | 10 | normal | متن و جدول |
| `secondary` | 9 | normal | توضیح، Status line، زمان |
| `caption` | 8 | normal | برچسب کوچک (کم‌استفاده) |
| `code` | 9 | normal | شناسه/مسیر/پرامپت؛ خانوادهٔ monospace |

خانواده: Windows ← `Segoe UI` (UI)، `Consolas` (code)؛ اگر نصب نیست، Tk به فونت سیستم برمی‌گردد. اندازه‌ها مثبت = pt تا با DPI ویندوز مقیاس بگیرند.

## ۴. فاصله، شکل، کنترل، Layout

- **Spacing** (`space.N`، واحد پایه 4px): `0=0, 1=4, 2=8, 3=12, 4=16, 6=24, 8=32`. نام‌های قدیمی `xs/s/m/l/xl` نگاشت به `0.5/1/2/3/4` و فقط برای سازگاری.
- **Shape:** `radius` 0 (ttk شعاع ندارد؛ گوشهٔ صاف یکدست)، `border_width` 1.
- **Control:** ارتفاع دکمه/فیلد ≈ 28px در 100٪ (`padding` 10×4)، `row_height` 26px، هدف کلیک ≥24px.
- **Layout:** `sidebar_width` 176، `sidebar_compact_width` 72، `inspector_width` 300 (≥1280) / 260، `content_min_width` 560، breakpoints `INSPECTOR_STACK_BELOW=1100`، `SIDEBAR_COMPACT_BELOW=900`، `MIN_SIZE=960×600`، `inspector_stacked_max` 30٪ ارتفاع.

## ۵. سلسله‌مراتب دکمه

| نوع | Style ttk | قاعده |
|---|---|---|
| Primary | `WS.Primary.TButton` | حداکثر یکی در هر نما؛ فعل + مفعول |
| Secondary | `WS.TButton` | اقدام مهم غیرغالب |
| Quiet | `WS.Quiet.TButton` | اقدام ردیفی/ابزار؛ بدون قاب |
| Danger | `WS.Danger.TButton` | رد/حذف؛ همیشه با تأیید یا برگشت‌پذیر |
| Nav | `WS.Nav.TButton` / `WS.NavActive.TButton` | فقط Sidebar |

اقدام نامجاز نمایش داده نمی‌شود (به‌جای Disabled بی‌دلیل).

## ۶. کامپوننت‌های مشترک (`workspace/components.py`)

| کامپوننت | قرارداد |
|---|---|
| `page_header(parent, title, purpose, actions)` | عنوان + جملهٔ هدف + ناحیهٔ اقدام (Primary آخر در LTR، اول در RTL) |
| `section(parent, title)` | عنوان بخش + فاصله؛ بدون کادر (جایگزین `LabelFrame`) |
| `banner(parent, level, text)` | `info/warning/danger/success`؛ نماد + متن؛ پس‌زمینهٔ `banner_*` |
| `button_row(parent, items, rtl)` | ترتیب دکمه‌ها با جهت |
| `table(parent, columns, height)` | Treeview + Scrollbar با `row_height`؛ heading و ردیف انتخاب از توکن |
| `style_text(widget, pal, code)` | رنگ‌دهی ویجت کلاسیک (`Text`/`Listbox`/`Spinbox`) |
| `kv(parent, rows)` | فهرست «برچسب: مقدار» برای Inspector |
| `empty_state(parent, text)` | یک جملهٔ muted |
| `status_badge(kind)` | نماد + متن از `i18n.status` (رنگ مکمل، نه جایگزین) |

## ۷. حالت‌های تعامل

`default · hover (accent_hover برای Primary، surface_alt برای بقیه) · focus (حلقهٔ focus) · selected (selected/selected_text) · disabled (muted) · busy (Status line «در حال …»، دکمه غیرفعال) · invalid (Banner danger + متن خطا کنار فیلد)`.

## ۸. محتوا و زبان

خطا = چه شد · اثر · چه چیزی حفظ شد · چه کنید. وضعیت بیرونی منبع دارد («ثبت‌شده توسط شما»، «از GitHub»). متن فارسی کامل، نه ترجمهٔ کوتاه. شناسه‌ها LTR در متن RTL.

## ۹. مثال درست و نادرست

| نادرست | درست |
|---|---|
| `ttk.Label(..., foreground="#a3161b")` | `ttk.Label(..., style="WS.danger.TLabel")` |
| `ttk.LabelFrame` تودرتو برای هر بخش | `components.section(parent, title)` |
| دکمهٔ «Do it» | «Review delivery HO-0002» |
| `tk.Text(...)` بدون تم | `components.style_text(tk.Text(...), pal)` |
| «Released ✓» سبز بر اساس متن کاربر | «◉ released — recorded by you (tag v1.0)» |

## ۱۰. استثناها

| استثنا | دلیل | محدوده | مالک | بازبینی |
|---|---|---|---|---|
| پنجره‌ها و Dialogهای کلاسیک (`AI_Workbench.py`) از این سیستم استفاده نمی‌کنند | خارج از Scope این Roadmap (پنجرهٔ کلاسیک) | فقط ابزارهای کلاسیک | مالک محصول | پس از 2.10.0 |

## ۱۱. Gate 4

- [x] همهٔ صفحات Wireframe با همین توکن‌ها و کامپوننت‌ها قابل ساخت‌اند (نگاشت §۶ ↔ `GUI_WIREFRAMES_FA.md`).
- [x] کنتراست همهٔ جفت‌ها برای Light و Dark محاسبه و تست می‌شود.
- NOT RUN: نمونهٔ Hi-Fi روی نمایشگر Windows واقعی و فونت Segoe UI. Hi-Fi در Xvfb با Screenshotهای 2.8.0 ثبت می‌شود.

**نتیجه:** Gate 4 — PASS (با NOT RUN صریح).

## Changelog Design System

- **1.0** (2026-10-19): نسخهٔ اول؛ جایگزین Palette ۱۴ رنگی 2.3.0.
