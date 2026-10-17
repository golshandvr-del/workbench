# AI Workbench Architecture

Version: 1.14.4  
Status: Architecture baseline and change-control contract

## 1. Product boundary
AI Workbench is a local, human-supervised model hand-off and project execution coordinator. It is not an autonomous agent, a security sandbox, or proof that a generated artifact is correct. Models propose text files, configuration, messages, and commands; Workbench parses, validates, previews, requests approval, executes approved operations, records evidence, and returns that evidence to the next prompt.

## 2. Architectural principles
1. **Protocol before UI:** model output is treated as untrusted input and parsed into a typed internal response before any UI action.
2. **One canonical execution pipeline:** manual Run, approved model commands, and file runners share path validation, explicit approval, bounded timeouts, output capture, redaction, event logging, and evidence semantics. Format-specific launchers only construct an argument vector; they do not bypass policy.
3. **Capability manifest is generated from implementation:** prompts must describe supported formats, actions, file runners, guardrails, and limits from code/constants, not from aspirational prose.
4. **No implicit execution:** import and preview never execute commands. Every execution displays the resolved command, working directory, timeout, and risk flags before approval.
5. **Evidence is not inference:** file written, process exited 0, simulator log updated, and task manually verified are distinct states.
6. **Deliverable-neutral:** project workflow follows the task and native artifact format; app/site scaffolding is never mandatory.
7. **Transactional change:** validate all proposed paths and content before apply; backup existing files; record snapshots and history; never silently partially apply a response.
8. **Failures are first-class data:** parsing, validation, apply, launch, timeout, process exit, and domain-tool verification failures carry stage, exact evidence, and next-step hints into repair prompts.
9. **Small modules and explicit contracts:** new features must have a defined service boundary, tests, documentation, and changelog entry. Avoid adding feature-specific branches to the UI when a registry/adapter fits.
10. **Safe defaults:** no shell unless required by a reviewed runner; never execute outside project root implicitly; bounded output/time; reject traversal, sensitive paths, symlinks and unsupported binary writes.


## 2.1 GitHub account and credential boundary (v1.14.2)
- The `aiwb.github` package owns REST API client behavior, account metadata lifecycle, PAT validation/redaction, and OS credential storage. It does not own local Git operations or Tkinter widgets.
- On Windows, API PATs are stored as generic credentials in Windows Credential Manager and referenced from `settings.json` only through an opaque `credential_ref`. No file-based plaintext fallback is allowed.
- Git CLI authentication remains under the configured Git credential helper (for example Git Credential Manager). A REST API PAT must not be injected into `remote.origin.url`, process arguments, logs, or project data.
- The initial `GET /user` call proves identity only. Repository visibility/write permission, Actions access, workflow dispatch, artifact download, and release write remain separate capabilities and must be checked by the relevant endpoint in subsequent versions.
- The production client sends bearer credentials only to `https://api.github.com`; custom endpoints are accepted only with an explicitly injected test transport. API calls use HTTPS, bounded response/time limits, an explicit REST API version, safe error categories, redaction, and no redirect following while credentials are attached.
- Account metadata persistence is a Tk-independent atomic update serialized with ordinary settings writes; API workers must not read or mutate Tk variables.
- Native Windows Credential Manager operations and actual installer execution are release-gated on Windows; mock or Linux/Xvfb tests are not native evidence.


## 2.2 GitHub Repository Browser and binding boundary (v1.14.3)
- `aiwb.github.api_client` owns the paginated `/user/repos` read path, response size/time limits, repository metadata validation, numeric-ID deduplication and categorized API errors. Pagination has a defined upper bound and reports truncation rather than silently claiming completeness.
- UI filtering runs against the loaded repository list, not just the first API page. Reported `permissions.push` is advisory data returned by GitHub; it is not a substitute for checking authorization at the time of a future mutating operation.
- `aiwb.github.repository_binding` is UI-independent. It validates versioned project bindings, maps a project directory to its canonical Git root and Monorepo subpath, and parses supported GitHub HTTPS/SSH remote forms without returning credential-bearing URL components.
- Repository ID, account reference and non-secret metadata are persisted. PAT values and raw remote URLs are never written into binding records. The binding's `html_url` is validated as an HTTPS `github.com` repository URL.
- A missing or mismatched local `origin` requires an explicit UI decision before mutation. The target remote is constructed as credential-free HTTPS. After changing `origin`, the service verifies the resulting repository identity; binding persistence failure attempts compensating remote restoration. Compensation is best-effort, not a filesystem/Git transaction guarantee.
- Linking never stages, commits, pushes, clones or initializes a Git repository. Unlinking removes Workbench binding metadata only and does not mutate local Git remotes or server-side state.
- `project_path`, `local_git_root` and `project_subpath` are stored separately so a Workbench project can be a subdirectory inside a shared Monorepo while Git operations remain rooted at the actual repository.
- Repository listing success establishes only the `repository_read` capability snapshot. Push, Actions, dispatch, artifact access and release capabilities remain unverified until their own API calls exist in later releases.

