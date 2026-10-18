# AI Workbench — نقشه‌راه اصلی (Master Roadmap)

> **این فایل تنها مرجع اجرایی ترتیب توسعه است.** هر کار توسعه باید به یکی از گام‌های همین فایل اشاره کند.
> اسناد `docs/specs/` منبع جزئیات و معیارهای پذیرش هستند؛ این فایل ترتیب، وضعیت و دروازه‌ها را تعیین می‌کند.
> اگر بین این فایل و یک سند مرجع تعارض دیده شد، طبق همین فایل عمل کن و تعارض را با یک ADR در `docs/adr/` حل کن.

**آخرین به‌روزرسانی:** 2026-10-18 · **نسخهٔ Desktop منتشرشده:** `desktop-v1.16.3` · **نسخهٔ Mobile منتشرشده:** `mobile-v0.2.0`
**گام فعال بعدی:** `v1.17.0` — مدل داده و Migration فاز دوم

راهنمای وضعیت: ✅ کامل (دروازه پاس شده) · 🟡 بخشی · ⬜ شروع‌نشده · ⏭ خارج از دامنهٔ فعلی

---

## ۰. قواعد استفاده از این نقشه‌راه

1. **یک گام در هر زمان.** گام بعدی فقط وقتی شروع می‌شود که همهٔ معیارهای پذیرش گام فعلی پاس شده و CI سبز باشد. شمارهٔ نسخه به‌تنهایی به معنی تکمیل نیست.
2. **وضعیت در همان PR به‌روز می‌شود.** هر PR که گامی را جلو می‌برد، جدول وضعیت و چک‌لیست همان گام را در این فایل به‌روز می‌کند. ✅ فقط با لینک به شواهد (تست، Run، Release).
3. **قابلیت موجود دوباره ساخته نمی‌شود.** قبل از شروع، کد واقعی بررسی می‌شود و فقط بخش ناقص تکمیل می‌شود.
4. **«NOT RUN» صریح می‌ماند.** آنچه در CI یا روی ویندوز واقعی اجرا نشده، PASS اعلام نمی‌شود.
5. **ادغام گام‌ها** فقط برای تغییرات کوچک و هم‌ریسک مجاز است. Credential، Git Sync، استخراج Artifact و امضای Release هرگز در یک انتشار ادغام نمی‌شوند.
6. **بازنویسی کامل ممنوع.** ماژولارکردن فقط با استخراج مرزهای پایدار و پوشش تست انجام می‌شود.

## ۱. اصول تغییرناپذیر محصول

(خلاصه از `AI_Workbench_Future_Roadmap_v1.14_FA.md` بخش ۰ و Handoff بخش ۰)

- کاربر پرامپت را در Workbench می‌سازد، در **چت معمولی** مدل (رایگان/پولی) کپی می‌کند و پاسخ را برمی‌گرداند. **اتصال به API مدل، API Key مدل یا ورود به حساب مدل جزو هدف نیست.**
- «Agent» یک نقش/پروفایل با قرارداد ورودی و خروجی است، نه فرایند خودمختار.
- هیچ خروجی مدلی بدون Preview و تأیید کاربر فایل نمی‌نویسد یا فرمان اجرا نمی‌کند.
- Workbench مرجع وضعیت محلی است؛ GitHub حافظهٔ خواندنی و مشترک برای مدل‌هاست، نه مرجع نهایی.
- ادعای مدل از شاهد واقعی (تست، Hash، Run) جداست. هیچ Task فقط با ادعای مدل Done نمی‌شود.
- Force Push، Hard Reset و Auto Commit بدون بازبینی در جریان عادی وجود ندارد.

## ۲. نمای کلی مسیر

```text
بخش A  زنجیرهٔ GitHub و Monorepo     1.14.1 … 1.14.13  →  1.15.0 (Stable)
بخش B  فاز اول: هوشمندسازی ورودی      1.16.x  (Response Inbox، خطای قابل‌فهم، Context Request)
بخش C  فاز دوم: V2 چند Agent         1.17.x … 1.20.x  →  2.0.0  (مهم‌ترین هدف محصول)
بخش D  فاز سوم: UI ساده/پیشرفته       2.1.x
مسیر موازی  Mobile                   0.1.0 (proof) → 0.2.x (قراردادها) → Companion (پس از 2.0)
```

