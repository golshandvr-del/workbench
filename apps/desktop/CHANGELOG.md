## [1.14.13] - 2026-10-18

### Release Candidate & Native Windows Validation (roadmap v1.14.13)
- **Real E2E** on a separate test repository (`tools/e2e_github_sandbox.py`): Sync & Build from preflight to verified artifact whose content is the pushed commit, idempotent commit/push, stale-plan refusal after a concurrent push, confirmed manual dispatch, no token leak. Report: `docs/release/v1.14.13/E2E_REPORT_v1.14.13.md`.
- **Windows CI upgrade test:** the previous published release is installed first, sentinels are written to `settings.json` and the data folder, then this build is installed over it and the sentinels must survive. The installed app is also smoke-tested from a Unicode path with spaces.
- **Settings recovery:** a corrupt `settings.json` is kept as `settings.json.corrupt-<timestamp>` instead of being silently overwritten on the next save; files with a UTF-8 BOM are accepted.
- **RC hardening tests** (`tests/test_rc_hardening.py`, 13): token redaction across URL/header/assignment forms, network errors never echo the token, rate-limit/401 polling policy, 16-thread operation-lock race, cancel-before-commit, resume after a lost push result without a second commit, records free of tokens, unreadable credential = failed preflight.
- **Protected signing:** the `release` Environment now requires a reviewer; mobile releases wait for approval.
- Docs: rollback plan (`docs/release/ROLLBACK_PLAN.md`), release-owner decisions, RC checklist with explicit NOT RUN items, ARCHITECTURE section for 1.14.5–1.14.13.

## [1.14.9] - 2026-10-18

### Repository policy & shared contracts (roadmap v1.14.9 – v1.14.11)
- ADR-005: monorepo layout, protected `main`, work-branch naming, independent `desktop-v*` / `mobile-v*` tags created only on green merge commits.
- `packages/contracts/`: JSON Schemas `release-manifest.v1`, `build-metadata.v1`, `capabilities.v1` with valid/invalid fixtures.
- `capabilities.yml` (reporting only, no feature gating).
- `tools/validate_contracts.py` (CI job `contracts`) validates schemas, fixtures, `capabilities.yml`, the real desktop `release-manifest.json` produced by the builder and the Sync & Build record conversion.
- `aiwb.github.orchestrator.build_metadata()` converts a Sync & Build record to the shared `build-metadata.v1` contract (no local paths).
- Android consumes the release-manifest contract (`ReleaseManifest.kt`, tested on the shared fixtures); the mobile release now publishes a contract `release-manifest.json`.

## [1.14.8] - 2026-10-18

### One-click Sync & Build Orchestrator (roadmap v1.14.8)
- New **Sync & Build…** window in the GitHub panel (`aiwb/github/orchestrator.py` service, `aiwb/github/sync_build_window.py`). Visible state chain: Checking → Review Required → Ready to Commit → Committed → Pushing → CI Queued → CI Running → Build Passed/Failed → Artifact Verified/Downloaded, with the last successful step, the real effect on Git and the next action.
- **Preflight:** account token, selected Build workflow, bound work branch (never `main`/`master`) checked out, remote `origin`, fetch, sync state (diverged/conflict/remote-ahead stop the flow).
- **Review:** each change is flagged *sensitive* (cannot be committed), *outside_scope* or *workflow_change* (both need explicit confirmation).
- **Stale plan:** the remote is fetched again before commit and checked live before push; if it moved, nothing is committed/pushed.
- **Exact build tracking:** runs are looked up by bound workflow + branch + the pushed commit's full SHA; artifacts must match `repository_id + run_id + head_sha` (+ the binding's artifact pattern).
- **Cancel:** before commit — nothing changed; after commit — local commit kept; after push — the Actions run is cancelled, the commit stays. No commit is ever deleted or undone.
- **Idempotency & lock:** operation ID per flow; repeated commit/push/download reuse the record (a push whose result was lost is detected from the remote SHA); one flow per repository/branch; unfinished operations can be resumed after reopening.
- **Records:** `GitOperationRecord` + `BuildRunRecord` in `.workbench/sync_build_operations.json` (Task → approved paths → Commit SHA → Run ID → Artifact ID → SHA-256); no credentials or prompt text.
- Fixed an undefined name (`RepositoryBindingError`) that turned a failed binding save into a NameError; CI now has an undefined-name gate (`tools/check_undefined_names.py`, pyflakes).

