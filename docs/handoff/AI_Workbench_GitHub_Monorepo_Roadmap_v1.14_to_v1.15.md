# نقشه‌راه توسعهٔ GitHub و Monorepo در AI Workbench

**مبنای برنامه‌ریزی:** سورس واقعی `AI_Workbench_Source_v1.14.0.zip`، نه صرفاً متن مشخصات اولیه  
**مسیر نسخه‌ها:** `1.14.1` تا `1.14.13` و سپس `1.15.0`  
**وضعیت این سند:** برنامه‌ریزی؛ در این مرحله هیچ فایل سورس یا تنظیمات پروژه تغییر داده نشده است.

---

## 1. تصمیم اجرایی

پیشنهاد می‌کنم متن بزرگ توسعه به انتشارهای کوچک، وابسته و قابل‌قبول‌شدن مستقل تقسیم شود. هر نسخه باید یک برش عمودی قابل استفاده را تحویل دهد، نه صرفاً چند فایل یا کلاس جدید. شماره‌گذاری `1.14.n` مطابق خواستهٔ محصول حفظ می‌شود؛ با این ملاحظه که از دید Semantic Versioning، اضافه‌شدن قابلیت‌های کاربرمحور معمولاً با افزایش Minor نشان داده می‌شود. در این پروژه، شماره‌های `1.14.n` را به‌عنوان زنجیرهٔ نقاط کنترل توسعه در نظر می‌گیریم و `1.15.0` را انتشار یکپارچهٔ پایدار قرار می‌دهیم.

**قاعدهٔ مهم:** شمارهٔ نسخه به‌تنهایی به معنی تکمیل نیست. هر مرحله فقط پس از عبور از معیارهای پذیرش و تست‌های رگرسیون بسته می‌شود. اگر دروازهٔ یک مرحله شکست بخورد، شمارهٔ مرحلهٔ بعد را شروع نمی‌کنیم.

### هدف قابل تحویل در `1.15.0`

کاربر باید بتواند از درون Workbench:

1. حساب GitHub را با Token محدود و به‌صورت امن متصل کند.
2. Repositoryها را ببیند و Repository یا زیرپوشه‌ای از Monorepo را به پروژه پیوند دهد.
3. تغییرات محلی را مرور کند، فایل‌های موردنظر را انتخاب کند، Sync Plan دریافت کند و از Force Push یا از دست‌دادن خاموش تغییرات مصون بماند.
4. Commit/Push و Workflow مرتبط را اجرا یا دنبال کند.
5. Build Run و Artifact را دقیقاً به Repository، Run ID و Commit SHA مشخص متصل کند.
6. Artifact آزمایشی را امن دانلود و Hash آن را بررسی کند.
7. سورس خود AI Workbench را در Monorepo با CI قابل تکرار نگهداری کند و یک مسیر اولیهٔ Android Build داشته باشد.
8. نسخه‌های Desktop و Mobile را مستقل نسخه‌گذاری کند و Releaseهای شماره‌دار را از Artifactهای موقت جدا کند.

GitHub App/OAuth پیشرفته، iOS، Companion موبایل و اتوماسیون خودمختارِ پرریسک، هدف انتشار `1.15.0` نیستند؛ معماری باید بعداً از آن‌ها پشتیبانی کند، اما افزودنشان نباید زنجیرهٔ اصلی را به تأخیر بیندازد.

---

## 2. آنچه واقعاً در `1.14.0` وجود دارد

بر اساس بررسی سورس `AI_Workbench.py` و مستندات بسته:

### موجود و قابل توسعه

- تب `Git / GitHub` در رابط دسکتاپ.
- تشخیص Git و وضعیت Repository/Branch/Remote و فایل‌های تغییرکرده.
- نصب یا به‌روزرسانی Git از رابط.
- ساخت Branch جدید.
- Stage و Commit فایل‌های تغییرکرده با پیام واردشده توسط کاربر.
- Push با استفاده از احراز هویت Git تنظیم‌شده در Windows؛ برنامه ادعا می‌کند Token را خودش ذخیره نمی‌کند.
- جلوگیری از Push مستقیم به `main` و `master` در مسیر فعلی UI.
- بررسی ابتدایی مسیرهای حساس و الگوهای احتمالی اسرار، هم‌زمان با اعلام اینکه این بررسی تضمین کامل نیست.
- اجرای عملیات Git در worker برای جلوگیری از مسدودشدن رابط.
- ماژول‌های جدا برای برخی قابلیت‌های Workbench در `aiwb/` و سرویس‌های جداشدهٔ تاریخچه، نسخه‌بندی، Restore و پروفایل اعتبارسنجی.

### هنوز در زنجیرهٔ محصول وجود ندارد

- GitHub REST API client و مدیریت چرخهٔ عمر حساب‌های GitHub.
- صفحهٔ GitHub Accounts، ثبت وضعیت مجوزها و ذخیره‌سازی Credential مستقل برای API.
- Repository Browser با pagination و فیلترها.
- مدل پایدار `RepositoryBinding` که Repository ID، ریشهٔ Git و `project_subpath` را از هم جدا کند.
- Sync Plan رسمی بر اساس `fetch`، ahead/behind/diverged و Fast-forward-only.
- Commit انتخابی با مرور کامل staged/unstaged/untracked/deleted و تشخیص تغییرات بیرون از Scope پروژه.
- Build Center، فهرست Workflow/Run/Job، dispatch، polling مبتنی بر rate limit و Cancel.
- Artifact Browser، دانلود امن، اعتبارسنجی ZIP و Hash، و تطبیق Artifact با SHA دقیق Commit.
- جریان یکپارچهٔ Sync & Build، ثبت رابطهٔ Task/Run/Commit/Artifact و Releaseهای نسخه‌دار.
- ساختار Monorepo محصول، CI رسمی Desktop/Mobile و Capability Registry مشترک.

