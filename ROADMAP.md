# AI Workbench — رودمپ V5.21 تا V5.30: رفع ریشه‌ای یافته‌های ممیزی

> مرجع اجرایی توسعه؛ جانشین رودمپ کامل‌شدهٔ V5.16–V5.20.
> نسخهٔ قبلی **بدون تغییر متن** در `docs/roadmap/archive/ROADMAP_v5.16-v5.20_Light_Clear_Short_FA.md` محفوظ است.
> تاریخ آغاز: 2026-11-05؛ خط مبنا: `19270b74`، آخرین انتشار Desktop: `desktop-v5.20.0`.
> این شماره‌ها مراحل هدف توسعه‌اند، نه ادعای انتشار یا تغییر نسخهٔ برنامه.

## هدف و حدود

رفع تمام یافته‌های مستقل فاز کشف، نه افزودن قابلیت نامرتبط. کاتالوگ مرجع:
`docs/BUG_FINDING.md`؛ حافظه و دستور ادامه: `docs/roadmap/SESSION_NOTES.md`.
خط مبنا: ۱۰۶ باگ باز (۱۱ S1، ۴۱ S2، ۵۴ S3)، BF-001 تا BF-109 با سه تکراری
BF-049→023، BF-050→021، BF-090→069. شواهد تکراری‌ها حذف نمی‌شود.
Mobile متوقف بودنِ انتشار دارد، نه معافیت از رفع باگ‌های ثبت‌شده؛ تغییرات مشترک باید در Kotlin هم بررسی شوند.

هیچ تضمین غیرواقعی «صفر باگ برای همیشه» داده نمی‌شود. پیشگیری یعنی مرزهای مشترک اعتبارسنجی،
تراکنش‌های قابل‌بازیابی، تست بازگشت هر شاهد و دروازهٔ مستقل Windows/Linux/Android.

## قوانین ثابت اجرای هر گام

1. دقیقاً **یک تغییر فایل → git add → git commit → git push**؛ سپس کار بعدی.
   شکست push = توقف ویرایش تا رفع مشکل. تست پس از checkpoint، نه به‌جای آن.
2. هر commit به مرحلهٔ V5.x و در صورت امکان BF اشاره می‌کند. از force-push، حذف شواهد و تغییر تاریخچه پرهیز شود.
3. هر رفع: شاهد بازتولید قبلی → تغییر ریشه → تست بازگشت مثبت/منفی و خطای تزریق‌شده → ثبت نتیجهٔ واقعی.
   تست جدید قبل از رفع می‌تواند عمداً قرمز checkpoint شود؛ رفع و سبزشدن باید صریح ثبت شوند.
4. `FIXED` فقط بعد از عبور تست مربوط و بررسی مسیرهای هم‌خانواده؛ آمار کاتالوگ از headingها محاسبه و تطبیق شود.
5. secrets در کد/مستند/remote URL ممنوع؛ سرویس‌های شبکه در تست fake هستند؛ workflow/release واقعی برای آزمایش اجرا نمی‌شود.
6. pushهای checkpoint ممکن است CI میان‌مرحله‌ای داشته باشند؛ هیچ tag/انتشاری پیش از عبور دروازهٔ نهایی انجام نمی‌شود.
7. قطع جلسه به معنی پایان پروژه نیست: NEXT، فایل‌ها، commitها، تست‌های قرمز/ردشده و ریسک‌های باقی‌مانده در حافظه ثبت شود.

## نقشهٔ پوشش کامل کاتالوگ

هر شناسهٔ مستقل دقیقاً یک مالک اصلی دارد؛ تست‌های مشترک می‌توانند چند مرحله را پوشش دهند.

