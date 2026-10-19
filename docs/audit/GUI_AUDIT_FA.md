# ممیزی GUI — وضعیت پایهٔ Desktop 2.6.0 (GUI roadmap، مرحلهٔ 0)

**تاریخ:** 2026-10-19 · **نسخه:** `desktop-v2.6.0` (main `9ca55dc`) · **مرجع:** `docs/specs/AI_Workbench_GUI_Only_Roadmap_FA_v1.0.md` §5 مرحلهٔ 0

## ۱. شرایط ثبت شواهد

| مورد | مقدار |
|---|---|
| ابزار | `tools/gui_screenshots.py` (قابل تکرار؛ `manifest.json` شرایط هر تصویر را ثبت می‌کند) |
| مجموعه Screenshot | `docs/audit/screens/v2.6.0/` — ۷ نما × Light/Dark × en/fa × `1280x720`/`1024x640`، به‌علاوهٔ «با انتخاب» برای Tasks و Team (۷۲ تصویر) |
| داده | `tests/fixtures_ten_agents.py` (۱۰ Agent، ۲ Task برای هر کدام، یک Decision، پاسخ ناقص، پاسخ قدیمی، پاسخ بدقالب) |
| محیط | Linux + Xvfb، `tk scaling` = 1.333 (≈96 DPI)، فونت پیش‌فرض سیستم (Segoe UI موجود نیست ← جایگزین DejaVu/Noto) |
| محدودیت | **Windows فیزیکی، DPI 125/150/200٪ و فونت Segoe UI: NOT RUN.** تصاویر Linux معادل Windows نیستند. |
| تأیید عدم تغییر State | ابزار پس از ۷۲ عکس `state_revision` و تعداد رویدادهای Ledger را مقایسه می‌کند: بدون تغییر (UX-18). |

## ۲. Baseline عملکرد (همین سندباکس، `tools/measure_baseline.py`، ۲۰۰ Task / ۲۰۰۰ رویداد)

| شاخص | مقدار |
|---|---|
| import برنامه | 191 ms |
| ساخت پنجرهٔ اصلی | 186 ms |
| باز کردن پروژه (میانه) | 149 ms |
| Read modelها (میانه) | overview 99 · task_rows 53 · timeline_page 15 · lanes 42 · team 27 · attention 28 · dashboard 29 ms |
| حافظه (max RSS) | 55.7 MiB |
| Payload نصب | 107 فایل، 2.15 MB |

## ۳. فهرست اجزای موجود Workspace (`apps/desktop/src/aiwb/workspace/`)

**پوسته (`shell.py`، ۹۱۹ خط):** Project Bar (☰، نام پروژه/هدف، وضعیت انتشار، Combobox حالت Simple/Advanced، Combobox زبان، Combobox تم، دکمهٔ ⓘ) · نوار Next Action تمام‌عرض با دکمهٔ «Do it» · Sidebar با ۷ دکمه · ناحیهٔ مرکزی · Inspector (عنوان، `tk.Text`، دکمه‌های عملیات) · Footer وضعیت.

**نماها و کنترل‌ها:**

| نما | کنترل‌ها | ابزار کلاسیکی که باز می‌کند |
|---|---|---|
| Overview | هدف، متن پیشرفت، Progressbar، شمارش وضعیت‌ها، Treeview «نیازمند توجه» (Open / Mark as read / Show read)، فعالیت اخیر، «Plan project…» | — |
| Timeline | Combobox نوع، Entry متن، Filter، صفحه‌بندی ‹ ›، «Lanes by agent»، Treeview رویدادها، جدول Milestone/Version، ۴ دکمه (New milestone، Accept milestone، Propose version، Record commit/tag/release) | — |
| Tasks | Treeview (Task، Status، Workflow، Agent)، `Text` پرامپت، `Text` پاسخ، Copy prompt، Check & import answer (Primary) | — |
| Team | شمارش وضعیت، Entry فیلتر، Checkbutton «needs action only»، Filter، Treeview ۸ ستونه، Listbox پروفایل‌های اکانت (Add / Enable-disable)، Team planning (Spinbox، Combobox PM، Save، Plan team & tasks Primary)، بازبینی Proposal (Accept selected Primary، Reject all، Request changes) | — |
| Files & Context | یک جمله + ۳ دکمه | Classic prompt & response، Response Inbox، Context request |
| Versions & Builds | یک جمله + ۲ دکمه | Build Center، Sync & Build |
| Settings | یک جمله میان‌برها + ۲ دکمه | Mobile Companion، Projects window (classic) |

