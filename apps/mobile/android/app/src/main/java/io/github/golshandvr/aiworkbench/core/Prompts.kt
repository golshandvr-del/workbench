package io.github.golshandvr.aiworkbench.core

/**
 * The ready-to-copy prompts of the standalone phone app (same text as desktop `aiwb/v2/handoff.build_prompt`,
 * `guide.repair_prompt` / `review_prompt` / `continue_project_prompt` and `proposals.manager_update_prompt`).
 * Pure functions of the state document.
 */
object Prompts {
    /**
     * How files must be delivered (mobile 1.0.1 / desktop 3.9.1). Chat apps render text outside code blocks as Markdown:
     * indentation and backticks are lost when the answer is copied. A four-backtick fence keeps the body verbatim
     * (inner ``` blocks stay intact) and the header has no body attribute, so a copy without fences still parses.
     */
    val FILE_RULES = listOf(
        "- Files: one AIWB file block per file, complete files only. Wrap every file body in a fence of FOUR backticks (````)" +
            " so the chat app keeps indentation and backticks when the answer is copied:",
        "<<<AIWB_FILE path=\"relative/path.ext\" action=\"write\">>>", "````", "(the complete file)", "````", "<<<AIWB_END_FILE>>>")

    private fun section(title: String, lines: List<String>): List<String> = listOf("", "## $title") + lines.ifEmpty { listOf("- (none)") }

    /** Python `json.dumps(v, ensure_ascii=False, indent=1)` (insertion order). */
    fun dumpsIndent1(v: Any?): String {
        val sb = StringBuilder()
        fun w(x: Any?, ind: Int) {
            when (x) {
                is Map<*, *> -> {
                    if (x.isEmpty()) { sb.append("{}"); return }
                    sb.append("{\n")
                    val ks = x.keys.toList()
                    ks.forEachIndexed { i, k ->
                        sb.append(" ".repeat(ind + 1)); StrictJson.quote(sb, k.toString()); sb.append(": "); w(x[k], ind + 1)
                        if (i < ks.size - 1) sb.append(","); sb.append("\n")
                    }
                    sb.append(" ".repeat(ind)).append("}")
                }
                is List<*> -> {
                    if (x.isEmpty()) { sb.append("[]"); return }
                    sb.append("[\n")
                    x.forEachIndexed { i, y -> sb.append(" ".repeat(ind + 1)); w(y, ind + 1); if (i < x.size - 1) sb.append(","); sb.append("\n") }
                    sb.append(" ".repeat(ind)).append("]")
                }
                else -> sb.append(StrictJson.stringify(x))
            }
        }
        w(v, 0)
        return sb.toString()
    }

    /** Python `json.dumps(v, ensure_ascii=False)` (", " / ": " separators). */
    fun dumpsSpaced(v: Any?): String = when (v) {
        is Map<*, *> -> v.entries.joinToString(", ", "{", "}") { StringBuilder().also { sb -> StrictJson.quote(sb, it.key.toString()) }.toString() + ": " + dumpsSpaced(it.value) }
        is List<*> -> v.joinToString(", ", "[", "]") { dumpsSpaced(it) }
        else -> StrictJson.stringify(v)
    }