| مرحله | ریشه و حوزه | شناسه‌های BF | وضعیت |
|---|---|---|---|
| V5.21 | زیرساخت تست صادقانه و کاتالوگ قابل‌ردیابی؛ اصلاح S5 و مالکیت تایمر | شکست harness ثبت‌شده، مستقل از شمار BF | فعال |
| V5.22 | تراکنش فایل، مسیر امن Windows، حفظ داده و integrity artifact | 007, 008, 009, 010, 026, 028, 051, 095, 104, 105, 106 | شروع‌نشده |
| V5.23 | گراف برنامه، readiness، لغو/بازگشایی و خروج از بن‌بست | 001, 002, 003, 004, 014, 033, 035, 048, 055, 057 | شروع‌نشده |
| V5.24 | یکسان‌سازی intake، حفظ متن و staging همهٔ ورودی‌ها؛ repair بدون گم‌شدن فایل | 006, 027, 032, 037, 038, 040, 041, 042, 043, 044, 053, 054, 076, 078, 079, 080, 083, 084, 085, 091, 092, 093, 094, 107 | شروع‌نشده |
| V5.25 | بازخورد واقعی در prompt، تفسیر PM و نقش‌ها، تصمیم‌های فارسی | 011, 013, 039, 045, 046, 047, 052, 056, 081 | شروع‌نشده |
| V5.26 | بازیابی state/settings، هویت bundle، import/archive/release اتمیک | 005, 016, 017, 020, 021, 022, 023, 034, 036, 082 | شروع‌نشده |
| V5.27 | Git/Actions؛ idempotency، عملیات پروژه‌محور و evidence معتبر | 018, 019, 024, 096, 097, 101, 103, 108, 109 | شروع‌نشده |
| V5.28 | اجرای محدود process، context امن، تحلیل dependency/semantic و معماری | 025, 029, 030, 031, 063, 064, 065, 066, 067, 087, 088, 089 | شروع‌نشده |
| V5.29 | UI قابل‌دسترسی، ترجمه، lifecycle منابع، Companion و Android | 015, 058, 059, 060, 061, 062, 068, 069, 070, 071, 072, 073, 074, 075, 077, 086, 098, 099, 100, 102 | شروع‌نشده |
| V5.30 | دروازهٔ یکپارچه، تطبیق ۱۰۶ شاهد، مهاجرت و آماده‌سازی انتشار | همه؛ تکراری‌ها تابع مالک اصلی | شروع‌نشده |

## معیار پذیرش مراحل

### V5.21 — تست‌ها قابل اعتماد باشند
- رفع cancellation با widget مالک callback، نه حذف کور فرمان Tcl از root.
- S5 بدون monkeypatch تشخیصی عبور کند؛ خط مبنا unit و GUI جداگانه ثبت شود.
- پوشش roadmap با headingهای کاتالوگ ماشینی مقایسه شود؛ هیچ BF باز بدون مالک نباشد.

### V5.22 — ابتدا حفظ داده
- همهٔ مقصدها پیش از نوشتن بررسی شوند: symlink/junction، device/ADS، collision/case، parent-is-file و hash پیش‌نمایش.
- Quick و guided از قرارداد تراکنشی یکسان استفاده کنند: backup یکتا و durable پیش از اولین write،
  rollback معکوس، cleanup temp، پیام قابل‌تکرار؛ accepted فقط پس از integration موفق.
- size limit و empty-file هیچ‌گاه silent skip نشوند. restore قابل‌تکرار و حافظ ویرایش جدید کاربر باشد.
- artifact فقط پس از تمام کنترل‌های hash/size/ZIP منتشر شود؛ failure نسخهٔ قبلی را دست‌نخورده بگذارد؛
  شناسه و `.zip` از truncation جان سالم ببرند؛ temp هر تلاش یکتا؛ ZIP خراب خطای دامنه‌ای با cleanup بدهد.
- تست fault injection در write دوم، hash mismatch با فایل قبلی، long-name collision، stale preview و retry.

### V5.23 — هیچ قدم پیشنهادی از پیش محکوم به شکست نباشد
- گراف نهایی شامل emergency edgeها قبل از commit معتبر باشد؛ reject مستقل از خرابی graph کار کند.
- حذف آخرین prerequisite readiness را تازه کند؛ دادهٔ قدیمی خراب راه خروج قابل‌فهم داشته باشد.
- لغو task، handoff و attempt را هماهنگ ببندد؛ task تمام‌شده با revise واقعاً باز شود یا صریح رد شود.
- تست مستقیم ریشه‌ها + سناریوی end-to-end و random walk با invariantهای graph/step.

### V5.24 — یک پاسخ، یک معنا در همهٔ ورودی‌ها
- Preview، Quick، Home، classic، phone از طبقه‌بندی/parse/stage/diagnose سازگار استفاده کنند.
- parser خطای action ناشناخته/marker تو در تو را آشکار کند؛ raw body، ZWNJ/ZWJ/NBSP و slashها حفظ شوند.
- JSON با quote تایپوگرافیک معتبر خراب نشود؛ prose قبل از JSON جلوی object سالم را نگیرد.
- repair/troubleshoot فایل خوب را نگه دارد؛ هیچ task کدنویسی با فقدان فایل به‌صورت clean قبول نشود.
- Inbox فقط برای پاسخ واقعاً ذخیره‌شده وعدهٔ نگهداری بدهد؛ ZIP warning بعد از debounce ناپدید نشود.
- fixtures مشترک Desktop/Mobile و تست تمام entry pointها، نه فقط parser واحد.