شماره‌های 1.16 به بعد پیشنهادی‌اند و فقط با ADR تغییر می‌کنند. ترتیب بخش‌ها از «ترتیب کار پیشنهادی» Future Roadmap و Handoff گرفته شده: ابتدا زنجیرهٔ GitHub در حال اجرا بسته می‌شود، سپس فاز اول (پیش‌نیاز داده‌ای V2)، سپس V2، سپس UI.

---

## بخش A — زنجیرهٔ GitHub و Monorepo (1.14.x → 1.15.0)

مرجع جزئیات: `docs/specs/AI_Workbench_GitHub_Monorepo_Roadmap_v1.14_to_v1.15.md` (بخش ۴) و `AI_Workbench_GitHub_Monorepo_Integration_Spec_v1.13_FA.md`.

### جدول وضعیت

| نسخه | عنوان | وضعیت | شواهد / باقی‌مانده |
|---|---|---|---|
| 1.14.1 | Git Service Foundation | ✅ | `apps/desktop/src/aiwb/git/service.py`, `tests/test_git_service.py` |
| 1.14.2 | Secure GitHub Account & PAT | ✅ | `aiwb/github/accounts.py`, `credential_store.py`؛ تست بومی Credential Manager در CI ویندوز |
| 1.14.3 | Repository Browser & API Capability Checks | ✅ | `aiwb/github/api_client.py`, `tests/test_github_repository_browser.py` |
| 1.14.4 | Project Binding & Monorepo-aware Paths | ✅ | `repository_binding.py`, ADR-004 |
| 1.14.5 | Safe Git Review & Sync Plan | ✅ | `aiwb/git/sync.py`, `review_dialog.py`, ۱۷ تست روی Repo واقعی؛ Release `desktop-v1.14.5` |
| 1.14.6 | Build Center: Workflow & Run Monitoring | ✅ | `aiwb/github/actions.py`, `build_center.py`, `tests/test_github_actions.py`, `tests/gui/gui_build_center_smoke.py`؛ Release `desktop-v1.14.6` |
| 1.14.7 | Workflow Dispatch & Safe Artifact Download | ✅ | `aiwb/github/artifacts.py`, `build_center_dialogs.py`, `tests/test_github_artifacts.py` (23), `gui_dispatch_artifacts_smoke.py`; dispatch و دانلود واقعی روی همین ریپو؛ Release `desktop-v1.14.7` |
| 1.14.8 | One-click Sync & Build Orchestrator | ✅ | `aiwb/github/orchestrator.py`, `sync_build_window.py`, `tests/test_orchestrator.py` (10, Git واقعی + remote محلی), `gui_sync_build_smoke.py`؛ Release `desktop-v1.14.8` |
| 1.14.9 | Self-hosting Repository & Desktop CI Baseline | ✅ | ریپو، CI روی Linux+Windows، Actionsهای pin‌شده، `CI summary`، گیت pyflakes؛ ADR-005 (سیاست Monorepo/branch/tag)؛ Release `desktop-v1.14.9` |
| 1.14.10 | Staged Monorepo Migration | ✅ | `apps/desktop/{src,tests,installer}`، manifest v2، نصاب بایت‌به‌بایت (PR #1)؛ `packages/contracts/` |
| 1.14.11 | Android Proof-of-Build & Capability Contracts | ✅ | JSON Schema `release-manifest.v1`/`build-metadata.v1`/`capabilities.v1` + fixtures؛ `capabilities.yml`؛ `tools/validate_contracts.py` (job `contracts`)؛ مصرف در Kotlin (`ReleaseManifest.kt` + تست روی fixtureهای مشترک) |
| 1.14.12 | Versioned Releases & Protected Signing | ✅ | تگ‌های جدا، SHA-256 و manifest قراردادی در هر دو release؛ Secretهای امضا فقط در Environment `release` با **Required reviewer**؛ `mobile-v0.2.0` |
| 1.14.13 | Release Candidate & Native Windows Validation | ✅ | E2E واقعی روی `aiwb-e2e-sandbox` (`tools/e2e_github_sandbox.py`)، تست ارتقا + مسیر Unicode در CI ویندوز، `test_rc_hardening.py` (13)، بازیابی `settings.json`، rollback plan و تصمیم‌های release owner؛ Release `desktop-v1.14.13` |
| 1.15.0 | Integrated GitHub & Monorepo Stable | ✅ | `docs/release/v1.15.0/DEFINITION_OF_DONE_v1.15.0.md`؛ Release `desktop-v1.15.0` |

> زیرساخت ریپو (1.14.9 تا 1.14.12) برای نگهداری و انتشار امن زودتر ساخته شد. این **ترتیب قابلیت‌های داخل اپ را تغییر نمی‌دهد**: گام فعال همچنان طبق جدول بالاست و موارد ⬜ این ردیف‌ها در نوبت خودشان بسته می‌شوند.

### v1.14.6 — Build Center: Workflow & Run Monitoring

**هدف:** مشاهده و پیگیری GitHub Actions از داخل اپ، هنوز بدون ترکیب با Push.

- [x] کشف `.github/workflows/*.yml|*.yaml` از Repository contents؛ نمایش نام، فایل، triggerها و وجود `workflow_dispatch`
- [x] انتخاب Workflow اصلی Build در binding پروژه؛ تغییرنام/حذف فایل → stale binding واضح
- [x] Build Center: آخرین Runها با status/conclusion، branch/ref، commit SHA، run ID، زمان‌ها و لینک GitHub
- [x] نمایش Jobs/Steps ناموفق و لینک Log
- [x] polling غیرمسدودکننده با cache، backoff و رعایت rate-limit headers
- [x] Cancel Run فقط با Permission و تأیید
- [x] جلوگیری از دو Sync/Build متعارض روی همان Repository/ref

**دروازه (پاس شد — تست‌های واحد + GUI smoke + بررسی روی API واقعی):** چند Run با branch/SHA متفاوت درست تفکیک شوند · Run قدیمی نتیجهٔ Push جدید نشان داده نشود · Workflow بدون `workflow_dispatch` قابل اجرای دستی نشان داده نشود · 401/403/rate-limit/timeout و `cancelled/skipped/failure/success` تفکیک شوند · UI حین polling فعال بماند.

### v1.14.7 — Workflow Dispatch & Safe Artifact Download

- [x] فرم `workflow_dispatch` از inputs واقعی Workflow با validation؛ ref مشخص
- [x] اتصال dispatch به Run ID فقط با تطبیق سخت‌گیرانه؛ 204 بدون Run قطعی ≠ موفقیت
- [x] فهرست Artifact: ID، نام، اندازه، `expires_at`، digest، Run/Commit
- [x] دانلود از endpoint رسمی؛ URL موقت در Log/clipboard نرود
- [x] دانلود به فایل موقت با سقف حجم/زمان؛ استخراج امن (traversal، case-collision، فایل ویژه، zip-bomb)
- [x] SHA-256؛ تفکیک «Hash محاسبه شد» از «با مرجع تطبیق داشت»
- [x] پاک‌سازی فایل ناقص؛ تفسیر درست 410 (منقضی)

### v1.14.8 — One-click Sync & Build Orchestrator

وضعیت‌ها: `Checking → Review Required → Ready to Commit → Committed → Pushing → CI Queued → CI Running → Build Passed/Failed → Artifact Verified/Downloaded`

- [x] Preflight حساب، binding، Git root، branch، working tree و Remote
- [x] Review کامل + هشدار فایل حساس، خارج از scope و تغییر Workflow
- [x] Fetch/reconcile مجدد پیش از Commit/Push؛ Plan قدیمی منسوخ شود
- [x] `GitOperationRecord` و `BuildRunRecord` با زنجیرهٔ Task → Apply → Commit SHA → Run ID → Artifact ID → Hash
- [x] Cancel واقعی در هر مرحله؛ هرگز حذف Commit یا Undo خودکار
- [x] operation lock و idempotency (دوبارکلیک/retry)

### v1.14.9 تا v1.14.12 — باقی‌ماندهٔ زیرساخت

- [x] **1.14.9:** ADR سیاست Monorepo، branch strategy و نام تگ‌ها
- [x] **1.14.10/11:** `packages/contracts/` با JSON Schema و fixture فقط برای موجودیت‌های واقعاً مشترک (Build metadata، Release manifest، Capability)
- [x] **1.14.11:** `capabilities.yml` (`planned/in_progress/implemented/partial/not_applicable/blocked`)؛ فقط گزارش، بدون feature gating
- [x] **1.14.11:** تغییر قرارداد → اعتبارسنجی + تست هر دو پلتفرم (job `contracts` در `ci.yml` آماده است)
- [x] **1.14.12:** Environment محافظت‌شدهٔ `release` (فقط تگ‌های `mobile-v*`) برای Secretهای امضای Android؛ Secretهای سطح ریپو حذف شدند
- [x] **1.14.12:** Required reviewer روی Environment `release` پیش از انتشار پایدار (در 1.14.13 فعال شود)

### v1.14.13 — Release Candidate & Native Windows Validation

- [x] E2E روی Repository آزمایشی جدا (نه ریپوی اصلی)
- [x] ویندوز (runner واقعی): نصب، ارتقا از آخرین 1.14.x، مسیر Unicode/فاصله‌دار، Credential Manager، smoke؛ خطای شبکه/rate limit/commit/push/download با تست واحد و E2E. موارد دستی (GCM prompt، قطع شبکه در GUI، SmartScreen) در چک‌لیست **NOT RUN** ماندند
- [x] عدم افشای Token در log، URL، process args، error و crash report
- [x] هم‌زمانی، لغو، retry، stale state، idempotency
- [x] مستندات FA/EN، CHANGELOG، ARCHITECTURE، checklist، hashها و rollback plan

### v1.15.0 — Definition of Done

حساب امن · Repository Browser و binding (کامل یا subpath) · Review/Commit انتخابی/Sync Plan/Push کنترل‌شده · Build Center دقیق · Sync & Build انتها‌به‌انتها با Hash verification · Monorepo + Desktop CI + Android proof + contracts · Release جدا با سیاست امضای محافظت‌شده · تست‌های رگرسیون + نصب واقعی ویندوز + SHA-256 manifest.

**خارج از 1.15.0:** GitHub App/OAuth کامل، iOS، Mobile Companion، Auto Commit & Push، Force Push/Hard Reset، Release موبایل بدون approval.

---

## بخش B — فاز اول: هوشمندسازی گردش‌کار (1.16.x)

مرجع: Future Roadmap بخش ۴ تا ۷ و ۲۶؛ Handoff بخش ۷ و ۸؛ باقی‌ماندهٔ v1.11.

| نسخه | محتوا | وضعیت |
|---|---|---|
| 1.16.0 | **Response Inbox:** ذخیرهٔ پاسخ خام پیش از Parse؛ `response_id`/`attempt_id` پایدار؛ Raw و Parse Result جدا؛ `schema_version`؛ Reparse بدون دریافت مجدد | ✅ `aiwb/inbox/{store,attempts,classify,pipeline}.py`، `inbox_window.py`، `test_inbox.py`، `gui_inbox_smoke.py`؛ Release `desktop-v1.16.0` |
| 1.16.1 | **خطای قابل‌فهم و بازیابی:** کد خطای استاندارد، مرحلهٔ شکست، آنچه سالم مانده، قدم بعدی؛ نجات پاسخ ناقص؛ تشخیص پاسخ قدیمی/متعلق به Task دیگر | ✅ `aiwb/inbox/{errors,salvage}.py` (۱۵ کد پایدار، نجات بلوک‌های کامل، `attempt_mismatch`/`stale_base`)؛ همراه `desktop-v1.16.0` |
| 1.16.2 | **Repair Prompt هوشمند** بر اساس خطا و Attempt واقعی؛ Diagnostics Bundle redacted (باقی‌ماندهٔ v1.11 بخش ۷.۴) | ✅ `aiwb/inbox/repair.py`، `aiwb/diagnostics.py`، `test_repair_diagnostics.py`، `gui_repair_diag_smoke.py`؛ همراه `desktop-v1.16.3` |
| 1.16.3 | **Context Request:** Capability Manifest، قرارداد `AIWB_CONTEXT_REQUEST`، استخراج خطوط/Symbol، inline در برابر ZIP، رد مسیر خطرناک/ناموجود | ✅ `aiwb/context_request.py`، `context_request_window.py`، `test_context_request.py`، `gui_context_request_smoke.py`؛ Release `desktop-v1.16.3` |

**دروازهٔ فاز اول (✅ با `desktop-v1.16.3`):** هیچ پاسخ خامی با شکست Parser از دست نمی‌رود · خطاهای مهم Import کد تشخیصی و مسیر بازیابی دارند · پاسخ ناقص قابل نجات است · Attempt/Response ID پایدار ثبت می‌شوند · Import به‌تنهایی فایل نمی‌نویسد · تست‌های رگرسیون برای JSON ناقص، ZIP مخرب، مسیر نامعتبر، Markdown مبهم، پاسخ تکراری و لغو.

---

## بخش C — فاز دوم: V2 سیستم مدیریت پروژه با چند Agent (1.17.x → 2.0.0)

> **مهم‌ترین هدف محصول.** مرجع: Future Roadmap بخش ۸ تا ۱۸، ۲۷ و ضمیمهٔ A/B؛ Handoff بخش ۹ تا ۱۵.

| نسخه | برش | محتوا | وضعیت |
|---|---|---|---|
| **1.17.0** | 2A | مدل داده و Migration: Agent، Task، Attempt، Handoff، Decision، Evidence با `schema_version` | ⬜ **گام فعال** |
| 1.17.1 | 2B | Agent Registry (۴ نقش پایه) و Task Graph با اعتبارسنجی وابستگی/چرخه | ⬜ |
| 1.18.0 | 2C | Handoff Protocol و اتصال به Response Inbox؛ انتقال Task بین دو چت/مدل مستقل | ⬜ |
| 1.18.1 | 2D | Decision Ledger و Evidence Ledger؛ وضعیت Task از سیاست + شواهد | ⬜ |
| 1.19.0 | 2E | Project State Snapshot و Auto-Publish به GitHub (صف پایدار، no-op، retry، conflict، fallback داخل Prompt) | ⬜ |
| 1.20.0 | 2F | Project Manager: Manager Update Prompt و Proposal Review با تشخیص stale | ⬜ |
| 1.20.1 | 2G | Next Action و سناریوی مرجع انتها‌به‌انتها (Future Roadmap بخش ۱۸) | ⬜ |
| **2.0.0** | — | **Release Gate فاز دوم** (Future Roadmap بخش ۲۷) | ⬜ |

**دروازهٔ 2.0.0 (خلاصه):** سه قرارداد Agent/Task، Handoff و Project State/Evidence مستند و تست شده · حداقل دو Agent با دو چت/مدل متفاوت روی یک پروژهٔ واقعی · انتقال کار بدون تاریخچهٔ چت قبلی · Evidence جدا از گزارش مدل · Auto-Publish کامل · سناریوی بخش ۱۸ بدون دست‌کاری دستی داده.

---

## بخش D — فاز سوم: رابط کاربری ساده و پیشرفته (2.1.x)

مرجع: Future Roadmap بخش ۱۹ و ۲۸.

| نسخه | محتوا | وضعیت |
|---|---|---|
| 2.1.0 | حالت Simple و Advanced روی یک منطق و داده؛ Next Action ثابت در هر دو | ⬜ |
| 2.1.x | خطاهای اولویت‌دار، وضعیت‌ها نه فقط با رنگ، واژگان FA/EN یکپارچه، پالایش بصری | ⬜ |

اصول UI از همین حالا رعایت می‌شوند؛ فقط بازطراحی بصری گسترده به این بخش موکول است.

---

## مسیر موازی — Mobile (Android)

| نسخه | محتوا | وضعیت |
|---|---|---|
| 0.1.0 | Proof-of-build: provenance، بررسی Releaseها، FA/EN، APK/AAB امضاشده | ✅ `mobile-v0.1.0` |
| 0.2.0 | مصرف `packages/contracts`: `ReleaseManifest.kt` سخت‌گیر + تست روی fixtureهای مشترک؛ `release-manifest.json` قراردادی در Release موبایل | ✅ `mobile-v0.2.0` |
| 0.2.x-tooling | مهاجرت هماهنگ AGP + Gradle + Kotlin در یک PR (PRهای #2، #5 و #8 Dependabot بسته شدند چون Build را می‌شکستند؛ AGP 8.13 با Gradle 9.8 سازگار نیست) | ⬜ |
| Companion | Pairing امن، مشاهدهٔ Task/Build، ورود پاسخ از موبایل (Integration Spec P3) | ⏭ پس از 2.0.0 |

اثرانگشت گواهی امضای Release اندروید (برای تأیید هر APK):
`SHA-256 6F:88:0A:C2:36:94:D0:C4:C0:E3:B5:9B:35:7D:F2:CE:A2:09:14:7B:7A:2E:01:7D:88:ED:2F:CE:87:3F:8D:59`

---

## تست‌های مشترک هر انتشار

1. Compile و همهٔ unit/regression tests (Linux 3.10/3.13 و Windows)
2. همهٔ GUI smokeها (`apps/desktop/tests/gui/run_all.py`) روی Linux/Xvfb و روی نسخهٔ نصب‌شده در ویندوز
3. یکپارچگی نصاب: `check_installer_manifest.py`، builder tests، verifier مستقل `tools/legacy/test_installer_packaging.py`
4. Migration Schema/config بدون از دست رفتن دادهٔ نسخهٔ قبل
5. Redaction رازها در Log، exception، URL و process args
6. تست منفی traversal، duplicate path، ZIP محدود، فایل خارج از root
7. Git: staged/unstaged/untracked/deleted/rename، divergence، non-fast-forward
8. API: pagination، 401/403/404/409/422، timeout، retry، rate limit
9. چک‌لیست ویندوز بومی در `docs/release/vX.Y.Z/` — موارد اجرانشده صریحاً «NOT RUN»

## خارج از دامنه (مگر با ADR جداگانه)

اتصال مستقیم API به مدل‌ها یا ورود به حساب مدل · ارسال/دریافت خودکار پیام چت · Agent پس‌زمینه‌ای خودمختار · اجرای بی‌تأیید فرمان یا تغییر فایل · بازنویسی کامل برنامه · انتشار پیش‌فرض Prompt/پاسخ خام در GitHub · ادغام خودکار تغییرات متعارض دو Agent · داشبوردهای بدون تصمیم عملی.

## نقشهٔ اسناد

| سند | نقش |
|---|---|
| `ROADMAP.md` (همین فایل) | ترتیب، وضعیت، دروازه‌ها — **مرجع اجرایی** |
| `docs/specs/AI_Workbench_GitHub_Monorepo_Roadmap_v1.14_to_v1.15.md` | جزئیات و معیار پذیرش بخش A |
| `docs/specs/AI_Workbench_GitHub_Monorepo_Integration_Spec_v1.13_FA.md` | مشخصات کامل GitHub Hub، Build Center، Mobile، Companion |
| `docs/specs/AI_Workbench_Future_Roadmap_v1.14_FA.md` | راهبرد فاز ۱ تا ۳، قراردادها و Release Gateها |
| `docs/specs/AI_Workbench_New_Developer_Handoff_v1.14_FA.md` | آشنایی با محصول، Response Inbox، Context Request، V2 |
| `docs/specs/AI_Workbench_v1.11.0_Development_Roadmap_FA.md` | سابقه؛ باقی‌مانده‌ها در بخش B ادغام شده‌اند |
| `docs/adr/` | تصمیم‌های معماری |
| `docs/audit/IMPLEMENTATION_AUDIT_FA.md` | ممیزی میزان پیاده‌سازی اسناد |
| `docs/release/vX.Y.Z/` | گزارش تست و چک‌لیست ویندوز هر نسخه |