### Validation
- 10 new orchestrator tests on real Git repositories with a local bare remote; new GUI smoke `gui_sync_build_smoke.py` (18 GUI smokes).

## [1.14.7] - 2026-10-18
### Workflow Dispatch & Safe Artifact Download (roadmap v1.14.7)
- New `aiwb/github/artifacts.py` (no Tk) and `aiwb/github/build_center_dialogs.py`; Build Center gets **Run workflow…** and **Artifacts…**.
- **Run workflow…** is enabled only for active workflows whose file declares `workflow_dispatch`. The form is generated from the file's real `workflow_dispatch.inputs` (string / boolean / choice / number / environment, required, default, options) by a small dependency-free YAML reader; values are validated before sending. The ref (branch/tag) is explicit and validated.
- Dispatch asks GitHub for run details. A run is reported as *the* dispatched run only if GitHub returned its ID, or if strict matching (same workflow, `workflow_dispatch` event, same ref, created after the request, not seen before) finds exactly one candidate. HTTP 204 without a run is reported as **Not confirmed**, never as success; several candidates are reported as ambiguous.
- **Artifacts…** lists ID, name, size, expiry, GitHub digest and run/commit. Expired artifacts and artifacts of another run/commit cannot be downloaded as this run's output.
- Download uses the official `/artifacts/{id}/zip` endpoint without following the redirect automatically; the short-lived URL is fetched **without** the token, only from GitHub/Azure blob hosts, and never appears in logs, errors or the UI. Streaming into a `.part` file with size and time caps, cancel button, size check against GitHub's value and ZIP validation; partial files are removed on any failure. HTTP 410 → "expired".
- SHA-256 is computed while downloading. The UI distinguishes **"matches the digest GitHub reported"** from **"computed; no reference (not verified)"**; a mismatch deletes the file.
- **Extract safely…** validates every entry first and extracts into a new folder via a staging directory: path traversal, absolute/drive paths, backslashes, duplicate and case-colliding names, file/folder collisions, Windows reserved/invalid names, symlinks and special files, encrypted entries, entry count, total size, suspicious compression ratio and entries that expand beyond their declared size are all rejected.
- Release tooling: `tools/bump_desktop_release.py` and `tools/mark_roadmap_step.py`.

### Validation
- 23 new unit tests (`tests/test_github_artifacts.py`), 282 in total; new GUI smoke `gui_dispatch_artifacts_smoke.py` (17 GUI smokes).
- Verified against the live GitHub API on this repository: a real `workflow_dispatch` returned a confirmed run ID; a real CI artifact downloaded with SHA-256 **matching** GitHub's digest and extracted safely.

## [1.14.6] - 2026-10-17
### Build Center: Workflow & Run Monitoring (roadmap v1.14.6)
- New **Build Center…** window in the GitHub panel (`aiwb/github/actions.py` service + `aiwb/github/build_center.py` window; no Tk in the service).
- Discovers `.github/workflows/*.yml|*.yaml` via the Actions API and reads each file to list its real triggers. "Manual run" is `yes` only when the file declares `workflow_dispatch`; unreadable files show `unknown`, never `yes`. Dynamic (Dependabot) workflows are excluded.
- The project's main Build workflow can be selected from the list and is saved in the binding; a renamed/deleted file is reported as a stale binding, a disabled workflow as disabled.
- Runs show status/result (success / failure / cancelled / skipped / timed out / … kept distinct), branch, commit SHA, run ID, attempt, created/updated times and a GitHub link.
- **Commit correlation:** the local HEAD is matched to a run only by exact 40-character SHA; if the newest run belongs to another commit, the window says so explicitly instead of showing it as the result of the latest changes.
- Jobs and their failed steps for the selected run; double-click opens the job log on GitHub (the short-lived raw-log URL is never copied).
- Non-blocking polling (worker thread + queue polled on the Tk thread) with a 5 s cache window, 10 s while runs are active, 60 s idle, exponential backoff on errors, `Retry-After`/rate-limit reset respected, and polling stopped on HTTP 401.
- **Cancel run…** only for unfinished runs, after confirmation; 403/404 → "needs Actions: write", 409 → already finishing.
- `RepositoryOperationGuard` prevents two Sync/Build operations on the same repository/ref (used by 1.14.8).
- No dispatch, Artifact download or push in this release.

### Validation
- 17 new unit tests (`tests/test_github_actions.py`), 259 in total; new GUI smoke `gui_build_center_smoke.py` (16 GUI smokes); verified read-only against the live GitHub API.

