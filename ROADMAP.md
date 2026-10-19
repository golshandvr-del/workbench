# AI Workbench — نقشه‌راه اصلی (Master Roadmap 3.x) — بازسازی محصول

> **این فایل تنها مرجع اجرایی ترتیب توسعه است.** هر PR باید به یک گام همین فایل اشاره کند.
> Roadmapهای قبلی در `docs/roadmap/archive/` بایگانی شده‌اند (superseded): `ROADMAP_v2.7-v2.10_GUI-only_FA.md`، `ROADMAP_v2.3-v2.6_FA.md`، `ROADMAP_v1.14-v2.2_FA.md`.

**آخرین به‌روزرسانی:** 2026-10-19 · **Desktop منتشرشده:** `desktop-v3.8.0` · **Mobile منتشرشده:** `mobile-v1.0.0`
**گام فعال:** 3.9.0 — Release Gate محصول

راهنما: ✅ کامل (Gate پاس) · 🟡 بخشی · ⬜ شروع‌نشده · NOT RUN = اجرا نشده

---

## ۰. هدف محصول (بدون تغییر، ولی این بار واقعاً)

کاربر **بدون API و بدون لاگین در اپ**، فقط با چت‌های معمولی (ChatGPT، Gemini، Claude، …) پروژه‌اش را جلو می‌برد.
اپ فقط دو کار با مدل‌ها دارد: **پرامپت می‌سازد** (کاربر کپی می‌کند) و **خروجی مدل را می‌گیرد** (کاربر Paste/فایل می‌دهد).
هیچ راه ارتباطی دیگری با مدل‌ها وجود ندارد و نخواهد داشت.

**تعریف موفقیت:** کاربر از «ایدهٔ پروژه» تا «نسخهٔ منتشرشده» بدون بن‌بست می‌رود؛ در هر لحظه اپ دقیقاً یک «قدم بعدی» با پرامپت آماده نشان می‌دهد.

## ۱. ریشه‌یابی مشکلات نسخهٔ 2.6/2.7

