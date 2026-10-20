package io.github.golshandvr.aiworkbench.core

/**
 * Guided loop without dead ends on the phone (port of desktop `aiwb/v2/guide.py`, roadmap 3.5.0 / mobile 1.0.0).
 *
 * [steps] returns at least one step for every reachable state, most urgent first. [perform] runs a step's action
 * through [Project] only — no extra state machine. Nothing is ever sent to a model.
 */
class Guide(val project: Project) {

    data class Action(val id: String, val label: String, val needs: List<String> = emptyList(), var primary: Boolean = false)

    data class Step(val key: String, val kind: String, val title: String, val explain: String, val actions: List<Action>,
                    val agentId: String = USER, val ref: String = "", val prompt: String = "", val rank: Int = 50) {
        val primary: Action? get() = actions.firstOrNull { it.primary }
    }

    data class Outcome(val message: String, val prompt: String = "", val kind: String = "")

    private fun a(id: String, label: String, vararg needs: String) = Action(id, label, needs.toList())

    private fun step(key: String, kind: String, title: String, explain: String, actions: List<Action>, agent: String = USER,
                     ref: String = "", prompt: String = "", rank: Int = 50): Step {
        if (actions.isNotEmpty() && actions.none { it.primary }) actions[0].primary = true
        return Step(key, kind, title, explain, actions, agent, ref, prompt, rank)
    }

    private fun g(st: Obj): Obj = Json.obj(Json.obj(st["settings"])["guide"])

    private fun openHandoff(st: Obj, taskId: String) = State.coll(st, "handoffs").values.map { Json.obj(it) }
        .any { it["task_id"] == taskId && it["status"] in OPEN_H }

    private fun wf(st: Obj, h: Obj) = Json.obj(Json.obj(State.coll(st, "attempts")[h["attempt_id"]])["workflow"])

    private fun owner(st: Obj, t: Obj): String {
        val agents = State.coll(st, "agents")
        val o = Json.str(t["owner_agent_id"])
        if (o.isNotEmpty() && o in agents && Json.obj(agents[o])["enabled"] != false) return o
        return if ("agent-implementer" in agents) "agent-implementer" else agents.keys.firstOrNull() ?: ""
    }

