# مشخصات فنی توسعهٔ یکپارچگی GitHub و Monorepo در AI Workbench

**مخاطب:** برنامه‌نویس مسئول توسعهٔ AI Workbench  
**نسخهٔ مرجع محصول:** 1.13  
**نوع سند:** مشخصات محصول، معماری، رفتار رابط کاربری، مراحل پیاده‌سازی و معیارهای پذیرش  
**هدف اصلی:** تبدیل GitHub به زیرساخت مرکزی اتصال پروژه‌ها، مدیریت تغییرات، اجرای CI/CD، ساخت خروجی موبایل/دسکتاپ و مشاهدهٔ انتشارها؛ با تجربهٔ کاربری ساده و یکپارچه از داخل AI Workbench.

> **یادداشت نسخه:** سورس کامل نسخهٔ 1.13 برای این بررسی ضمیمه نشده است. پیش از پیاده‌سازی، برنامه‌نویس باید قابلیت‌های واقعی نسخهٔ 1.13 و تغییرات پس از 1.11 را از روی سورس و مستندات فعلی بررسی کند. این سند هدف و قرارداد رفتار موردنظر را تعریف می‌کند، نه ادعا دربارهٔ اینکه کدام جزء در 1.13 قطعاً پیاده‌سازی شده است. قابلیت‌های موجود باید توسعه داده شوند، نه اینکه بدون دلیل از نو نوشته شوند.

---

## ۱. چشم‌انداز محصول

AI Workbench باید یک لایهٔ مرکزی برای کار با GitHub داشته باشد که به کاربر اجازه دهد:

1. حساب GitHub خود را یک‌بار به هر دستگاه متصل کند.
2. برای هر پروژهٔ Workbench یک Repository یا یک زیرپوشه از Monorepo مشخص کند.
3. عملیات Git را بدون جابه‌جایی مداوم بین ترمینال، مرورگر و برنامه مدیریت کند.
4. پس از تأیید خروجی مدل، تغییرات را به Branch مناسب Commit و Push کند.
5. GitHub Actions را اجرا یا دنبال کند، نتیجهٔ تست‌ها و Build را ببیند و Artifact خروجی را مستقیماً دریافت کند.
6. نسخه‌های آزمایشی و پایدار را از هم جدا کند و تاریخچهٔ هر خروجی را به Commit، Task و Run دقیق آن متصل نگه دارد.
7. از همان زیرساخت هم برای Monorepo خود AI Workbench و هم برای پروژه‌های شخصی دیگری که به Repositoryهای مستقل متصل‌اند استفاده کند.
8. در آینده از موبایل عملیات قابل‌انجام را مدیریت کند و برای کارهایی که به فایل‌سیستم یا ابزارهای ویندوز نیاز دارند از حالت Companion دسکتاپ استفاده کند.

هدف این نیست که همهٔ کارها بی‌توقف و خودکار انجام شوند؛ هدف، کوتاه‌کردن مسیر کار با حفظ امکان مشاهده، کنترل و بازیابی است. هر عملیات می‌تواند به سطح اتوماسیون مشخصی تعلق داشته باشد و سطح آن برای هر پروژه تنظیم شود.

## ۲. تصمیم‌های معماری کلیدی

### ۲.۱. Monorepo برای خود محصول، Repository مستقل برای پروژه‌های کاربر

سورس AI Workbench می‌تواند در یک Monorepo قرار گیرد؛ برای نمونه:

```text
AI-Workbench/
├── apps/
│   ├── desktop/             # برنامهٔ Windows موجود
│   └── mobile/              # برنامهٔ Android و در صورت نیاز iOS
├── packages/
│   └── contracts/           # Schemaها، fixtureها و قراردادهای مشترک
├── docs/
├── tools/
├── tests/
├── .github/
│   └── workflows/
├── README.md
└── CHANGELOG.md
```

این ساختار پیشنهادی است، نه دستور برای جابه‌جایی فوری فایل‌ها. انتقال سورس و نصب‌کنندهٔ فعلی به این ساختار باید مرحله‌ای، با حفظ مسیرهای build و تست‌های رگرسیون انجام شود.

**نکتهٔ مهم:** Monorepo مربوط به سورس خود AI Workbench است. این موضوع مانع آن نمی‌شود که هر پروژه‌ای که کاربر داخل Workbench ساخته، به Repository مستقلی متصل شود. یک پروژه ممکن است یک Repository کامل داشته باشد یا از یک پوشهٔ خاص داخل یک Monorepo مشترک استفاده کند.

### ۲.۲. نسخه‌های Desktop و Mobile مستقل باشند

کد در یک Repository قرار دارد، اما انتشار دسکتاپ و موبایل به یک شماره نسخه یا یک زمان انتشار مشترک وابسته نباشد. به‌عنوان نمونه، Tagها می‌توانند این الگو را داشته باشند:

- `desktop-v1.14.0`
- `mobile-v0.1.0`

الگوی دقیق نسخه‌ها پس از بررسی سیاست فعلی نسخه‌گذاری انتخاب شود. نسخهٔ فعلی دسکتاپ 1.13 است؛ نسخهٔ موبایل می‌تواند چرخهٔ مستقل داشته باشد. هر Release باید به Commit دقیق و مجموعهٔ فایل‌های تولیدشده قابل ردیابی باشد.

### ۲.۳. یک زیرسیستم GitHub؛ نه منطق پراکنده در دکمه‌ها

تمام قابلیت‌های GitHub و Git باید از سرویس‌های مرکزی استفاده کنند. UI نباید خودش مستقیماً Token را به درخواست HTTP اضافه کند یا در هر دکمه، منطق احراز هویت و Git را دوباره پیاده‌سازی کند.

مرزهای پیشنهادی:

- `github_accounts`: افزودن حساب، اعتبارسنجی، قطع اتصال و وضعیت اعتبارنامه.
- `credential_store`: ذخیره و بازیابی اعتبارنامه از مخزن امن سیستم‌عامل.
- `github_api_client`: فراخوانی REST API، pagination، rate limit، خطاها و نسخهٔ API.
- `repository_registry`: جست‌وجو و انتخاب Repository و نگهداری فرادادهٔ آن.
- `project_git_binding`: پیوند پروژهٔ Workbench به Repository، مسیر محلی و Branchها.
- `git_service`: وضعیت محلی، diff، stage، commit، fetch، pull، push، branch و conflict.
- `sync_service`: هماهنگ‌کردن وضعیت محلی و Remote و تولید Sync Plan پیش از اجرا.
- `actions_service`: جست‌وجو و اجرای Workflowها، پیگیری runها و دریافت نتیجه.
- `artifact_service`: فهرست و دریافت Artifactهای Build و اعتبارسنجی Hash.
- `release_service`: Tag، Release، نسخه‌گذاری، یادداشت انتشار و دانلود دارایی‌ها.
- `build_center`: منطق ترکیبی UI برای وضعیت CI، خروجی‌ها و رویدادهای Build.
- `capability_registry`: ثبت وضعیت قابلیت‌ها در پلتفرم‌های Desktop و Mobile.

نام فایل‌ها و کلاس‌ها می‌تواند با الگوی فعلی سورس هماهنگ شود؛ الزام اصلی، جدایی مسئولیت‌ها و وجود قرارداد روشن بین UI و سرویس‌هاست.

---

## ۳. مدیریت حساب‌های GitHub

### ۳.۱. صفحهٔ GitHub Accounts

