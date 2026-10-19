# AI Workbench — User Guide (desktop 3.9.0 · mobile 1.0.0)

AI Workbench helps you build a software project with the chat AIs you already use (ChatGPT, Gemini,
Claude, …) — **no API keys and no login inside the app**. The app does exactly two things with models:

1. it **writes a prompt** for you to copy into a chat, and
2. it **reads the answer** you paste back (or load from a file).

At every moment the app shows one **Next step**. Follow it and you go from an idea to a released version
without a dead end.

---

## 1. Install

**Windows desktop:** download `AI_Workbench_Setup_<version>.zip` from the GitHub release, unzip, run
`Setup.bat`. The app installs per user into `%LOCALAPPDATA%\Programs\AIWorkbench` and needs no admin
rights. An upgrade keeps your projects and settings.

**Android:** install `AI_Workbench_Mobile_<version>.apk` from the GitHub release (allow installation from
this source when Android asks).

## 2. The main window

One window, a navigation rail on the left:

| Page | What it is for |
|---|---|
| **Home** | Your projects; the *Next step* card of the active project |
| **Project Workbench** | Overview, Timeline, Tasks, Team, Files & Context, Versions & Builds |
| **Prompt** | The prompt for the current step, ready to copy |
| **AI Response** | Paste or load an AI answer → review → apply |
| **Settings** | Theme (light/dark), Simple/Advanced mode, project bundles |

*Simple* mode shows only the guided pages. *Advanced* adds Project Profile, History, Run & Report and
Git / GitHub. Every page shows at most four main buttons; the rest are under **More ▾**.

## 3. Your first project (the guided loop)

1. **Home → + New project**, pick a folder.
2. The Next step asks for your **goal** ("An offline todo app for desktop and mobile").
3. Next step: **Project Charter**. Click *Copy prompt*, paste it into your project-manager chat, click
   *I sent it*.
4. Copy the whole answer from the chat and click *Paste answer*. The app cleans what chat copies break
   (smart quotes, invisible spaces, escaped markers, extra code fences). If the answer was cut off, you get
   a ready *continue from where you stopped* prompt.
5. **Review** the charter: architecture, how many AIs work in parallel, who owns which files, the roadmap
   with milestones and versions, and the start prompt of each AI. Accept the parts you want.
6. From now on the Next step is always one of:
   * **a prompt** for a specific AI (each AI has its own queue — several can work at the same time);
   * **paste the answer** of that AI (files + a handoff note);
   * **a decision** for you (approve, request changes, pick an option);
   * **a small form** (record a test run, a commit, a release).
7. AI claims such as "tests pass" never count. A task is done only when *you* record the validation run.
8. When all tasks of a milestone are done you accept the milestone; when a version is ready you record the
   commit/tag and it is **released** — shown as a solid line on the Timeline.

If an answer is incomplete, the step offers a **repair prompt** that lists exactly what arrived and what
is still missing.

## 4. Timeline

Workbench → **Timeline**: one lane per AI plus "project". Circle size = importance (minor → critical).
Dashed vertical line = proposed version, solid = released. Mouse wheel or `+`/`-` to zoom, drag to pan,
click an event to see its details.

## 5. Phone

### Standalone mode (no PC needed)
Main screen → **Standalone mode**. Create a project, then use the same loop: the *Next step* card, the
*Paste an AI answer* box (the app recognises a charter, a manager proposal or a task answer
automatically) and the Timeline (pinch to zoom, drag, tap).

### Moving a project between PC and phone
* Desktop: **Settings → Export project bundle** → a `.aiwb-bundle.json` file.
* Phone: **Import project bundle** and pick the file (or the other way round with *Export*).
* Bundles are **never merged**. The app tells you whether the incoming copy is *new*, *the same*, *newer*,
  *older* or *diverged*. New and newer are applied directly; older/diverged need an explicit *Replace*.
  A backup of the replaced project is always kept.

### Companion (pairing with the desktop)
Desktop: **Mobile Companion → Pair** shows a QR code and a 16-character code (valid 10 minutes, 5
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

## 8. Privacy

Everything stays on your machine/phone. The app never talks to a model. GitHub is contacted only when you
use the Git / GitHub page with your own token.
