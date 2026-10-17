# AI Workbench 1.14.4 — Monorepo-aware Project Binding

## What's new in 1.14.4

- **Versioned binding schema v2:** repository bindings now include the workflow file, artifact-name pattern, release channel (`dev`, `beta`, `stable`), and optional synchronization metadata. Existing schema-v1 records are normalized idempotently; before settings are rewritten, the migration creates a timestamped backup. Invalid or duplicate rows are reported rather than silently treated as valid bindings.
- **Binding settings UI:** configure the active project's working branch, optional workflow path under `.github/workflows/`, artifact pattern and release channel. This release stores configuration only; Workflow dispatch, CI monitoring and Artifact downloads remain later stages.
- **Clone and initialize options:** Clone Selected creates a new local clone in a user-chosen empty destination. Initialize & Link prepares local Git on a non-main `workbench/initial-sync-*` branch and configures origin only after explicit confirmation. Neither action stages, commits or pushes project files.
- **Initial Push Review:** an explicit, non-mutating review lists tracked/untracked files, distinguishes active-subproject files from files outside the scope, flags suspicious paths and token/private-key signatures, and marks large files. It proposes `.gitignore` patterns; existing content is preserved and suggestions are appended only after a separate user approval. The review is advisory, not a guarantee that all secrets are detectable.
- **Monorepo-aware local Git:** Workbench resolves the true Git root and active project subpath, shows sibling/outside-scope changes as warnings, and scopes Commit staging to the active project. Existing staged index changes block a Workbench commit so they cannot be silently mixed into it. Pathspecs are passed literally; branch and push operations remain repository-wide and push-to-main/master protection stays active.
- **Correct private Git exclude path:** `.workbench/` is added to the actual repository's private `.git/info/exclude`, even when the active Workbench project is nested below the Git root; tracked files and user `.gitignore` content are not rewritten by this helper.
- **Regression coverage:** migration backup/idempotency, shared repository IDs across separate subpaths, renamed repository metadata, scope-aware initial review, non-mutating review, `.workbench` exclusion and a real local-Git GUI test proving that a subproject commit does not include a sibling/root file.

### Scope and release boundary

This release implements local binding configuration and safe Monorepo-aware operations. It does not yet implement a full file-by-file Stage/Diff review, Fetch/Sync Plan, remote divergence handling, GitHub Actions Build Center or Artifact retrieval. The test suite was run in Linux and Linux/Xvfb, including real local Git repositories. Native Windows installation, PowerShell installer execution, Windows Credential Manager, and live GitHub clone/API authentication remain **NOT RUN** here; see `WINDOWS_RELEASE_CHECKLIST_v1.14.4.md`.

---

# AI Workbench 1.14.3 — GitHub Repository Browser and Project Binding

## What's new in 1.14.3

- Added a validated `GET /user/repos` flow to the independent `aiwb.github` REST client. It loads repositories across API pages (100 per page by default, up to a clear 10,000-repository safety ceiling), deduplicates numeric repository IDs, bounds response sizes, validates metadata and classifies authentication, permission/policy, rate-limit, network, timeout and malformed-response failures.
- Added the Repository Browser to the Git / GitHub tab with account selection, name/owner/description search, All/Private/Public/Forks/Archived filters, visibility, fork/archive status, default branch, last update, description and the `push` permission signal when supplied by GitHub. Filters run on the complete loaded list rather than only the first API page.
- Added versioned, validated `github_repository_bindings` metadata. A binding records the GitHub numeric repository ID, account reference, canonical local Git root, Workbench project path, Monorepo subpath, owner/name, default branch and working branch; it never stores an access token or a raw remote URL.
- Added safe local remote inspection for HTTPS and common SSH GitHub remote formats. If `origin` is missing or points elsewhere, Workbench explicitly asks before adding/replacing it. The selected repository URL contains no credential. If durable binding metadata cannot be saved, the app attempts to restore the previous origin configuration.
- Added Unlink Project and Open on GitHub actions. Unlink only removes Workbench metadata; it does not delete commits, modify the local remote or alter the GitHub repository. Linking does not stage, commit or push files.
- A successful repository listing records `repository_read=available`; a permission/policy rejection records that this specific capability is not available for the current credential/policy. Other capabilities remain unverified until their specific operations exist.
- Added API pagination/data-validation tests, local-Git/Monorepo integration tests, credential-redaction/rollback tests, and an end-to-end GUI smoke flow using an injected HTTP transport and a temporary local Git repository.

