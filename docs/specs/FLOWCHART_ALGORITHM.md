# Owner's algorithm — node-by-node analysis (source of Roadmap 4.x)

Source: `docs/specs/flowchart/owner_algorithm.pdf`. Colours: **yellow = app**, **green = user**, **blue = GitHub**.
The flowchart reads right-to-left (Persian). This document fixes the node ids used in code (`project-flow.v1`).

## 1. Main line

```
F1 Start project (user)
 ├─► F2 Start timeline (app)
 ├─► F3 Create repo / update existing repo (GitHub)
 └─► F4 Get name, specification and number of available AIs (app)
      ► F5 Design the project-manager prompt (app)
      ► F6 Give the prompt to the PM AI (user)
      ► F7 Bring the PM output back (user)
      ► F8 Check the PM output (the ROADMAP) carefully (app)
      ► F9 Split the project into parallel paths following the model output (app)   ──► timeline
      ► F10 Generate a suitable prompt for every AI (app)        ◄── (emergency task) ◄── (stage remaining)
      ► F11 Give each AI its prompt (user)                        ◄── F15
      ► F12 Bring every AI's output back (user)
      ► F13 Is the output acceptable? (app)
           no  ► F14 Smart problem detection (app) ► F15 Troubleshooting prompt (app) ► F11
           yes ► F16 User approval (user) ──► timeline update
                 ► F17 Add to the project files (app)
                 ► F18 Status prompt for the PM AI (app)   ◄── GitHub info (after release)
                 ► F19 Give it to the PM (user) ► F20 Bring the PM output back (user)
                 ► F21 Did the PM define an emergency intervention task?
                      yes ► F10
                      no  ► F22 Save changes on GitHub ► F23 If a RELEASE is needed ► F24 Publish new version (GitHub)
                          ► F25 Is any ROADMAP stage left?
                               yes ► F10
                               no  ► F26 Announce completion (app) ──► timeline update
                                    ► F27 Expand the project? (user)
                                         yes ► F1 (new cycle, same project)
                                         no  ► F28 Archive the project (app)
```

## 2. Where the blue (GitHub) boxes belong

They are a **third category: integrations the app prepares and the user authorises**. The app performs them with
the user's own GitHub token (GitHub only — never a model account), and every write (create repository, commit/push,
tag, release) needs one explicit confirmation. Without a token, the same step is shown as manual instructions plus a
"record the result" form, so the loop never dead-ends.

## 3. Scientific review — corrections adopted (no node removed)

| # | Issue in the drawn algorithm | Correction |
|---|---|---|
| C1 | F13→F14→F15→F11 can loop forever | At most 3 troubleshooting attempts per task, then escalate to the PM in the next status prompt |
| C2 | Work is only saved to GitHub after the PM answers (F22); a crash before that loses approved work | Checkpoint on approval (F16/F17) to the project branch; F22 then only finalises (merge/tag) |
| C3 | "Parallel paths" ignore dependencies | F10 only releases tasks whose prerequisites are done, at most `max_parallel_chats` at a time (waves) |
| C4 | An emergency task may contradict work still in flight | Emergency tasks get top priority and block in-flight tasks that depend on them |
| C5 | "Is the output acceptable?" undefined | Two layers: automatic diagnosis (format, cut-off, scope, deliverables, copy damage, unsupported test claims) then the user's judgement; model claims are never evidence |
| C6 | "Expand" back to F1 would lose history | Expansion = next major cycle of the same project with an expansion charter; history kept |
| C7 | Repo creation (F3) needs the name from F4 | F3 runs right after F4 in practice (the drawing's parallel branch is kept, ordered by data dependency) |

## 4. Mapping to code

| Node(s) | Phase | Desktop | Mobile |
|---|---|---|---|
| F1–F8 | start, repo, brief, charter_prompt, charter_review | `v2/flow.py`, `v2/charter.py` | `core/Flow.kt`, `core/Charter.kt` |
| F9–F12 | split, dispatch, collect | `v2/flow.py` (waves), `v2/guide.py` | `core/Flow.kt`, `core/Guide.kt` |
| F13–F15 | check, troubleshoot | `v2/diagnose.py` | `core/Diagnose.kt` |
| F16–F17 | approve, integrate | `v2/guide.py`, Apply | `core/Files.kt` |
| F18–F21, F25 | status_report, pm_decision | `v2/flow.py` (status prompt + PM routing) | `core/Flow.kt` |
| F3, F22–F24 | repo, publish | `github/*` | `core/GitHub.kt` |
| F26–F28 | complete, expand_or_archive, archived | `v2/flow.py` | `core/Flow.kt` |