**Dialogها:** ۱۲ فراخوانی `simpledialog`/`messagebox`/`Toplevel` (Plan project، Request a change با دو پرسش متنی پشت‌سرهم، Add account، Bind chat با ورود دستی ID، Project brief، Milestone، Version، Advance version، تأیید Start تکراری، …).

**توکن‌ها (`theme.py`):** دو Palette (۱۴ رنگ)، SPACING ۵ پله، FONT_SIZES ۴ پله، Breakpoints (`INSPECTOR_STACK_BELOW=1100`، `SIDEBAR_COMPACT_BELOW=900`)، MIN_SIZE `960x600`، تست کنتراست 4.5:1.

## ۴. مشکلات (هر مورد: مدرک · اثر بر کاربر · اولویت)

اولویت: **P1** = در مسیر اصلی کار را خراب/گمراه می‌کند · **P2** = اصطکاک قابل توجه · **P3** = پولیش.

### ۴.۱ IA / UX

| ID | مشکل | مدرک | اثر | اولویت |
|---|---|---|---|---|
| IA-1 | سه نمای Files & Context، Versions & Builds و Settings فقط یک جمله و چند دکمهٔ «باز کردن ابزار کلاسیک» دارند؛ محتوای خودِ مقصد وجود ندارد. | `settings_*`، `files_*`، `versions_*` | کاربر وارد مقصد اصلی می‌شود و هیچ وضعیتی نمی‌بیند؛ مقصد سطح‌اول عملاً «لانچر» است. | P1 |
| IA-2 | Next Action تمام‌عرض با دکمهٔ Primary «Do it / انجام بده» در همهٔ نماها تکرار می‌شود و با Primary داخل صفحه (مثلاً «Check & import answer») رقابت می‌کند؛ متن دکمه نتیجه را نمی‌گوید. | همهٔ تصاویر | دو Primary هم‌زمان؛ «انجام بده» مبهم (سند مرجع §6.3). فرضیهٔ ۲ تأیید شد. | P1 |
| IA-3 | Milestone/Version داخل Timeline هستند، Build/Release در «Versions & Builds». مفهوم تحویل در دو مقصد پخش شده است. | `timeline_*`، `versions_*` | سناریوی ۹ (Build با چه شاهدی) دو مقصد دارد. | P2 |
| IA-4 | Request a change با دو `simpledialog` پشت‌سرهم و تایپ نام مسیر (`fix_task` / `new_task` / `replan`) انجام می‌شود. Bind chat هم ID اکانت را با تایپ می‌گیرد. | `shell.dialog_change_request`، `dialog_bind_chat` | انتخاب مسیر با تایپ رشتهٔ فنی؛ خطای انسانی محتمل (UX-08). | P1 |
| IA-5 | تیم: جدول Agentها، Listbox اکانت‌ها، تنظیمات برنامه‌ریزی و بازبینی Proposal همگی در یک صفحهٔ عمودی؛ در `1024x640` جدول Agentها **کاملاً ناپدید** می‌شود (ارتفاع صفر). | `team_*_1024x640.png` | کار اصلی (دیدن Agentها) در پنجرهٔ محدود ممکن نیست (UX-15). | P1 |
| IA-6 | در `1024x640` با Inspector انباشته (stacked)، Treeview وظایف به ارتفاع صفر می‌رسد. | `tasks_*_1024x640_sel.png` | فهرست Task دیده نمی‌شود. | P1 |
| IA-7 | انتخاب Mode (simple/advanced) در Project Bar کنار زبان و تم؛ هیچ‌کدام کار روزانه نیستند. | همهٔ تصاویر | Project Bar شلوغ؛ فرضیهٔ ۱ تأیید شد. | P2 |
| IA-8 | فعالیت اخیر و Timeline کد خام رویداد را نشان می‌دهند (`attempt_status att-2026… exported → waiting_response`، `change`). | `overview_*`، `timeline_*` | زبان کاربر نیست؛ تشخیص رویداد واقعی سخت (سناریو ۱۰). | P2 |
| IA-9 | Overview بدون هدف «No goal yet» نشان می‌دهد ولی هم‌زمان ۱۸ مورد «Ready to start» در صف توجه دارد؛ «Ready to start» اطلاع است نه اقدام فوری. | `overview_light_en_1280x720.png` | صف اضطراری با موارد عادی شلوغ می‌شود (6A). | P2 |
| IA-10 | پرامپت و پاسخ دو `Text` خالی زیر جدول‌اند، بدون نشان دادن اینکه پرامپت به کدام Task/Handoff تعلق دارد و آیا کپی/ارسال شده است. | `tasks_*` | UX-03/04: وضعیت «آماده / کپی‌شده / ارسال‌شده» در کنار متن دیده نمی‌شود. | P1 |