در نتیجه، بخش Git فعلی را حفظ و به سرویس منتقل می‌کنیم؛ API و Build Center را واقعاً از صفر اضافه می‌کنیم. به‌ویژه، منطق GitHub را نباید به‌صورت شرط‌های پراکنده در handlerهای Tkinter قرار دهیم.

---

## 3. معماری هدف و قواعد غیرقابل‌مذاکره

### 3.1 ساختار پیشنهادی

```text
AI-Workbench/
├── apps/
│   ├── desktop/                  # سورس فعلی Windows، مهاجرت مرحله‌ای
│   └── mobile/                   # ابتدا Android proof-of-build
├── packages/
│   └── contracts/                # Schema، fixture و Capability Registry
├── aiwb/                         # در مرحلهٔ مهاجرت، سپس به محل نهایی منتقل/تقسیم شود
│   ├── github/
│   │   ├── api_client.py
│   │   ├── accounts.py
│   │   ├── credential_store.py
│   │   ├── repository_registry.py
│   │   ├── project_binding.py
│   │   ├── actions_service.py
│   │   ├── artifact_service.py
│   │   └── release_service.py
│   ├── git/
│   │   ├── service.py
│   │   ├── sync_plan.py
│   │   └── models.py
│   ├── application/
│   │   └── sync_build_workflow.py
│   └── ...
├── docs/
│   ├── adr/
│   └── release/
├── tools/
├── tests/
├── .github/workflows/
├── README.md
└── CHANGELOG.md
```

این ساختار، مقصد نهایی پیشنهادی است، نه دستور جابه‌جایی یکباره. محل نهایی `aiwb/` در زمان مهاجرت باید با ساخت و نصب واقعی هماهنگ شود؛ مهم، مرز مسئولیت است، نه نام دایرکتوری.

### 3.2 مرز مسئولیت

- **UI/Tkinter:** نمایش داده، دریافت انتخاب، گرفتن تأیید و نمایش خطا؛ نه ساخت درخواست API یا اجرای مستقیم Git.
- **Application services:** هماهنگی Preflight → Review → Commit → Push → Build → Verify → Record.
- **Git service:** اجرای Git محلی، تشخیص وضعیت، Diff، Branch و Sync Plan.
- **GitHub API client:** HTTP، headerهای رسمی، pagination، خطاهای API، timeout، rate limit و redaction.
- **Credential store:** نگهداری امن Secret و بازگرداندن آن فقط در زمان نیاز؛ تنظیمات پروژه فقط `credential_ref` دارد.
- **Actions/Artifact/Release services:** مسئولیت‌های جدا، به‌جای کلاس واحد «GitHub Manager» بزرگ.
- **Persistence:** مهاجرت نسخه‌دار تنظیمات، bindingها و رکورد عملیات؛ migration ناموفق نباید دادهٔ قبلی را بی‌صدا حذف کند.

### 3.3 امنیت و رفتار پایه

1. هیچ Token در Remote URL، command-line argument، JSON پروژه، Repository، Commit، Log یا گزارش خطا نوشته نشود.
2. مسیر Git محلی همچنان از Git Credential Manager/credential helper سیستم استفاده کند؛ Token ذخیره‌شده برای REST API نباید به‌صورت خودکار داخل URL یا آرگومان Git تزریق شود.
3. روی Windows، Git Credential Manager در حالت پیش‌فرض از Windows Credential Manager پشتیبانی می‌کند؛ Workbench باید تنظیم موجود را بررسی کند، نه اینکه ذخیره‌ساز موازی و متعارض بسازد. Credential مربوط به REST API با `credential_ref` مستقل نگهداری می‌شود.
4. برای شروع، PAT دستی با راهنمای ساخت Fine-grained PAT و حداقل Permissionها پشتیبانی شود. معماری از ابتدا `AuthenticationProvider` را مستقل نگه دارد؛ GitHub App/OAuth با PKCE یا جریان رسمی مناسب بعداً اضافه شود و هیچ client secret محرمانه‌ای داخل برنامه بسته‌بندی نشود.
5. موفقیت `GET /user` به معنی داشتن مجوز همهٔ عملیات نیست. وضعیت Permission برای هر قابلیت جدا ثبت شود: `available`, `not_available`, `not_checked`, `requires_approval`.
6. هر عملیات تغییردهندهٔ Repository، Workflow یا Release، Preview/تأیید واضح داشته باشد. تغییر `.github/workflows/**` پرریسک محسوب شود.
7. Sync عادی Force Push، Hard Reset یا حذف خاموش تغییرات محلی ندارد.
8. Artifact ZIP پیش از استخراج، از نظر traversal، مسیر مطلق، مسیر تکراری/case-collision، symlink/فایل ویژه، تعداد فایل و اندازهٔ فشرده و بازشده کنترل شود.
9. موفقیت Build به معنی صحت عملکرد محصول نیست؛ تست و بازبینی لازم باقی می‌ماند.
10. API version در یک ثابت مرکزی ثبت شود و هنگام هر release با مستندات رسمی دوباره بررسی شود؛ نسخهٔ API در چند فایل تکرار نشود.

---

## 4. برنامهٔ نسخه‌به‌نسخه

## `v1.14.1` — Git Service Foundation