در تنظیمات برنامه صفحه‌ای به نام `GitHub Accounts` اضافه شود. این صفحه فهرست حساب‌های متصل را نشان دهد و امکان افزودن، اعتبارسنجی دوباره، تغییر اعتبارنامه، و قطع اتصال را فراهم کند.

اطلاعات نمایشی هر حساب:

- نام کاربری و تصویر/آواتار در صورت دریافت از API.
- روش اتصال: `Personal Access Token`، GitHub App/OAuth یا روش دیگری که در آینده اضافه می‌شود.
- وضعیت اتصال: `Connected`، `Needs re-authentication`، `Permission missing`، `Rate limited` یا `Connection error`.
- زمان آخرین اعتبارسنجی موفق.
- تعداد Repositoryهای قابل‌دسترسی، در صورت معلوم‌بودن.
- دکمه‌های `Test Connection`، `Refresh Repositories`، `Replace Credential` و `Disconnect`.

Token هرگز در صفحه به‌صورت متن کامل نمایش داده نشود. پس از ثبت موفق، UI تنها وضعیت و شناسهٔ Credential را نشان دهد. در صورت تعویض، کاربر مقدار جدید را وارد کند.

### ۳.۲. روش اتصال نسخهٔ اولیه

برای اولین نسخه، دو روش در نظر گرفته شود:

**الف) اتصال با Personal Access Token:** کاربر Token را Paste می‌کند، گزینهٔ Test Connection را می‌زند و برنامه حساب را از endpoint رسمی حساب احرازشده می‌خواند. پس از موفقیت، حساب و قابلیت‌های قابل‌دسترسی ثبت می‌شوند.

**ب) ورود با GitHub App/OAuth در مرحلهٔ بعد:** جریان مبتنی بر مرورگر برای تجربهٔ یکپارچه‌تر و حذف ورود دستی Token قابل افزودن باشد. برای برنامهٔ بومی، از الگوی احراز هویت مناسب public client و PKCE مطابق مستندات رسمی استفاده شود؛ client secret محرمانه را داخل اپ دسکتاپ یا موبایل بسته‌بندی نکنید.

معماری باید از ابتدا طوری باشد که UI به نوع اعتبارنامه وابسته نباشد. رابط `AuthenticationProvider` یا معادل آن، روش احراز هویت را از مصرف‌کننده‌های GitHub جدا کند.

### ۳.۳. پشتیبانی از PATهای مختلف

مسیر اتصال دستی باید بتواند PAT کلاسیک و Fine-grained را در حدی که GitHub برای endpointها پشتیبانی می‌کند قبول کند. برنامه نباید صرفاً از روی اینکه Token «معتبر» است نتیجه بگیرد که همهٔ عملیات مجازند؛ اعتبار توکن با اختیار انجام تمام عملیات برابر نیست.

بعد از اعتبارسنجی، قابلیت‌ها با درخواست‌های خواندنی/کم‌خطر و پاسخ واقعی API ارزیابی شوند. نمونهٔ قابلیت‌ها:

- مشاهدهٔ حساب و Repositoryها.
- خواندن Repository خصوصی.
- عملیات Git روی HTTPS.
- ایجاد Repository.
- مدیریت فایل‌های Repository از API، اگر واقعاً لازم است.
- مشاهدهٔ Actions و runها.
- اجرای دستی Workflow.
- دانلود Artifact.
- ایجاد Release و بارگذاری دارایی.
- تغییر تنظیمات Repository یا Workflow، اگر کاربر آن عملیات را فعال کرده باشد.

در UI وضعیت هر قابلیت نمایش داده شود: `Available`، `Not available`، `Not checked` یا `Requires approval`. اگر یک عملیات به permission خاص یا سیاست Organization نیاز دارد، توضیح API در پیام خطا نمایش داده شود. هرگز نشان سبز کلی «همه‌چیز آماده است» صرفاً بر مبنای موفقیت `GET /user` نشان داده نشود.

### ۳.۴. ذخیره‌سازی Credential

Token از اطلاعات عادی پروژه جدا نگهداری شود.

- در Windows از Windows Credential Manager یا سازوکار امن معادل سیستم‌عامل استفاده شود.
- در Android از Android Keystore همراه با ذخیره‌سازی امن و مناسب Token استفاده شود؛ Credential در فایل Preferences یا دیتابیس عادی ذخیره نشود.
- در iOS، در صورت پیاده‌سازی، از Keychain استفاده شود.
- فایل تنظیمات Workbench تنها یک `credential_ref` یا شناسهٔ امن داشته باشد؛ مقدار Token در JSON/YAML پروژه یا Repository نوشته نشود.
- Credential هرگز در URL مربوط به Remote، command-line argument، stdout/stderr، exception، telemetry یا log ظاهر نشود.
- قطع اتصال باید مرجع Credential را حذف و در صورت انتخاب کاربر، دادهٔ محلی مربوط به حساب را نیز پاک‌سازی کند؛ این عمل نباید Repository محلی یا Commitهای کاربر را حذف کند.
- Credential نباید از طریق Monorepo یا Workbench Data Sync به دستگاه دیگری کپی شود. هر دستگاه اعتبارنامهٔ خودش را نگه می‌دارد.

این موارد الزامات پیاده‌سازی عادی برای اعتبارنامه هستند و مانع تجربهٔ سادهٔ اتصال نمی‌شوند.

### ۳.۵. رابط Credential برای API و Git

GitHub REST API و Git over HTTPS دو مسیر مجزا هستند؛ این دو باید در زیرساخت برنامه هماهنگ شوند.

- برای API درخواست‌ها از `github_api_client` استفاده کنند.
- برای `git fetch/push/pull` از Git Credential Manager یا credential helper امن استفاده شود؛ Token داخل `remote.origin.url` قرار نگیرد.
- اگر Git Credential Manager از قبل نصب و پیکربندی شده، Workbench نباید بی‌دلیل یک ذخیره‌ساز رقیب بسازد.
- اگر کاربر هم حساب GitHub در Workbench ثبت کرده و هم Git Credential Manager حساب مستقلی دارد، UI باید وضعیت ناسازگار بودن Credentialها را تشخیص دهد و آن را روشن نمایش دهد.

### ۳.۶. خطاهای اتصال

پیام‌های عمومی و دقیق تعریف شوند:

- `401`: Token نامعتبر/لغوشده یا احراز هویت ناموفق؛ درخواست ورود دوباره.
- `403`: permission ناکافی، محدودیت سازمانی یا rate limit؛ پاسخ و headers را بررسی و دلیل محتمل را تفکیک کن.
- `404`: ممکن است Repository وجود نداشته باشد یا حساب اجازهٔ مشاهده نداشته باشد؛ اطلاعات خصوصی را ناخواسته افشا نکن.
- `409/422`: تعارض عملیاتی یا ورودی نامعتبر؛ جزئیات قابل‌فهم نمایش داده شود.
- شبکه قطع شده: عملیات قابل‌تکرار با دکمه Retry، بدون ساخت Commit یا اجرای تکراری ناخواسته.
- rate limit: زمان retry طبق headers رسمی رعایت شود و UI شمارش معکوس یا زمان تقریبی قابل‌اعتماد نشان دهد.

تمام درخواست‌ها باید pagination را درست مدیریت کنند. فهرست Repositoryها نباید به اولین صفحه محدود شود. برای بیش از یک حساب، نتایج در UI با owner و avatar از هم جدا شوند.

---

## ۴. GitHub Hub و انتخاب Repository

### ۴.۱. Repository Browser