### ۴.۲ Visual hierarchy

| ID | مشکل | مدرک | اولویت |
|---|---|---|---|
| VH-1 | Sidebar با دکمه‌های برجستهٔ ttk (قاب سه‌بعدی) ساخته شده؛ مقصد فعال فقط با Bold متمایز است. | همه | P2 |
| VH-2 | عنوان صفحه (12pt) هم‌اندازهٔ عنوان Next Action است؛ نقطهٔ تمرکز غالب ندارد. | همه | P2 |
| VH-3 | `LabelFrame`های پی‌درپی (Needs attention، Recent activity، Account profiles، Team planning، Milestones) کادر روی کادر می‌سازند. | `overview_*`، `team_*` | P2 |
| VH-4 | Inspector خالی ۴۰٪ ارتفاع را با متن «Nothing selected» در فونت monospace می‌گیرد. | همه بدون `_sel` | P3 |

### ۴.۳ Component consistency

| ID | مشکل | مدرک | اولویت |
|---|---|---|---|
| CC-1 | **Dark mode ناقص:** `tk.Text`، `Listbox`، Treeview، Entry، Combobox و دکمه‌ها رنگ تم را نمی‌گیرند (سفید/خاکستری روشن روی پس‌زمینهٔ تیره). | `*_dark_*` | P1 |
| CC-2 | Treeview در Dark به‌صورت نوار خالی و فشرده رندر می‌شود (heading بدون متن). | `tasks_dark_en_1024x640_sel.png` | P1 |
| CC-3 | سه سبک دکمه درهم: `WS.Primary` (آبی پر)، ttk پیش‌فرض، و دکمه‌های Inspector تمام‌عرض. فقط ۴ جای Primary تعریف شده؛ ۳۰ دکمه بدون سلسله‌مراتب. | `shell.py` | P2 |
| CC-4 | Inspector متن را در `tk.Text` (monospace، بدون ساختار) می‌ریزد؛ ساختار (وضعیت، مالک، گام) فقط متن خطی است. | `tasks_*_sel` | P2 |
| CC-5 | Footer وضعیت (`WS.Muted`) کوچک‌ترین متن صفحه است ولی پیام‌های مهم («هنوز ارسال نشده») آنجا نمایش داده می‌شوند. | `shell.inspector_action` | P1 |

### ۴.۴ Responsive / Accessibility