    /** Self-contained handoff prompt: works in a fresh chat with no history. */
    fun handoff(s: Obj, h: Obj, previous: Obj?): String {
        val tasks = State.coll(s, "tasks")
        val t = Json.obj(tasks[h["task_id"]])
        val agent = Json.obj(State.coll(s, "agents")[h["to_agent_id"]])
        val taskId = Json.str(h["task_id"])
        val decisions = State.coll(s, "decisions").values.map { Json.obj(it) }
        val accepted = decisions.filter { it["status"] == "accepted" && (Json.strs(it["affected_task_ids"]).isEmpty() || taskId in Json.strs(it["affected_task_ids"])) }
        val rejected = decisions.filter { it["status"] == "rejected" && taskId in Json.strs(it["affected_task_ids"]) }
        val depLines = ArrayList<String>()
        for (d in Json.strs(t["depends_on"]).mapNotNull { tasks[it] as? Map<*, *> }) {
            val last = State.coll(s, "handoffs").values.map { Json.obj(it) }
                .filter { it["task_id"] == d["task_id"] && it["status"] == "accepted" }.sortedBy { Json.str(it["handoff_id"]) }.lastOrNull()
            val sum = Json.str(last?.get("summary"))
            depLines.add("- ${d["task_id"]} ${d["title"]} — status ${d["status"]}" + (if (sum.isNotEmpty()) "; delivered: ${sum.take(400)}" else ""))
            for (a in Json.list(last?.get("artifact_refs")).take(20).map { Json.obj(it) })
                depLines.add("  - artifact ${a["logical_path"]} sha256 ${Json.str(a["sha256"]).take(16)}…")
        }
        val scope = Json.obj(t["scope"])
        val lines = mutableListOf("AIWB_ATTEMPT_ID: ${h["attempt_id"]}", "(Repeat the line above as the first line of your answer.)", "",
            "# AI Workbench handoff ${h["handoff_id"]} — you are ${agent["name"]} (${agent["agent_id"]}, role ${agent["role"]})",
            "You have NO access to earlier chats. Everything you may rely on is below. Do not assume anything else.")
        lines += section("1. Your role", listOf("- Purpose: ${Json.str(agent["purpose"])}") + Json.strs(agent["instructions"]).map { "- $it" })
        lines += section("2. Mission", listOf("- Task ${t["task_id"]} revision ${t["task_revision"]}: ${t["title"]}", "- Objective: ${t["objective"]}",
            "- Project state revision ${h["base_state_revision"]}" + (if (Json.str(h["base_commit_sha"]).isNotEmpty()) ", base commit ${h["base_commit_sha"]}" else "")))
        lines += section("3. Acceptance criteria and limits", Json.strs(t["acceptance_criteria"]).map { "- [ ] $it" } + listOf(
            "- Scope include: ${Json.strs(scope["include"]).joinToString(", ").ifEmpty { "(not restricted)" }}",
            "- Scope exclude: ${Json.strs(scope["exclude"]).joinToString(", ").ifEmpty { "(none)" }}",
            "- Deliverables: ${Json.strs(t["deliverables"]).joinToString(", ").ifEmpty { "(see objective)" }}"))
        lines += section("4. Accepted decisions (binding)", accepted.map { "- ${it["decision_id"]} ${it["title"]}: ${it["decision"]}" } +
            rejected.map { "- REJECTED ${it["decision_id"]} ${it["title"]}: ${it["rationale"]} — do not propose it again" })
        lines += section("5. Prerequisites and their outputs", depLines)
        if (previous != null) {
            lines += section("6. Previous handoff ${previous["handoff_id"]} (${Json.str(previous["outcome"]).ifEmpty { "n/a" }})",
                listOf("- Summary: ${Json.str(previous["summary"]).ifEmpty { "(none)" }}") +
                    Json.strs(previous["completed_items"]).map { "- Done: $it" } + Json.strs(previous["unresolved_items"]).map { "- Open: $it" } +
                    Json.strs(previous["assumptions"]).map { "- Assumption: $it" } + Json.strs(previous["validation_claims"]).map { "- Claimed (NOT verified): $it" })
        } else lines += section("6. Previous handoff", listOf("- This is the first handoff for this task."))
        lines += section("7. Relevant files", Json.strs(t["context_refs"]).map { "- $it" } +
            "- If you need a file that is not here, answer ONLY with an AIWB_CONTEXT_REQUEST.")
        lines += section("8. Conflicts / do not assume", Json.strs(t["flags"]) +
            "- Do not claim that you ran tests or builds; Workbench records real evidence separately.")
        if (Json.str(h["note"]).isNotEmpty()) lines += section("Note from the user", listOf(Json.str(h["note"])))
        val manifest = linkedMapOf<String, Any?>("schema_version" to "1.0", "handoff_id" to h["handoff_id"], "task_id" to h["task_id"],
            "task_revision" to h["task_revision"], "attempt_id" to h["attempt_id"], "outcome" to "complete|partial|blocked|needs_decision|failed",
            "summary" to "…", "completed_items" to listOf("done and delivered"), "unresolved_items" to listOf("not done"),
            "assumptions" to listOf("what you assumed"), "decision_requests" to listOf("what the user must decide"),
            "validation_claims" to listOf("what you believe works (unverified)"), "recommended_next_action" to "…")
        lines += section("9. Expected delivery", FILE_RULES + listOf(
            "- Then exactly one manifest block:", "<<<AIWB_HANDOFF>>>", dumpsIndent1(manifest), "<<<AIWB_END_HANDOFF>>>",
            "- Keep separate: done, proposed, not run, needs decision."))
        return lines.joinToString("\n")
    }