یک پنجرهٔ انتخاب Repository ساخته شود که از حساب انتخاب‌شده، مخزن‌های قابل دسترسی را با pagination دریافت کند.

قابلیت‌ها:

- جست‌وجو بر اساس نام و owner.
- فیلتر `All`، `Private`، `Public`، `Forks` و `Archived` در صورت دریافت دادهٔ کافی.
- نمایش نام کامل `owner/repo`، visibility، branch پیش‌فرض، آخرین به‌روزرسانی و توضیح Repository.
- Refresh و نمایش زمان آخرین همگام‌سازی فهرست.
- نمایش هشدار برای Repository آرشیوشده یا فاقد دسترسی نوشتن.
- نمایش Repositoryهای از قبل متصل به پروژه‌ها؛ انتخاب مجدد باید آگاهانه باشد.
- امکان ساخت Repository جدید در حساب انتخاب‌شده، با نام، توضیح و visibility؛ عملیات حذف Repository در نسخهٔ اولیه لازم نیست.

برای پایداری، `repository_id` عددی GitHub ذخیره شود و `owner`، `name`، `html_url` و `default_branch` نیز به‌عنوان فراداده ذخیره شوند. اگر نام یا owner تغییر کرد، برنامه با شناسهٔ ثابت Repository را دوباره پیدا و URLها را تازه‌سازی کند.

### ۴.۲. اتصال پروژهٔ Workbench به Repository

در تنظیمات هر پروژه، بخش `GitHub Repository` وجود داشته باشد:

- حساب GitHub.
- Repository متصل.
- مسیر محلی Repository.
- مسیر زیرپوشهٔ پروژه در Repository در صورت نیاز.
- Default branch.
- Working/development branch.
- سیاست Commit و Push.
- Workflow ساخت مرتبط.
- الگوی نام Artifact.
- Release channel پیش‌فرض.
- شناسه/هش آخرین Commit همگام‌شده.

یک پروژهٔ Workbench ممکن است زیرپوشه‌ای از یک Monorepo باشد. در این حالت root واقعی Git باید جدا از subpath پروژه نگهداری شود. تمام عملیات Git در root انجام می‌شود؛ در حالی‌که Scope فایل‌ها و build می‌تواند به یک subpath محدود شود.

### ۴.۳. پیوند دادن Repository موجود به پوشهٔ محلی

هنگام Link:

1. Workbench مسیر محلی را canonicalize و وجود `.git` را بررسی کند.
2. Remoteهای موجود را بخواند و مقصد هرکدام را بدون افشای Credential نمایش دهد.
3. کاربر Remote/Repository موردنظر را تأیید کند.
4. GitHub metadata را با API دریافت و شناسهٔ Repository را ثبت کند.
5. اگر Remote محلی با Repository انتخاب‌شده متفاوت است، عملیات Link متوقف و گزینه‌های Replace Remote یا Cancel نمایش داده شوند؛ Remote به‌صورت پنهانی تغییر نکند.
6. اگر پروژه هنوز Git Repository نیست، دو گزینه وجود داشته باشد: ساخت محلی و Push اولیه، یا Clone کردن Repository موجود.

پیش از اولین Push از پروژهٔ موجود باید Preview فایل‌های Git که قرار است ارسال شوند نشان داده شود. فایل‌های محلی حساس، خروجی‌های build، دیتابیس‌های موقت، `.env`، کلیدها و cacheها بررسی شوند. `.gitignore` پیشنهادی ایجاد یا تکمیل شود، ولی محتوای آن بدون Preview جایگزین نشود.

### ۴.۴. یک Repository متصل به چند پروژه

این حالت در Monorepo طبیعی است. مدل داده باید اجازه دهد چند `ProjectBinding` به یک `repository_id` اشاره کنند و هر کدام `subpath` متفاوت داشته باشند. در عین حال، عملیات Commit/Push همیشه روی root Repository انجام می‌شود. Workbench باید فایل‌های تغییرکرده خارج از subpath پروژهٔ فعال را نیز نشان دهد؛ نباید تغییرات مشترک را نادیده بگیرد یا ناخواسته Commit کند.

---

## ۵. مرکز عملیات Git

### ۵.۱. پنل Git پروژه

در صفحهٔ پروژه یک پنل قابل دسترس شامل این اطلاعات باشد:

- Branch جاری و وضعیت upstream.
- وضعیت local: clean، تغییرات unstaged، staged، untracked، deleted.
- وضعیت remote: ahead/behind/diverged، در صورت امکان پس از fetch.
- آخرین Commit محلی و آخرین Commit Remote.
- فهرست تغییرات به تفکیک staged/unstaged/untracked.
- آخرین عملیات Git و نتیجهٔ آن.
- دکمه‌های `Refresh Status`، `Fetch`، `Commit & Push`، `Pull/Sync`، `Create Branch` و `Open on GitHub`.

هر عملیات در worker/background thread اجرا شود؛ درخواست شبکه یا اجرای Git نباید UI را قفل کند. خروجی عملیات به‌صورت مرحله‌ای نمایش داده شود و در صورت بستن پنجره، عملیات در صورت امکان کنترل‌شده ادامه یابد یا لغو امن شود.

### ۵.۲. Commit مرتبط با Task

برای Commitهایی که از Workbench ایجاد می‌شوند، ارتباط با تسک قابل‌ردیابی باشد. قالب پیام قابل تنظیم باشد، مثلاً:

`AIWB-142: Add restore preview`

در صورت امکان، metadata محلی شامل `task_id`، `run_id` و شناسهٔ Apply به Commit مرتبط شود؛ اطلاعات محرمانه یا کل محتوای Prompt در پیام Commit قرار نگیرد مگر کاربر صریحاً بخواهد. در UI بتوان Commit را به Task/Run برگرداند و از Task به Commit رسید.

پیشنهاد پیام Commit می‌تواند از عنوان تسک و خلاصهٔ تغییرات ساخته شود؛ کاربر پیش از Commit امکان ویرایش آن را داشته باشد.

### ۵.۳. Sync Plan پیش از Push/Pull

قبل از عملیات همگام‌سازی، وضعیت محلی و Remote مقایسه و یک Plan قابل‌فهم ساخته شود:

- فقط local جلوتر است: Push می‌تواند ادامه یابد.
- فقط Remote جلوتر است و local clean است: Fetch و Fast-forward طبق سیاست مجاز است.
- local و Remote هر دو جلو هستند: وضعیت diverged است؛ عملیات باید متوقف و مسیر merge/rebase یا انتخاب دستی پیشنهاد شود.
- working tree دارای تغییرات محلی است: قبل از Pull/Reset بررسی شود که تغییرات در معرض overwrite قرار نگیرند.
- Branch مورد انتظار وجود ندارد یا Remote تغییر کرده: وضعیت جدید و اقدام لازم نمایش داده شود.

Force Push در نسخهٔ نخست در جریان عادی Sync وجود نداشته باشد. عملیات destructive مانند reset سخت، پاک‌کردن تغییرات محلی یا force push در مسیر عادی دکمهٔ Sync قرار نگیرند.

### ۵.۴. سیاست سطح اتوماسیون به‌ازای هر پروژه

در تنظیمات Repository یکی از حالت‌ها انتخاب شود:

1. `Manual`: کاربر هر بار Commit و Push را جداگانه اجرا می‌کند.
2. `One-click Sync`: یک عملیات پس از Preview، Commit/Push و در صورت انتخاب کاربر، اجرای Build را انجام می‌دهد.
3. `After-Apply Proposal`: پس از Apply موفق، پیشنهاد Commit/Push ساخته می‌شود، ولی خودکار اجرا نمی‌شود.
4. `Auto Commit & Push to Development` (پیشرفته و اختیاری): فقط پس از فعال‌سازی صریح، در Branch توسعهٔ مشخص و تحت قواعد از پیش تعیین‌شده عمل می‌کند. اگر تعارض، فایل حساس، تغییر Workflow، تغییر خارج از scope یا تست ناموفق باشد، اتوماسیون متوقف شود.

حالت‌های پیشرفته باید در UI کاملاً شفاف باشند؛ فعال‌شدن آن‌ها نباید به‌صورت پیش‌فرض برای تمام پروژه‌ها انجام شود. سیاست یک پروژه نباید روی پروژهٔ دیگر اثر بگذارد.

---

## ۶. دکمهٔ یک‌کلیکی Sync & Build

### ۶.۱. هدف

از داخل Workbench یک مسیر واضح وجود داشته باشد که تغییرات تأییدشده را به GitHub بفرستد، CI را اجرا/پیگیری کند و Artifact متعلق به همان Commit را برگرداند.

### ۶.۲. مراحل داخلی

1. **Preflight:** بررسی حساب متصل، Repository، root محلی، Branch، working tree و وضعیت Remote.
2. **Change Review:** نمایش همهٔ staged/unstaged/untracked/deleted files و Diff. فایل‌های untracked را پنهان نکن.
3. **Sensitive-file review:** بررسی احتمالی `.env`، کلیدهای خصوصی، Tokenها، فایل‌های credential، dumpهای محلی و فایل‌های خروجی حجیم/ناخواسته. نتیجه فقط پیشنهاد نیست؛ موارد پرریسک باید قبل از Stage/Commit تعیین تکلیف شوند.
4. **Commit preparation:** پیشنهاد عنوان Commit بر اساس Task ID، عنوان و تغییرات؛ امکان ویرایش.
5. **Fetch and reconcile:** وضعیت Remote دوباره بررسی شود. اگر Remote از snapshot اولیه تغییر کرده، Plan تازه ساخته شود.
6. **Commit:** فقط تغییرات انتخاب‌شده commit شوند. Commit خالی فقط در حالتی مجاز باشد که عملیات release/dispatch عمداً به Commit موجود اشاره می‌کند.
7. **Push:** به Branch مشخص‌شده. در خطای non-fast-forward توقف و توضیح؛ force push خودکار ممنوع.
8. **Run CI:** Workflow مرتبط بر اساس پیکربندی پروژه و Commit SHA دقیق دنبال شود؛ اگر workflow نیاز به dispatch دستی دارد، از endpoint مناسب استفاده شود.
9. **Monitor:** مرحله‌ها، زمان اجرا، خطاها و لینک مستقیم به GitHub Actions در UI ظاهر شوند.
10. **Retrieve artifact:** فقط پس از پایان موفق و با تطبیق Repository، run ID و commit SHA، Artifact موردنظر دانلود شود.
11. **Verify:** Hash فایل دانلودشده محاسبه و نتیجه ثبت شود؛ در صورت موجود بودن manifest امضاشده/منتشرشده نیز تطبیق داده شود.
12. **Record:** Git operation، Task/Run، commit SHA، workflow run، artifact ID، نام فایل، Hash و نتیجه در تاریخچه ثبت شوند.

### ۶.۳. وضعیت UI

وضعیت‌های قابل‌فهم، برای نمونه:

`Checking` → `Review Required` → `Ready to Commit` → `Committed` → `Pushing` → `CI Queued` → `CI Running` → `Build Passed/Failed` → `Artifact Downloaded`.

شکست در مرحلهٔ Push نباید به‌صورت کلی «Build Failed» نشان داده شود. در هر مرحله، پیام خطا و اقدام بعدی مرتبط نمایش داده شود. اگر Commit ساخته شده ولی Push ناموفق بوده، برنامه باید این واقعیت را روشن گزارش کند و Commit محلی را بی‌دلیل حذف نکند.

### ۶.۴. اجرای هم‌زمان و Cancel

برای هر Repository از اجرای دو Sync/Build متعارض به‌صورت هم‌زمان جلوگیری شود، مگر عملیات مستقل با Branchهای جداگانه باشند. دکمهٔ Cancel باید معلوم کند کدام بخش قابل لغو است: قبل از Push می‌توان Stage/Commit بعدی را متوقف کرد؛ پس از شروع GitHub Actions باید از API لغو Run استفاده شود، ولی حذف Commit یا Undo خودکار انجام نشود.

---

## ۷. GitHub Actions و Build Center

### ۷.۱. صفحهٔ Build Center

صفحه‌ای با عنوان `Build Center` داشته باش که برای پروژهٔ انتخاب‌شده این اطلاعات را نشان دهد:

- Repository و Branch.
- Workflowهای کشف‌شده از `.github/workflows/` و وضعیت فعال بودنشان.
- آخرین چند workflow run.
- وضعیت run: queued، in progress، success، failure، cancelled، skipped یا نتیجهٔ دیگری که API گزارش می‌کند.
- commit SHA کوتاه و لینک commit.
- زمان شروع/پایان و duration در صورت موجود بودن.
- Job و Step ناموفق و لینک Log در GitHub.
- Artifactهای موجود، اندازه/نام در صورت ارائه و تاریخ انقضا اگر API آن را گزارش کند.
- دکمه‌های `Run Workflow`، `Refresh`، `Open Run on GitHub`، `Download Artifact` و `Cancel Run` در صورت مجازبودن.

### ۷.۲. کشف Workflow

در زمان اتصال Repository، فایل‌های `.github/workflows/*.yml` و `*.yaml` بررسی شوند. برای هر Workflow، نام، فایل، triggerهای قابل‌تشخیص و ورودی‌های `workflow_dispatch` در صورت وجود نمایش داده شوند. نباید فرض شود همهٔ Workflowها دستی قابل اجرا هستند.

برای هر پروژه یک Workflow اصلی Build انتخاب شود و انتخاب در تنظیمات ذخیره گردد؛ در صورت حذف/تغییرنام فایل، خطای binding روشن نمایش داده شود.

### ۷.۳. اجرای دستی Workflow

UI ورودی‌های تعریف‌شده در `workflow_dispatch` را از schema یا فایل Workflow بخواند، نوع و مقادیر مجاز را نشان دهد و فرم اجرا بسازد. چون GitHub API برای dispatch ورودی‌های مشخص را می‌پذیرد و نیازمندی permission بسته به نوع Token متفاوت است، برنامه باید خطای permission را به‌شکل جداگانه تفسیر کند. در صورت dispatch موفق، از run ID یا اطلاعات بازگشتی API استفاده شود؛ اگر شناسهٔ run در پاسخ موجود نیست، run مرتبط بر اساس Repository، workflow، ref و زمان شروع پیدا شود و تا وقتی تطبیق با اطمینان کافی انجام نشده، به‌عنوان خروجی همان درخواست نمایش داده نشود.

### ۷.۴. دنبال‌کردن Run درست

برای جلوگیری از اشتباه وقتی چند Push در فاصلهٔ کم انجام می‌شوند، تمام نتایج به `repository_id + workflow_id + run_id + head_sha` متصل شوند. دریافت «آخرین APK» بدون بررسی Commit، روش قابل‌قبولی نیست.

### ۷.۵. دریافت Artifact

