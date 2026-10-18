# ممیزی پیاده‌سازی: کدام اسناد توسعه عملی شده‌اند و چقدر؟

**تاریخ:** 2026-10-17 · **مبنا:** سورس واقعی `apps/desktop` (نسخهٔ 1.14.4 وارد‌شده تا 1.14.6 فعلی)، نه ادعای اسناد.
**روش:** جست‌وجوی کد، اجرای تست‌ها روی Linux و Windows واقعی (GitHub Actions)، و مقایسه با معیارهای پذیرش هر سند.

راهنمای وضعیت: ✅ کامل · 🟡 بخشی · ❌ انجام‌نشده · ⏭ عمداً به بعد موکول

---

## ۱. خلاصهٔ اجرایی

| سند | موضوع | میزان عملی‌شدن |
|---|---|---|
| `AI_Workbench_v1.11.0_Development_Roadmap_FA.md` | پایداری پاسخ، Repair، Diagnostics، Transaction | **≈ 85٪** |
| `AI_Workbench_GitHub_Monorepo_Integration_Spec_v1.13_FA.md` | GitHub Hub، Binding، Build Center، Artifact، Monorepo محصول | **≈ 40٪** (+ زیرساخت Monorepo/CI که اکنون ساخته شد) |
| `AI_Workbench_GitHub_Monorepo_Roadmap_v1.14_to_v1.15.md` | مسیر 1.14.1 → 1.15.0 | **1.14.1 تا 1.14.6 انجام** (6 از 14 گام) + بخش‌هایی از 1.14.9 تا 1.14.12 |
| `AI_Workbench_New_Developer_Handoff_v1.14_FA.md` | Response Inbox، Context Request، V2 چند Agent | **≈ 15٪** (فاز A شروع نشده؛ فقط پایه‌ها) |
| `AI_Workbench_Future_Roadmap_v1.14_FA.md` | راهبرد بلندمدت، V2، Release Gates | **≈ 10٪** (فقط Release Gate و CI) |
| `ADR-004` | Binding v2 و Scope در Monorepo | **✅ کامل** |

---

## ۲. نقشه‌راه 1.14 → 1.15 (سند اجرایی اصلی)

| نسخه | هدف | وضعیت | شواهد در کد |
|---|---|---|---|
| 1.14.1 | استخراج سرویس Git از UI | ✅ | `src/aiwb/git/service.py`, `models.py`, `tests/test_git_service.py` |
| 1.14.2 | حساب GitHub + Credential Manager ویندوز | ✅ | `aiwb/github/accounts.py`, `credential_store.py` — تست بومی ویندوز اکنون در CI **سبز** است |
| 1.14.3 | مرورگر Repository | ✅ | `aiwb/github/api_client.py`, `test_github_repository_browser.py` |
| 1.14.4 | Binding v2 و Scope در Monorepo | ✅ | `repository_binding.py`, ADR-004 |
| 1.14.5 | Safe Git Review & Sync Plan | ✅ | `aiwb/git/sync.py`, `aiwb/git/review_dialog.py`, `test_git_sync.py` (17 تست روی Repo واقعی) |
| 1.14.6 | Build Center: Workflow & Run Monitoring | ✅ | `aiwb/github/actions.py`, `build_center.py`, `test_github_actions.py` (17 تست)، GUI smoke |
| 1.14.7 | Workflow Dispatch & Safe Artifact Download | ✅ | `aiwb/github/artifacts.py`, `build_center_dialogs.py`, `tests/test_github_artifacts.py` (23), `gui_dispatch_artifacts_smoke.py`; dispatch و دانلود واقعی روی همین ریپو |
| 1.14.8 | One-click Sync & Build Orchestrator | ❌ | — |
| 1.14.9 | Self-hosting Repository & Desktop CI Baseline | 🟡 | ریپو، CI لینوکس/ویندوز، Actionsهای pin‌شده، permissions حداقلی انجام شد؛ ADR سیاست branch/tag مانده |
| 1.14.10 | Staged Monorepo Migration | 🟡 | `apps/desktop/{src,tests,installer}` با نصاب بایت‌به‌بایت یکسان؛ `packages/contracts` مانده |
| 1.14.11 | Android Proof-of-Build & Capability Contracts | 🟡 | اپ و APK از CI ✅؛ قرارداد مشترک و `capabilities.yml` مانده |
| 1.14.12 | Versioned Releases & Protected Signing | 🟡 | تگ‌ها و workflowهای release ✅؛ Environment محافظت‌شده برای Secret امضا مانده |
| 1.14.13 | Release Candidate & Native Windows Validation | ❌ | — |
| 1.15.0 | Stable | ❌ | — |

### جزئیات 1.14.5 در برابر معیارهای پذیرش سند