    /** Ask the same AI only for what delivery [h] is missing; [n] is the fresh handoff the answer must name. */
    fun repair(state: Obj, h: Obj, n: Obj = h): String {
        val t = Json.obj(State.coll(state, "tasks")[h["task_id"]])
        val done = Json.list(h["artifact_refs"]).map { Json.str(Json.obj(it)["logical_path"]) }.ifEmpty { Json.strs(h["completed_items"]) }
        val missing = Json.strs(h["unresolved_items"])
        val lines = mutableListOf("AIWB_ATTEMPT_ID: ${n["attempt_id"]}", "(Repeat the line above as the first line of your answer.)", "",
            "# AI Workbench — repair request for ${h["handoff_id"]} (${t["task_id"]} ${t["title"]})",
            "Your previous delivery was incomplete. Send ONLY what is missing; do not resend what already arrived.")
        if (done.isNotEmpty()) lines += listOf("", "## Arrived complete (do NOT resend)") + done.map { "- $it" }
        lines += listOf("", "## Still missing") + missing.map { "- $it" }.ifEmpty { listOf("- (see the acceptance criteria below)") }
        lines += listOf("", "## Acceptance criteria") + Json.strs(t["acceptance_criteria"]).map { "- [ ] $it" }.ifEmpty { listOf("- (none)") }
        lines += listOf("", "## Format") + FILE_RULES + listOf("- Then one manifest:", "<<<AIWB_HANDOFF>>>",
            dumpsSpaced(linkedMapOf("schema_version" to "1.0", "handoff_id" to n["handoff_id"], "task_id" to n["task_id"],
                "task_revision" to n["task_revision"], "attempt_id" to n["attempt_id"], "outcome" to "complete|partial", "summary" to "…",
                "completed_items" to listOf("…"), "unresolved_items" to emptyList<Any?>(), "validation_claims" to emptyList<Any?>())),
            "<<<AIWB_END_HANDOFF>>>")
        return lines.joinToString("\n")
    }

    fun review(state: Obj, taskId: String): String {
        val t = State.require(state, "tasks", taskId)
        val last = State.coll(state, "handoffs").values.map { Json.obj(it) }.filter { it["task_id"] == taskId && it["status"] == "accepted" }
            .sortedBy { Json.str(it["handoff_id"]) }.lastOrNull() ?: linkedMapOf()
        val lines = mutableListOf("# AI Workbench — review request for $taskId ${t["title"]}",
            "You have NO access to earlier chats or to the project files. Review only what is below.", "",
            "## Objective\n${t["objective"]}", "", "## Acceptance criteria")
        lines += Json.strs(t["acceptance_criteria"]).map { "- [ ] $it" }.ifEmpty { listOf("- (none)") }
        lines += listOf("", "## Delivery summary", Json.str(last["summary"]).ifEmpty { "(no summary)" })
        lines += Json.strs(last["completed_items"]).map { "- Done: $it" }
        lines += Json.strs(last["unresolved_items"]).map { "- Open: $it" }
        lines += Json.strs(last["validation_claims"]).map { "- Claimed (NOT verified): $it" }
        lines += Json.list(last["artifact_refs"]).take(40).map { "- File: ${Json.obj(it)["logical_path"]}" }
        lines += listOf("", "## Answer", "For every criterion answer PASS, FAIL or UNKNOWN with one sentence. Then one line " +
            "`VERDICT: APPROVE` or `VERDICT: CHANGES` and the exact changes needed. Never claim you ran anything.")
        return lines.joinToString("\n")
    }

    const val MANAGER_FORMAT = """Return your analysis in plain text, then exactly ONE block:
<<<AIWB_MANAGER_PROPOSAL>>>
{"schema_version": "1.0", "proposal_type": "project_plan_update", "base_state_revision": <the state_revision above>,
 "summary": "…",
 "operations": [
  {"operation": "create_task", "temporary_ref": "new-1", "title": "…", "objective": "…", "owner_role": "implementer",
   "depends_on_refs": ["TASK-0001" or "new-2"], "acceptance_criteria": ["…"], "scope": {"include": ["path/**"], "exclude": []},
   "priority": "medium"},
  {"operation": "add_dependency", "task_id": "TASK-0003", "depends_on_task_id": "TASK-0002", "reason": "…"},
  {"operation": "update_task", "task_id": "TASK-0002", "changes": {"acceptance_criteria": ["…"]}, "reason": "…"},
  {"operation": "assign_agent", "task_id": "TASK-0002", "agent_id": "agent-implementer"},
  {"operation": "propose_decision", "title": "…", "problem": "…", "options": ["…"], "recommendation": "…", "affected_task_ids": ["TASK-0002"]},
  {"operation": "reorder_priority", "task_id": "…", "priority": "high"},
  {"operation": "close_or_cancel_task", "task_id": "…", "reason": "…"},
  {"operation": "request_more_evidence", "task_id": "…", "reason": "…"},
  {"operation": "report_risk", "description": "…"}],
 "risks": ["…"], "questions_for_user": ["…"]}
<<<AIWB_END_MANAGER_PROPOSAL>>>
Rules: never mark tasks done; Workbench assigns all IDs (use temporary_ref for new tasks); only existing TASK-/agent- IDs may be referenced."""