- از API/روش رسمی GitHub برای فهرست و دانلود Artifact استفاده شود.
- برای Repository خصوصی، دانلود با Credential معتبر انجام شود و لینک موقت/دانلودشده در Log افشا نشود.
- Artifact ZIP قبل از استخراج از نظر تعداد فایل، مسیر traversal، اندازهٔ فشرده/بازشده، تکرار مسیر و فایل‌های ویژه اعتبارسنجی شود.
- کاربر بتواند مستقیم Artifact را دانلود کند یا محل ذخیره را انتخاب کند.
- فایل موقت ناقص پس از شکست پاک‌سازی شود.
- Artifactهای Actions تاریخ انقضا دارند؛ پس از زمان نگهداری قابل تنظیم حذف می‌شوند. خروجی‌های مهم و پایدار باید به GitHub Release منتقل شوند، نه اینکه فقط به Artifact موقت وابسته باشند.

### ۷.۶. Rate limit و polling

درخواست وضعیت Run نباید به‌صورت حلقهٔ سریع و ثابت اجرا شود. از فاصلهٔ polling معقول، backoff و headers نرخ درخواست استفاده شود. هنگام بازشدن Build Center، آخرین اطلاعات cacheشده فوری نشان داده و به‌صورت پس‌زمینه تازه‌سازی شود. UI نباید قفل شود.

---

## ۸. معماری CI برای Monorepo

### ۸.۱. Workflowهای جدا با قرارداد مشترک

پیشنهاد اولیه:

- `desktop-ci.yml`: تست و بسته‌بندی/اعتبارسنجی بخش دسکتاپ.
- `mobile-ci.yml`: تست، analyze و build بخش موبایل.
- `contracts-ci.yml` یا بخشی مشترک در workflowها: اعتبارسنجی schemaها و fixtureها؛ تغییر قراردادهای مشترک باید تست هر دو پلتفرم را فعال کند.
- `release-desktop.yml`: ساخت و انتشار نسخهٔ دسکتاپ.
- `release-mobile.yml`: ساخت APK/AAB و انتشار موبایل.
- `pr-checks.yml` اختیاری: یک Check جمع‌بندی‌شده که وضعیت jobهای مرتبط را نشان دهد.

فایل‌های Workflow باید ساده و دارای بخش‌های مشترک قابل‌بازاستفاده باشند. در صورت نیاز از composite action یا reusable workflow استفاده شود؛ اما در نسخهٔ نخست از abstraction بیش‌ازحد پرهیز شود.

### ۸.۲. اجرای تست بر اساس مسیرهای تغییرکرده

- تغییر در `apps/desktop/**` باید تست‌های Desktop را اجرا کند.
- تغییر در `apps/mobile/**` باید تست‌های Mobile را اجرا کند.
- تغییر در `packages/contracts/**` باید تست‌های مرتبط هر دو اپ را اجرا کند.
- تغییر در ریشهٔ build، dependencies، lockfileهای مشترک، ابزارهای code generation یا workflowهای مشترک باید jobهای متأثر را اجرا کند.
- تغییر `docs/**` به‌تنهایی می‌تواند Build کامل را نیاز نداشته باشد، مگر قراردادهای انتشار/مستندات آن تغییر کرده باشند.

**نکتهٔ GitHub Actions:** استفادهٔ صرف از `paths` ممکن است کل Workflow را اجرا نکند و اگر یک Check برای Merge اجباری شده باشد، Check مورد انتظار در وضعیت Pending باقی بماند. برای branch protection، طراحی باید تضمین کند که یک Check جمع‌بندی‌شده همیشه وضعیت نهایی بدهد؛ یا Workflow همیشه اجرا شود و jobهای نامرتبط داخل آن با شرط اجرا نشوند. این رفتار در تست Pull Request بررسی شود.

### ۸.۳. Branch strategy

برای شروع:

- `main`: شاخهٔ قابل انتشار؛ تغییر مستقیم با سیاست پروژه محدود شود.
- `development` یا Branchهای feature: کار روزمره و توسعهٔ مدل‌ها.
- `feature/<task-id>-short-name`: برای تغییرات بزرگ/پرریسک یا کارهای موازی.
- Pull Request به `main` برای تغییرات مشترک/انتشار.

برای استفادهٔ شخصی، کاربر می‌تواند عملیات روزمره را از داخل Workbench ساده کند؛ اما CI باید مستقل باشد و به اجرای UI روی ویندوز وابسته نشود.

### ۸.۴. Build قابل‌تکرار و ارتباط با Commit

هر Build باید از Commit مشخصی روی runner پاک ساخته شود. Build نباید به فایل‌های محلی خارج از Repository، تنظیمات تصادفی دستگاه برنامه‌نویس یا خروجی‌های باقیمانده از اجرای قبلی وابسته باشد. فایل‌های dependency lock و نسخه‌های ابزارهای حیاتی به‌روزرسانی و ثبت شوند.

نسخهٔ Build باید بتواند این مقادیر را ارائه کند: platform، app version، build number/versionCode در موبایل، commit SHA، branch/tag و channel. این اطلاعات در صفحهٔ About نسخهٔ موبایل نیز در دسترس باشند.

---

## ۹. انتشار و به‌روزرسانی اپ موبایل

### ۹.۱. Artifact آزمایشی در مقابل Release پایدار

این دو مفهوم جدا باشند:

- **Actions Artifact:** مناسب خروجی موقت از هر اجرای CI؛ برای تست سریع.
- **GitHub Release Asset:** مناسب نگهداری نسخهٔ شماره‌گذاری‌شده، فایل APK/AAB یا نصب‌کننده و Release Notes.

سیاست نگهداری Artifactهای Actions محدود است و به‌طور پیش‌فرض Artifactها پس از مدتی (در مستندات فعلی GitHub معمولاً ۹۰ روز، قابل تنظیم بر اساس سیاست Repository) منقضی می‌شوند. نسخه‌ای که باید پایدار و قابل دانلود بماند باید در Release قرار بگیرد.

### ۹.۲. نسخه‌گذاری موبایل

- `versionName` برای نمایش به کاربر.
- `versionCode` عدد صحیح افزایشی برای Android؛ هر Build قابل انتشار به نسخهٔ متناسب خود نیاز دارد.
- برای هر انتشار، شناسهٔ Commit و کانال (`dev`، `beta`، `stable`) ثبت شود.
- افزایش نسخه فقط در یک محل قابل‌اعتماد انجام شود؛ از تعریف چند مقدار متناقض در فایل‌های پراکنده جلوگیری شود.
- Tagهای دسکتاپ و موبایل مستقل نام‌گذاری شوند تا نسخه‌های یک اپ با دیگری تداخل نکنند.

### ۹.۳. امضای Android

- Debug build و release build از هم جدا باشند.
- کلید امضای Release داخل Git قرار نگیرد.
- فقط Workflow انتشار محافظت‌شده به Secretهای امضا دسترسی داشته باشد.
- نسخه‌های به‌روزرسانی باید با کلید امضای سازگار با نسخهٔ نصب‌شده ساخته شوند؛ کلید امضا بخشی حیاتی از تداوم نصب/به‌روزرسانی است.
- Pull Requestهای معمولی و branchهای ناشناخته نباید Secret امضای Release دریافت کنند.
- APK آزمایشی و APK پایدار در UI با برچسب روشن نمایش داده شوند.

### ۹.۴. به‌روزرسانی مستقیم از داخل Android

در مرحلهٔ اول، Build Center امکان دریافت APK را از داخل دسکتاپ فراهم کند. قابلیت بررسی نسخهٔ جدید داخل اپ موبایل در مرحلهٔ بعد اضافه شود.