### Scope and release boundary

This release links an already-existing local Git repository to a selected GitHub repository. It does not clone repositories, initialize Git automatically, stage/commit/push changes, validate live Git write access, provide Actions/Build Center, or download artifacts. Those are later roadmap stages. Live GitHub credentials and real user data were not used in the build tests. Native Windows installation, real Windows Credential Manager operation and a live PAT/API call remain **NOT RUN** in this Linux build environment; complete `WINDOWS_RELEASE_CHECKLIST_v1.14.3.md` on Windows 10/11 before claiming native release validation.

---


# AI Workbench 1.14.1 — Modular Git Service Foundation

## What's new in 1.14.1

- Extracted local Git executable discovery, command execution, status parsing, changed-path collection and version reporting into the UI-independent `aiwb.git` package.
- Added typed immutable `GitStatusEntry` and `GitStatusSnapshot` models. The old `git_status_info()` dictionary and tuple-based porcelain parser remain compatibility adapters so current GUI/report flows do not need a risky rewrite.
- Added an injectable `GitCommandRunner` boundary for deterministic unit tests; Git is launched with argv and `shell=False`, terminal prompting disabled, timeout bounded, and errors routed through the application's secret redactor.
- Routed project `git init` through the shared Git service rather than invoking Git directly from a GUI callback.
- Added regression coverage for status output containing Unicode, whitespace and newline paths, non-repository results, timeout/missing-Git conditions, shell-free argv execution and redaction.

This is a foundation release only. It does **not** yet add GitHub REST API authentication, Personal Access Token storage, repository browsing, GitHub Actions or artifact downloads. Those remain scheduled for later `1.14.n` releases. Native Windows installation/update verification is still required; see `WINDOWS_RELEASE_CHECKLIST_v1.14.1.md`.



AI Workbench is a local Windows desktop utility for multi-project development using regular GPT and Gemini chat accounts with manual clipboard hand-off. It does not require a model API key and does not scrape model websites. It is a controlled bridge between model-generated changes and a local project workspace.

## 1.14.0 features retained in this release

- **Typed file operations (`workbench-v3`):** model responses can propose `write`, `delete`, `rename`, and `move`. Legacy `workbench-v1` and `workbench-v2` remain write-only-compatible. Delete/Rename/Move are validated, shown in Preview, backed up, applied transactionally, and recorded with pre/post hashes for Restore. Destinations cannot overwrite existing files; rename stays within one directory.
- **Architecture-plan round trip:** the project Wizard and Project Profile can create/import/edit/validate/save/export a `workbench-architecture-v1` plan. Saved plans live in `.workbench/architecture_plan.json` and are optional prompt context; plans never authorize source changes.
- **Candidate comparison:** save validated text/JSON responses locally, then select the preferred candidate independently for each destination path. All paths default to Skip; the merged response is re-validated and previewed. Command actions are intentionally not merged. ZIP archives with binary content are not candidate-store inputs.
- **Structured semantic diff:** Python AST summaries distinguish added/removed symbols and modified definitions; JSON changes are reported by structural paths; CSV supports keyed row/cell comparison when a unique `id`/`uuid`/`key`/`slug` column exists. Other source languages use explicitly labeled regex heuristics and always retain a bounded text diff. YAML-specific semantic parsing is not yet included.
- **Task playbooks:** select a deterministic workflow for feature implementation, bug fixes, architecture refactors, security, performance, documentation/release work, or engineering simulation.
- **Semantic diff and static dependency impact:** Python changes use AST-based symbol analysis; other supported languages use explicitly labeled heuristics. The impact graph reports resolved direct/transitive dependents and unresolved imports where found. These are advisory analysis, not compiler/runtime proof.
- **Incremental modularization:** new domain services live in the `aiwb/` package (`architecture_plan`, `candidate_store`, `dependency_analysis`, `semantic_diff`, `task_playbooks`). `AI_Workbench.py` remains the stable GUI entry point for this release so the existing workflows and installer are not destabilized by a one-shot rewrite.
- **Packaging updated:** the installer now requires and installs the `aiwb/` runtime package; installer regression checks verify those module files are present.