### v1.14.3 migration and validation gate
Existing projects are not auto-linked, remotes are not rewritten during startup, and old settings are retained. The new binding key is additive. Pagination, URL validation, duplicate-ID handling, monotonic scope constraints, explicit remote decisions, rollback behavior, credential redaction, GUI flow and installer inclusion require regression coverage. Linux/Xvfb tests do not count as native Windows or live GitHub validation.


## 2.3 Binding schema v2 and Monorepo-aware Git actions (v1.14.4)
- Binding records now carry validated `workflow_file`, `artifact_pattern`, `release_channel`, optional `last_known_remote_sha`, and sync/metadata timestamps. Schema-v1 records normalize to v2; the UI backs up the original settings file before persisting a migration. Invalid/duplicate entries are surfaced in a startup notice rather than accepted as valid bindings.
- `project_path`, `local_git_root` and `project_subpath` are checked against the real Git root before mutating Git operations. A stale binding stops Branch/Commit/Push rather than silently switching scope. Multiple project paths may share one repository ID while retaining independent subpaths/preferences.
- Initial Push Review uses `ls-files` for a non-mutating, advisory file inventory. It flags sensitive path shapes, common token/private-key signatures and large files, identifies outside-scope files, and suggests `.gitignore` entries. Suggestion application is explicit and appends only absent lines; scanning is not a secret-detection guarantee.
- Commit obtains status at the canonical Git root, excludes paths outside the active subpath, blocks when the index is already staged, revalidates scope and path sets before staging, uses literal pathspecs, checks staged paths are still in scope, and runs sensitive-path/staged-blob checks before creating a commit. A local Git GUI regression verifies that an active-subproject commit does not include a root/sibling untracked file.
- `.workbench/` is written to the true repository `.git/info/exclude` even when the active project is nested in a Monorepo. This is a convenience, not a mechanism to hide files already tracked; existing tracked metadata remains subject to sensitive-path protection.
- Creating a branch and pushing remain repository-level Git actions because Git branches/commits are shared by the whole Monorepo. Push directly to `main`/`master` remains blocked. This version is not yet the file-by-file Git Review/Sync Plan stage; staged changes created outside Workbench are rejected rather than merged.
- Native Windows install, real Credential Manager and live GitHub auth remain release gates; passing Linux/Xvfb or mocked API tests are not native evidence.

## 3. Logical layers
- **Presentation layer:** Tkinter views, dialogs, and user approvals. It must not implement parsers or launch commands directly.
- **Application services:** prompt construction, project lifecycle, import/preview/apply orchestration, workflow state, repair-prompt generation.
- **Protocol adapters:** workbench JSON, AIWB file/action blocks, best-effort Markdown, and GPT ZIP artifact intake. Each adapter converts untrusted input into the same normalized response model; ZIP import must never extract archive entries directly. The selected transport contract must also persist through repair prompts and continuation handoffs.
- **Domain validation:** path normalization, response schema, project configuration schema, command review flags, output limits and sensitive-path rules.
- **Execution adapters:** Python, Node, PowerShell, Windows batch, executable, LTspice, and approved manual command. Each returns the same `ExecutionResult`-shaped dictionary with command, cwd, status, exit code, timing, timeout, output, error and evidence metadata.
- **Persistence:** project manifest, task state, response snapshots, action queue, execution history, backups and release metadata.
- **Diagnostics:** structured import diagnostics, execution events, continuation handoff and repair prompt.

## 4. Response protocol evolution
The response contract must remain versioned. Any new model-to-Workbench feature (user message, project settings, artifact operation, test request) must use a typed field/block, schema validation, preview, explicit policy, and regression tests. Do not infer executable intent from ordinary prose. Unknown fields must fail closed with a useful diagnostic.