## [1.14.5] - 2026-10-17
### Safe Git Review & Sync Plan (roadmap v1.14.5)
- New **Review & Sync…** window in the Git / GitHub tab, backed by the UI-independent `aiwb/git/sync.py` service.
- Status is read with `git status --porcelain=v2 --branch -z`; each path is shown as staged / unstaged / untracked / deleted / renamed (with original path) / conflict, with its in/OUT active-project scope and a per-file diff (staged and unstaged shown separately, binary and outside-repo paths refused).
- File-by-file selection for commit. In-scope files are pre-selected; selecting outside-scope files requires an extra confirmation.
- Pre-existing staged changes that were not selected **block** the commit (nothing is mixed in). After `git add`, the index is re-read and any unexpected path aborts before committing.
- `Fetch + build Sync Plan` classifies: clean / local ahead / remote ahead / diverged / local changes / conflict / no upstream / detached, with explicit manual options for diverged and conflict states.
- Only a `merge --ff-only` is ever performed, and only when the remote is strictly ahead, the tree is clean and HEAD/branch still match the plan.
- Before push the live remote branch SHA is re-read with `ls-remote`; if it changed since the plan, nothing is pushed and a new plan is required. No force push exists. Push to `main`/`master` remains blocked.
- Editable commit message with `Workbench-Task` / `Workbench-Run` / `Workbench-Apply` trailers prefilled from local task/run/apply metadata. The prompt is never stored in the commit.
- Results distinguish "commit failed" from "local commit WAS created, but push failed".
- Secret scanning stays a best-effort auxiliary check and is reported as such.

### Windows portability fixes (found by the new native Windows CI)
- Fixed a crash recording an applied project version when the project path is a Windows 8.3 short path / junction (`relative_to` on unresolved root).
- Fixed four tests that assumed POSIX (shell-script fake LTspice runner, text-mode newline translation, unresolved temp path).

### Release engineering
- The app now lives in the `golshandvr-del/workbench` monorepo (`apps/desktop`). The installer is built reproducibly by `tools/build_desktop_installer.py` (it rebuilds the published 1.14.4 installer byte-for-byte from tag `desktop-v1.14.4`).
- CI runs the full suite on Linux (Python 3.10/3.13) and natively on Windows, installs from `Setup.bat` on a clean runner, checks shortcuts, and runs GUI smokes of the installed copy and of the new review window.

### Validation
- 242 unit/regression tests (17 new real-repository sync tests using a local bare remote: ff-only, dirty-tree block, stale plan, divergence, concurrent remote update before push, commit-created-but-push-failed, pre-staged files, main/master block, first push without upstream).

## [1.14.4] - 2026-10-17
### Project binding v2 and Monorepo-aware Git scope
- Extended `RepositoryBinding` to schema v2 with validated Workflow path, Artifact-name pattern, release channel, last-known remote SHA and sync/metadata timestamps. Schema-v1 bindings migrate idempotently with a timestamped settings backup before persistence.
- Added binding settings UI for working branch, workflow file, artifact pattern and release channel; the values are configuration only and do not dispatch workflows or download artifacts.
- Added Clone Selected and Initialize & Link flows with explicit destination/origin confirmation. Initialization starts on a non-main `workbench/initial-sync-*` branch and does not stage, commit or push files.
- Added non-mutating Initial Push Review for scope, sensitive-path/secret-signature and large-file warnings, plus explicit `.gitignore` suggestion/append behavior that preserves existing content.
- Git status now warns about changed paths outside the active project subpath. Workbench Commit stages only paths inside the active Monorepo scope; pre-staged index changes block the operation rather than being silently mixed in. Commit uses literal pathspecs and revalidates root/scope/status before staging. Branch/push remain repository-wide, and direct push to main/master remains blocked.
- Fixed `.workbench/` exclusion path resolution to target the real Git root's private `info/exclude`, including a Workbench project nested in a Monorepo.
- Added v1.14.4 service and GUI integration tests, including an actual local-Git commit proving a sibling/root path is not included.

### Validation limits
- `compileall`, 225 unit/regression tests, 14 Linux/Xvfb GUI smoke tests, installer payload byte-identity, clean payload-layout import and the v1.14.4 repository-binding tests passed. Native Windows installation, PowerShell execution, Windows Credential Manager, and live GitHub clone/API auth remain **NOT RUN**. See `WINDOWS_RELEASE_CHECKLIST_v1.14.4.md`.