### Safety and validation boundary

All model-proposed file operations remain subject to schema/path validation, Preview, explicit Apply approval, transaction backups, and hash-guarded Restore. Proposed commands are not merged from candidates and still require separate review/approval before execution. Static analysis is heuristic. The unit/GUI test results in the release report are not native Windows install evidence; see `WINDOWS_RELEASE_CHECKLIST_v1.14.0.md`.


## What's new in 1.12.0 — context-plan protocol consistency

- **Root cause fixed across prompt and importer:** earlier prompts could tell a model to return `workbench-plan-v1` without a complete, authoritative schema, while the importer accepted only newer field names. A sensible plan could therefore be rejected before Workbench used its requested paths. New prompts now append one canonical `workbench-plan-v2` schema that explicitly overrides implementation transport rules when essential source context is missing.
- **Backward-compatible schema adapter:** valid legacy `workbench-plan-v1` payloads using `requests`/`request`, `mode=whole_file` / `line_range` / manual-upload variants, and `manual_attachments` (including the observed misspelling `manual_attechent`) are normalized to canonical fields. `next_steps` and `completion_status` are retained. The adapter is not a permissive fallback: unknown keys and malformed nested fields still fail with a targeted error, and all file paths continue through the same traversal/sensitive-path/symlink guards.
- **Correct context-plan diagnostics:** context plans are identified as a separate workflow response, with the requested file/range/manual-upload counts displayed. Diagnostics no longer present a valid plan as an implementation response with “no files applied” as the only finding; import still never applies files or runs commands.
- **More defensive type validation:** malformed protocol/status/action/scope field types produce Workbench validation errors instead of leaking internal `TypeError`/`AttributeError` exceptions. Duplicate wrapper/import errors are deduplicated.
- **Failed-attempt observability:** rejecting a context plan now saves the exact failed reply against the active prompt-history step where local persistence succeeds, writes a structured execution event, and shows the current response SHA-256 plus the actual JSON top-level keys. This makes it possible to distinguish a changed paste from a stale/copied error report without storing raw response text in the diagnostics journal.
- **Regression coverage:** the exact older `requests` payload, alias misspellings, path-traversal rejection after migration, prompt contracts, invalid JSON field types, failed-plan history, and full GUI context selection/history path are covered.

**Important detail in the reported reproduction:** the pasted JSON uses `requests` and `manual_attachments`, but the quoted error names `request` and `manual_attechent`. The previous validator generated its unknown-key list directly from the input object's keys, so those texts do not describe the same exact JSON unless one was transcribed with a typo. Version 1.12 shows the input fingerprint and top-level keys explicitly.

**Interpretation:** in the example where the prompt included only a file tree and no file contents, returning a context plan was the correct model behavior; the bug was the incompatible plan schema and the failed importer migration. After import, the user still needs to review the selected context, build the next prompt, and send that prompt back to the same model conversation. No source implementation should be claimed before the required source contents are provided and actually reviewed.

## What's new in 1.10.0 — model-response intake reliability

- **Root fix for inconsistent model output:** one supported JSON object can be parsed even when a model wraps it in a short explanation or Markdown fence. Conflicting protocol objects are rejected rather than guessed; malformed JSON retains its specific diagnostic instead of being reported as an unrelated generic format failure.
- **Explicit raw-body AIWB blocks:** new Gemini prompts use `body="raw"`, so a file's own opening/closing Markdown fences are preserved exactly and are not mistaken for the block wrapper. Legacy fenced replies remain supported.
- **No silent file-boundary recovery:** if a block is missing its end marker before another block begins, Workbench rejects the complete response and tells you which marker is missing. It will not silently merge two files.
- **More actionable import errors:** prose-only answers, incomplete diffs, unlabeled code and descriptions of a ZIP that is not actually available are explained as such. For GPT, select a genuinely downloaded ZIP using **Load response / ZIP…**; otherwise use the complete JSON fallback. For Gemini, copy every raw AIWB block including its ending marker.
- **Safety/review unchanged:** parsing and validation do not write project files. A diff preview and explicit file-apply approval remain required, as does separate approval for model-proposed commands.