## 5. Project initialization contract
A new project begins with a **design/configuration pass** before implementation. The model recommends target artifact, architecture, file layout, dependencies/toolchain, validation plan, and unresolved choices. Workbench presents the proposed settings for user review; only validated, explicitly approved settings are written to the project manifest. The implementation prompt is generated after the configuration has been accepted. If the user asks to skip design, record that choice.

## 6. Model-to-user messages
Responses may include a bounded plain-text user message separate from file contents and commands. Workbench must display it prominently after analysis, sanitize/control its length, and never interpret it as a command. A message cannot claim an operation ran unless matching execution evidence exists.

## 7. Execution contract
- Import and preview never run a command.
- Every runner resolves the file inside the project and revalidates immediately before launch.
- Use argv with `shell=False` wherever possible. Shell-dependent formats (Windows `.bat/.cmd`) have one isolated, tested quoting adapter.
- Every run records runner type, resolved target, command, working directory, start/end, timeout, exit code, stdout/stderr, logs, and evidence status. The file runner must drain both output streams concurrently and bound memory while the child is active, not just truncate after process exit.
- A process return code alone is not domain verification for LTspice; a fresh non-empty log and simulator diagnostics are required.
- Run results are attached to the next handoff, with bounded output and secret redaction.

## 8. Testing gates for each release
1. Syntax compilation for the supported Python baseline.
2. Unit tests for parsers, path rules, project manifests, runner command construction, execution status and prompt contracts.
3. Regression tests for every user-reported failure.
4. GUI smoke tests for critical user flows.
5. Build/package integrity checks and SHA-256 manifest.
6. Explicitly report platform gaps: Linux/Xvfb tests are not Windows-native installation tests; fake-tool tests are not real LTspice simulation tests.

## 9. Change management
Every release changes `CHANGELOG.md`, this architecture document when contracts/layers change, tests, version metadata and test report. A bug fix must include: reproduction, root cause, invariant, code change, regression test, and residual limitation. Do not ship a one-scenario workaround when the invariant can be fixed in a shared layer.

## 10. Modularization status and migration debt (v1.14.0)
The GUI and most legacy orchestration remain in `AI_Workbench.py` as the stable entry point, but the new cohesive domain services are now an installed `aiwb/` package:

- `architecture_plan.py`: schema validation and project-local architecture-plan round trip.
- `candidate_store.py`: bounded, local candidate persistence and explicit per-file candidate composition.
- `dependency_analysis.py`: conservative static import graph, reverse dependents, and impact hints.
- `semantic_diff.py`: Python AST additions/removals/modified definitions; path-aware JSON changes; keyed CSV row/cell changes; clearly labeled regex heuristics for selected source languages; bounded text-diff fallback.
- `task_playbooks.py`: deterministic task workflow templates.

These modules may depend on the Python standard library, but must not import `AI_Workbench.py`, instantiate Tk widgets, or execute project code. The GUI imports them and owns the interactive flow. `restore_service.py`, `conversation_store.py`, `project_version_store.py`, and `validation_profiles.py` remain separate services with their current contracts.

Do not perform a wholesale extraction of the ~8k-line GUI module as one change. Extract by domain boundary with explicit input/output/error contracts, compatibility adapters, deterministic unit tests, and GUI integration tests. Recommended next order is (1) move response parsing/normalization into a pure protocol package, (2) define a typed operation plan shared by Preview/Apply/Restore, (3) move subprocess runners behind an execution service, (4) centralize settings and project-state migration, and only then (5) split GUI composition into tabs/view-models. Avoid circular imports; service modules must never call GUI methods or display dialogs. The GUI translates service errors into user-facing messages.

Historical deferrals at the v1.9.0 baseline (superseded by later releases where noted):
- The architecture-plan Wizard round-trip was subsequently implemented in v1.14.0 through `aiwb/architecture_plan.py`; plans are validated and explicitly reviewed before persistence.
- A dedicated typed model-to-user message remains separate follow-up work; summary and next-step text are available through existing views.
- Binary asset import was implemented in v1.13.0: permitted ZIP binary entries are retained as exact bytes and previewed by size/hash rather than text diff.