    fun steps(): List<Step> {
        val st = project.state()
        val gd = g(st)
        val out = ArrayList<Step>()
        val tasks = State.coll(st, "tasks")
        (gd["continue"] as? Map<*, *>)?.let { c ->
            out.add(step("continue", "prompt", "The last answer was cut off — ask to continue",
                "The pasted answer ended before it finished. Copy this prompt into the same chat; it asks for the rest only. Then paste the new answer.",
                listOf(a("copy", "Copy continue prompt"), a("paste", "Paste the rest", "text"), a("dismiss", "Ignore the cut-off answer")),
                agent = Json.str(c["agent_id"]).ifEmpty { USER }, prompt = Json.str(c["prompt"]), rank = 0))
        }
        for (p in State.coll(st, "proposals").values.map { Json.obj(it) }.sortedBy { Json.str(it["proposal_id"]) }) {
            if (p["status"] != "pending") continue
            val n = Json.list(p["operations"]).count { Json.obj(it)["valid"] == true }
            out.add(step("proposal:${p["proposal_id"]}", "decision", "Review the plan ${p["proposal_id"]} ($n change${if (n != 1) "s" else ""})",
                Json.str(p["summary"]).ifEmpty { "The project manager proposed changes." } + " Nothing is applied until you accept it." +
                    (if (p["stale"] == true) " It was written for an older state — check it." else ""),
                listOf(a("accept", "Accept all valid changes"), a("reject", "Reject the plan"), a("request_changes", "Ask for changes…", "note")),
                ref = Json.str(p["proposal_id"]), rank = 5))
        }
        for (d in State.coll(st, "decisions").values.map { Json.obj(it) }.sortedBy { Json.str(it["decision_id"]) }) {
            if (d["status"] != "proposed") continue
            val opts = Json.strs(d["options"])
            out.add(step("decision:${d["decision_id"]}", "decision", "Decide: ${d["title"]}",
                Json.str(d["problem"]) + (if (opts.isNotEmpty()) " Options: ${opts.joinToString(", ")}." else "") +
                    (if (Json.str(d["recommendation"]).isNotEmpty()) " Recommended: ${d["recommendation"]}." else ""),
                listOf(a("decide", "Decide…", "choice", "rationale"), a("reject_decision", "Reject…", "rationale")),
                ref = Json.str(d["decision_id"]), rank = 8))
        }
        for (h in State.coll(st, "handoffs").values.map { Json.obj(it) }.sortedBy { Json.str(it["handoff_id"]) }) {
            val t = Json.obj(tasks[h["task_id"]])
            val who = Json.str(h["to_agent_id"]); val hid = Json.str(h["handoff_id"])
            val label = "${h["task_id"]} ${Json.str(t["title"])}".trim()
            when (h["status"]) {
                "reconciled" -> {
                    val missing = Json.strs(h["unresolved_items"])
                    val acts = mutableListOf(a("accept_handoff", "Accept the delivery"), a("reject_handoff", "Reject…", "reason"))
                    if (missing.isNotEmpty()) acts.add(1, a("repair", "Ask only for what is missing"))
                    out.add(step("handoff:$hid", "decision", "Check what $who delivered for $label",
                        Json.str(h["summary"]).ifEmpty { "The answer was read." } + (if (missing.isNotEmpty()) " Missing: ${missing.take(4).joinToString("; ")}." else "") +
                            " Accepting never applies files and never closes the task.", acts, ref = hid, rank = 10))
                }
                "stale", "reconciliation_required" -> out.add(step("handoff:$hid", "decision", "The answer for $label is out of date",
                    Json.strs(h["stale_reasons"]).joinToString("; ").take(300).ifEmpty { "The task changed after the prompt was made." },
                    listOf(a("accept_handoff", "Accept anyway…", "reason"), a("reject_handoff", "Reject…", "reason")), ref = hid, rank = 11))
                "prepared", "prompt_exported", "response_received", "parsed" -> {
                    val w = wf(st, h)
                    val copied = Json.str(w["copied_at"]).isNotEmpty() || h["status"] != "prepared"
                    val sent = Json.str(w["sent_confirmed_at"]).isNotEmpty()
                    val (title, kind, rank) = when {
                        !copied -> Triple("Copy the prompt for $label into $who's chat", "prompt", 22)
                        !sent -> Triple("Send the copied prompt for $label to $who", "prompt", 21)
                        else -> Triple("Paste $who's answer for $label", "paste", 20)
                    }
                    val acts = when {
                        !copied -> mutableListOf(a("copy", "Copy prompt"), a("sent", "I sent it"), a("paste", "Paste the answer", "text"))
                        !sent -> mutableListOf(a("sent", "I sent it"), a("copy", "Copy again"), a("paste", "Paste the answer", "text"))
                        else -> mutableListOf(a("paste", "Paste the answer", "text"), a("copy", "Copy the prompt again"))
                    }
                    acts.add(a("abandon", "Drop this prompt…", "reason"))
                    out.add(step("handoff:$hid", kind, title, "Workbench never sends anything itself. Paste the whole answer when it is ready; " +
                        "a cut-off answer gets a continue prompt.", acts, agent = who, ref = hid, prompt = Json.str(h["prompt"]), rank = rank))
                }
            }
        }
        for (t in tasks.values.map { Json.obj(it) }.sortedBy { Json.str(it["task_id"]) }) {
            val tid = Json.str(t["task_id"]); val s = Json.str(t["status"]); val name = "$tid ${t["title"]}"
            if (openHandoff(st, tid)) continue
            val decisions = State.coll(st, "decisions").values.map { Json.obj(it) }
            when {
                s == "in_review" -> out.add(step("task:$tid", "decision", "Review $name",
                    "Compare the delivery with the acceptance criteria: " + Json.strs(t["acceptance_criteria"]).joinToString("; ").take(300),
                    listOf(a("approve", "Approve"), a("reject_review", "Needs changes…", "note"), a("review_prompt", "Ask a reviewer AI")), ref = tid, rank = 16))
                s == "validation_pending" -> out.add(step("task:$tid", "decision", "Verify $name",
                    "Run the tests or the build (e.g. ./gradlew test in Android Studio or a CI run), then record what really happened. " +
                        "A model's claim does not count. If you cannot run anything here, accept it on review alone — it stays marked NOT RUN.",
                    listOf(a("validation_passed", "Tests/build passed…", "run_id"), a("validation_failed", "Tests/build failed…", "note"),
                        a("waive_validation", "I can't run tests — accept on review…", "reason"),
                        a("record_validation", "Record the result (passed/failed)…", "result", "run_id")), ref = tid, rank = 14))
                s == "ready" || s == "in_progress" -> {
                    val who = owner(st, t)
                    out.add(step("task:$tid", "prompt", "Start $name with $who",
                        "All prerequisites are done. Workbench builds a self-contained prompt for that AI's chat.",
                        listOf(a("prepare", "Prepare the prompt")), agent = who, ref = tid, rank = 40))
                }
                s == "needs_decision" && decisions.none { it["status"] == "proposed" && tid in Json.strs(it["affected_task_ids"]) } ->
                    out.add(step("task:$tid", "decision", "$name waits for a decision", Json.str(t["blocked_reason"]).ifEmpty { "The AI asked for a decision." },
                        listOf(a("decide", "Decide and continue…", "choice", "rationale"), a("manager_prompt", "Ask the project manager")), ref = tid, rank = 9))
                s == "blocked" && !Json.str(t["blocked_reason"]).startsWith("waiting for") ->
                    out.add(step("task:$tid", "decision", "$name is blocked", Json.str(t["blocked_reason"]).ifEmpty { "The task cannot continue as it is." },
                        listOf(a("unblock", "It can continue now"), a("manager_prompt", "Ask the project manager to re-plan"), a("cancel", "Cancel the task…", "reason")),
                        ref = tid, rank = 60))
                s == "draft" || s == "proposed" -> out.add(step("task:$tid", "decision", "Approve $name",
                    "The task is a draft. Approve it so it can start, or cancel it.",
                    listOf(a("make_ready", "Approve the task"), a("cancel", "Cancel…", "reason")), ref = tid, rank = 70))
            }
        }
        val milestones = State.coll(st, "milestones")
        for (m in milestones.values.map { Json.obj(it) }.sortedBy { Json.str(it["milestone_id"]) }) {
            val ids = Json.strs(m["task_ids"])
            if (m["status"] != "planned" || ids.isEmpty()) continue
            if (ids.all { Json.obj(tasks[it])["status"] in State.TERMINAL_TASK })
                out.add(step("milestone:${m["milestone_id"]}", "decision", "Accept milestone ${m["title"]}",
                    "All its tasks are done. Check its criteria: " + Json.strs(m["criteria"]).joinToString("; ").take(300),
                    listOf(a("accept_milestone", "Accept the milestone")), ref = Json.str(m["milestone_id"]), rank = 75))
        }
        for (v in State.coll(st, "versions").values.map { Json.obj(it) }.sortedBy { Json.str(it["version_id"]) }) {
            if (v["status"] in setOf("released", "withdrawn")) continue
            val ms = Json.strs(v["milestone_ids"]).map { Json.obj(milestones[it]) }
            if (ms.isNotEmpty() && ms.all { it["status"] == "accepted" })
                out.add(step("version:${v["version_id"]}", "decision", "Release version ${v["label"]}",
                    "Its milestones are accepted (status now ${v["status"]}). Record the real commit, tag and build run or artifact; Workbench never assumes a release.",
                    listOf(a("release", "Record the release…", "commit_sha", "tag", "run_id"), a("withdraw", "Withdraw the version")),
                    ref = Json.str(v["version_id"]), rank = 78))
        }
        if (tasks.isEmpty() && State.coll(st, "proposals").values.none { Json.obj(it)["status"] == "pending" }) {
            val goal = Json.str(Json.obj(st["settings"])["goal"]).trim()
            if (goal.isEmpty()) out.add(step("design", "form", "Start the project",
                "Give the project a name, its goal (one or two sentences), the platform, any constraints and how many AI chats you " +
                    "can use at the same time. Workbench starts the timeline and builds the 'design the whole project' prompt for your project-manager chat.",
                listOf(a("design", "Start the project…", "goal", *BRIEF_OPTIONAL)), agent = MANAGER, rank = 1))
            else out.add(step("charter", "prompt", "Get the Project Charter from your project-manager chat",
                "Goal: ${goal.take(200)}. Copy the prompt, send it, then paste the whole answer.",
                listOf(a("copy", "Copy the charter prompt"), a("sent", "I sent it"), a("paste", "Paste the charter", "text"), a("design", "Change the project details…", "goal", *BRIEF_OPTIONAL)),
                agent = MANAGER, prompt = Charter.prompt(LinkedHashMap<String, Any?>(Json.obj(Json.obj(st["settings"])["brief"])).also { it["goal"] = goal }, st), rank = 2))
        }
        val actionable = out.filter { it.agentId == USER || it.kind == "prompt" || it.kind == "form" }
        if (actionable.isEmpty()) {
            val due = Json.int(st["state_revision"]) > Json.int(gd["manager_seen_revision"])
            out.add(step("manager_update", "prompt",
                if (due) "Tell the project manager what changed and ask for the next step" else "Ask the project manager for the next step",
                "Nothing else is waiting for you. Copy the update, send it, then paste the manager's plan.",
                listOf(a("copy", "Copy manager update"), a("sent", "I sent it"), a("paste", "Paste the plan", "text")),
                agent = MANAGER, prompt = Prompts.continueProject(Prompts.managerUpdate(st)), rank = 90))
        }
        return out.sortedWith(compareBy({ it.rank }, { it.key }))
    }