| # | مشکل گزارش‌شده | ریشه | راه حل (نسخه) |
|---|---|---|---|
| P1 | «لباس وصله‌پینه»؛ Project Workbench یک اپ دیگر با زبان/تم جدا | دو پنجره (`WorkbenchApp` و `WorkspaceWindow` به‌صورت Toplevel)، دو سیستم Style (۵۴ رنگ hard-code در کلاسیک + `WS.*`)، تنظیمات نمایش فقط داخل Workspace | یک پنجره، یک ناوبری، یک Theme، یک Settings برای کل اپ (3.0.0) |
| P2 | دیالوگ‌ها از کادر بیرون می‌زنند؛ دکمه‌ها در پنجرهٔ کوچک دیده نمی‌شوند؛ تقارن ندارد | ۲۲+۱۴ Toplevel با `geometry` ثابت، Toolbarهای `pack(side=left)` بدون wrap، نبود Grid مشترک | `ui/layout.py`: قرار دادن همهٔ دیالوگ‌ها در Work area، Toolbar جریانی (wrap)، صفحات Scrollable، Grid فاصله‌گذاری ۴px؛ تست خودکار overflow (3.1.0) |
| P3 | Simple/Advanced فقط در Workbench و بی‌اثر | Mode فقط در `ProjectsController` و فقط چند Label را عوض می‌کرد | Mode سراسری: Simple = مسیر هدایت‌شده (Home → قدم بعدی)، صفحات پیشرفته پنهان؛ Advanced = همه‌چیز (3.0.0) |
| P4 | بعد از Paste خروجی مدل «هیچ کاری نمی‌شود کرد»؛ پرامپت بعدی تولید نمی‌شود | `next_action` فقط «نوع» عمل را می‌گوید؛ بسیاری از عمل‌ها (approve_task، start_task، …) پرامپت نمی‌سازند و دکمه فقط به Tasks می‌برد | موتور «حلقهٔ هدایت‌شده» (Guided Loop): هر وضعیت → یک قدم با پرامپت/دکمهٔ واقعی؛ تست ثابت «هیچ وضعیتی بن‌بست نیست» + E2E شبیه‌سازی‌شده (3.4.0) |
| P5 | Timeline گرافیکی (دایره با اندازهٔ اهمیت، خطوط عمودی نسخه) وجود ندارد | Timeline فقط Treeview متنی است | ویجت Canvas اختصاصی: محور افقی زمان، دایره با اندازهٔ اهمیت، خط عمودی برای هر نسخه، Lane هر Agent، Zoom/Scroll/Tooltip (3.5.0) |
| P6 | پرامپت اولیه معماری کامل پروژه را تعریف نمی‌کند (تعداد AI موازی، هماهنگی، Roadmap، وظیفهٔ هر AI) | `planning_prompt`/`team_planning_prompt` فقط «تیم + ۳ تا ۸ Task» می‌خواهد | قرارداد تازهٔ **Project Charter** (`project-charter.v1`): معماری، تیم موازی، پروتکل هماهنگی، Roadmap با نسخه‌ها، نقش و پرامپت شروع هر AI؛ Import یک‌جا (3.3.0) |
| P7 | GPT Output هنوز خراب دریافت می‌شود | Parserها روی متن خام کار می‌کنند؛ کپی از ChatGPT کاراکترهای پنهان (NBSP، zero-width، نقل‌قول هوشمند)، escape مارک‌داون (`\<\<\<`، `\_`)، HTML entity، fence اضافه، ویرگول انتهایی و JSON بریده‌شده می‌آورد | لایهٔ `intake/normalize.py` پیش از همهٔ Parserها + پیکرهٔ تست از الگوهای واقعی خرابی GPT + تشخیص بریدگی و پرامپت «ادامه بده» خودکار (3.2.0) |
| P8 | GUI ساده و «AI-ساخت» | ttk `clam` پیش‌فرض، بدون سلسله‌مراتب بصری | تم Fluent (Sun Valley، MIT، ۹۲KB، فقط Tcl+PNG، بدون وابستگی Python) + کارت‌ها، Command bar، Nav rail با آیکن، Typography نقش‌محور (3.0.0) |
| P9 | کد اتصال موبایل خیلی طولانی | Base64 شناسه + کلید ۳۲ بایتی + آدرس | QR (رندر با Canvas، کتابخانهٔ QR خالص vendored) + Deep link `aiwb://pair` + کد دستی کوتاه ۱۶ نویسه‌ای با محدودیت تلاش (3.6.0 / mobile 0.4.0) |
| P10 | موبایل باید مستقل از ویندوز کار کند | اپ موبایل فقط Companion است | حالت Standalone: هستهٔ Kotlin (پروژه، Charter، پرامپت، Intake، Task، حلقه، Timeline) + Export/Import بستهٔ پروژه با Desktop (mobile 1.0.0) |

## ۲. اصول معماری (الزامی برای هر PR)

1. **یک پنجره.** هیچ صفحه‌ای Toplevel مستقل نیست؛ فقط دیالوگ‌های کوتاه و Modal، همه از `ui/layout.place_dialog`.
2. **یک Theme و یک Settings.** `ui/theme` تنها منبع رنگ/فونت/فاصله است؛ تغییر تم/زبان/Mode همهٔ صفحات را بلافاصله عوض می‌کند. رنگ hard-code در Viewها ممنوع (تست).
3. **هیچ بن‌بست.** هر وضعیت پروژه دقیقاً یک «قدم بعدی» دارد که یا پرامپت آماده است یا یک دکمهٔ تصمیم واقعی (تست ثابت).
4. **ارتباط با مدل فقط Copy/Paste/File.** بدون API، بدون مرورگر داخلی، بدون لاگین.
5. **خروجی مدل داده‌ی نامطمئن است.** Normalize → Parse → Review → Apply؛ هیچ چیز بدون بازبینی کاربر State یا فایل را عوض نمی‌کند.
6. **سبک می‌ماند.** Python + Tk، بدون وابستگی pip در زمان اجرا؛ کتابخانه‌های کوچک فقط vendored با مجوز MIT/BSD. حجم Payload < 4MB.
7. **قانون Checkpoint** (CONTRIBUTING): هر تغییر فایل → commit → push، بدون استثنا.
8. **NOT RUN صریح.** آزمون روی Windows فیزیکی، گوشی واقعی و چت واقعی مدل که اجرا نشده PASS اعلام نمی‌شود.
9. **سیاست زبان (دستور صریح مالک محصول، 2026-10-19):** فعلاً اپ **فقط انگلیسی** است — هم Desktop (Windows) و هم Android. هیچ کار توسعه، ترجمه، RTL یا تست برای زبان فارسی در UI انجام نمی‌شود و Gateها فقط در انگلیسی اجرا می‌شوند. افزودن فارسی فقط با درخواست صریح مالک در نسخه‌های بعدی. (مستندات داخلی پروژه می‌توانند فارسی بمانند.)