## 11. Installer packaging contract
The Windows self-extracting `.bat` wrapper must not place a multiline Base64 payload inside a `cmd.exe` quoted command or inside a PowerShell `-Command` string. The bootstrap command is a single-line `-EncodedCommand`; the payload is stored after a terminal `exit /b` and enclosed by exact begin/end marker lines. The bootstrap reads the file as data, validates both markers and Base64, extracts to a unique temporary directory, and invokes `install.ps1` as a child process. A packaging test must prove that the embedded bytes exactly match the release ZIP. A Linux string-level test is not a substitute for execution on native Windows.


## 12. GPT ZIP artifact contract (v1.8.0)
- GPT is asked for an actual downloadable ZIP for multi-file projects when the active chat interface supports file artifacts; otherwise its prompt requires the structured JSON fallback. The ZIP is an input transport format, not a second apply pipeline.
- The preferred GPT artifact contract requires project paths directly at the archive root, a human-usable `README.md`, and a root `AIWB_RESPONSE.json` using `workbench-v2` metadata; its actions array may be empty. The importer permits simple ZIPs without the manifest for compatibility. ZIP is a write-only transport; typed Delete/Rename/Move require workbench-v3 JSON. Workbench consumes the control file but never writes it into the project.
- ZIP contents are read without disk extraction. Enforce archive size, entry count, expanded total/per-file size, duplicate canonical paths, reserved/sensitive paths, traversal rejection, and symlink/special-file rejection. UTF-8 text entries and permitted binary entries are retained as their exact bytes; binary review uses size/hash rather than a text diff. The normalized snapshot records archive SHA-256 and safe source metadata.
- ZIP parsing must produce the same `FileChange` records and review window as pasted JSON/Gemini blocks. The control file must not be writable by model output; no operation is applied and no action is executed during archive load or preview.
- A shared delivery-rule helper governs repair prompts and continuation handoffs so they cannot silently switch the task from ZIP to JSON/Gemini. The protocol actually used in planning prompts is recorded as JSON.
- The response schema rejects file/directory collisions such as `settings` and `settings/app.json`, existing parent-file blockers, and Windows-invalid control characters at validation time rather than waiting for apply to fail. ZIP preview keeps a missing/empty root README warning visible even when the model summary reaches its length limit. Selected context files are revalidated against sensitive-path and symlink rules and are read with an enforced byte limit.
- Historical note: binary import was migration debt at the v1.8.0 baseline. Current supported binary ZIP entries are preserved as bytes; do not silently skip a required asset or rename arbitrary text to simulate one.

## 13. Connected prompt conversation and context hand-off (v1.9.0)
- Every app-generated prompt is a durable project-local history entry with task ID, monotonic per-task sequence (`Start`, `Step 1`, …), parent entry, stage, output protocol, Workbench version, editable display-title/classification metadata and notes. The UI renders parent links as nested tree nodes; a metadata filter falls back to task-level placement if it hides a matching child’s parent. The full prompt and response body is separate from the lightweight index so the tree view does not read every large body just to render the list.
- Storage lives only under `.workbench/conversation_history/`. Entry writes use atomic replacement; the index is updated separately; history has an explicit per-project entry cap and body-size bounds. Corrupt/unavailable entry reads are not silently treated as successful writes. History cannot claim a response was saved if its persistence operation raises.
- Prompt/output bodies are treated as an audit record: ordinary metadata edits do not rewrite them. The user can rename/classify/annotate entries, create an edited prompt revision as a new linked step, or explicitly delete an entry. The UI filters by indexed metadata, displays local-history status and copies prompt/output on request. Sensitive project content may exist in these files; nothing in this feature transmits them remotely.
- A context-plan response can request complete visible local text files, exact 1-based line ranges (at most 500 lines per range), and manual external/binary/oversized attachments. Whole files are selected in the project tree. Ranges are read again during prompt building, after path/symlink/sensitive-path/size/encoding and secret checks, then numbered lines are included in the next app-generated prompt. Requests belong to a task; changing task text must not carry old requests into the new task.
- Workbench cannot upload files into ordinary GPT/Gemini chats. Files that cannot be safely embedded are shown in a manual upload checklist. The app must not claim an attachment was sent; the user attaches it in the same model conversation.
- A manual runtime/build/test/simulation/installation report is linked to the selected history entry and task state, recorded in the execution journal, and used to construct a repair prompt whose history entry points to the failed step. It must preserve the actual user-provided error and reproduction context, within documented limits.
- Continuation hand-off includes the bounded recent thread index, active-step detail, and bounded error/context evidence from linked ancestor steps (because a repair prompt itself becomes the active step). It does not paste every historical prompt/output body by default; users can inspect/copy a specific record from Prompt History.
- Regression gates cover sequence and metadata persistence, exact line-range extraction, requested upload reminders, task-change isolation, manual-error association, repair-step linkage, continuation hand-off and the end-to-end GUI path. The app's model hand-off remains manual; history is not a cloud conversation sync.