برای بررسی نسخه، یک Manifest انتشار تعریف شود که حداقل شامل این موارد باشد:

```json
{
  "app": "ai-workbench-mobile",
  "versionName": "0.1.0",
  "versionCode": 1,
  "channel": "beta",
  "commitSha": "COMMIT_SHA",
  "releaseUrl": "RELEASE_URL",
  "assetName": "AIWorkbench-mobile.apk",
  "sha256": "SHA256_OF_ASSET",
  "minimumSupportedVersionCode": 1,
  "releaseNotes": "..."
}
```

این JSON فقط نمونهٔ قرارداد است؛ مقادیر واقعی باید توسط Release Workflow تولید شوند، نه دستی و ناسازگار با APK. Manifest از منبع قابل اعتماد دریافت شود. اپ باید نسخهٔ فعلی را با `versionCode` مقایسه کند، کانال انتخاب‌شدهٔ کاربر را رعایت کند، Hash فایل دانلودشده را بررسی کند و پیش از نصب، سیستم‌عامل را به جریان نصب مناسب هدایت کند. نصب خارج از فروشگاه ممکن است به تأیید کاربر/مجوز نصب از منبع مشخص نیاز داشته باشد؛ برنامه نباید نصب بی‌صدای تضمین‌شده را وعده دهد.

برای Repository خصوصی، مسیر دریافت Release باید احراز هویت داشته باشد. PAT کاربر نباید hardcode شود یا از یک حساب به کاربر دیگر منتقل شود. برای توزیع گسترده، فروشگاه یا سرویس توزیع مناسب ممکن است تجربهٔ بهتری بدهد.

### ۹.۵. iOS در آینده

اگر iOS اضافه شد، چرخهٔ Build/Distribution آن مستقل از APK خواهد بود؛ گواهی‌ها و provisioning، signing و کانال تست iOS باید جدا مدیریت شوند. قراردادهای Task/Artifact/Release می‌توانند مشترک باشند، اما جزئیات امضا و نصب را نباید با Android یکی فرض کرد.

---

## ۱۰. قرارداد مشترک قابلیت‌ها و جلوگیری از عقب‌ماندن موبایل

### ۱۰.۱. Capability Registry

در Repository یک فایل مانند `packages/contracts/capabilities.yml` نگهداری شود که وضعیت هر قابلیت را برای Desktop، Mobile و Companion نشان می‌دهد.

نمونه:

```yaml
schemaVersion: 1
features:
  task_history:
    desktop: implemented
    mobile: planned
    companion: supported
  restore_manager:
    desktop: implemented
    mobile: planned
    companion: planned
  github_build_center:
    desktop: planned
    mobile: planned
    companion: supported
```

وضعیت‌ها می‌توانند شامل `planned`، `in_progress`، `implemented`، `partial`، `not_applicable` و `blocked` باشند. این Registry در نسخهٔ نخست اطلاعات/هشدار است و نباید به‌تنهایی قابلیت را به‌طور خودکار فعال یا غیرفعال کند مگر feature gating صریحاً طراحی و تست شده باشد.

### ۱۰.۲. Feature ID و Definition of Done

هر قابلیت مهم یک ID پایدار داشته باشد، مثلاً `restore_manager` یا `context_planning`. تسک ویندوز می‌تواند Feature ID، معیار پذیرش، قراردادهای دادهٔ تغییرکرده و نیازمندی موبایل را ثبت کند.

هنگام تکمیل تسک ویندوز، Workbench اگر Feature ID موبایل هنوز `planned` یا `partial` است، پیشنهاد ساخت/به‌روزرسانی تسک موبایل بدهد. این پیشنهاد می‌تواند از قالب آماده برای مدل استفاده کند: رفتار مطلوب، پلتفرم‌های مورد تأثیر، fixtureها، تست‌های مشترک و محدودیت‌های UI موبایل.

این کار انتقال خودکار کد ویندوز نیست؛ انتقال قرارداد و تعریف رفتار است.

### ۱۰.۳. قراردادهای دادهٔ مشترک

برای موجودیت‌هایی که باید در هر دو اپ معنای یکسان داشته باشند، schema نسخه‌دار تعریف شود؛ حداقل:

- `Project`
- `Task`
- `Run`
- `PromptRecord`
- `Artifact`
- `ReviewDecision`
- `ValidationResult`
- `GitHubRepositoryBinding`
- `BuildRun`
- `CapabilityStatus`

JSON Schema یا یک قرارداد صریح معادل به‌عنوان source of truth نگهداری شود. برای Python و زبان موبایل typeها می‌توانند تولید یا به‌صورت دستی نگهداری شوند، اما fixtureهای مشترک باید در CI هر دو پلتفرم پردازش شوند. تغییر schema باید version داشته باشد و نمونه‌های نسخهٔ قبل به‌عنوان regression test حفظ شوند.

### ۱۰.۴. Desktop و Mobile برابر کامل نیستند

برای هر Feature، رفتار پلتفرمی صریح تعریف شود. مثلاً:

- عملیات فایل پروژهٔ Windows و اجرای فرمان ویندوز در اپ مستقل موبایل در دسترس نیست.
- موبایل می‌تواند Task بسازد، Prompt تهیه کند، پاسخ دریافت کند و CI را مشاهده کند.
- Companion می‌تواند از دسکتاپ درخواست عملیات کند، ولی اعمال فایل/اجرای فرمان همچنان روی ویندوز و از طریق مجوزهای آن انجام می‌شود.
- GitHub Build Center می‌تواند از هر دو پلتفرم وضعیت Workflow و Artifact را نمایش دهد، مشروط به دسترسی حساب و مجوزها.

ماتریس قابلیت‌ها باید تفاوت را توضیح دهد، نه اینکه هر تفاوت پلتفرمی را به‌عنوان باگ ثبت کند.

---

## ۱۱. Companion موبایل برای کنترل Workbench ویندوز

این قابلیت از GitHub Sync جداست و بهتر است پس از تثبیت Repository و Build Center ساخته شود.

### ۱۱.۱. هدف

گوشی می‌تواند به Workbench در حال اجرا روی PC متصل شود تا کاربر تسک بسازد، پاسخ مدل را تحویل دهد، وضعیت Apply/CI را ببیند و درخواست عملیات را ارسال کند؛ عملیات فایل و فرمان روی PC اجرا شود.

### ۱۱.۲. Pairing و دسترسی

- کاربر از UI ویندوز `Pair device` را انتخاب کند؛ برنامه یک QR/کد یک‌بارمصرف با زمان انقضا بسازد.
- گوشی کد را اسکن کند و کاربر اتصال را در دسکتاپ تأیید کند.
- ارتباط رمزنگاری و احراز هویت داشته باشد؛ Tokenهای GitHub دسکتاپ به گوشی کپی نشوند.
- دسترسی‌ها تفکیک شوند: مشاهدهٔ پروژه، ایجاد Task، ارسال پاسخ، تأیید Preview، درخواست Apply، مشاهدهٔ Log و اجرای فرمان. مجوزهای حساس قابل لغو باشند.
- هر درخواست از موبایل به سرویس‌های مرکزی دسکتاپ ارجاع شود؛ نباید API شبکه‌ای جداگانه‌ای وجود داشته باشد که کنترل‌های Apply/Runner را دور بزند.
- اتصال محلی، reconnect، قطع اتصال، لغو Pairing و فهرست دستگاه‌های مجاز قابل مدیریت باشد.
- بازکردن اتصال مستقیم از اینترنت عمومی، بدون طراحی Relay و مدل تهدید مناسب، در نسخهٔ اولیه انجام نشود.