## [1.14.3] - 2026-10-17
### GitHub Repository Browser and project binding
- Added bounded, paginated `GET /user/repos` support to the independent GitHub REST client. Repository IDs are deduplicated and API payload metadata, URLs, pagination bounds and response sizes are validated.
- Added the GitHub Repository Browser UI with account selection, search over owner/name/description, All/Private/Public/Forks/Archived filters, default branch, updated timestamp, description and reported push permission.
- Added versioned `github_repository_bindings` records storing repository numeric ID, account reference, canonical local Git root, active project path, Monorepo subpath and non-secret metadata. No PAT or raw origin URL is persisted in binding records.
- Added explicit, guarded origin add/replace actions for HTTPS and supported SSH GitHub remotes, with verification and best-effort compensation if metadata persistence fails. Linking does not stage, commit or push; unlinking removes Workbench metadata only.
- Added API pagination, validation, real-local-Git, Monorepo, rollback/redaction and GUI smoke tests; installer payload now includes the new binding service and its tests.

### Validation limits
- Compile, unit/regression, Linux/Xvfb GUI smoke and offline payload-integrity checks run for this release. Native Windows install, live PAT/API access, and real Windows Credential Manager remain NOT RUN in this environment. See `WINDOWS_RELEASE_CHECKLIST_v1.14.3.md`.

## [1.14.2] - 2026-10-17
### Secure GitHub Accounts and Personal Access Tokens
- Added the UI-independent `aiwb.github` package: PAT validation/redaction, injectable REST transport, authenticated-user verification, account metadata registry, and safe add/replace/test/refresh/disconnect lifecycle.
- Added a Windows Credential Manager implementation for persistent generic credentials. Production has no plaintext or memory-store fallback; the in-memory credential store is an explicit unit-test double only.
- Added the GitHub Accounts panel inside Git / GitHub with masked PAT input and background work for network/credential operations.
- Added `GET /user` REST client with User-Agent, Accept, `X-GitHub-Api-Version: 2026-03-10`, bounded timeout and response size, no redirect following, and categorized authentication, permission/policy, rate-limit, network, timeout, server and invalid-response errors.
- Settings contain only safe account metadata and an opaque credential reference. A successful identity check leaves repository, Git write, Actions, dispatch, artifact and release capabilities as `not_checked`.
- Replacing a credential verifies the same immutable GitHub user ID before switching references; disconnect removes account metadata and attempts to delete the OS credential without touching local projects or Git transport credentials.
- Added API/account unit tests, GUI smoke test, native Windows Credential Manager test script, ADR-002 and Windows release checklist.
- Restricted live bearer-token transport to `https://api.github.com`; non-GitHub HTTPS hosts and path prefixes are rejected unless an HTTP transport is explicitly injected for tests.
- Separated account metadata persistence from Tk-dependent settings serialization and synchronized both settings writers with a shared lock, preventing background PAT operations from accessing Tk variables or clobbering concurrent settings saves.
- Added regression coverage for live-host allowlisting and account creation from a background worker.

### Validation limits
- Native Windows Credential Manager and actual `.bat` install/update were not run in this Linux environment. Execute `test_windows_credential_store.py` on a Windows target and complete `WINDOWS_RELEASE_CHECKLIST_v1.14.2.md`; do not infer native success from mocked or Xvfb tests.

# Changelog

## [1.14.1] - 2026-10-17
### Modular local Git service foundation
- Extracted Git executable discovery, version reporting, shell-free command execution, porcelain status parsing, local repository status inspection and changed-path collection into the UI-independent `aiwb.git` package.
- Added immutable `GitStatusEntry` / `GitStatusSnapshot` models and kept the former dictionary/tuple interfaces as compatibility adapters.
- Added injectable `GitCommandRunner` dependencies for executable discovery, subprocess launching, environment, redaction and quiet Windows process settings. The runner disables Git terminal prompting, enforces bounded timeouts, rejects invalid argument sequences/NUL bytes and always launches with `shell=False`.
- Routed project initialization (`git init`) through the shared service boundary instead of launching Git directly from a GUI callback.
- Updated installer copying logic for nested `aiwb/git/` modules and added `test_git_service.py` to the release/diagnostic payload.
- Added service tests for argument-vector integrity, timeout/missing executable handling, secret redaction, legacy status shape, Unicode and unusual filenames. Existing UI-facing adapter signatures and status result fields are preserved.

### Validation limits
- New Git-service tests and the full regression/GUI suites are reported in `AI_Workbench_Test_Report_v1.14.1.txt`. Native Windows install/upgrade and actual Windows Credential Manager behavior remain **NOT RUN** in this environment. No GitHub REST API, PAT store, Repository Browser or Actions support is claimed in v1.14.1.