## What's new in 1.11.0 — project history and semantic version provenance

- **Validated prompt/output checkpoint:** after a model response passes Workbench validation, the Response tab enables **Save validated prompt + output to history**. This marks the exact prompt/output pair as an important project-history checkpoint without duplicating the entire response. If you edit the response after validation, the existing preview and checkpoint button are immediately invalidated; analyze the new text again.
- **Two related history layers:** every generated prompt, model reply, invalid response and manual error is automatically retained as a project-local audit/conversation trail. Marked checkpoints identify the hand-offs you explicitly want to preserve as milestones. Both are stored inside the selected project, under `.workbench/`: prompt/response audit steps in `.workbench/conversation_history/`, and version records plus response snapshots in `.workbench/project_versions/`. These project-local files are reloaded when the same project folder is opened again; they do not depend on the app installation directory.
- **Linked project versions:** only a successful, user-approved file apply creates a new project version when the project file-tree hash actually changes. The record shows its parent version, changed file paths, project inventory/hash, history-step ID, prompt/output hashes and an immutable response snapshot where possible. The History tree shows the version beside its source step; **Project versions…** can open the exact linked prompt + output.
- **Semantic bump policy:** in **Project versions…**, choose the next version bump: `patch` (default), `minor`, or `major`. It applies once to the next actual file-tree change; `minor` resets the patch component and `major` resets minor and patch. A no-op does not consume the policy. This version ledger is provenance and inventory—not Git, not a full restore point, and not evidence that tests passed.
- **Editable history tree:** right-click an entry to rename/edit metadata, edit prompt as a new revision, mark/unmark a checkpoint, select a parent, move to task root, indent/outdent, reorder among siblings, or delete. Deleting a parent lifts its children to the parent level so no dangling links remain; cyclic parent changes are rejected.
- **Project-history context:** a user can toggle inclusion when generating a prompt or click **Add history to prompt**. When a planning response explicitly requests project history, its requested scope and entry IDs are saved to that step and used in the next prompt. Only the history included in a generated prompt is sent onward manually when the user copies it to GPT/Gemini; local history is not uploaded automatically.
- **Background progress instead of console flashes:** initial inventory, Git refresh and version hashing run in progress-backed workers. Project-version work is serialized behind existing background tasks so a concurrent Git update cannot silently drop the version link. Background Windows child processes use hidden-window flags where supported; errors are still captured and surfaced.

## What's new in 1.9.0

- **Project-local prompt conversation history:** every generated prompt is stored as a Start / Step N entry associated with a task ID, parent step, prompt stage, response protocol, Workbench version, editable feature/project-version metadata and notes. Full prompt and model-response records live under `.workbench/conversation_history/`; the in-app **Prompt History** tab groups and displays them. History entries can be renamed, annotated or explicitly deleted. Use **Edit prompt as new revision…** to create an editable linked copy; the original prompt/output bodies are not overwritten.
- **Connected runtime-error repair:** use **Report manual runtime / test error…** in the response view or **Report error…** in Prompt History when an actual build/runtime/test/simulation/install failure was not detected by Workbench. Enter the observed error, affected file and reproduction steps. It is saved against the relevant history step and a repair prompt is created as the next linked step.
- **Model-requested context hand-off:** planning responses may request whole local files, exact 1-based source ranges (up to 500 lines per range), or external/binary/oversized files that need manual attachment. Whole files are selected in the tree; approved exact ranges are re-read under the existing path/size/secret checks and included in the next generated prompt. Files that Workbench cannot safely read produce a visible checklist for the user to upload to the same GPT/Gemini chat—Workbench does not upload them itself.
- **Continuation now includes the thread:** recent history-step metadata and the active step's error/context-request details are included in continuation hand-offs, tying the initial design prompt to implementation, response, manual failure and repair.
- **Durability and limits:** project-local history uses atomic JSON writes, bounded entry counts and response sizes, safe project-relative metadata paths, and an index that is separate from the full prompt/output bodies. If history cannot be durably saved, Workbench warns rather than implying the prompt was archived successfully.