**هدف:** جداکردن زیرساخت Git موجود از GUI و ایجاد قراردادهای امن و آزمون‌پذیر، بدون تغییر محسوس در رفتار کاربر.

### تغییرات
- استخراج تدریجی `git_run`, `git_status_info`, `git_changed_paths`, بررسی Branch و عملیات Commit/Push از `AI_Workbench.py` به `aiwb/git/` یا محل ماژولار هم‌ارز.
- تعریف مدل‌های صریح برای Git status، changed path، remote identity، عملیات و خطاها.
- افزودن لایهٔ `GitCommandRunner` قابل تزریق برای تست؛ مسیر واقعی همچنان Git executable و `shell=False` باشد.
- تعریف قرارداد اولیه و migration version برای `RepositoryBinding` بدون فعال‌سازی هنوزِ API.
- ثبت ADRهای کوتاه: Git executable/credential helper، storage، schema config، layout و نسخه‌گذاری.
- حفظ handlerهای GUI به‌عنوان adapter سازگاری؛ حذف رفتار فعلی فقط با آزمون اثبات‌شده.

### معیار پذیرش
- تست‌های Git فعلی و GUI بدون تغییر رفتار قابل مشاهده پاس شوند.
- مسیرهای دارای فاصله و نویسه‌های فارسی، statusهای NUL-delimited و نام فایل‌های عجیب خراب نشوند.
- خطاها Token یا اطلاعات حساس را افشا نکنند.
- نصب‌کننده تمام فایل‌های ماژول جدید را نصب کند.
- هیچ HTTP یا Credential واقعی در این مرحله لازم نباشد.

### خارج از محدوده
حساب GitHub، PAT، Repository Browser و Build Center.

---

## `v1.14.2` — Secure GitHub Account & PAT

**هدف:** اتصال امن و قابل‌تشخیص یک یا چند حساب GitHub.

### تغییرات
- ساخت `credential_store` برای Windows Credential Manager؛ استفاده از شناسهٔ امن به‌جای Secret در تنظیمات.
- صفحهٔ `GitHub Accounts`: افزودن، Test Connection، Replace Credential، Refresh و Disconnect.
- دریافت حساب احرازشده و ثبت `github_user_id`، `login`، نوع روش اتصال و زمان آخرین اعتبارسنجی.
- redaction متمرکز برای Token در exception، HTTP debug و log.
- اتصال API بر مبنای interface؛ در تست‌ها transport mock استفاده شود.
- نمایش تفاوت «Token معتبر» با «Permission برای عملیات خاص بررسی شده».
- بررسی رفتار قطع/لغو Token و حذف Credential reference بدون دست‌زدن به Repository محلی.

### معیار پذیرش
- Token معتبر حساب درست را نشان دهد؛ Token نامعتبر یا منقضی خطای روشن و امن بدهد.
- 401، 403، 404، timeout، قطع شبکه و rate limit پیام‌های متمایز و قابل اقدام داشته باشند.
- با جست‌وجوی فایل‌های تنظیمات، Log و Remote URL هیچ Secret واقعی وجود نداشته باشد.
- Disconnect حساب، Git history و پوشهٔ پروژه را حذف نکند.
- تست Windows-native ذخیره/خواندن/حذف Credential در این release یا دروازهٔ انتشار مرتبط اجرا شود؛ mock تنها برای unit test کافی است.

---

## `v1.14.3` — Repository Browser & API Capability Checks

**هدف:** کشف Repositoryهای قابل‌دسترسی و انتخاب آن‌ها از داخل Workbench.

### تغییرات
- `github_api_client` با User-Agent، Accept/API-Version header، timeout، pagination، مدیریت خطا و rate limit.
- Repository Browser با جست‌وجوی owner/name و فیلترهای `All`, `Private`, `Public`, `Forks`, `Archived` در حد دادهٔ API.
- نمایش `owner/repo`، ID عددی پایدار، visibility، default branch، آخرین زمان به‌روزرسانی و Remote URLs تمیز.
- صفحه‌بندی کامل؛ فهرست نباید به اولین صفحه محدود باشد.
- ارزیابی کم‌خطر قابلیت‌ها و ذخیرهٔ snapshot همراه زمان بررسی؛ snapshot در زمان عملیات حساس دوباره بازبینی می‌شود.
- امکان Create Repository با visibility و توضیح؛ این عملیات تأیید مجزا دارد. حذف Repository در P0/P1 وجود ندارد.
- ذخیرهٔ cache غیرحساس همراه زمان آخرین Sync و دکمهٔ Refresh.

### معیار پذیرش
- بیش از یک صفحه نتیجه درست بارگذاری شود و خطای صفحهٔ بعد باعث گزارش صادقانه شود.
- Repository خصوصی که Token مجاز به دیدنش نیست، به‌عنوان یک Repository قابل دسترسی ساخته نشود.
- خطای 404 از نظر پیام به شکلی نمایش داده شود که اطلاعات Repository خصوصی افشا نشود.
- ایجاد Repository فقط پس از تأیید رخ دهد؛ Cancel هیچ تغییری نسازد.
- چند حساب با یک login یا Repositoryهای مشابه در UI مبهم نباشند.

---

## `v1.14.4` — Project Binding & Monorepo-aware Paths

**هدف:** پیوند مدل‌داده‌ای پروژهٔ Workbench به Repository، بدون فرض اینکه هر پروژه یک Repository جدا دارد.