## 15. Project-history and semantic-version invariants (v1.11.0)
The project-local history is intentionally split into two linked concepts:
- `conversation_store.py` holds the prompt/output/error audit trail. An explicit `project_history_saved` flag marks user-curated checkpoints; it does not duplicate or rewrite prompt/output bodies. Only a successfully validated current response can be marked. Any subsequent response edit invalidates the preview and checkpoint action until re-analysis.
- `project_version_store.py` records a baseline and applied file-tree versions under `.workbench/project_versions/`. Each real tree change after a user-approved file apply records parent version, changed paths, inventory manifest/tree hash, prompt/output hashes, source history ID, and a separate bounded response snapshot if available. An unchanged tree references the existing version instead of inventing a release.
- Semantic version bumps are one-shot (`patch`, `minor`, `major`) and default to patch. Major/minor bumps reset lower components. The setting is consumed only when a new tree hash is recorded, then resets to patch. Version recording is provenance/inventory, not a complete source snapshot, rollback facility, test pass, or replacement for Git.
- The GUI tree is a projection of durable parent IDs and sibling order, not the source of truth. Mutations are atomic and reject cycles. Deleting a node lifts descendants to its parent/root to avoid dangling parent references. A visible filter may temporarily lift entries visually when their parent is filtered out, without changing stored links.
- History context is opt-in: through the user prompt toggle/button or an explicitly stored `workbench-plan-v1` request. The formatter is bounded and metadata-first, and local history is not transmitted merely because it exists.
- Project inventory and version hashing run as progress-backed background work. A queue serializes version recording behind existing workers; a Git status refresh is scheduled after a version is recorded so a simultaneous worker cannot silently drop provenance. File apply is not blocked on test execution, and no version status implies verification.

## 16. Background-process and progress contract
Subprocesses initiated by the GUI must not create transient console windows on Windows when `CREATE_NO_WINDOW` is available. stdout/stderr, exit status, timeouts, and diagnostic logs remain captured. The shared background-worker path owns progress-bar start/stop and callback delivery on Tk's UI thread; long inventory hashing must not run on the Tk event loop. If multiple jobs are needed, queue them instead of silently discarding one. A hidden window is a presentation choice, never a reason to discard failures.

## 14. Model response intake invariants (v1.10.0)

The response parser is a transport boundary, not a best-effort code extractor. The defects addressed in v1.10 had two complementary causes: the format detector expected too narrow a shape of JSON response, while the AIWB block parser inferred the meaning of Markdown fences from their appearance rather than an explicit mode. A second failure mode could consume a following block when an earlier end marker was missing.

- **Protocol precedence:** handle a recognized explicit AIWB block response first, otherwise parse one supported JSON object, otherwise try labeled Markdown code blocks. A real ZIP is selected through the ZIP input path; text claiming that a ZIP was attached does not substitute for archive bytes. If multiple conflicting versioned protocol objects are present, reject rather than choosing one arbitrarily.
- **Explicit body mode:** newly generated AIWB blocks use `body="raw"`. In raw mode, every line from immediately after the header through the line before the matching end marker is content; no Markdown-fence stripping is attempted. This removes the impossible-to-resolve ambiguity between an outer wrapper fence and a file that itself begins with a fence. The old header without `body` continues through the legacy auto-detection path. `body="fenced"` is an explicit compatibility mode.
- **Boundary safety:** `<<<AIWB_END_FILE>>>` and `<<<AIWB_END_COMMAND>>>` must each be on a line by themselves. If another AIWB header occurs before the required end marker, reject the whole response with a targeted error and line number. Never recover by treating the later marker as the earlier block's boundary. The response remains read-only until all blocks validate.
- **No implicit destination guessing:** JSON needs recognized versioned protocol/schema fields and complete paths/content; Markdown fallback needs explicit file/path labels. Prose, diffs without safe destination labels, and attachment claims are not files. Incomplete/invalid JSON errors should not be overwritten by the less useful generic Markdown failure.
- **Review and safety unchanged:** intake normalizes proposed changes but does not write them. All path, size, sensitive-file, collision, action-command, and workspace checks remain enforced. File writes still go through review/diff and explicit approval; proposed commands are queued separately and require their own explicit user approval.
- **Regression requirements:** test a JSON object surrounded by explanation/fences; malformed/truncated JSON; unknown and conflicting protocols; old and new AIWB blocks; raw content beginning/ending with Markdown fences; missing boundaries before another header; files from legacy response samples; a GUI preview that does not write; and a GUI apply path with an intentionally malformed re-import clearing the stale preview.