## [1.14.0] - 2026-10-17
### Typed operations, architecture plans, candidate comparison and modular services
- Added strict `workbench-v3` typed operations for `write`, `delete`, `rename`, and `move`; legacy `workbench-v1` / `workbench-v2` remain supported as write-only protocols. All paths are validated before mutation; rename is same-directory only; move/rename destinations must be absent; duplicate operation IDs and path collisions are rejected.
- Generalized Apply transactions to snapshot every affected endpoint, including paths expected to be absent. Delete/Move/Rename generate pre/post state hashes and verified backups; rollback attempts restore pre-apply bytes, and Restore can reverse a delete or both endpoints of a move while refusing post-apply edits.
- Added a validated, round-trippable `workbench-architecture-v1` plan: the new-project Wizard accepts a plan, Project Profile can reopen it, model JSON can be imported/exported/edited, and plans are saved to `.workbench/architecture_plan.json` for optional prompt context. A plan never authorizes edits.
- Added local, bounded response candidate storage and a per-destination comparison window. Every destination defaults to Skip; chosen operations are composed as v3 JSON and sent through the ordinary Preview/approval pipeline. Candidate commands are never silently merged.
- Added task playbooks for general work, feature implementation, bug fixing, refactoring, security, performance, documentation/release, and engineering/simulation. Selection is persisted in app settings and injected into generated prompts.
- Added structured semantic diffs for Python definitions (AST), JSON paths/values, and CSV columns/keyed rows/cells; selected source languages use explicitly labeled regex heuristics. Added static dependency graph / direct/transitive impact analysis for Python, JS/TS, C/C++, Java, C#, Go, Rust, Ruby, PHP, Swift, Kotlin and Scala source files. Scan limits and coverage caveats remain visible.
- Began incremental modularization in the new `aiwb/` package, retaining `AI_Workbench.py` as the stable GUI entry point rather than making a high-risk all-at-once rewrite. Updated the installer to install the package and added dedicated service, transaction, protocol, and installer-packaging tests.

### Validation limits
- The Python unit/regression suite, compile checks, GUI smoke tests and offline installer-payload checks were run in this environment; results are recorded in `AI_Workbench_Test_Report_v1.14.0.txt`. Native Windows double-click install/update and real LTspice simulation remain NOT RUN here. Do not label the release Windows-verified until the v1.14 release checklist has target-machine evidence.

## [1.13.0] - 2026-10-17
### Transaction recovery, selective review, validation profiles and binary ZIP artifacts
- Added per-file Apply selection in the review tree (all/new/changed/none). Apply uses only the selected subset, rechecks original bytes immediately before writing, keeps command approval separate, warns when a queued command appears to reference an excluded path, and records partial application distinctly.
- Every successful write transaction now receives a stable transaction ID and an immutable transaction manifest linking task/history IDs, canonical paths, before/after SHA-256 hashes, sizes and backup locations. Failure to persist the manifest is treated as an Apply failure and triggers the existing rollback path.
- Added a Restore Manager for selecting historical Apply transactions and files. Restore is allowed only when current hashes match the recorded post-Apply hashes and required backup bytes verify. Conflicts stop the selected batch; no force-overwrite option exists. Restore is itself recorded as a reversible transaction, with an execution event and project-version ledger entry.
- Added project-local validation profiles in `.workbench/validation_profiles.json`. Profiles use typed `argv` with no shell by default, bounded timeouts, ordered steps, explicit approval, optional expected-file freshness checks, and evidence statuses. Missing tools/working directories are Blocked; manual steps remain Not run; process exit is not represented as domain verification.
- ZIP import now retains binary entries as exact bytes alongside text entries. Binary review shows size and SHA-256 instead of fabricating a text diff; import remains read-only, and Apply/backup/Restore use the same transactional path. ZIP traversal, symlink/special entries, duplicate/case-colliding paths, entry/file-count limits and expanded-size limits remain enforced.
- Context recommendation now respects a conservative subset of `.gitignore` and `.workbenchignore`, preserves existing selections when recommending additional files, and offers a rationale/exclusion view. Ignore matching is explicitly not claimed to be a full Git-compatible implementation; manual selection does not bypass security-protected path checks.
- Added a reviewed, local-only redacted diagnostics JSON export. By default it excludes source, prompts, model responses, command text, process output and full user paths; the UI warns that redaction is not a perfect guarantee.
- Added `restore_service.py` and `validation_profiles.py` service boundaries, regression tests, release checklist, installer inclusion, and architecture/changelog documentation. Legacy JSON/AIWB/Markdown and text-only ZIP adapters remain supported.