### تغییرات
- تنظیمات `GitHub Repository`: account ID، repository ID، owner/name، local Git root، `project_subpath`، default/working branch، workflow binding، artifact pattern و release channel.
- تفکیک `local_git_root` از `project_subpath`; عملیات Git در root انجام می‌شود، تحلیل/build می‌تواند به subpath محدود باشد.
- Wizard برای Link کردن Repository موجود، Clone، یا Initialize محلی و Push اولیه.
- خواندن Remoteهای فعلی و مقایسه با Repository انتخاب‌شده؛ تعویض Remote هرگز خاموش انجام نشود.
- canonicalize مسیر و بررسی اینکه subpath واقعاً درون Git root است.
- پیش‌نمایش فایل‌های اولین Push، تکمیل `.gitignore` به‌صورت پیشنهاد بدون overwrite خاموش و تشخیص موارد حساس/حجیم.
- پشتیبانی چند پروژه از یک `repository_id` با subpathهای متفاوت.

### معیار پذیرش
- اتصال Repository صحیح را با ID عددی و Remote metadata پایدار ذخیره کند.
- تغییر نام owner/repo باعث گم‌شدن بی‌دلیل binding نشود؛ metadata به‌روزرسانی شود.
- فایل‌های تغییرکرده خارج از subpath در پنل نشان داده شوند و بدون انتخاب کاربر Commit نشوند.
- Remote متفاوت باعث توقف و نمایش گزینه‌های صریح شود.
- Migration داده‌های نسخهٔ قبلی idempotent باشد و در شکست، backup/گزارش فراهم کند.

---

## `v1.14.5` — Safe Git Review & Sync Plan

**هدف:** ارتقای تب Git موجود به گردش کار انتخابی و قابل پیش‌بینی.

### تغییرات
- نمایش تفکیک‌شدهٔ staged، unstaged، untracked، deleted و rename، به همراه Diff فایل.
- انتخاب فایل‌به‌فایل برای Stage/Commit؛ کاربر بتواند فایل‌های آماده را جدا از تغییرات محلی دیگر Commit کند.
- شناسایی staged changes موجود که Workbench ایجاد نکرده است؛ هرگز ناخواسته همراه عملیات جدید Commit نشوند.
- `Fetch` و تولید Sync Plan: clean/local ahead/remote ahead/diverged/untracked/modified/conflict.
- در حالت فقط Remote جلوتر و working tree پاک: Fast-forward-only مجاز؛ در حالت diverged توقف و مسیرهای دستی پیشنهاد شود.
- پیش از Push وضعیت Remote دوباره بررسی شود؛ remote SHA که از snapshot اولیه عوض شده باعث ساخت Plan مجدد شود.
- اتصال `task_id`, `run_id`, `apply_id` به metadata محلی و پیام Commit پیشنهادی قابل ویرایش؛ Prompt کامل در Commit ذخیره نشود.
- حفظ ممنوعیت Push مستقیم `main`/`master` در مسیر پیش‌فرض؛ هیچ Force Push خودکار وجود نداشته باشد.

### معیار پذیرش
- فایل untracked، حذف‌شده، staged از قبل و تغییر خارج از Scope هر کدام درست نشان داده شوند.
- آزمون‌های non-fast-forward، divergence، remote update هم‌زمان و working tree کثیف، بدون overwrite خاموش متوقف شوند.
- لغو پیش از Commit/Push اثری فراتر از Fetch/status نداشته باشد.
- پیام خطا مشخص کند Commit محلی ساخته شده ولی Push شکست خورده است یا خود Commit شکست خورده است.
- Secret scan به‌عنوان کنترل کمکی گزارش شود، نه تضمین نبود Secret.

---

## `v1.14.6` — Build Center: Workflow & Run Monitoring

**هدف:** مشاهده و پیگیری GitHub Actions بدون هنوز ترکیب‌کردن آن با Push.

### تغییرات
- کشف فایل‌های `.github/workflows/*.yml` و `*.yaml` از Remote/repository contents؛ نمایش نام، فایل، triggerهای قابل‌تشخیص و `workflow_dispatch`.
- انتخاب Workflow اصلی Build در binding پروژه؛ تغییرنام یا حذف فایل باعث stale binding واضح شود.
- Build Center: آخرین Runs، status/conclusion، branch/ref، commit SHA، run ID، زمان‌ها و لینک مستقیم GitHub.
- نمایش Jobs/Steps ناموفق و لینک Log در GitHub. دانلود خام Log به‌عنوان قابلیت جداگانه می‌تواند به بعد موکول شود.
- polling غیرمسدودکننده با cache فوری، backoff و رعایت rate-limit headers.
- Cancel Run فقط وقتی API و Permission اجازه دهند؛ عملیات با تأیید مناسب.
- جلوگیری از اجرای دو Sync/Build متعارض برای همان Repository/ref.

### معیار پذیرش
- چند Run با branchها و SHAهای مختلف به‌صورت درست تفکیک شوند.
- Run قدیمی به‌عنوان نتیجهٔ Push جدید نمایش داده نشود.
- workflow بدون `workflow_dispatch` به‌عنوان Run دستی فعال نشان داده نشود.
- 401/403/rate limit/timeout و `cancelled`, `skipped`, `failure`, `success` از هم تفکیک شوند.
- UI حین refresh/polling فعال بماند.

---

## `v1.14.7` — Workflow Dispatch & Safe Artifact Download

**هدف:** اجرای Workflowهای دستی و دریافت امن Artifactهای مشخص.