| معیار پذیرش | وضعیت | تست |
|---|---|---|
| untracked، حذف‌شده، staged از قبل، خارج از Scope درست نمایش داده شوند | ✅ | `test_review_snapshot_classifies_real_changes`، ستون Scope در پنجره |
| non-fast-forward / divergence / remote update هم‌زمان / tree کثیف بدون overwrite متوقف شوند | ✅ | `test_diverged_…`, `test_remote_changed_after_plan_refuses_push`, `test_dirty_tree_blocks_fast_forward_…`, `test_stale_plan_…` |
| لغو پیش از Commit/Push اثری فراتر از Fetch/status ندارد | ✅ | همهٔ عملیات تغییر‌دهنده پس از تأیید صریح اجرا می‌شوند |
| پیام خطا تفکیک کند Commit ساخته شد ولی Push نشد | ✅ | `test_commit_created_but_push_failed_is_reported_distinctly` |
| Secret scan کمکی گزارش شود، نه تضمین | ✅ | متن پیام‌ها و `test_secret_check_blocks_commit` |
| ممنوعیت Push مستقیم main/master؛ بدون Force Push | ✅ | `test_push_blocked_on_main`؛ در ماژول هیچ `--force` وجود ندارد |
| اتصال task_id / run_id / apply_id به پیام Commit | ✅ | Trailerهای `Workbench-Task/Run/Apply`؛ Prompt ذخیره نمی‌شود |

---

## ۳. Integration Spec v1.13

| بخش | وضعیت | توضیح |
|---|---|---|
| Monorepo برای خود محصول | 🟡→✅ ساختار | مخزن `golshandvr-del/workbench` با `apps/desktop`, `apps/mobile`, `tools`, `docs` |
| GitHub Hub (حساب، PAT، Credential Manager) | ✅ | از 1.14.2 |
| اتصال Repository / Clone / Init & Link | ✅ | از 1.14.3–1.14.4 |
| Sync امن | ✅ | 1.14.5 |
| Build Center / workflow_dispatch / Run monitoring | ❌ | در کد هیچ `workflow_dispatch` نیست |
| Artifact download داخل Workbench | ❌ | |
| CI/CD برای انتشار ویندوز و اندروید | ✅ | `.github/workflows/ci.yml`, `release-desktop.yml`, `release-mobile.yml` |
| قرارداد مشترک (packages/contracts) | ❌ | پوشه پیش‌بینی شده، CI آماده است ولی Schema نوشته نشده |

---

## ۴. نقشه‌راه v1.11.0 (پایداری پاسخ و بازیابی)

| قابلیت | وضعیت |
|---|---|
| اعتبارسنجی پاسخ، چند فرمت (JSON/Markdown/Gemini) | ✅ |
| Repair Prompt و Diagnostics | ✅ |
| Transaction / Backup / Restore Manager | ✅ (`restore_service.py`, 1.13.0) |
| انتخاب فایل‌به‌فایل Apply | ✅ (1.13.0) |
| Validation profiles | ✅ |
| Semantic diff (AST/JSON/CSV) | ✅ |
| `response_id` / `attempt_id` پایدار برای تشخیص پاسخ کهنه | ❌ (جست‌وجو در کد: 0 مورد) |
| Diagnostics bundle قابل اشتراک و redacted | 🟡 |

---

## ۵. Handoff v1.14 و Future Roadmap (فاز A و V2)

| قابلیت | وضعیت |
|---|---|
| Response Inbox (ورودی واحد همهٔ خروجی‌ها) | ❌ |
| Context Request (`AIWB_CONTEXT_REQUEST`) | ❌ |
| تشخیص `stale_response` / `attempt_mismatch` | ❌ |
| Next Action / حالت ساده و پیشرفته | ❌ |
| V2: چند Agent، Decision/Evidence Log، Handoff بین Agentها | ❌ (فقط `task_playbooks` و Capability manifest پایه) |
| Definition of Done و Release Gates | 🟡 Gateهای خودکار CI (تست Linux+Windows، نصب واقعی، GUI smoke، هش تکرارپذیر) پیاده شد |

---

## ۶. یافته‌های مهم ممیزی

1. **ادعای «Native Windows NOT RUN» در 1.14.4 واقعاً خطرناک بود.** اولین اجرای CI ویندوز 6 شکست نشان داد که یکی باگ واقعی محصول بود (crash با مسیر کوتاه 8.3). همه در 1.14.5 رفع شد.
2. نصاب `install.ps1` فهرست فایل‌ها را صریح نگه می‌دارد؛ اکنون `tools/check_installer_manifest.py` در CI تضمین می‌کند ماژول جدیدی از قلم نیفتد.
3. نصاب 1.14.4 از روی تگ `desktop-v1.14.4` **بایت‌به‌بایت** بازتولید می‌شود (SHA-256 `da854e62…`).
4. `AI_Workbench.py` هنوز ≈ 10,400 خط است؛ مهاجرت تدریجی به `aiwb/` ادامه دارد.

## ۷. اولویت پیشنهادی بعدی

ترتیب اجرایی مرجع در [`ROADMAP.md`](../../ROADMAP.md) است: 1.14.6 Build Center → 1.14.7 Dispatch و Artifact امن → 1.14.8 Sync & Build → بستن باقی‌ماندهٔ 1.14.9–1.14.12 → 1.14.13 RC → 1.15.0؛ سپس فاز اول (Response Inbox) و V2.

> اصلاحیه 2026-10-17: نسخهٔ قبلی این ممیزی شماره‌های 1.14.7 تا 1.14.12 را با عنوان‌های نادرست آورده بود؛ جدول بخش ۲ اکنون دقیقاً مطابق سند مرجع است.