New format example:

```text
<<<AIWB_FILE path="README.md" action="write" body="raw">>>
# Complete file contents
<<<AIWB_END_FILE>>>

<<<AIWB_COMMAND id="tests" timeout_seconds="120" working_directory="." body="raw">>>
python -m unittest
<<<AIWB_END_COMMAND>>>
```

Do not put a line identical to an AIWB boundary marker inside a file body; use the JSON transport for that case. ZIP input remains the preferred GPT transport for larger multi-file changes where actual downloadable artifacts are available.

## 17. Context-plan wire protocol, migration and diagnostics (v1.12.0)

- `workbench-plan-v2` is the canonical response format for context discovery. The exact schema is generated by `build_context_plan_override_contract()` and appended to base implementation, repair and continuation prompts. It explicitly takes precedence over JSON-file, GPT-ZIP and Gemini-block transport rules when essential source contents are absent.
- `workbench-plan-v1` remains a compatibility input only. `_normalise_context_plan_wire_schema()` maps known aliases (`requests`, `request`, `manual_attachments`, `manual_attachment`, `manual_attechent`) and known request modes to canonical `requested_context_files`, `requested_context_ranges`, and `requested_user_uploads`. Metadata such as `next_steps` and `completion_status` is retained, not used as authority to claim source implementation or verification.
- Migration is deliberately narrow. Unknown top-level or item keys fail closed. Canonical fields must have their declared list/object/string types before aliases are merged. Migrated paths and line ranges flow through the same project-relative path, traversal, symlink, sensitive-file, line-count and size validations as a native v2 plan. A context plan can only request context; it cannot produce file writes or executable actions.
- Diagnostics detect context plans before the implementation-response fallback, report the actual migration/validation error, and show selected-request counts. All diagnostics include a response SHA-256 and parsed top-level JSON keys, allowing copied error text to be compared with the current response without putting raw response content in the execution journal. A rejected plan import is saved as a response attempt against the active prompt where persistence is available; the execution journal receives only structured metadata/error and the response fingerprint.
- Import refreshes the local file inventory, selects only available safe files, records the plan against the source prompt, persists ranges/upload requests/history requests, and only then switches the prompt stage. A valid plan is not a file-apply success.
- The original user report exposed a legitimate two-part workflow: the prompt contained an inventory but no source contents, so the model was correct to request exact source files; Workbench was wrong to reject the valid legacy dialect. The reported error names (`request`, `manual_attechent`) did not exactly match the pasted JSON (`requests`, `manual_attachments`); the prior validator echoed the actual unknown keys, so the discrepancy points to a changed paste or a transcription typo. The new input fingerprint and top-level key list make the active text unambiguous. After plan import, the user reviews selections, builds the follow-up prompt, and manually sends it back to the same model conversation.
- Protocol parsing must treat model-supplied types as untrusted. Protocol identifiers are type-checked before set membership checks; malformed status/action/scope types result in validation errors rather than internal `TypeError` failures. Duplicate wrapper/import errors are deduplicated at the diagnostic boundary.



## 9. Apply transactions and Restore Manager (1.13.0)

`apply_changes_transactionally` remains the write boundary. Selective Apply filters the validated preview list before entering it; the service revalidates canonical paths and exact pre-Apply bytes immediately before mutation. A successful transaction stores `aiwb-apply-transaction.json` beside the pre-Apply backup, with a stable transaction ID, task/history links, before/after SHA-256, sizes and backup locations. Failure to write this manifest causes the write transaction to fail and attempts rollback.

