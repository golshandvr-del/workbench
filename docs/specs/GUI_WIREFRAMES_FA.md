# Wireframe و تصمیم‌های Layout (GUI roadmap، مرحلهٔ 3)

**تاریخ:** 2026-10-19 · **نسخهٔ سند:** 1.0 · **ورودی:** `GUI_INFORMATION_ARCHITECTURE_FA.md`

جهت LTR نشان داده شده؛ در RTL کل ساختار افقی آینه می‌شود (Sidebar راست، Inspector چپ، ترتیب دکمه‌ها برعکس).

## ۱. قاب مشترک — سه سطح عرض

**عریض (≥1280):**
```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ ☰  Project name · goal (short)          local / GitHub status          ⓘ   │ Project Bar (36–44px)
├────────────┬──────────────────────────────────────────────┬─────────────────┤
│ Overview   │ Page title                     [secondary] [PRIMARY]│ Inspector  │
│ Tasks      │ one-line purpose (muted)                     │  title          │
│ Team       │ ┌ Banner (only when important) ────────────┐ │  key: value     │
│ Timeline   │ └──────────────────────────────────────────┘ │  key: value     │
│ Files&Ctx  │ section title                                │  ─────          │
│ Deliveries │ list / table / form                          │  [action]       │
│            │                                              │  [action]       │
│ Settings   │                                              │                 │
├────────────┴──────────────────────────────────────────────┴─────────────────┤
│ status line: last result · local state                                       │
└─────────────────────────────────────────────────────────────────────────────┘
 Sidebar 176px                     content ≥ 560px                 Inspector 300px
```

**معمولی (1100–1279):** همان؛ Inspector 260px.

**محدود (<1100، حداقل 960×600):** Inspector زیر محتوا با ارتفاع حداکثر 30٪ و اسکرول داخلی؛ Sidebar برچسب کوتاه (<900). جدول‌ها حداقل ۵ ردیف دیده می‌شوند (رفع IA-5/IA-6/RA-3). محتوای بلند (Team، Deliveries) در ناحیهٔ اسکرول‌پذیر عمودی.

## ۲. Overview

```text
Overview                                                    
Goal: <goal text or empty-state>                            
┌ NEXT STEP ───────────────────────────────────────────────┐
│ ▶ Review what the agent delivered — HO-0002   [Review delivery HO-0002] │  ← تنها Primary صفحه
└──────────────────────────────────────────────────────────┘
Progress   3 of 18 tasks verified · 17% by count (not effort)   ▕████░░░░░░▏
Needs your attention (6)                 [Open] [Mark as read] [Show read]
  ✕ Decision     DEC-0001  Decide: Pick database
  ⚠ Stale answer TASK-0005 · agent-fx-03  Reconcile or discard the old answer
  ⚠ Partial      TASK-0003 · agent-fx-02  Ask for the missing items
  … Ready to start (14) — collapsed
Recent activity
  02:45  You copied the prompt for TASK-0009
  02:45  Handoff HO-0004 exported
```

## ۳. Tasks و Prompt/Answer

```text
Tasks                                 [filter ▾] [text____]   
┌ Task ─────────────────┬ Status ─────────┬ Step ─────────────┬ Agent ──┐
│ TASK-0005 title       │ … Waiting       │ Older answer      │ fx-03   │
└───────────────────────┴─────────────────┴───────────────────┴─────────┘
Prompt & answer — TASK-0005 · HO-0004          ● Copied — not sent
┌ Prompt (Workbench never sends it) ─┐ ┌ Paste the model's answer ────┐
│                                     │ │                              │
└─────────────────────────────────────┘ └──────────────────────────────┘
[Copy prompt] [I sent this prompt]                 [Check & import answer]
```
Primary صفحه: «Check & import answer» فقط وقتی پاسخ Paste شده یا منتظر پاسخ هستیم؛ وگرنه «Copy prompt» Secondary است.

## ۴. Team (زیربخش‌ها با Tabهای ttk.Notebook)

```text
Team   Verified 0 · working 3 · waiting for your paste 1 · blocked 0 · needs action 18
[ Agents ] [ Account profiles ] [ Team planning ] [ Proposal (1) ]
  Agents: [filter__] [x] needs action only
  table: Agent · Role · Account · Chat · Open · Current step · Needs you · Ready?
```
دلیل Tab: چهار کار مستقل با فرم‌های متفاوت؛ در 1024×640 هر کدام کل ارتفاع را می‌گیرد (رفع IA-5). Tab «Proposal» فقط وقتی Proposal منتظر هست و با شمارش.