| ID | مشکل | مدرک | اولویت |
|---|---|---|---|
| RA-1 | **RTL ناقص:** در فارسی Sidebar همچنان سمت چپ است، Project Bar و Inspector جابه‌جا نمی‌شوند؛ فقط متن‌ها راست‌چین‌اند. فلش Next Action «←» است ولی جای دکمه تغییر نمی‌کند. | `*_fa_*` | P1 |
| RA-2 | متن فارسی در Tk روی Linux بدون shaping (حروف جدا) نمایش داده می‌شود. روی Windows (Uniscribe) shaping انجام می‌شود؛ این مورد **محیطی** است و باید روی Windows فیزیکی تأیید شود (NOT RUN). | `*_fa_*` | — (محیطی) |
| RA-3 | `MIN_SIZE=960x600` ولی در `1024x640` محتوای Team/Tasks حذف می‌شود؛ هیچ اسکرول عمودی برای کل صفحه وجود ندارد. | `*_1024x640*` | P1 |
| RA-4 | Focus قابل مشاهدهٔ ttk پیش‌فرض (خط‌چین کم‌رنگ) در Dark دیده نمی‌شود؛ میان‌برها فقط در Settings ذکر شده‌اند. | تحلیل کد + `*_dark_*` | P2 |
| RA-5 | رنگ‌های وضعیت در Treeview استفاده نمی‌شوند (فقط نماد ▶ … ✓)؛ این از نظر «رنگ تنها نشانه نیست» درست است ولی وضعیت‌های بحرانی هم بصری متمایز نیستند. | `tasks_*` | P3 |

## ۵. ماتریس مسیرهای کاربر (سناریوهای §2 سند مرجع) در 2.6.0

| # | سناریو | مسیر فعلی | مشکل اصلی |
|---|---|---|---|
| 1 | اولین باز کردن و یافتن اقدام بعدی | Next Action بالای صفحه | دکمهٔ مبهم «Do it» (IA-2) |
| 2 | آماده‌سازی و کپی پرامپت | Inspector → Prepare prompt → Tasks → Copy prompt | وضعیت «هنوز ارسال نشده» فقط در Footer (CC-5، IA-10) |
| 3 | تأیید ارسال و بازگشت با پاسخ | Inspector → I sent it → Paste → Check & import | پاسخ به کدام Handoff وصل می‌شود دیده نمی‌شود |
| 4 | پاسخ ناقص و Repair | Needs attention → Open → Inspector | Repair در Inspector، پاسخ قبلی دیده نمی‌شود |
| 5 | قابلیت جدید: ادامه / Task جدید / Re-plan | Inspector → Request a change → دو پرسش متنی | تایپ نام مسیر (IA-4) |
| 6 | Context Request | Paste → Files & Context → ابزار کلاسیک | مقصد بدون محتوا (IA-1) |
| 7 | بازبینی Team Proposal | Team → پایین صفحه | در پنجرهٔ محدود قابل دسترس نیست (IA-5) |
| 8 | ۱۰ Agent و موارد نیازمند اقدام | Overview صف توجه / Team | صف با «Ready to start» شلوغ (IA-9) |
| 9 | Build/Version با چه شاهدی | Timeline (Version) + Versions & Builds (Build) | پخش در دو مقصد (IA-3) |
| 10 | فعالیت گذشته و رویداد واقعی | Timeline | کد خام رویداد (IA-8) |

## ۶. فهرست «نباید تغییر کند» (Gate 0)

State Schema و `db_version` · `v2/store`، `v2/models` و Event Ledger (`event-ledger.v1`) · وضعیت‌های Task/Workflow و قواعد Attempt/Handoff · Inbox، Repair، Context Request و parserها · Account Profile / Chat Binding · Team Planner (`team-proposal.v1`) و منطق پذیرش/رد · Dashboard و رتبه‌بندی Needs Attention (`v2/dashboard.py`) · `v2/changes.py` · GitHub/Publisher/Build Center/Sync & Build · Installer و `release_manifest.json` · مسیر دستی کپی/پیست (بدون ارسال خودکار) · ذخیرهٔ ترجیحات در `ui.json` (نه State پروژه) · `WorkspaceController` API موجود (فقط افزودنی، بدون تغییر معنای متدهای فعلی).

## ۷. Gate 0

- [x] هر مشکل مدرک (Screenshot یا خط کد)، اثر و اولویت دارد.
- [x] Baseline عملکرد و Screenshot با شرایط ثابت ثبت شد.
- [x] فهرست «نباید تغییر کند» ثبت شد.
- [x] هیچ تغییر کد بصری در این مرحله انجام نشده است (فقط `tools/gui_screenshots.py` و سند).
- NOT RUN: Screenshot روی Windows فیزیکی و DPI 125/150/200٪.

**نتیجه:** Gate 0 — PASS (با NOT RUN صریح).