`restore_service.py` is independent of Tkinter. It validates the project root, relative paths, protected metadata paths, symlinks, backup containment, backup hashes and current post-Apply hashes. It has no force-overwrite mode. A restore writes a new transaction manifest and backup so that the restore can itself be undone. The execution journal and project version ledger receive new records; old Apply records are not rewritten.

## 10. Validation profiles and artifacts (1.13.0)

`validation_profiles.py` owns a versioned, bounded schema under `.workbench/validation_profiles.json`. Only user-created/saved profiles can run; model output cannot create trusted profiles. The UI explicitly confirms each run, and command steps use an argv list through the bounded runner. Expected artifacts must exist and be fresh to support a Passed result; a process exit alone remains process evidence, not domain correctness.

ZIP text and binary entries share path/collision checks and the same Apply/backup/Restore pipeline. Binary artifacts are held as exact bytes, show metadata/hash rather than a fabricated text diff, and are never executed. Import still does not extract directly to the project. The `.gitignore` / `.workbenchignore` recommendation adapter is a conservative convenience subset, not a complete Git ignore engine or security boundary.

The redacted diagnostics exporter is local-only and opt-in after preview. Its default payload excludes source, prompts, responses, command text, process output and full user paths; redaction remains best-effort and the UI says so.

## 11. Native Windows release gate

`WINDOWS_RELEASE_CHECKLIST_v1.14.0.md` is a test plan, not a claim of completion. Linux/Xvfb, mock tests, byte-level installer checks and real Windows Explorer double-click installation must be reported separately. A release is not Windows-verified until the target Windows checklist has observed results.

## 16. v1.14.0 capability contracts

- `workbench-v3` JSON expresses each file operation explicitly as `write`, `delete`, `rename`, or `move`. Legacy `workbench-v1` / `workbench-v2` retain write-only semantics. Delete/Rename/Move never overwrite an existing destination; Rename is limited to one directory. Every endpoint is represented in the transaction state ledger, including paths expected to be absent, and Restore checks both pre/post hashes.
- Architecture plans use a separate `workbench-architecture-v1` schema. Import/edit/export/save is a planning workflow only and cannot write proposed source files. The model-facing plan shape is versioned and strict.
- Candidate merging is explicit and destination-scoped; every row defaults to Skip. Only operations selected by the user enter the merged Preview. Candidate `actions` are not propagated. The result re-enters normal response validation and approval.
- Static dependency analysis and semantic diffs are bounded advisory mechanisms. They must describe confidence and coverage gaps, never claim compiler/runtime proof.


## 17. v1.14.1 — Git service boundary

The local Git integration is now separated into `aiwb/git/`:

- `models.py` defines immutable `GitStatusEntry` and `GitStatusSnapshot` value objects. Snapshot fields describe local state only and do not imply remote freshness or permission to mutate a remote.
- `service.py` owns Git executable discovery, the shell-free subprocess boundary, bounded command timeouts, `GIT_TERMINAL_PROMPT=0`, version reporting, porcelain-v1 parsing, status inspection and changed-path collection.
- `GitCommandRunner` accepts injected executable, subprocess, environment, redaction and quiet-process providers so unit tests can exercise exact `argv`, environment and failure behavior without a GitHub account or network access.
- `GitService` exposes typed snapshot APIs and a `to_legacy_dict()` compatibility adapter. The top-level GUI functions (`git_run`, `git_status_info`, `git_changed_paths`, `parse_git_status_porcelain`) remain thin adapters and preserve their established signatures/shapes.
- Project initialization now goes through the same service boundary. The GUI still owns user consent and presentation; the service owns local command mechanics.

No GitHub API authentication or API client was added in this release. The Git credential helper configured in the operating system remains responsible for Git-over-HTTPS authentication; the service never accepts, stores or injects a GitHub PAT. The `aiwb.git` package is installed as a required runtime dependency by the self-extracting installer, including its nested package files.

### Current boundary and remaining migration work

The existing UI still coordinates Branch creation, staging/commit/push and security review. Subsequent releases should progressively move those orchestration policies into application services only after tests protect each behavior. This release intentionally avoids modifying commit selection, direct-push policy, Git credential handling, remote synchronization semantics or existing GUI labels.