## ۵. Timeline

```text
Timeline                [type ▾] [text____] [Filter]  [Lanes by agent]  ‹ 1/3 › 
┌ When ──┬ What happened ─────────────────────────┬ Reference ─┬ Source ─┐
│ 02:45  │ You confirmed sending TASK-0007        │ TASK-0007  │ you     │
└────────┴────────────────────────────────────────┴────────────┴─────────┘
```

## ۶. Files & Context

```text
Files & Context
Prepared context is NOT sent until you paste it into the chat yourself.
Context requests (from pasted answers)
┌ Task ──────┬ Files / lines ─────────────┬ Reason ───────┬ Status ───────────┐
│ TASK-0009  │ src/app.py 10–40           │ need handler  │ ● Requested       │
└────────────┴────────────────────────────┴───────────────┴───────────────────┘
Empty: "No context requests yet. When an answer asks for files, it appears here."
Tools:  [Prepare context package…] [Response Inbox…] [Classic prompt & response…]
```

## ۷. Deliveries

```text
Deliveries       Builds and releases are recorded only when they really happened.
Milestones and versions                     [New milestone…] [Propose version…]
┌ Item ───────────────┬ Status ───────┬ Evidence ─────────────────┬ Tasks ──┐
│ v1.0 MVP            │ ◐ tagged      │ tag v1.0 (recorded by you)│ 4       │
└─────────────────────┴───────────────┴───────────────────────────┴─────────┘
[Accept milestone] [Record commit / tag / release…]
Build & sync:  [Build Center…] [Sync & Build…]
```

## ۸. Settings

```text
Settings
Display      Language [en ▾]   Theme [light ▾]   Mode [simple ▾]
             View, language and theme never change project data.
Keyboard     Ctrl+B sidebar · Ctrl+I inspector · Alt+1…7 sections
Other tools  [Mobile Companion…] [Projects window (classic)…]
```

## ۹. حالت‌ها (برای هر نما)

| حالت | الگو |
|---|---|
| Empty | یک جمله: چه چیزی اینجا ظاهر می‌شود + اقدام شروع (اگر وجود دارد) |
| Loading | (Read modelها همزمان و زیر 100ms اند؛ حالت Loading جدا لازم نیست — اندازه‌گیری §۸.۳) |
| Success | Status line + Banner اطلاعی فقط برای تغییر برداشت |
| Error | Banner خطا: چه شد · اثر · چه چیزی حفظ شد · چه کنید |
| Disabled | اقدام نامجاز نمایش داده نمی‌شود (Inspector فقط اقدام‌های مجاز را دارد) |
| Long content | جدول اسکرول؛ متن‌ها wrap؛ شناسه‌ها هرگز بریده نمی‌شوند |

## ۱۰. Decision log

| # | تصمیم | دلیل | مدرک |
|---|---|---|---|
| L1 | Next Action فقط در Overview | گزینهٔ B تحقیق §۴ | IA-2 |
| L2 | Mode/Language/Theme به Settings | R2 | IA-7 |
| L3 | Team با Notebook چهار Tab | فرم‌های مستقل؛ ارتفاع | IA-5 |
| L4 | Milestone/Version به Deliveries؛ برچسب «Versions & Builds» ← «Deliveries» | یک مقصد برای سناریو ۹ | IA-3 |
| L5 | Inspector محدود به ۳۰٪ ارتفاع در عرض کم | فهرست دیده شود | IA-6 |
| L6 | ترتیب Sidebar: Overview، Tasks، Team، Timeline، Files، Deliveries، Settings | ترتیب اهمیت کاربر (6A→6E) | IA §۲ |
| L7 | RTL = آینهٔ ساختار | R11 | RA-1 |
| L8 | Request a change = یک Dialog با Radio | انتخاب نه تایپ | IA-4 |

## ۱۱. Gate 3

- [x] ساختار صفحه، مقصدها و مسیر سناریوها تعریف و به مشکلات ممیزی وصل شدند.
- [x] سه سطح عرض با تغییر جای پنل (نه فقط فشرده‌سازی).
- NOT RUN: آزمون وظیفه با کاربر روی Wireframe. Walkthrough سناریوهای F1–F10 انجام شد.

**نتیجه:** Gate 3 — PASS (با NOT RUN صریح). تغییر IA از اینجا به بعد فقط با شواهد.