Important limits: prompt/response transfer to standard GPT/Gemini chats remains manual. ZIP import preserves reviewed binary artifacts as bytes, but the ZIP transport itself is write-only: use strict workbench-v3 JSON when Delete/Rename/Move is required. History and saved candidates are local project data; review them before sharing the project folder. Native Windows installation is not proven by Linux/Xvfb tests.

## What's new in 1.8.0

- **GPT ZIP-first delivery:** for multi-file projects, the prompt asks GPT to attach a real ZIP when downloadable artifacts are supported, with a README, file-location map, exact usage instructions and a root `AIWB_RESPONSE.json` control manifest (the actions array may be empty). If the interface cannot attach files, the prompt explicitly falls back to strict JSON.
- **Review-safe ZIP import:** `Load response / ZIP…` reads an archive without extracting it, checks traversal paths, symlinks/special entries, duplicate Windows-normalized paths, sensitive files, file count, uncompressed size, text encoding and per-file limits, then opens the same file-tree/diff preview used by pasted responses. Importing never writes a file or executes a command. A missing/empty root README produces a visible review warning instead of being silently treated as a complete delivery.
- **Bounded file-runner output:** the built-in file runner now drains stdout and stderr concurrently and keeps bounded tails while the child process runs, rather than collecting unlimited output and truncating only after process exit. Timeout handling attempts to stop the process tree.
- **ZIP provenance:** the normalized response snapshot records the source archive's filename, SHA-256, size, and import counts without storing its absolute path.
- **Stable response transport:** repair prompts and continuation handoffs preserve the selected ZIP/JSON/Gemini response contract instead of silently switching formats. Planning prompts record JSON as their actual protocol even when ZIP is selected for implementation.
- **Earlier failure detection:** conflicting proposed file paths such as `config` and `config/settings.json` are rejected before preview/apply. Context files are revalidated for sensitive paths and symlinked parents and are read under a strict size cap.

Historical note for earlier releases: before v1.13.0 ZIP import was text-only. Current releases preserve permitted binary ZIP entries as exact bytes, with size/hash preview and the shared backup/Apply/Restore path. Native Windows installer execution is not validated by Linux tests.

## What's new in 1.7.1

- Fixed the self-extracting Windows installer: the embedded payload is now outside the PowerShell command and decoded via a single-line encoded bootstrap, preventing CMD from executing Base64 chunks as commands.
- Added explicit payload markers and validation before extraction; installation errors remain visible and pause for review.


The v1.5 review-first workflow is retained. This release adds more robust import parsing, editable context menus, and a user-approved project-file runner:

1. **Nested Markdown fence handling:** AIWB file/action blocks are read up to their explicit end marker and the outer closing fence is identified immediately before that marker. This preserves inner README/documentation code fences even when the model mistakenly uses the same fence length for wrapper and content. The outer fence must still exist before the end marker.
2. **Markdown-wrapped Python special paths:** the narrowly recognized artifact `**init**.py` is normalized to `__init__.py` before path validation, and the import summary explains the normalization. Other names containing asterisks are still rejected.
3. **Right-click editing menus:** editable Tk/ttk text fields now provide Cut, Copy, Paste, Delete, Select all, and—where appropriate—Undo/Redo. Disabled/read-only widgets keep editing actions disabled.
4. **Approved file run / simulation:** the Run tab can launch selected project-contained `.py`, `.js`, `.ps1`, `.bat`, `.cmd`, `.exe`, and LTspice `.asc`, `.cir`, `.sp`, `.net` files. It shows the exact command and requires confirmation, enforces a timeout, captures output/exit code, and includes updated LTspice `.log` contents in the report. An exit code of zero without a fresh, non-empty log is reported as unverified/failure, not a successful simulation. This executes with the current user’s permissions and is not a sandbox.
5. **Deliverable-neutral project profiles:** a General engineering/simulation profile and a dedicated LTspice profile guide prompts toward native schematics, SPICE artifacts and domain checks rather than forcing an app/site, GUI, entry point or installer.