### تغییرات
- فرم `workflow_dispatch` از inputs تعریف‌شده در Workflow و با validation نوع/مقدار ساخته شود؛ dispatch برای ref مشخص و قابل مشاهده باشد.
- استفاده از run ID/URL بازگشتی در صورت پشتیبانی API؛ در غیر این صورت، جست‌وجوی Run مرتبط فقط با تطبیق سخت‌گیرانه انجام شود.
- فهرست Artifact با ID، نام، اندازه، `expires_at`, `expired`, digest و Run/Commit مربوطه.
- دانلود از endpoint رسمی و مدیریت redirect URL موقت؛ URL دانلود موقت در Log ذخیره نشود.
- دریافت ZIP به فایل موقت، محدودیت اندازه و زمان، اعتبارسنجی ZIP و استخراج امن فقط پس از تأیید.
- محاسبهٔ SHA-256 و مقایسه با digest/manifest قابل اعتماد در صورت وجود؛ «Hash محاسبه شد» را با «Hash مرجع تطبیق داشت» اشتباه نگیریم.
- انتخاب محل ذخیره و پاک‌سازی فایل ناقص پس از شکست.

### معیار پذیرش
- dispatch موفق به Run ID مشخص وصل شود؛ API 204/نبود ID به‌عنوان موفقیت بدون Run قطعی گزارش نشود.
- Artifact متعلق به Run یا SHA متفاوت قابل تحویل به‌عنوان خروجی آن Task نباشد.
- ZIPهای دارای traversal، duplicate/case-collision، فایل ویژه یا اندازهٔ بازشدهٔ بیش‌ازحد رد شوند.
- Artifact منقضی‌شده قابل دانلود اعلام نشود؛ خطای 410 درست تفسیر شود.
- redirect/download token یا URL موقت به log یا clipboard ناخواسته نرود.

---

## `v1.14.8` — One-click Sync & Build Orchestrator

**هدف:** اتصال تمام مراحل قبلی به یک گردش کار قابل مشاهده و قابل توقف.

### وضعیت‌ها

`Checking` → `Review Required` → `Ready to Commit` → `Committed` → `Pushing` → `CI Queued` → `CI Running` → `Build Passed/Failed` → `Artifact Verified/Downloaded`.

### تغییرات
- Preflight حساب، binding، Git root، branch، working tree و Remote.
- Change Review کامل به‌همراه بررسی فایل‌های حساس، خارج از scope و تغییر Workflow.
- Commit title پیشنهادی از Task، قابل ویرایش و شامل شناسه‌های مرجع غیرمحرمانه.
- Fetch/reconcile مجدد پیش از Commit/Push؛ Plan قدیمی در صورت تغییر Remote منسوخ شود.
- Commit فقط مسیرهای تأییدشده، Push به Branch تعریف‌شده، دنبال‌کردن Run دقیق، دانلود Artifact و Verify.
- ثبت یک `GitOperationRecord` و `BuildRunRecord` با مسیر شواهد: Task → Apply → Commit SHA → Run ID → Artifact ID → Hash.
- Cancel در هر مرحله معنای واقعی داشته باشد: پیش از Commit توقف؛ بعد از Push لغو Workflow فقط با endpoint رسمی؛ هرگز حذف Commit/Undo خودکار.
- idempotency/operation lock برای جلوگیری از دوبارکلیک، تکرار commit یا dispatch ناخواسته.

### معیار پذیرش
- در شکست هر مرحله، آخرین مرحلهٔ موفق، اثر واقعی روی Git و اقدام بعدی درست نمایش داده شود.
- Push ناموفق پس از Commit، Commit محلی را حذف نکند.
- دوبارکلیک یا retry پس از قطع شبکه باعث Commit/Dispatch تکراری بی‌دلیل نشود.
- دو Run نزدیک به هم، Artifactها را با `repository_id + workflow_id + run_id + head_sha` درست به هم متصل کنند.
- همهٔ عملیات قابل پیگیری از تاریخچه باشند، بدون ثبت Credential یا Prompt محرمانه.

---

## `v1.14.9` — Self-hosting Repository & Desktop CI Baseline

**هدف:** آماده‌سازی Repository رسمی خود AI Workbench و اثبات CI دسکتاپ قبل از انتقال بزرگ فایل‌ها.

### تغییرات
- انتخاب و ثبت سیاست Monorepo، branch strategy و نام Tagها در ADR.
- ساخت Repository محصول یا تنظیم Repository موجود در محیط واقعی، پس از تأیید مالک.
- Workflow دسکتاپ که syntax compile، unit/regression tests، GUI smokeهای قابل اجرا، packaging integrity و SHA manifest را روی runner پاک اجرا کند.
- PR check جمع‌بندی‌شده که در همهٔ PRهای مربوط همیشه وضعیت نهایی بدهد.
- pin کردن GitHub Actions به نسخهٔ قابل اعتماد؛ ترجیح pin به commit SHA کامل/روش رسمی lock مطابق سیاست جاری.
- حداقل permissionهای `GITHUB_TOKEN` در هر workflow/job و جداسازی CI معمولی از Release.
- ساختن artifact تستی installer در CI؛ در این مرحله امضای Release یا انتشار خودکار عمومی فعال نشود.

### معیار پذیرش
- PR از runner پاک Build و تست را اجرا کند؛ به محیط محلی توسعه وابسته نباشد.
- چنانچه تغییر docs به‌تنهایی Build را skip کند، check لازم PR در وضعیت Pending دائمی نماند.
- Secretهای Release در PR عادی در دسترس نباشند.
- Artifact CI قابل اتصال به Commit SHA باشد.

---

## `v1.14.10` — Staged Monorepo Migration

**هدف:** انتقال تدریجی سورس Desktop به Monorepo بدون شکستن Installer، import pathها یا سابقهٔ تست.