    fun next(): Step = steps().first()

    fun find(key: String): Step = steps().firstOrNull { it.key == key } ?: throw ModelError("step $key is no longer open")

    private fun setGuide(seen: Boolean = false, vararg kv: Pair<String, Any?>) {
        project.store.transaction("guide") { s ->
            val settings = Json.obj(s["settings"])
            val gd = Json.obj(settings.getOrPut("guide") { LinkedHashMap<String, Any?>() })
            if (seen) gd["manager_seen_revision"] = (Json.int(s["state_revision"]) + 1).toLong()
            for ((k, v) in kv) if (v == null) gd.remove(k) else gd[k] = v
        }
    }

    fun perform(key: String, action: String, inp: Map<String, String> = emptyMap()): Outcome {
        val st = find(key)
        val act = st.actions.firstOrNull { it.id == action } ?: throw ModelError("'$action' is not possible for this step")
        for (need in act.needs) if (need !in OPTIONAL && inp[need].isNullOrBlank()) throw ModelError("${need.replace('_', ' ')} is required")
        val kind = key.substringBefore(":"); val ref = if (":" in key) key.substringAfter(":") else ""
        val p = project
        fun i(k: String) = inp[k].orEmpty().trim()
        return when (action) {
            "paste" -> paste(st, inp["text"].orEmpty())
            "copy" -> {
                if (kind == "handoff") p.markCopied(ref) else if (kind == "manager_update" || kind == "charter") setGuide(false, "manager_copied_at" to State.nowUtc())
                Outcome("Copied. Paste it into the chat, send it, then tap 'I sent it'.", st.prompt)
            }
            "sent" -> {
                if (kind == "handoff") p.confirmSent(ref) else setGuide(true, "manager_sent_at" to State.nowUtc())
                Outcome("Recorded as sent. Paste the answer when you have it.")
            }
            "dismiss" -> { setGuide(false, "continue" to null); Outcome("The cut-off answer is ignored.") }
            "design" -> {
                Flow.startProject(p.store, (listOf("goal") + BRIEF_OPTIONAL).associateWith { i(it) })
                Outcome("Project started. Project Charter prompt ready to copy.", p.charterPrompt(i("goal")))
            }
            "accept" -> Outcome("Plan $ref ${p.acceptAllValid(ref)["status"]}.")
            "reject" -> { p.reviewProposal(ref, emptyList()); Outcome("Plan $ref rejected. Nothing changed.") }
            "request_changes" -> {
                val prompt = Prompts.proposalRevision(p.state(), ref, i("note"))
                p.reviewProposal(ref, emptyList())
                Outcome("Change request ready to copy to the project manager.", prompt)
            }
            "decide", "reject_decision" -> {
                val why = i("rationale").ifEmpty { "decided in the guided loop" }
                if (kind == "task") {
                    val t = State.require(p.state(), "tasks", ref)
                    val reason = Json.str(t["blocked_reason"])
                    val did = p.proposeDecision(reason.ifEmpty { "Decision" }.take(200), reason, listOf(ref))
                    p.resolveDecision(did, true, i("choice"), why)
                    Outcome("Decision recorded ($did); $ref can continue.")
                } else { p.resolveDecision(ref, action == "decide", i("choice"), why); Outcome("Decision $ref recorded.") }
            }
            "accept_handoff" -> { p.resolveHandoff(ref, true, i("reason").ifEmpty { "accepted in the guided loop" }); Outcome("Delivery $ref accepted. Next: review the task.") }
            "reject_handoff" -> { p.resolveHandoff(ref, false, i("reason")); Outcome("Delivery $ref rejected. A new prompt can be prepared.") }
            "repair" -> {
                val h = State.require(p.state(), "handoffs", ref)
                val tid = Json.str(h["task_id"])
                p.resolveHandoff(ref, true, "partial delivery accepted; repair requested for the missing items")
                if (State.require(p.state(), "tasks", tid)["status"] == "in_review") p.transition(tid, "in_progress", "repair requested")
                val nh = p.startTask(tid, Json.str(h["to_agent_id"]))
                val nid = Json.str(nh["handoff_id"])
                val prompt = p.store.transaction("repair prompt") { s ->
                    val n = State.require(s, "handoffs", nid)
                    Prompts.repair(s, h, n).also { n["prompt"] = it; n["repair_of"] = ref }
                }
                Outcome("Repair prompt for $tid ready (only the missing items).", prompt)
            }
            "abandon" -> { p.resolveHandoff(ref, false, i("reason").ifEmpty { "dropped by the user" }); Outcome("Prompt $ref dropped.") }
            "prepare" -> { val h = p.startTask(ref, st.agentId); Outcome("Prompt for $ref ready. Copy it into ${h["to_agent_id"]}'s chat.", Json.str(h["prompt"])) }
            "approve" -> Outcome("$ref review approved → ${p.reviewTask(ref, true, i("note")).first}.")
            "reject_review" -> Outcome("$ref needs changes → ${p.reviewTask(ref, false, i("note")).first}.")
            "review_prompt" -> Outcome("Review prompt ready for a reviewer AI (its answer is advice; you decide).", Prompts.review(p.state(), ref))
            "record_validation" -> {
                val r = when (i("result").lowercase()) {
                    "passed", "pass", "ok", "yes", "green", "success", "y" -> "passed"
                    "failed", "fail", "no", "red", "failure", "n" -> "failed"
                    else -> throw ModelError("result must be 'passed' or 'failed' (or use the 'passed' / 'failed' buttons)")
                }
                Outcome("Validation $r recorded → $ref ${p.recordValidation(ref, r == "passed", i("run_id")).first}.")
            }
            "validation_passed", "validation_failed" -> {
                val ok = action == "validation_passed"
                val run = i("run_id").ifEmpty { i("note").take(100) }
                Outcome("Validation ${if (ok) "passed" else "failed"} recorded → $ref ${p.recordValidation(ref, ok, run).first}.")
            }
            "waive_validation" -> Outcome("$ref accepted on review without tests (NOT RUN) → ${p.waiveValidation(ref, i("reason")).first}.")
            "make_ready" -> { p.transition(ref, "ready", "approved in the guided loop"); Outcome("$ref approved.") }
            "unblock" -> { p.transition(ref, "ready", "unblocked by the user"); Outcome("$ref can continue.") }
            "cancel" -> { p.transition(ref, "cancelled", i("reason").ifEmpty { "cancelled by the user" }); Outcome("$ref cancelled.") }
            "manager_prompt" -> Outcome("Manager update ready to copy.", p.managerUpdate())
            "accept_milestone" -> { p.acceptMilestone(ref); Outcome("Milestone $ref accepted.") }
            "release" -> {
                var v = State.require(p.state(), "versions", ref)
                if (v["status"] == "proposed") v = p.advanceVersion(ref, "local", commitSha = i("commit_sha"))
                if (v["status"] == "local") p.advanceVersion(ref, "tagged", tag = i("tag").ifEmpty { "v" + Json.str(v["label"]) })
                p.advanceVersion(ref, "released", runId = i("run_id"))
                Outcome("Version ${v["label"]} released.")
            }
            "withdraw" -> { p.advanceVersion(ref, "withdrawn"); Outcome("Version $ref withdrawn.") }
            else -> throw ModelError("unknown action '$action'")
        }
    }