The following five workflow improvements from v1.5.0 remain implemented:

1. **Live Workbench Capability Manifest:** every generated prompt includes versioned, current capability and guardrail information, including project inventory/state, selected response protocol, parser formats, file/action/size limits, approval behavior, Git availability, and the distinction between applying code, running tests, and manual verification. The manifest uses JSON for planning passes and the chosen format for implementation passes.
2. **Import diagnostics:** paste/import validation reports format, file/action counts, start/end marker counts, candidate paths, concrete rejection errors, and next steps. Import diagnostics are saved separately; the raw response is also attached to the selected step in the local Prompt History when it is within the history size limit. Failed format detection enters the same validation/diagnostics path rather than ending at a status message.
3. **File tree + per-file diff preview:** the review window shows every proposed path with create/replace status and content size. Selecting a path shows its own diff; proposed commands and model next steps have a separate review tab. A new analysis attempt invalidates any older pending preview to prevent applying stale changes.
4. **Task state machine:** task state is explicitly tracked through Draft → Prompt Ready → Response Received → Validated → Files Applied / Actions Completed → Tests Run → Verified, with Import Failed, Apply Failed, Action Failed, and Blocked states. Stage transitions are time-stamped and recorded in task history. Workbench never marks a task Verified automatically; the user must explicitly confirm review.
5. **Evidence-based repair prompt:** import, file-apply, and test/command errors can be transformed into a bounded repair prompt containing the actual recorded failure and diagnostics. Use **Copy repair prompt…** in Import diagnostics or **Repair prompt from latest failure…** in Run & Report, then paste into the same model chat. Raw invalid response text is not copied into the repair prompt by default.

- File-block parser accepts `path` and `action` attributes in either order, matching real-world Gemini output.
- Malformed file markers now explain the expected format without treating code or prose as a destination path.
- **Evidence-based continuation, reviewed actions, execution journal/recovery, batch-first prompts, Git install/update, and the durability gate** from v1.4.1 remain available; see the sections below.

- **Evidence-based continuation:** every accepted model response is saved as `.workbench/latest_model_response.json` with a normalized snapshot, response SHA-256, file paths, file hashes, and sizes. Workbench task IDs remain authoritative; any task ID claimed by the model is stored separately.
- **Reviewed model actions:** prompts can ask the model to return a batch of ordered, non-interactive validation commands alongside file changes. Actions are validated, presented in the review window, then queued. They never run on paste/import and require a separate approval in **Run & Report**.
- **Execution journal and recovery:** `.workbench/action_queue.json`, `.workbench/execution_history.json`, and `.workbench/task_state.json` record the queue, statuses, start/finish times, exit codes, timeouts, elapsed time, and bounded/redacted command output. If Workbench exits while an action is Running, it becomes **Interrupted** with an explicit warning that the process may have had partial effects. Failed or interrupted commands are not silently retried.
- **Continuation handoff:** use **Build continuation handoff** after output is available. It includes observed file-application state, file hash comparisons, command status/output/error and next steps. Optionally include the latest generated file contents for a new chat; this produces a larger handoff.
- **Batch-first prompts:** choose the execution strategy to ask the model to complete more implementation work and include predictable tests in one response instead of stopping after every command. Runtime-dependent choices still wait for real output.
- **Git install/update controls:** the Git / GitHub tab includes **Check Git**, **Install Git**, and **Update Git**. Install/update use `winget` when available and request confirmation; otherwise the app can open the official Git for Windows download page.
- **Durability gate:** if Workbench cannot save the validated response snapshot/history, it blocks file application and action queuing until the response can be analyzed and recorded again.

## Main capabilities retained