### Verification limits
- Python compilation, unit/regression tests and GUI smoke flows were run in Linux/Xvfb. Native Windows double-click installation/update and real LTspice integration are **NOT RUN** here; see `WINDOWS_RELEASE_CHECKLIST_v1.13.0.md`. Do not treat the package as Windows-verified until a target Windows run records evidence.
- At the time v1.13.0 shipped, Delete/Rename/Move, architecture-plan round-trip, candidate comparison, task playbooks, change-impact analysis and multi-language semantic/dependency analysis remained follow-on work. v1.14.0 implements the first versions described at the top of this changelog; richer YAML-aware semantic parsing, compiler-backed dependency resolution and context-budget optimization remain future improvements.


All notable changes to AI Workbench are recorded here. Versions follow semantic versioning where practical.

## [1.12.0] - 2026-10-17
### Context-plan protocol migration and diagnostics
- Fixed the contract split between prompts saying “return `workbench-plan-v1`” and the importer expecting only a newer field schema. New base, repair and continuation prompts share the canonical `workbench-plan-v2` schema; the schema explicitly overrides file-delivery transport when required source context is missing.
- Added a constrained legacy migration adapter for `requests`, singular `request`, the documented whole-file/line-range/manual-upload modes, `manual_attachments`, `manual_attachment`, and the reported typo `manual_attechent`. Retained `next_steps` and `completion_status`; no legacy context request can become a file write or command action.
- Added strict adapter validation for unknown top-level/nested keys and malformed canonical list fields. Migrated paths/ranges still pass the same normal validators for project-relative paths, traversal, sensitive paths, symlinks, line ranges, list limits and text lengths.
- Context-plan diagnostics now classify plan replies separately from implementation manifests, display request counts/paths, deduplicate duplicate error messages and make it clear that no files were applied. Context-plan import refreshes the file inventory before selecting requested files and saves the exact plan/history association before moving stages.
- Hardened malformed protocol/status/action/scope type handling so user/model JSON errors become actionable `WorkbenchError` validation failures instead of internal type exceptions. Valid context plans receive a distinct diagnostic status color.
- Added regression coverage for malformed schema value types, response identity, and failed-plan history persistence; the full suite contains 144 unit/regression tests. The exact-reproduction GUI test covers legacy `workbench-plan-v1` → canonical migration → file-tree selection/history, plus a rejected-plan attempt.

### Validation limits
- 144 unit/regression tests and nine GUI smoke flows passed in Linux/Xvfb. Python compilation and installer payload byte-integrity checks passed. Native Windows installer execution was not performed in this environment; target-machine install/update remains unverified.

## [1.11.0] - 2026-10-17
### Project history, provenance and versioning redesign
- Split the local history concept into two linked but distinct records: the automatically maintained conversation/audit trail, and user-curated `project_history_saved` checkpoints. The Response tab enables “Save validated prompt + output to history” only after a successful import/validation; editing the response text immediately invalidates the old preview and checkpoint authorization.
- Added a project-local version ledger at `.workbench/project_versions/`, with a baseline and monotonically recorded semantic versions for actual file-tree changes. Each applied version records its parent, file inventory and hashes, changed paths, exact source history-step ID, prompt/output SHA-256 hashes, and an immutable response snapshot when the bounded source snapshot is available. A no-op file tree does not fabricate a new version.
- Added explicit one-shot semantic-version bump policy (`patch`, `minor`, or `major`) in Project versions…; `patch` is the default. `minor` resets patch to zero; `major` resets both minor and patch. A no-op does not consume the selected bump, and a real applied change resets the policy to `patch`.
- Linked each newly applied version to the exact history prompt/output entry, surfaced version IDs in the History tree and Project versions dialog, and added a UI action to open the source prompt/output. Project history can be added directly to a generated prompt or be included when the model requests recent summaries, version links, or selected history IDs. History content remains local and is not sent unless included in a generated prompt the user chooses to copy/send.
- Added right-click tree actions to rename/edit metadata, edit prompt as a new revision, save/unsave a checkpoint, change parent, indent/outdent, reorder siblings, and delete a step. Deleting a parent safely lifts its children rather than leaving dangling references; cyclic parent changes are rejected.
- Moved project baseline/hash inventory and applied-version hashing to progress-backed workers. Serialized pending version records behind active workers so a concurrent Git refresh cannot drop a version record after files have already been applied. Split file-tree refresh from its Git follow-up at the version-recording boundary.
- Suppressed visible transient Windows consoles for background subprocesses using `CREATE_NO_WINDOW` and retained the progress indicator for startup inventory, Git refresh, and version recording. Real errors remain visible; hiding console windows is not error suppression.
- Added regression coverage for curated checkpoint validity, stale preview invalidation, parent cycle prevention and deletion behavior, version-bump semantics, exact prompt/output provenance, no-op detection, and GUI apply→checkpoint→version-link workflow.