### V5.25 — حلقهٔ بازخورد بدون تحریف
- دلیل reject و validation failure در prompt بعدی حاضر؛ ادعای مدل از نتیجهٔ تأییدشده جدا.
- assessment هرگز create یا objective overwrite ناخواسته نسازد؛ role inference حدس مدیریتی نسازد.
- عنوان تصمیم فارسی نرمال‌سازی معنایی شود؛ helper ورودی را بی‌اطلاع قطع/جایگزین نکند.

### V5.26 — state و lifecycle بازیابی‌پذیر
- تنظیمات undecodable حفظ و بازیابی شوند؛ failure ذخیره به کاربر گفته شود و secret orphan نشود.
- آخرین state سالم قابل‌بازیابی، هویت پایدار برای folder فارسی/space، تأیید import براساس تمام کار محلی.
- archive/release ابتدا preflight و write موفق، سپس state؛ retry idempotent؛ هیچ bundle خیالی اعلام نشود.
- تست corrupt/permission/disk failure با حفظ داده و مهاجرت backward-compatible.

### V5.27 — اثر خارجی فقط برای هویت دقیق عملیات
- repository/account/binding/project/ref/commit/task/attempt در آغاز عملیات capture و پیش از نتیجه تأیید شوند.
- جابه‌جایی پروژه، rebase یا selection/ref جدید، evidence/schema/jobs قدیمی را به مقصد جدید نرساند.
- remote guard همان branch مقصد push را کنترل کند؛ خطای partial GitHub create/release retry امن داشته باشد.
- fake transports و bare Git repos؛ هیچ شاهد verified با SHA خودش علیه خودش اعتبارسنجی نشود.

### V5.28 — اجرای محدود و context قابل‌اعتماد
- child یا grandchild صاحب pipe زمان پاسخ را نامحدود نکند؛ output UTF-8 فارسی روی Windows سالم باشد.
- path و محتوای حساس/secret/link در context و Quick افشا نشود؛ binary/encoding/empty file صادقانه گزارش شود.
- Markdown state قابل تزریق نباشد؛ semantic خروجی truncated را «بدون تغییر» ننامد؛ relative import درست resolve شود.

### V5.29 — UI و phone قابل بازیابی
- scroll محتوای بلند با footer/error ثابت، wrap و حد صفحه؛ tests روی 1366×768 و DPI ویندوز.
- نوتیفیکیشن identity رویداد داشته باشد؛ labels/why فارسی و next step با Home سازگار باشد.
- pairing expiry/skew/permissions و محدودیت اندازه پیام روشن؛ rotation/process recreation پاسخ و export را گم نکند.
- Android ZIP bounded/backup/normalization؛ تست JVM و instrumentation در محیط Android، نبود SDK صریح blocker است.

### V5.30 — شرط پایان (نه ادعای فعلی)
- تمام BF مستقل تعیین تکلیف با evidence، تست و commit؛ duplicateها نگه داشته شوند؛ هیچ S1/S2 باز برای انتشار باقی نماند.
- unit کامل، GUI کامل و Windows CI بدون failure؛ skippedها با علت و ریسک؛ Android لازم برای رفع‌های mobile.
- تست مهاجرت پروژه‌های موجود، non-ASCII، چندپروژه‌ای، filesystem fault و تکرار عملیات.
- README/CHANGELOG/release checklist و نسخه فقط پس از عبور gateها؛ tag انتشار جدا و آگاهانه.

## ترتیب اجرایی شروع

V5.21/S5 → V5.22 artifact (محدودهٔ کوچک و جلوگیری فوری از حذف فایل) → V5.23 بن‌بست‌های S1
→ V5.22 تراکنش‌های Quick/guided → V5.24 staging/repair → سایر مراحل.
تقسیم ریشه‌ها به معناى ممنوعیت رفع ریسک زودتر نیست؛ دلیل تغییر اولویت و نتیجه در SESSION_NOTES ثبت شود.

## وضعیت جاری

- رودمپ ثبت شده؛ هنوز هیچ BF در این سند رفع‌شده اعلام نشده است.
- تست پایهٔ جلسهٔ قبلی: unit 921 (10 skipped)، GUI 61/62؛ S5 failure واقعی در harness، نه موفقیت فرضی.
- NEXT: اصلاح ماندگار S5، سپس تست بازگشت BF-104/105/106 و اصلاح مرز artifact.