- Multi-project dashboard, New Project wizard, project-specific profiles, search/switch/reveal actions, and per-project metadata in `.workbench/project.json`.
- Recommended context selection and model-specific prompt templates.
- GPT downloadable ZIP artifacts, GPT/general strict JSON and Gemini named file/action blocks, plus backward-compatible parsing for older response formats.
- Validated relative paths, path/symlink checks, sensitive-path and best-effort secret scanning, Diff review, backups, rollback attempt on failed write transaction, manual commands, test/report view, Git branches/commits/push, and a local execution history.

## Install / update

1. Close AI Workbench.
2. Run `AI_Workbench_OneClick_Installer_v1.12.0.bat` on Windows 10/11.
3. The installer checks Python 3.10+ and Tkinter, and can attempt a per-user Python installation with `winget` when needed.
4. The normal per-user installation does not request administrator elevation. Internet and a working `winget` source may be needed for installation/update.
5. The release validation report says explicitly that the installer must still be exercised on the target Windows system; build-time GUI tests run in a Linux virtual display. The project-file runner is covered with test scripts and GUI smoke tests, but native Windows installation and LTspice execution still need verification on the target computer.

## Recommended workflow

1. Open **Projects**, create a new project or register an existing folder.
2. Configure **Project Profile** and set the task in **Workspace & Prompt**.
3. Choose an output format and execution strategy. **Batch first (minimize interruptions)** is recommended for longer implementation work.
4. Review context files, build the prompt and paste it into the regular GPT/Gemini chat. Workbench stores it as `Start` or the next `Step N` in **Prompt History**.
5. If the model returns a context plan, use **Import context plan**. Requested whole files are selected; exact ranges are inserted into the next generated prompt after validation. Attach any listed external/binary/oversized files yourself to the same model chat.
6. Import the model response (`Load response / ZIP…` for GPT ZIP, or paste Gemini/JSON text), then review every file and proposed action. Import does not write files or run commands.
7. Approve file changes and queue proposed actions. Existing files are backed up first; this step does **not** execute commands.
8. In **Run & Report**, inspect and separately approve each selected command or use **Run / simulate selected file…**. Workbench records the actual output/status; success is not equivalent to domain verification.
9. If an error or incorrect result is missed by automatic detection, use **Report manual runtime / test error…**. The error is saved against the selected prompt step, and a linked repair prompt is created.
10. Use **Prompt History** to inspect both sides of earlier hand-offs, rename entries and edit feature/version/notes, copy a prior prompt/output, or create a repair prompt from the relevant step. Right-click entries to restructure the tree. In AI Response, save a validated prompt/output checkpoint only after import succeeds. **Project versions…** lists file-apply versions and opens the exact source prompt/output; its one-shot bump selector supports patch/minor/major increments. **Build continuation handoff** summarizes the latest recorded state for continued work in the same model chat.
11. Review Git status and use a feature branch; commit/push only when ready.

## Output protocols

### GPT ZIP artifact protocol (v1.8.0)

For multi-file work, the GPT prompt prefers a real downloadable ZIP when the chat interface supports file attachments. The preferred GPT archive contract contains project files at its root, `README.md` with setup/run instructions and a file map, and a root `AIWB_RESPONSE.json` control manifest using `workbench-v2` for summary, commands and next steps. Its `actions` array may be empty. The manifest is never written into the project. The importer also accepts plain text-only ZIPs without the control manifest for compatibility.

Use **Load response / ZIP…** to inspect the archive. Workbench does not extract it to the workspace: it enforces archive/file-count/size limits, rejects traversal, links, duplicate Windows-normalized paths and sensitive destinations, and routes text plus permitted binary entries through the same Preview, backup and explicit approval flow. Binary preview uses byte counts and SHA-256 rather than a fabricated text diff. ZIP remains a write-only transport; when typed Delete/Rename/Move is necessary, request strict `workbench-v3` JSON.

### `workbench-v2` — strict JSON manifest