    private fun paste(st: Step, text: String): Outcome {
        if (text.isBlank()) throw ModelError("the answer is empty")
        val rep = Normalize.truncationReport(text)
        val r = project.routeAnswer(text)
        if (r.kind in setOf("proposal", "handoff", "charter_rejected")) {
            setGuide(st.key == "manager_update" || st.key == "charter", "continue" to null)
            var msg = r.message
            if (r.kind == "handoff" && rep.truncated) msg += " The answer looks cut off — use 'Ask only for what is missing'."
            return Outcome(msg, r.prompt, r.kind)
        }
        if (rep.truncated) {
            val att = if (st.key.startsWith("handoff:")) Json.str(Json.obj(State.coll(project.state(), "handoffs")[st.ref])["attempt_id"]) else ""
            val prompt = Normalize.continuePrompt(rep, att)
            setGuide(false, "continue" to linkedMapOf<String, Any?>("prompt" to prompt, "agent_id" to st.agentId, "for" to st.key, "at" to State.nowUtc()))
            return Outcome("The answer was cut off. A continue prompt is ready.", prompt, "truncated")
        }
        return Outcome(r.message, r.prompt, r.kind)
    }

    companion object {
        const val USER = "you"
        const val MANAGER = "agent-project-manager"
        private val OPEN_H = setOf("prepared", "prompt_exported", "response_received", "parsed", "reconciled", "stale", "reconciliation_required")
        /** Optional inputs of the start form (roadmap 4.0.0, flowchart F4). */
        val BRIEF_OPTIONAL = arrayOf("name", "platform", "constraints", "ais")
        private val OPTIONAL = setOf("note", "reason", "rationale", "run_id", "commit_sha", "tag") + BRIEF_OPTIONAL
        /** What each input asks for (the UI shows these as field hints). */
        val INPUT_HINTS = mapOf("goal" to "What should this project achieve? (one or two sentences)", "note" to "Note (optional)",
            "name" to "Project name (optional)", "platform" to "Platform / technology (optional)", "constraints" to "Constraints (optional)",
            "ais" to "How many AI chats can you use at the same time? (1-12, optional)",
            "reason" to "Reason (optional)", "rationale" to "Why? (optional, kept in the decision log)", "choice" to "Your decision",
            "result" to "passed or failed", "run_id" to "Run ID, build number or commit (optional)",
            "commit_sha" to "Commit SHA (optional)", "tag" to "Tag (optional, default v<version>)", "text" to "Paste the whole answer here")
    }
}