### Validation limits
- Unit/regression tests and eight GUI smoke flows run in Linux/Xvfb. The Windows installer payload is checked byte-for-byte; native Windows install/run behavior is still not claimed without a Windows target-machine test. Project-version records are provenance/inventory records, **not** full source snapshots or automatic restore points.

## [1.10.0] - 2026-10-17
### Model-response intake reliability (root-cause fix)
- Reworked response intake so JSON parsing is not limited to a response beginning exactly with `{`: a single supported protocol object may be extracted from surrounding explanation/fences, while multiple conflicting protocol objects are rejected instead of guessed. JSON-like parse errors now remain JSON-specific when the Markdown fallback cannot safely identify files.
- Added an explicit `body="raw"` flag for AIWB file/action blocks. The new generated contract no longer guesses whether a leading Markdown fence is file content or a wrapper; files that begin or end with fenced Markdown are preserved exactly. The older auto-detected fenced format remains supported for compatibility.
- Fixed unsafe boundary recovery: a new AIWB header before the previous block's end marker now rejects the whole response with the missing marker and line number. The former parser could consume a later file into the previous file and appear to succeed.
- Improved import errors so prose-only answers, incomplete diffs, unlabeled code blocks, and text claims about nonexistent downloadable attachments are distinguished from actual importable files. The diagnostic no longer tells users to chase unrelated marker/attribute-order fixes.
- Kept the validation and review model intact: all candidate files/actions are validated before preview; preview stays read-only; applying files and executing proposed actions still require separate approval. ZIP/JSON/legacy-block compatibility remains covered by regression tests.
- Added targeted tests for raw content starting with fences, raw command blocks, JSON error preservation, conflicting/unknown protocols, missing end markers, prompt contracts, prior sample responses, and GUI preview/apply/rejection paths.

### Validation limits
- Python unit/regression tests and Tk GUI smoke tests run in the available Linux/Xvfb build environment. The embedded one-click installer is checked for byte-identical payload integrity, but a native Windows double-click install/update cannot be claimed from Linux and remains a target-machine integration check.

## [1.9.0] - 2026-10-17
### Connected prompt/response workflow
- Added a project-local, indexed conversation history with `Start` / `Step N` sequencing, parent links, editable title/feature/project-version metadata and notes, prompt-stage/protocol/version records, metadata filtering, UI inspection/copy/delete controls, and a linked prompt-revision editor that preserves the original body.
- Every newly generated prompt is stored before the workflow reports it as ready. Model outputs—including invalid/import-error responses—are associated with the active step and bounded by documented storage limits; GPT ZIP imports store the normalized payload plus archive provenance instead of a placeholder response marker.
- Added a manual runtime/build/test/simulation/installation error dialog that stores the user's error and reproduction steps against the selected prompt, writes an execution-journal event, sets it as active evidence, and generates a linked repair-prompt step.
- Extended context planning to request whole files, exact 1-based line ranges up to 500 lines, and manual file uploads. The next prompt automatically re-reads requested ranges under path/size/symlink/secret checks and lists files the user must attach to the same model chat. The app does not claim or attempt automatic chat upload.
- Added recent thread summaries plus active/ancestor manual-error and context details to continuation hand-offs; capability/help text and both READMEs now document the linked flow and local persistence.
- Extracted the durable history service into `conversation_store.py` and included it in installation. History uses atomic JSON writes, safe project-local paths, a lightweight bounded metadata index, explicit deletion, bounded input reads, and bounded entry/output sizes.
- Added regression tests for history sequence and prompt revisions, bounded history reads, range validation/formatting, manual upload reminders, task-change isolation, parent-step error continuity, continuation hand-off and GUI flow from planning context request through model response and manual-error repair.

### Limits and validation
- Prompt and response transfer to regular GPT/Gemini chats remains manual. Binary attachments requiring model inspection must be manually attached by the user; Workbench only prepares a checklist.
- History is local project data and can include sensitive prompt/output content. Native Windows install was not executed in this build environment; see the current release test report.