### تغییرات
- ایجاد `apps/desktop/` و انتقال کنترل‌شدهٔ سورس و تست‌های Desktop.
- تعریف ابزارهای build/package در `tools/` در صورت نیاز و سازگاری با مسیرهای موجود.
- ساخت `packages/contracts/` با JSON Schema/fixtures اولیه برای موجودیت‌های مشترک، ابتدا فقط قراردادهای واقعاً مشترک.
- به‌روزرسانی workflow و installer builder تا مسیرهای جدید را مصرف کنند؛ ترجیح استفاده از یک source of truth برای version و file manifest.
- حفظ adapter موقت برای مسیرهای قدیمی فقط در صورت نیاز و با تست حذف آینده.
- migration در PRهای جدا/تغییرات کوچک؛ حفظ history تا جایی که ابزار Git به‌طور طبیعی امکان دهد.

### معیار پذیرش
- نصب‌کنندهٔ ساخته‌شده از مسیر جدید از نظر payload، imports و startup تست شود.
- همهٔ تست‌های رگرسیون قبل/بعد قابل مقایسه باشند.
- هیچ کد محصولی صرفاً برای رعایت شکل دایرکتوری دوباره‌نویسی نشود.
- build محلی و CI از یک مسیر رسمی و مستند استفاده کنند.

---

## `v1.14.11` — Android Proof-of-Build & Capability Contracts

**هدف:** اثبات اینکه Monorepo می‌تواند Desktop و Mobile را مستقل Build کند و قراردادهای مشترک را validate کند.

### تغییرات
- اپ آزمایشی حداقلی Android در `apps/mobile/`؛ فقط برای اثبات چرخهٔ ساخت و نسخه‌گذاری، نه ادعای Companion کامل.
- `mobile-ci.yml` برای test/analyze/build و آپلود APK آزمایشی به Actions Artifact.
- `contracts-ci.yml` یا job مشترک برای اعتبارسنجی JSON Schema و fixtureها.
- `capabilities.yml` با وضعیت `planned`, `in_progress`, `implemented`, `partial`, `not_applicable`, `blocked` برای Desktop/Mobile/Companion.
- اجرای تست هر دو پلتفرم وقتی قرارداد مشترک تغییر می‌کند.
- metadata Build: platform، app version، build number، commit SHA، branch/tag و channel.

### معیار پذیرش
- APK از runner پاک ساخته شود و به همان Commit SHA متصل باشد.
- تغییر contract حداقل validation مشترک و تست مصرف‌کنندگان مرتبط را فعال کند.
- Capability Registry در نسخهٔ اول فقط وضعیت/هشدار ارائه کند و بدون طراحی، feature gating خاموش/روشن نکند.
- شکست Mobile CI به‌صورت جدا از Desktop CI دیده شود.

---

## `v1.14.12` — Versioned Releases & Protected Signing

**هدف:** تفکیک Artifact موقت Actions از نسخهٔ رسمی قابل دانلود.

### تغییرات
- Tagهای مستقل، مانند `desktop-v1.15.0` و `mobile-v0.1.0`، پس از تصویب الگوی نهایی.
- `release-desktop.yml` و `release-mobile.yml` با ورودی Tag/Commit دقیق.
- Release Notes، assetها، SHA-256 و release manifest تولیدشده در Workflow.
- Android `versionName` و `versionCode` از source of truth تعریف‌شده؛ جلوگیری از نسخه‌های متناقض.
- جداسازی debug build از release build.
- کلید امضای Android خارج از Git و فقط در Environment/Job محافظت‌شده؛ PR معمولی حق دسترسی به Secretهای Release را نداشته باشد.
- انتشار نسخهٔ پایدار فقط پس از approval موردنیاز و CI سبز.

### معیار پذیرش
- هر release با Tag و Commit SHA مشخص بازتولید و ردیابی شود.
- Manifest با asset واقعی از نظر نام، version، SHA-256 و channel سازگار باشد.
- workflow غیرقابل‌اعتماد نتواند Secret امضا را بخواند.
- artifact موقت Actions به‌عنوان جایگزین دائمی Release معرفی نشود.

---

## `v1.14.13` — Release Candidate & Native Windows Validation

**هدف:** بستن ریسک‌های یکپارچگی و آماده‌کردن نامزد انتشار `1.15.0`.

### تغییرات
- اجرای تست کامل GitHub integration روی Repository آزمایشی کنترل‌شده، نه Repository اصلی در ابتدا.
- تست Windows-native برای نصب، ارتقا، launch، pathهای Unicode/space، Git Credential Manager، API credential store، خطاهای شبکه، محدودیت rate، clone/link، commit/push و download.
- تست بازیابی config و migration از نسخهٔ قبلی.
- بررسی عدم افشای Token در log، URL، process args، error و crash report.
- تست هم‌زمانی عملیات، لغو، retry، stale state و idempotency.
- بررسی Permission matrix بر اساس رفتار API واقعی؛ عدم اتکا به snapshot قدیمی برای عملیات مخرب.
- نهایی‌کردن documentation فارسی/انگلیسی، CHANGELOG، Architecture، release checklist، hashes و rollback plan.

### معیار پذیرش
- تمام تست‌های بحرانی امنیت/فایل/ترکیب Git و Build پاس شوند.
- موارد «NOT RUN» در چک‌لیست انتشار صریح باقی بمانند؛ به جای PASS نشان داده نشوند.
- برای هر شکست شناخته‌شده، تصمیم release owner و اثر آن مستند باشد.
- نصب ارتقایی روی محیط واقعی، تنظیمات و دادهٔ پروژهٔ موجود را حفظ کند.

