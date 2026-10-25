# AI Workbench — User Guide (desktop 5.11.0 · mobile 2.0.0)

AI Workbench helps you build a software project with the chat AIs you already use (ChatGPT, Gemini,
Claude, …) — **no API keys and no login inside the app**. The app does exactly two things with models:

1. it **writes a prompt** for you to copy into a chat, and
2. it **reads the answer** you paste back (or load from a file).

At every moment the app shows one **Next step**. Follow it and you go from an idea to a released version
without a dead end.

---

## 1. Install

**Windows desktop:** download `AI_Workbench_<version>_Setup.bat` from the GitHub release and
double-click it (Python 3.10+ with Tkinter is detected, or installed per user via winget). The app installs per user into `%LOCALAPPDATA%\Programs\AIWorkbench` and needs no admin
rights. An upgrade keeps your projects and settings.

**Android:** install `AIWorkbench-mobile-<version>.apk` from the GitHub release (allow installation from
this source when Android asks).

## 2. The main window

One window ("Mission Map" look, Midnight or Daylight): a **toolbar** on top (New Project ▾ · Open · Save · Run),
an **icon rail** on the left and a **status bar** at the bottom (agents running, milestone, saved state).
Each rail page has one job:

| Page | What it is for |
|---|---|
| **Home** | The cockpit of the active project: the **Mission Map** (one lane per AI, one circle per task in its version's column), **Map view**, task details and the **Next step** card — where you do every step (5.11.0) |
| **Projects** | **Your projects** as cards (click = select, double-click = open, *Find* filters; *More ▾* → Open selected · Reveal folder · Remove from list), then the Workbench of the open project in three sections: **Plan & Tasks** · **Timeline** · **Project settings** |
| **Agents** | One card per AI (state, current task, load, record), the selected AI's queue, *Copy briefing*, *Memory note…*, Balance alerts and suggested moves |
| **History** | **Timeline** of everything that happened, then every prompt and AI answer of the project |
| **Settings** | Light/Dark, Simple/Advanced, Reduce motion, Mobile Companion, Restore Manager, App Map |

*Simple* mode shows only the guided pages. *Advanced* adds each page's **Tools**: Projects › Project Profile and
Run & Report, Agents › Prompt and AI Response, History › Git / GitHub. Every page shows at most eight controls at once
and at most four main buttons per bar; the rest are under **More ▾**.

**Mission Map tips (Home):** right-click a task circle for COPY PROMPT · SEND PROMPT · GET AI RESPONSE · MARK AS
DONE (only the ones possible now are enabled). *Map view* → **Hide finished tasks** and **Only AIs with open work**
make a big project readable; the lane numbers never change. **Click an AI's number or name** and the Next-step card
shows that AI's own prompt or answer step (*More › Back to the next step* returns). *Task details › More* has Jump to
active task, Copy task summary and **Copy map summary** (every lane and its tasks as plain text). On short windows the project cards (Projects) and the History timeline fold away.

## 3. Your first project (the guided loop)

1. **Toolbar › New Project**. One window with three steps (5.9.0):
   * **Project** — name, parent folder, your **goal** in one or two sentences ("An offline todo app for desktop and
     mobile"), the kind of project (it fills *Platform / technology*; change it freely) and, folded away,
     technical details (constraints, README, Git).
   * **Team** — *how many AIs work in parallel* besides the project manager, then one row per AI: a **name you
     choose** (any language), its role (Developer, Reviewer / tester, Architect, Researcher), the model or account
     it runs on (just a label) and a note. Every AI gets its own lane on the Mission Map under that name.
   * **Answers** — how the AIs return files: *AIWB file blocks* (recommended), *Strict JSON* or *GPT ZIP*. The task
     prompts ask for that format; whatever an AI returns anyway (Markdown code blocks with the file name above them,
     JSON, a ZIP) is read too (5.10.0).
   *Create project* makes the folder and the team and opens **Home**, already on the first step — nothing is asked
   again afterwards. Change the team any time:
   **Agents › Team › Edit team…** (an AI that already has work is switched off, never deleted). Projects made
   before 5.9.0 keep their AIs; *Edit team…* offers to remove template AIs that never got a task.
2. For a folder added with *Add existing folder…* the Next step's first action **Start the project…** opens the same
   window without the folder fields.
3. Everything below happens on **Home › Next step**: the card names the step and the AI, has the step's main button
   and a *More ▾* menu, and — when the step takes an answer — a **paste box right on the page**. First step:
   **Project Charter**. Click *Copy the charter prompt* and paste it into your project-manager chat. The prompt tells
   the project manager that your team is binding.
4. Copy the whole answer from the chat, paste it into the card's box and click *Use this answer*. While you paste,
   the box shows a **live
   diagnosis** — *Charter ✓ · 4 AIs · 9 tasks · 2 auto-fixes*, *3 files (Markdown code blocks)*, *Cut off ✗* or the
   exact problem; nothing is imported before *Use this answer*. A downloaded archive goes in with **Load ZIP…**.
   The app cleans what chat copies break (smart quotes, invisible spaces, escaped markers, extra code fences) and
   reads the charter leniently: JSON without markers, comments, role names such as *developer* or *tester*,
   versions such as *v0.1* and similar slips are fixed — every fix is listed. Only a really ambiguous answer (a
   task that depends on a task that does not exist, an AI outside your team) is refused, with a ready **fix
   prompt** for the same chat. If the answer was cut off, you get a ready *continue* prompt (for a charter: send
   the complete charter again, shorter).
5. **Review** the charter: architecture, how many AIs work in parallel, who owns which files, the roadmap
   with milestones and versions, and the start prompt of each AI. Accept the parts you want.
6. From now on the Next step is always one of:
   * **a prompt** for a specific AI (each AI has its own queue — several can work at the same time); *Prepare the
     prompt* also copies it, so you go straight to the AI's chat;
   * **paste the answer** of that AI (files + a handoff note);
   * **a decision** for you (approve, request changes, pick an option);
   * **a small form** (record a test run, a commit, a release).
7. AI claims such as "tests pass" never count. A task is done only when *you* record the validation run.
8. When all tasks of a milestone are done you accept the milestone; when a version is ready you record the
   commit/tag and it is **released** — shown as a solid line on the Timeline.

If an answer is incomplete, the step offers a **repair prompt** that lists exactly what arrived and what
is still missing.

## 3a. The whole algorithm (flowchart F1–F28)

The phase bar at the top of the project (desktop and phone) always says where you are in the owner's flowchart
(`Flow F10 · Generate a suitable prompt for every AI (app)`). Kinds: **app** = Workbench does it, **you** = your
action, **GitHub** = optional repository step.

| Stage | Nodes | What happens |
|---|---|---|
| Start | F1–F4 | One form: name, goal, platform, constraints and **how many AI chats** you can follow at once. The timeline starts (`project_started`). Optionally connect a GitHub repository (F3) — Workbench only writes its own branch `aiwb/<project>`, never `main`. |
| Charter | F5–F8 | Copy the charter prompt → *I sent it* → paste the answer → check it. Nothing is created before you accept. |
| Parallel paths | F9–F12 | The roadmap becomes parallel paths (one per AI) in waves that respect dependencies and your chat limit. The **dispatch desk** prepares every prompt of the wave at once; copy each into its AI's chat, then paste each answer. |
| Smart check | F13–F15 | Every pasted answer is checked: cut off, missing manifest, wrong attempt, files outside the AI's paths, empty files, missing deliverables, copy damage, test claims without evidence. Problems → a **troubleshooting prompt** with only the problems (max 3, then the project manager is asked). |
| Approve & integrate | F16–F17 | You accept the delivery (files go to the project files with a backup), review the task, and record the real test/build run (or accept it as NOT RUN). |
| Status report | F18–F21 | When nothing else waits, Workbench writes the status prompt for the project manager. Its answer may define **emergency tasks** (they go first and pause what they block) and says whether a roadmap stage is left. |
| GitHub | F22–F24 | Save the approved files on the project branch (one commit, no force push), and publish a version (tag + release) when all its milestones are accepted. Without a token you get exact manual steps and record the result. |
| End | F25–F28 | No stage left → **announce completion** (summary of tasks, versions and evidence). Then **expand** (the next major cycle, with the whole history, back to F1) or **archive** (final bundle; the project becomes read-only until you reopen it). |

Workbench 4.7.0 / mobile 2.0.0 tests every one of the 32 edges of this flowchart end to end, with three scripted AIs
working in parallel (`test_algorithm_e2e.py`, `AlgorithmE2ETest`).

## 4. Timeline

Projects › Workbench → **Timeline**: one lane per AI plus "project". Circle size = importance (minor → critical).
Dashed vertical line = proposed version, solid = released. Mouse wheel or `+`/`-` to zoom, drag to pan,
click an event to see its details.

## 5. Phone

### Standalone mode (no PC needed)
Main screen → **Standalone mode**. Create a project, then use the same loop: the *Next step* card, the
*Paste an AI answer* box (the app recognises a charter, a manager proposal or a task answer
automatically) and the Timeline (pinch to zoom, drag, tap).

### Moving a project between PC and phone
* Desktop: **Project Workbench → Project settings → Project tools ▾ → Export project for the phone…** → a
  `.aiwb-bundle.json` file (*Import project from the phone…* is in the same menu).
* Phone: **Import project bundle** and pick the file (or the other way round with *Export*).
* Bundles are **never merged**. The app tells you whether the incoming copy is *new*, *the same*, *newer*,
  *older* or *diverged*. New and newer are applied directly; older/diverged need an explicit *Replace*.
  A backup of the replaced project is always kept.

### Companion (pairing with the desktop)
Desktop: **Settings → Application → More ▾ → Mobile Companion… → Pair** shows a QR code and a 16-character code (valid 10 minutes, 5
attempts). Phone: *Scan QR* or type the code. The phone then sees the desktop project over your local
network.

## 6. Git and GitHub (optional, Advanced)

Git / GitHub can commit the files the AIs delivered, bind a GitHub repository with a personal access token
(stored in Windows Credential Manager) and follow CI runs. None of this is needed for the guided loop.

## 7. Troubleshooting

| Problem | What to do |
|---|---|
| "Nothing recognised" after paste | Copy the *whole* answer, including the `<<<AIWB_…>>>` lines. Use *Load file* if the chat offers a download. |
| Answer cut off | Use the *continue* prompt the app shows; then paste the continuation. |
| Bundle refused (damaged / other project) | Export it again; do not edit bundle files by hand. |
| Bundle is *older* or *diverged* | Decide which copy is right; *Replace* keeps a backup of the other. |
| Window too small | All pages scroll and toolbars wrap; minimum supported size is 1024×640. |

## 8. Not run by the developers (NOT RUN)

These checks need hardware or accounts only the product owner has; they are listed, never claimed:

- Physical Windows at 100 / 125 / 150 / 200 % DPI.
- A complete project with real ChatGPT / Gemini / Claude chats (three AIs in parallel).
- A real phone: standalone mode, project files, GitHub with a real token.

## 9. Privacy

Everything stays on your machine/phone. The app never talks to a model. GitHub is contacted only when you
use the Git / GitHub page with your own token.