    private val ACTIVE = setOf("ready", "in_progress", "in_review", "validation_pending")

    /** Short local status (desktop `render_status_md` subset used as the manager-update fallback). */
    fun statusMarkdown(st: Obj): String {
        val tasks = State.coll(st, "tasks").values.map { Json.obj(it) }.sortedBy { Json.str(it["task_id"]) }
        fun by(vararg s: String) = tasks.filter { it["status"] in s }
        val goal = Json.str(Json.obj(st["settings"])["goal"])
        val lines = mutableListOf("# Project status — ${st["project_id"]}", "",
            "> Generated by AI Workbench (phone) from local state; not written by a model.", "",
            "- **State revision:** ${Json.int(st["state_revision"])}")
        if (goal.isNotEmpty()) lines += "- **Goal:** $goal"
        lines += listOf("", "## Summary", "",
            "| Active | Blocked | Needs decision | In review | Validation pending | Done (verified) | Total |", "|---|---|---|---|---|---|---|",
            "| ${by(*ACTIVE.toTypedArray()).size} | ${by("blocked").size} | ${by("needs_decision").size} | ${by("in_review").size} | " +
                "${by("validation_pending").size} | ${by("done").size} | ${tasks.size} |")
        for ((head, list) in listOf("Active tasks" to by(*ACTIVE.toTypedArray()), "Blocked" to by("blocked"),
            "Needs decision" to by("needs_decision"), "Done with evidence" to by("done"))) {
            lines += listOf("", "## $head", "") + list.map {
                "- ${it["task_id"]} — ${it["title"]} (${it["status"]})" + (if (it["status"] == "blocked" && Json.str(it["blocked_reason"]).isNotEmpty()) ": ${it["blocked_reason"]}" else "")
            }.ifEmpty { listOf("- none") }
        }
        val decisions = State.coll(st, "decisions").values.map { Json.obj(it) }.sortedBy { Json.str(it["decision_id"]) }
        lines += listOf("", "## Open decisions", "") + decisions.filter { it["status"] == "proposed" }.map { "- ${it["decision_id"]} — ${it["title"]}" }.ifEmpty { listOf("- none") }
        lines += listOf("", "## Accepted decisions", "") + decisions.filter { it["status"] == "accepted" }
            .map { "- ${it["decision_id"]} — ${it["title"]}: ${Json.str(it["decision"]).take(500)}" }.ifEmpty { listOf("- none") }
        return lines.joinToString("\n") + "\n"
    }

    fun managerUpdate(st: Obj): String {
        val rev = Json.int(st["state_revision"])
        val md = statusMarkdown(st).let { if (it.length <= 6000) it else it.take(6000) + "\n…(truncated)\n" }
        val lines = mutableListOf("# AI Workbench — Manager update", "State revision: $rev (generated ${State.nowUtc()})",
            "", "## Published state", "- Not published. Use ONLY the summary below; do not claim you read GitHub.",
            "", "## Local summary (authoritative fallback)", md,
            "", "## Rules", "- Separate: read from the snapshot / reported by agents / your inference / unknown.",
            "- Model claims are NOT evidence; only Workbench evidence counts. Never declare a task done.",
            "- Use base_state_revision $rev.", "", MANAGER_FORMAT)
        return lines.joinToString("\n")
    }

    fun continueProject(update: String): String = update + "\n\n## What I need now\nEvery planned task is finished or waiting. Propose the next step: new " +
        "tasks for the next milestone, fixes for blocked work, or say that the project is complete. Answer with one AIWB_MANAGER_PROPOSAL block."

    fun proposalRevision(state: Obj, proposalId: String, note: String): String {
        val p = State.require(state, "proposals", proposalId)
        return listOf("# AI Workbench — please revise your plan $proposalId",
            "The user did not accept the plan as it is. Nothing was applied.", "",
            "## The user's request", note.ifBlank { "(no note — improve the plan and keep it small)" }, "",
            "## Your previous summary", Json.str(p["summary"]).ifEmpty { "(none)" }, "",
            "Return a COMPLETE corrected plan based on state revision ${Json.int(state["state_revision"])}.", "", MANAGER_FORMAT).joinToString("\n")
    }
}