## ۳. نسخه‌ها و Gateها

| نسخه | عنوان | محتوا | Gate (شرط انتشار) | وضعیت |
|---|---|---|---|---|
| **3.0.0** | پوستهٔ واحد و ظاهر حرفه‌ای | پنجرهٔ واحد با Nav rail (Home، Project، Prompt، Inbox/Response، Tasks، Team، Timeline، Files، History، Run، Git، Settings)؛ Workbench به‌عنوان صفحه (نه Toplevel)؛ تم Fluent light/dark سراسری؛ Settings سراسری (تم، زبان، Mode)؛ Simple/Advanced سراسری؛ حذف رنگ‌های hard-code کلاسیک | smoke: هیچ Toplevel برای Workbench؛ تغییر تم همهٔ صفحات را عوض می‌کند؛ Simple صفحات پیشرفته را پنهان می‌کند؛ همهٔ تست‌های قبلی سبز | ✅ (`gui_single_shell_smoke`، ADR-009) |
| **3.1.0** | Layout مقاوم و متقارن | `ui/layout.py`: `place_dialog` (clamp به Work area و مرکز والد)، `FlowBar` (Toolbar با wrap)، `ScrollPage`؛ تبدیل همهٔ دیالوگ‌ها و Toolbarها؛ Grid فاصله‌گذاری یکسان | smoke: در 1024×640، 1280×720 و 1920×1080 هیچ دکمه‌ای بیرون از پنجره نیست و هیچ دیالوگی از Work area بیرون نمی‌زند (همهٔ صفحات و دیالوگ‌ها) | ✅ (`gui_layout_smoke`) |
| **3.2.0** | دریافت مطمئن خروجی مدل (GPT) | `intake/normalize.py` (BOM، NBSP، zero-width، CRLF، نقل‌قول هوشمند بیرون از رشته، escape مارک‌داون مارکرها، HTML entity، fence بیرونی، ویرگول انتهایی، کامنت JSON)؛ تشخیص بریدگی + پرامپت «ادامه از جایی که قطع شد»؛ قالب پیش‌فرض GPT = بلوک‌های AIWB بدون fence؛ یک ورودی Paste برای همه‌چیز با تشخیص خودکار نوع | پیکرهٔ ≥ ۳۰ نمونهٔ خرابی واقعی GPT/Gemini/Claude پاس؛ هیچ نمونهٔ سالم قبلی خراب نمی‌شود | ✅ (`test_intake_normalize`، `gui_intake_smoke`؛ ۳۶ نمونه) |
| **3.3.0** | معماری اطلاعات UI (چینش تب‌ها و دکمه‌ها) | درخواست مالک: صفحهٔ AI Response با ۱۷ دکمه و Git با ۲۴ دکمه شلوغ و گیج‌کننده است. نقشهٔ درختی کامل (صفحه → بخش → دکمه → دیالوگ) در `docs/specs/UI_TREE.md` (فعلی و هدف)؛ قاعده: هر صفحه حداکثر ۴ دکمهٔ اصلی قابل‌مشاهده، بقیه در منوی گروه‌بندی‌شدهٔ «More ▾»؛ حذف دکمه‌های تکراری که صفحهٔ Rail دارند (Project Workbench، Mobile Companion)؛ AI Response: Paste / Load / Review & apply + نوار وضعیت؛ Git: زیرتب‌های Local / GitHub accounts / Repositories؛ حذف بخش زبان از Settings (سیاست فقط انگلیسی)؛ `ui/actions.py` (ActionBar) | تست `gui_ia_smoke`: شمارش دکمه‌های قابل‌مشاهدهٔ هر صفحه ≤ حد، هر فرمان قبلی هنوز از منو در دسترس است، هیچ دکمهٔ تکراری Rail | ✅ (`gui_ia_smoke`، `test_ui_actions`؛ `docs/specs/UI_TREE.md`) |
| **3.4.0** | Project Charter | پرامپت «طراحی معماری کل پروژه»: معماری و ماژول‌ها، تعداد AI موازی و دلیل، پروتکل هماهنگی (مالکیت فایل/مسیر، قراردادهای مشترک، نقاط Sync، حل تعارض)، Roadmap با Milestone و نسخه، Task هر AI، پرامپت شروع هر AI؛ قرارداد `project-charter.v1` (schema + fixture)؛ Import یک‌جا با بازبینی → Agentها، Milestoneها، نسخه‌ها، Taskها | تست قرارداد و Import؛ پرامپت همهٔ بخش‌های الزامی را می‌خواهد (تست)؛ Charter ناقص با پیام دقیق و پرامپت اصلاح رد می‌شود | ✅ (`test_v2_charter`، `gui_charter_smoke`، `validate_contracts`) |
| **3.5.0** | حلقهٔ هدایت‌شده (بدون بن‌بست) | `v2/guide.py`: برای هر وضعیت یک Step با عنوان، توضیح، پرامپت آماده یا تصمیم؛ کارت «قدم بعدی» در Home و Project؛ صف هر AI؛ پرامپت Manager Update/Review/Repair/Continue خودکار؛ ثبت «کپی شد/ارسال شد» با یک کلیک | تست ثابت روی همهٔ وضعیت‌های قابل‌رسیدن: هیچ Step بدون عمل؛ E2E شبیه‌سازی‌شده از ایده تا نسخهٔ منتشرشده با پاسخ‌های اسکریپتی ۳ AI موازی | ✅ (`test_v2_guide`، `gui_guide_smoke`) |
| **3.6.0** | Timeline تصویری | `ui/timeline_canvas.py`: محور افقی زمان، دایره با اندازهٔ اهمیت (minor/normal/major/critical)، خط عمودی هر نسخه (پیشنهادی خط‌چین، منتشرشده توپر)، Lane هر AI، Zoom/Pan، Tooltip، کلیک → Inspector | smoke: رندر ۲۰۰۰ رویداد < 300ms؛ اندازهٔ دایره و خط نسخه مطابق داده؛ Dark (فقط انگلیسی) | ✅ (`test_timeline_canvas`، `gui_timeline_smoke`) |
| **3.7.0** + mobile **0.4.0** | اتصال موبایل با QR | QR روی Desktop (Canvas، بدون PIL)؛ URI `aiwb://pair?h=&p=&k=`؛ کد دستی ۱۶ نویسه (Base32، ۸۰ بیت، ۱۰ دقیقه، ۵ تلاش)؛ موبایل: اسکنر داخلی + Deep link از دوربین سیستم | تست واحد QR (decode با کتابخانهٔ مرجع در CI)، قرارداد کد کوتاه در هر دو طرف | ✅ (`test_qr_pairing` با zbar، `PairingContractTest` با ZXing، `companion-pairing.v2`) |
| mobile **1.0.0** + **3.8.0** | موبایل مستقل | هستهٔ Kotlin: پروژه‌ها، Charter، پرامپت‌ها، Intake با همان Normalizer (پیکرهٔ مشترک در `packages/contracts/fixtures`)، Task، حلقهٔ هدایت‌شده، Timeline Canvas؛ Export/Import `aiwb-bundle.v1` بین Desktop و موبایل | تست‌های JVM روی پیکرهٔ مشترک؛ round-trip بسته | ✅ (`IntakeCorpusTest`، `BundleContractTest`، `StandaloneLoopTest`، `test_bundle`؛ `fixtures/bundle/`) |
| **3.9.0** | Release Gate محصول | E2E کامل، Screenshotهای قبل/بعد، Performance، مستندات کاربر EN | همهٔ Gateها؛ NOT RUNها صریح | ⬜ |

## ۴. موارد NOT RUN که فقط مالک محصول می‌تواند اجرا کند

- Windows فیزیکی با DPI 100/125/150/200٪.
- سناریوی کامل با چت واقعی ChatGPT/Gemini (۳ AI موازی).
- گوشی واقعی: اسکن QR، Pairing، حالت مستقل.

## ۵. اسناد

| سند | نقش |
|---|---|
| `docs/roadmap/archive/` | Roadmapهای قبلی (superseded) |
| `docs/specs/GUI_DESIGN_SYSTEM_FA.md` | توکن‌ها (از 2.7.0؛ در 3.0.0 به تم Fluent نگاشت می‌شود) |
| `docs/specs/UI_TREE.md` | نقشهٔ درختی صفحه → بخش → دکمه → منو (از 3.3.0؛ تولیدشده از اپ واقعی) |
| `docs/adr/ADR-009-*.md` | تصمیم پوستهٔ واحد و تم Fluent (3.0.0) |
| `packages/contracts/schemas/` | قراردادها (از جمله `project-charter.v1`، `aiwb-bundle.v1`) |