---

## `v1.15.0` — Integrated GitHub & Monorepo Stable

این نسخه زمانی منتشر می‌شود که تمام دروازه‌های لازم نسخه‌های قبل پاس شده باشند. شمارهٔ `1.15.0` را زودتر از تکمیل زنجیرهٔ واقعی Sync → Actions → Artifact → Verification استفاده نمی‌کنیم.

### تعریف Done

- GitHub Accounts و Credential امن.
- Repository Browser و binding برای Repository کامل یا subpath Monorepo.
- Git Review، Commit انتخابی، Sync Plan و Push کنترل‌شده.
- Build Center با Run/Job/Artifactهای دقیق.
- Sync & Build end-to-end و Hash verification.
- Monorepo محصول، Desktop CI، Android proof build و contract/capability checks.
- Release workflow جداگانه برای Desktop/Mobile و سیاست Secret/Signing قابل بررسی.
- Regression tests، نصب واقعی Windows، مستندات انتشار و SHA-256 manifest.

### مواردی که از `1.15.0` خارج می‌مانند

- ورود کامل GitHub App/OAuth تا زمانی که قرارداد provider، callback/deep-link و چرخهٔ refresh token طراحی و تست نشده باشد.
- iOS build/signing/TestFlight.
- Mobile Companion برای کنترل Workbench محلی.
- Auto Commit & Push بدون بررسی کاربر؛ حتی پس از 1.15.0 فقط سیاست صریح، محدود و قابل لغو می‌تواند این قابلیت را فعال کند.
- Force Push/Hard Reset در Sync عادی.
- Release موبایل خودکار و بدون approval از PRهای ناشناخته.

---

## 5. وابستگی‌های نسخه‌ها

```text
1.14.1 Git service foundation
    ↓
1.14.2 secure account + PAT
    ↓
1.14.3 API client + repository browser
    ↓
1.14.4 project binding / monorepo subpath
    ↓
1.14.5 safe Git review + sync plan
    ↓
1.14.6 Actions Build Center
    ↓
1.14.7 workflow dispatch + artifact download
    ↓
1.14.8 one-click Sync & Build
    ↓
1.14.9 self-hosting repo + Desktop CI
    ↓
1.14.10 staged Monorepo migration
    ↓
1.14.11 Android proof build + contracts/capabilities
    ↓
1.14.12 versioned releases + protected signing
    ↓
1.14.13 release candidate + native Windows QA
    ↓
1.15.0 stable
```

اگر به دلایل اجرایی لازم شد دو شماره به یک تحویل منطقی تبدیل شوند، فقط در صورت کوچک و مستقل ماندن سطح تغییرات ادغام می‌شوند. نسخه‌های Credential، Git Sync، Artifact extraction و Release signing را به‌دلیل ریسک متفاوت در یک انتشار بزرگ ادغام نکنیم.

---

## 6. تست‌های مشترک برای همهٔ نسخه‌ها

هر release علاوه بر تست اختصاصی خود باید این مجموعه را اجرا کند:

1. Python compile و همهٔ unit/regression tests.
2. GUI smoke برای پروژهٔ جدید، پروژهٔ قدیمی، Cancel، خطای شبکه و بسته‌شدن پنجره در حین worker.
3. Installer packaging integrity؛ ماژول تازه اضافه‌شده باید در payload وجود داشته باشد.
4. Schema/config migration و عدم از دست‌رفتن دادهٔ نسخهٔ قبلی.
5. Secret redaction در Log، exception، URL و process arguments.
6. تست منفی path traversal، duplicate path، ZIP محدودیت‌خورده و فایل خارج از root.
7. Git status tests برای staged/unstaged/untracked/deleted/rename، Remote تغییرکرده، divergence و non-fast-forward.
8. API tests برای pagination، 401/403/404/409/422، timeout، retry و rate limit.
9. Actions tests برای چند Run مشابه، run ID متفاوت، SHA متفاوت، Run لغوشده/منقضی و Artifact منقضی.
10. Native Windows checklist؛ شبیه‌سازی Linux/Xvfb یا mock API جایگزین آن نیست.

برای Unit/Integration از transport mock و repository fixture استفاده شود؛ تست End-to-End با GitHub واقعی در یک Repository آزمایشی جدا، با Token محدود و دادهٔ غیرمحرمانه اجرا شود. تست واقعی نباید ناخواسته Repository شخصی یا Branch اصلی را تغییر دهد.

---

## 7. ریسک‌های اصلی و کنترل آن‌ها

| ریسک | کنترل طراحی | نسخهٔ آغازین کنترل |
|---|---|---|
| Token در log/URL/config | Credential reference، redaction و تست منفی | 1.14.2 |
| Token معتبر ولی Permission ناکافی | Capability snapshot + خطای endpoint-specific | 1.14.2–1.14.3 |
| تغییر فایل خارج از زیرپوشهٔ پروژه | Git root و project subpath جدا؛ نمایش scope خارج از پروژه | 1.14.4–1.14.5 |
| Push روی Remote تغییرکرده | Fetch و Sync Plan تازه؛ منع Force Push | 1.14.5 |
| Artifact از Commit اشتباه | اتصال repository/workflow/run/head SHA | 1.14.6–1.14.8 |
| ZIP مخرب یا بیش‌ازحد بزرگ | دانلود موقت، حدود اندازه و استخراج امن | 1.14.7 |
| دوبارکلیک و اجرای تکراری | operation lock، idempotency و حالت وضعیت | 1.14.8 |
| شکستن installer با جابه‌جایی فایل | CI از قبل، migration مرحله‌ای و payload tests | 1.14.9–1.14.10 |
| Secret امضا در PR | job/environment محافظت‌شده و حداقل permissions | 1.14.12 |
| ادعای تأیید Windows بدون تست | checklist شواهددار و release gate | 1.14.13 |