## [1.8.0] - 2026-10-17
### GPT artifact delivery and runtime reliability
- Added a ZIP-first GPT output profile with exact usage/file-map documentation requirements and a strict JSON fallback when the chat interface cannot attach downloadable files.
- Added secure ZIP artifact intake. Archive entries are validated without extraction, converted to ordinary file changes, and routed through the existing diff/backup/approval pipeline. Root `AIWB_RESPONSE.json` contributes validated summary/next-step/action metadata but is never written into the project; its actions array may be empty.
- Added archive provenance to the normalized response snapshot: source filename, SHA-256, byte size and import counts (without persisting the absolute local source path).
- Unified the transport instructions used by repair prompts and continuation handoffs so ZIP/JSON/Gemini choices do not drift mid-task. Planning state records JSON as the actual protocol.
- Rejected file/directory conflicts (for example `settings` and `settings/app.json`), existing parent-file blockers and Windows-invalid control characters during response validation, before the preview/apply stage. ZIP imports now surface a review warning when the contract-required root README is missing/empty, preserving that warning even when the model summary uses its full character limit.
- Hardened context-file reads by revalidating sensitive paths and every path component for symlinks and enforcing the byte limit while reading.
- Added a GUI integration test that loads an actual ZIP, confirms preview is non-mutating, applies reviewed files, and verifies the control manifest is never written into the workspace.
- Added streaming bounded `argv` execution for project-file runners. Both output streams are drained concurrently and their captured tails are capped during execution; timeout handling attempts to terminate the process tree.
- New installations default to the GPT ZIP-first format; existing saved user format choices are preserved.

### Limits and validation
- ZIP artifacts accept UTF-8 text files only. Binary assets, invalid encodings, archive traversal, symlinks/special entries, sensitive paths, duplicate Windows-casefolded paths, excessive size/count and invalid metadata are rejected explicitly.
- Added ZIP safety/provenance, GPT prompt contract, bounded-output and timeout regression tests plus delivery-transport continuity, path-conflict and bounded context-read coverage.
- Native Windows installer execution and native LTspice simulation remain platform integration checks and are not inferred from Linux tests.

## [1.7.1] - 2026-10-17
### Windows installer reliability (root-cause fix)
- Fixed the installer packaging defect that put multiline Base64 data inside a PowerShell `-Command` string. Windows CMD split the payload into commands and PowerShell reported an unterminated string.
- Replaced that design with a one-line `-EncodedCommand` bootstrap, an embedded payload placed after `exit /b`, exact begin/end markers, Base64 validation, unique temporary extraction, and a checked child-process exit code.
- Documented the packaging invariant in `ARCHITECTURE.md` and updated regression expectations to version 1.7.1.

### Validation limits
- Payload decoding and archive-byte identity are checked in the build environment; unit and GUI smoke tests are rerun.
- A native Windows double-click installation is still not executed in this Linux build environment and remains the final machine-specific integration check.

## [1.7.0] - 2026-10-16
### Architecture and reliability
- Added `ARCHITECTURE.md` as the architecture baseline, including layer boundaries, response protocol rules, execution/evidence semantics, project initialization contract, test gates and migration debt.
- Added a change-control rule: every user-reported defect needs a reproduction, root cause, invariant, regression test and documented residual limitation.
- Corrected Windows `.bat/.cmd` command construction. The old `cmd.exe /d /s /c` quoting lost reliable quoting around script paths containing spaces; command construction is isolated in `build_windows_batch_argv` and regression-tested without running a Windows shell.
- Kept project-file execution and model-proposed command execution separate from import/preview; the execution result must be recorded before it can be included as observed evidence in a follow-up prompt.
- Updated the live capability manifest release version to 1.7.0.

### Validation
- Regression test added for `.bat` paths and arguments containing spaces.
- The test suite must be rerun for the release build; native Windows `.bat` execution and a real LTspice simulation remain platform/integration checks, not inferred from unit tests.

## [1.6.0] - 2026-10-16
- Added project-file runner and execution diagnostics, including LTspice batch support.
- Added right-click editing context menus, file-run result evidence, and deliverable-neutral engineering project guidance.
- Fixed Markdown fence parsing and normalization of Markdown-wrapped `__init__.py` paths.

## [1.5.0] - 2026-10-16
- Added live capability manifest, import diagnostics, file preview/diff, workflow states and repair prompts from recorded failures.