A response contains one JSON object with `protocol`, `task_id`, `summary`, `files`, `actions`, `next_steps`, and `completion_status`. Each file is a complete final UTF-8 text file with a relative path. Each action has a unique ID, purpose, one command, a project-relative working directory, and a timeout. `files` or `actions` may be empty, but at least one must contain an item. Actions are queued only after response validation and user review.

### `workbench-v3` — typed operation JSON

Use this protocol when the response needs an explicit deletion or path change. The top-level `operations` array accepts `write` (`path`, complete UTF-8 `content`), `delete` (`path`), `rename` (`source_path`, `destination_path` in the same directory), and `move` (different relative paths). Each operation has a unique short `id`; destinations must be absent. The app validates every operation and previews the source/destination impact before Apply. Delete/Move/Rename are backed up and represented by hash-guarded Restore state. A plan does not authorize overwriting any destination.

Legacy `workbench-v1` and `workbench-v2` remain write-only-compatible. GPT ZIP and Gemini blocks also remain write-only transports.

### Gemini named file/action blocks

Each file is returned as:

````text
<<<AIWB_FILE path="src/main.py" action="write">>>
````python
# complete file contents
````
<<<AIWB_END_FILE>>>
````

Each command is returned as a separate block:

````text
<<<AIWB_COMMAND id="unit-tests" timeout_seconds="120" working_directory=".">>>
Purpose: Run the project's unit tests
````powershell
python -m unittest
````
<<<AIWB_END_COMMAND>>>
````

Use the prompt generated by Workbench for the authoritative full schema and restrictions. `workbench-v1` remains supported for legacy file manifests. `workbench-plan-v2` is the canonical context-plan protocol; legacy `workbench-plan-v1` plans are migrated from known aliases such as `requests`, singular `request`, and `manual_attachments` before the same strict path and schema validation.

## Safety model and important limits

- Regular GPT/Gemini accounts do not directly access local files. You manually move the prompt and response between the chat and Workbench.
- Selected file contents included in a prompt may be sent to the cloud provider when pasted into chat. Review what you disclose.
- **An approved command runs on the local computer with the current Windows account's permissions.** The static command scanner is heuristic, not a complete sandbox and cannot guarantee that every dangerous command will be detected. Do not approve commands you do not understand. Prefer reviewed project test/build commands and avoid installing packages or accessing the network unless necessary.
- Model commands are never run automatically on import. The action queue has separate review and explicit execution approval.
- One command per action; command chaining, common redirection/pipes, dangerous/destructive patterns, remote publishing and privilege/admin patterns are rejected or flagged. This reduces risk but is not a security boundary against arbitrary code execution.
- Failed or **Interrupted** commands may have partially changed files or external state. Inspect the workspace before retrying.
- Secret scanning is best-effort and can miss secrets. `.workbench` is reserved for local Workbench metadata and is blocked from model writes/Git commit selection.
- Git credentials are not collected or saved by Workbench. Direct pushes to `main`/`master` are blocked.
- No prompt/response processing is performed by calling a model API; transfer remains manual.

## Local state paths

- Global settings and project library: `%LOCALAPPDATA%\AIWorkbench\settings.json`
- Project profile/manifest: `<project>\.workbench\project.json`
- Validated model response snapshot: `<project>\.workbench\latest_model_response.json`
- Queued actions: `<project>\.workbench\action_queue.json`
- Task state and last applied files: `<project>\.workbench\task_state.json`
- Execution journal: `<project>\.workbench\execution_history.json`
- Prompt/output conversation history index: `<project>\.workbench\conversation_history\index.json`
- Full history steps: `<project>\.workbench\conversation_history\entries\<id>.json`
- Backups: `%LOCALAPPDATA%\AIWorkbench\backups`
- App log: `%LOCALAPPDATA%\AIWorkbench\logs\app.log`
- Installer Python diagnostic: `%TEMP%\AIWorkbench-python-diagnostic.txt`

## Validation

Release test details and SHA-256 values are in `AI_Workbench_Test_Report_v1.12.0.txt`. Unit tests and GUI integration are run in the build environment; the embedded Windows installer itself is not executed on Windows during that build. A clean installation/update test on the target Windows computer remains necessary.