---

## 8. تصمیم‌های معماری که باید از ابتدا تثبیت شوند

1. **REST API credential و Git transport credential یکی فرض نشوند.** Workbench برای API به Credential امن نیاز دارد؛ Git HTTPS بهتر است از Git Credential Manager موجود استفاده کند. رفتار ناسازگاری Credentialها در UI گزارش شود.
2. **`repository_id` مرجع پایدار است.** `owner/name` دادهٔ نمایش و مسیریابی است؛ در rename باید از API refresh شود.
3. **Task/Run/Commit/Artifact موجودیت‌های مستقل‌اند.** رابطه‌ها صریح ثبت شوند؛ هیچ «آخرین APK» بدون کنترل Run و SHA پذیرفته نیست.
4. **Artifact Actions و Release asset متفاوت‌اند.** Artifact برای CI و دارای expiration است؛ نسخهٔ پایدار باید Release asset داشته باشد.
5. **Monorepo محصول با پروژه‌های کاربر متفاوت است.** انتقال سورس Workbench به Monorepo، پروژه‌های شخصی کاربر را مجبور به اشتراک Repository نمی‌کند.
6. **Capability Registry منبع حقیقت وضعیت مستندشده است، نه سیستم جادویی فعال‌سازی Feature.** تا زمانی که gating واقعی طراحی و تست نشده، نباید صرف نوشتن `implemented` مسیر اجرایی را روشن کند.
7. **سیاست‌های per-project واقعاً جدا باشند.** حساب پیش‌فرض یا سیاست Push یک پروژه نباید بدون تأیید روی پروژهٔ دیگر اعمال شود.
8. **ماژولارکردن را به استخراج مرزهای پایدار محدود کنیم.** از افزودن کلاس/لایهٔ بی‌مصرف یا بازنویسی کل `AI_Workbench.py` پیش از داشتن تست یکپارچه پرهیز شود.

---

## 9. منابع رسمی برای بررسی مجدد هنگام پیاده‌سازی

مستندات GitHub تغییر می‌کنند. هنگام شروع هر نسخه، endpoint، API version، permission و رفتار واقعی را از مستندات روز بررسی و نتیجه را در ADR همان نسخه ثبت کنید.

- Personal access tokens و توصیه‌های امنیتی: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- GitHub Apps در برابر OAuth Apps: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps
- GitHub REST API — workflow runs و فیلتر `head_sha`: https://docs.github.com/en/rest/actions/workflow-runs
- GitHub REST API — dispatch دستی Workflow: https://docs.github.com/en/rest/actions/workflows
- GitHub REST API — Artifacts، digest، expiration و دانلود redirect: https://docs.github.com/en/rest/actions/artifacts
- GitHub REST API — Rate limit headers: https://docs.github.com/en/rest/rate-limit/rate-limit
- GitHub Actions — Secure use: https://docs.github.com/en/actions/reference/security/secure-use
- GitHub Actions — Workflow syntax و مسیرهای PR: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- Git Credential Manager — credential stores: https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/credstores.md
- Android — App signing: https://developer.android.com/studio/publish/app-signing
- Android — App versioning: https://developer.android.com/studio/publish/versioning

### نکته‌های تأییدشده در بررسی مستندات آنلاین

- GitHub REST API برای workflow runs فیلتر `head_sha` دارد؛ از آن برای محدودکردن نتایج استفاده شود، نه اتکا به «آخرین Run» به‌تنهایی.
- Workflow dispatch در API فعلی می‌تواند در صورت درخواست جزئیات، run ID و URL را برگرداند؛ پیاده‌سازی باید این رفتار را با API version انتخابی تأیید کند و پاسخ بدون ID را اشتباه به Run مشخص نسبت ندهد.
- API Artifact اطلاعاتی مانند `expired`, `expires_at`, `digest` و اطلاعات Run را ارائه می‌کند؛ دانلود از endpoint Artifact می‌تواند redirect موقت بدهد و خطای Gone برای Artifact منقضی‌شده باید درست تفسیر شود.
- مستندات GitHub هشدار می‌دهد Workflowهایی که به دلیل path filtering اجرا نمی‌شوند ممکن است Check مورد انتظار را Pending نگه دارند؛ بنابراین Check جمع‌بندی‌شدهٔ PR باید وضعیت نهایی قابل اتکا بدهد.
- Git Credential Manager در Windows از Windows Credential Manager پشتیبانی می‌کند؛ از این موضوع برای استفاده از credential helper موجود بهره ببریم، نه برای قرار دادن PAT در Remote URL.

---

## 10. گام بعدی پس از تصویب نقشه‌راه

نسخهٔ بعدی که باید واقعاً تغییر کند **`1.14.1`** است. دامنهٔ آن عمداً کوچک است: انتقال منطق Git فعلی به یک سرویس مستقل، تعریف قراردادهای داخلی و تست‌پذیرکردن آن، ثبت ADRهای ضروری و اطمینان از نصب‌شدن ماژول‌های جدید. هنوز PAT، API یا Repository Browser اضافه نمی‌شود. پس از پاس‌شدن این مرحله، `1.14.2` روی Credential و حساب GitHub ساخته می‌شود.