### ۱۱.۳. مراحل توسعه

ابتدا Pairing محلی و read-only (وضعیت Task/Build)؛ سپس ساخت Task و ارائهٔ پاسخ؛ و تنها بعد از تست دسترسی‌ها، درخواست عملیات نوشتن/اجرایی با تأیید روشن کاربر.

---

## ۱۲. مدل دادهٔ پیشنهادی

نام جدول‌ها/کلاس‌ها با datastore موجود هماهنگ شود؛ ساختار مفهومی باید این اطلاعات را پوشش دهد.

### ۱۲.۱. `GitHubAccount`

- `account_id` محلی پایدار.
- `provider_type` (PAT، GitHub App/OAuth یا نوع بعدی).
- `github_user_id` و `login`.
- `credential_ref`؛ فقط ارجاع امن، نه خود Token.
- `connection_status` و `last_verified_at`.
- `capability_snapshot` با زمان بررسی؛ snapshot جایگزین بررسی واقعی permission در عملیات نمی‌شود.
- تنظیمات غیرحساس مانند label کاربر.

### ۱۲.۲. `RepositoryBinding`

- `binding_id`.
- `project_id`.
- `account_id`.
- `repository_id`.
- `owner`, `name`, `html_url`, `default_branch`.
- `local_git_root` و `project_subpath`.
- `working_branch` و سیاست Sync.
- `workflow_file`، `artifact_pattern` و `release_channel`.
- `last_known_remote_sha` و زمان آخرین Sync.

### ۱۲.۳. `GitOperationRecord`

- `operation_id`, `project_id`, `task_id`, `run_id`.
- نوع عملیات و وضعیت.
- branch، commit SHA، remote URL بدون credential.
- فهرست تغییرات و نتیجهٔ Preflight.
- زمان شروع/پایان، کد خروج و خطای redactشده.
- شناسهٔ workflow run در صورت اتصال به Build.

### ۱۲.۴. `BuildRunRecord`

- `repository_id`, `workflow_id`, `run_id`, `head_sha`, `ref`.
- وضعیت، نتیجه، URL وب، زمان شروع/پایان.
- Artifact IDها، نام‌ها، metadata و Hash فایل دریافت‌شده.
- `source_task_id` یا `source_operation_id` در صورت شروع از Workbench.

### ۱۲.۵. Migration و سازگاری

اگر تنظیمات پروژه در نسخهٔ 1.13 schema دیگری دارند، داده‌ها با مهاجرت نسخه‌دار منتقل شوند. Migration باید idempotent باشد یا با نسخهٔ schema از اجرای دوباره جلوگیری کند. شکست Migration نباید تنظیمات قبلی را بی‌صدا پاک کند؛ backup و گزارش خطا فراهم باشد.

---

## ۱۳. امنیت، حریم خصوصی و کنترل اجرای مدل

1. مدل می‌تواند فایل Workflow یا اسکریپت Build را تغییر دهد؛ بنابراین تغییر در `.github/workflows/**` یک تغییر پرریسک محسوب شود و Preview واضح داشته باشد.
2. در CI مربوط به Pull Requestهای غیرقابل‌اعتماد، Secretهای Release در دسترس نباشند. امضای APK و انتشار عمومی در job/environment محافظت‌شده انجام شود.
3. از `GITHUB_TOKEN` داخلی Actions برای عملیات داخل همان Workflow تا جای ممکن استفاده شود؛ برای دسترسی از Workbench محلی به API، credential کاربر طبق روش اتصال انتخاب‌شده استفاده شود.
4. مجوزهای Workflow در `permissions:` صریح و حداقلی تعریف شوند؛ وقتی Job فقط read لازم دارد، `contents: read` و مجوزهای دیگر غیرفعال/تعریف‌نشده باقی بمانند.
5. Actionهای شخص ثالث به نسخهٔ مشخص و قابل‌اعتماد pin شوند؛ استفاده از refهای متغیر برای Actionهای حساس از بازتولیدپذیری و کنترل زنجیرهٔ تأمین می‌کاهد.
6. توکن نه در Git، نه در فایل JSON پروژه، نه در URL Remote و نه در گزارش‌ها قرار بگیرد.
7. اجرای فرمان‌های مدل و فایل‌های اجرایی دریافت‌شده از CI/ZIP همچنان نیازمند همان کنترل‌ها و تأییدهای تعریف‌شدهٔ Workbench باشد.
8. Buildی که موفق می‌شود به‌معنای بی‌خطر یا درست‌بودن منطقی اپ نیست؛ تست‌های لازم و بازبینی انسانی قبل از Release پایدار همچنان اعمال شوند.
9. ساخت APK و Release را بر اساس commit SHA مشخص انجام بده تا تغییر ورودی پس از شروع Build منجر به ابهام منشأ نشود.
10. اگر حساب یا Token قطع/لغو شد، عملیات جدید متوقف شود؛ عملیات در حال اجرا باید وضعیت و امکان ادامه/لغو آن را گزارش کند.

---

## ۱۴. برنامهٔ اولویت‌بندی‌شده

### P0 — راه‌اندازی کم‌ریسک و اثبات مسیر کامل

**هدف:** یک Repository از داخل Workbench قابل اتصال باشد و Build قابل دانلود تولید کند.

1. بررسی سورس و معماری واقعی نسخهٔ 1.13 و تعیین سرویس‌های قابل استفادهٔ مجدد.
2. ایجاد/تثبیت Monorepo و مهاجرت مرحله‌ای سورس Desktop.
3. ایجاد ساختار اولیهٔ `apps/mobile` و یک اپ آزمایشی حداقلی برای اثبات Build pipeline.
4. ایجاد Workflow سادهٔ CI که روی PR اجرا شود و تست‌ها را اجرا کند.
5. ایجاد Workflow Android Build که APK آزمایشی بسازد و آن را به‌صورت Actions Artifact منتشر کند.
6. صفحهٔ GitHub Accounts با PAT، Test Connection و ذخیرهٔ Credential در secure store.
7. Repository Browser و اتصال یک پروژهٔ آزمایشی به Repository.
8. پنل Git با وضعیت، Diff، Commit و Push کنترل‌شده.
9. تأیید اینکه Build اجراشده به همان Commit SHA مربوط است و Artifact از داخل Workbench قابل دریافت است.

**معیار عبور از P0:** کاربر بتواند از داخل Workbench یک تغییر آزمایشی را بررسی، Commit و Push کند؛ GitHub Actions موفق شود؛ APK مربوط به همان SHA دریافت شود؛ و هیچ نیازی به کپی Token داخل command line، URL یا فایل پروژه وجود نداشته باشد.

### P1 — تجربهٔ یکپارچهٔ روزانه

1. Sync Plan قبل از Push/Pull و رسیدگی به divergence.
2. Sync & Build یک‌کلیکی با وضعیت مرحله‌به‌مرحله.
3. مشاهدهٔ Workflow runها، خطاها و Logها.
4. دریافت امن Artifact و اتصال آن به Task/Commit.
5. مدیریت چند حساب و چند Repository در پروژه‌های مختلف.
6. Commit message پیشنهادی و لینک متقابل Task ↔ Commit.
7. Branchهای توسعه و Feature branch.
8. تست خودکار خطاهای Token، مجوز، rate limit، تعارض Git و قطع شبکه.

### P2 — انتشار نسخه‌دار و همگام‌سازی قابلیت‌ها

1. Release workflows مجزا برای Desktop و Mobile.
2. Tagگذاری مستقل مانند `desktop-v*` و `mobile-v*`.
3. تولید Release Notes، Manifest، Hash و assetهای نسخه.
4. مدیریت امضای Android در Secret/Environment محافظت‌شده.
5. Capability Registry و schema/fixtureهای مشترک.
6. اجرای تست‌های هر دو پلتفرم در تغییر قراردادهای مشترک.
7. دانلود نسخه‌های قبلی از GitHub Release و نمایش منشأ آن‌ها.

### P3 — Companion و خودکارسازی پیشرفته

1. Pairing امن موبایل/دسکتاپ.
2. نمایش Task/Build از موبایل.
3. ایجاد Task و واردکردن پاسخ از موبایل.
4. درخواست Preview/Apply از گوشی از مسیر سرویس مرکزی دسکتاپ.
5. سیاست‌های خودکار per-project برای commit/push/build، با توقف در تعارض یا تغییر پرریسک.
6. در صورت نیاز، ورود با GitHub App/OAuth برای حذف Token دستی در دستگاه‌هایی که جریان ورود یکپارچه مطلوب است.

---

## ۱۵. معیارهای پذیرش کل پروژه

پیاده‌سازی فقط وقتی کامل محسوب می‌شود که این سناریوها آزمایش شده باشند:

1. افزودن PAT معتبر، تشخیص حساب و فهرست‌کردن Repositoryها با pagination.
2. Token معتبر اما فاقد permission لازم: قابلیت‌های موجود و غیرموجود درست گزارش شوند.
3. لغو Token یا حساب: عملیات بعدی خطای مناسب بدهد و credential پاک/جایگزین‌شدنی باشد.
4. اتصال پوشهٔ محلی به Repository موجود بدون قرارگرفتن Token در Remote URL.
5. اتصال پروژه به subpath در Monorepo؛ Commit فقط فایل‌های انتخاب‌شده را شامل شود و تغییرات بیرون از scope پنهان نشوند.
6. Push موفق و Push ردشده به دلیل non-fast-forward؛ هیچ Force Push خودکاری انجام نشود.
7. چند Push نزدیک به هم؛ Build Center Artifact را با تطبیق دقیق `head_sha` به Commit درست متصل کند.
8. Workflow دستی با ورودی‌های لازم اجرا شود؛ Workflow بدون `workflow_dispatch` به‌عنوان دستی قابل اجرا نشان داده نشود.
9. API rate limit، 401، 403، 404، timeout و قطع شبکه از هم تفکیک شوند.
10. ZIP Artifact با path traversal، مسیر تکراری یا حجم غیرعادی رد شود.
11. Artifact موقت منقضی یا حذف‌شده، به‌عنوان دانلودشدنی نشان داده نشود؛ لینک GitHub Release برای نسخه‌های پایدار حفظ شود.
12. CI مربوط به Desktop، Mobile و contracts بر اساس تغییرات مرتبط اجرا شود؛ Checkهای مورد انتظار PR در وضعیت Pending دائمی نمانند.
13. Secret امضای APK در job عادی PR قابل دسترس نباشد.
14. تغییر Feature ID در ویندوز، در صورت نبود پشتیبانی موبایل، تسک/هشدار همگام‌سازی پیشنهاد دهد.
15. هیچ Credential در Log، exception، Commit، Remote URL یا Repository ظاهر نشود.
16. UI هنگام Clone/Push/Build/Download قفل نشود و نتیجهٔ واقعی هر مرحله ثبت گردد.
17. تست native Windows برای Git Credential Manager، مسیرها، نصب‌کننده و فرایندهای فرزند اجرا شود.

---

## ۱۶. تصمیم‌های لازم پیش از شروع پیاده‌سازی

برنامه‌نویس پس از بررسی سورس 1.13، این تصمیم‌ها را در یک ADR کوتاه ثبت کند:

1. ساختار فعلی سورس Desktop چگونه به Monorepo منتقل شود بدون شکستن installer و مسیرهای build؟
2. برای Git محلی، کدام Git executable/credential helper موجود استفاده می‌شود و چگونه با Token ذخیره‌شده هماهنگ خواهد شد؟
3. محل Secure Credential Store در Windows و معماری بعدی Android چیست؟
4. schema و migration تنظیمات پروژهٔ فعلی چگونه نسخه‌گذاری می‌شوند؟
5. مدل نسخه‌گذاری و Tagهای Desktop/Mobile دقیقاً چیست؟
6. کدام Workflowها باید به‌طور اجباری روی PR همیشه Check نهایی گزارش دهند؟
7. APK آزمایشی دقیقاً از کدام Workflow دریافت می‌شود و نام Artifact چیست؟
8. کلید امضای نسخهٔ موبایل کجا نگهداری می‌شود و چه محیطی اجازهٔ استفاده از آن را دارد؟
9. آیا ابتدا فقط Android هدف است یا باید از نخستین نسخهٔ ساختار، iOS نیز در نظر گرفته شود؟
10. کدام عملیات GitHub در P0 لازم‌اند و کدام‌ها باید به نسخه‌های بعد منتقل شوند؟

هیچ‌کدام از این تصمیم‌ها نباید باعث به‌تعویق افتادن اثبات مسیر اصلی شوند. ابتدا یک زنجیرهٔ کامل کوچک بساز و قابل اعتماد بودن آن را ثابت کن؛ سپس امکانات بیشتر را اضافه کن.

---

## ۱۷. منابع رسمی برای پیاده‌سازی

مستندات آنلاین ممکن است تغییر کنند؛ هنگام اجرا، نسخهٔ API، مجوز endpointها و رفتار Workflow را با مستندات روز GitHub تطبیق بده.

- GitHub: Managing personal access tokens  
  https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- GitHub: OAuth app best practices  
  https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/best-practices-for-creating-an-oauth-app
- GitHub REST API: permissions required for fine-grained PATs  
  https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens
- GitHub REST API: repositories  
  https://docs.github.com/en/rest/repos/repos
- GitHub REST API: workflows and workflow dispatch  
  https://docs.github.com/en/rest/actions/workflows
- GitHub Actions: workflow syntax and path filters  
  https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Actions: secure use  
  https://docs.github.com/en/actions/reference/security/secure-use
- GitHub Actions: downloading workflow artifacts  
  https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts
- GitHub: About Releases  
  https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- Android: App signing  
  https://developer.android.com/studio/publish/app-signing
- Android: App versioning  
  https://developer.android.com/studio/publish/versioning
- Apple: TestFlight overview  
  https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/

---

## تصمیم نهایی پیشنهادی

اولویت اصلی، **GitHub Hub + اتصال Repository + Sync & Build + دانلود Artifact از داخل Workbench** است. این مسیر باید پیش از توسعهٔ بزرگ اپ موبایل کامل شود؛ چون نتیجهٔ واقعی آن، زیرساختی است که بعداً برای ساخت، تست و انتشار موبایل و دسکتاپ استفاده خواهد شد.

پس از اثبات این حلقه، سورس فعلی دسکتاپ در Monorepo تثبیت شود، اپ موبایل به‌تدریج ساخته شود، قراردادهای مشترک و Capability Registry اضافه شوند و در مرحلهٔ بعد Companion موبایل توسعه یابد. در کل مسیر، وضعیت هر پروژه و هر دستگاه مستقل باقی بماند؛ فقط قراردادها، سورس و Artifactهایی که عمداً برای اشتراک انتخاب شده‌اند بین آن‌ها مشترک شوند.
