package io.github.golshandvr.aiworkbench.core

import java.security.MessageDigest
import java.security.SecureRandom
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/**
 * One standalone project on the phone (roadmap mobile 1.0.0): the same services the desktop uses
 * (`aiwb/v2` proposals, tasks, attempts, handoffs, evidence, timeline), written against the same state document so a
 * bundle moves between the two apps without conversion. Nothing is ever sent to a model: the user copies prompts and
 * pastes answers; every state change is an explicit user action.
 */
class Project(val store: ProjectStore) {

    data class Routed(val kind: String, val message: String, val ref: String = "", val prompt: String = "")

    fun state(): Obj = store.load()

    // ------------------------------------------------------------------ agents

    fun installTemplates(): List<String> {
        val added = ArrayList<String>()
        store.transaction("install agent templates") { s ->
            val agents = State.coll(s, "agents")
            for ((id, tpl) in TEMPLATES) {
                if (id in agents) continue
                agents[id] = agent(linkedMapOf<String, Any?>("agent_id" to id).also { it.putAll(StrictJson.copy(tpl) as Obj) }
                    .also { it["template_id"] = "$id@1" })
                added.add(id)
            }
            if (added.isNotEmpty()) State.emit(s, "agents_installed", "agent_ids" to ArrayList<Any?>(added))
        }
        return added
    }

    fun setGoal(goal: String) {
        store.transaction("project goal") { s ->
            val settings = Json.obj(s["settings"])
            if (settings["goal"] != goal.trim()) {
                settings["goal"] = goal.trim().take(2000)
                State.emit(s, "project_settings_updated", "field" to "goal")
            }
        }
    }

    // ----------------------------------------------------------- charter + plans

    fun charterPrompt(goal: String): String = Charter.prompt(mapOf("goal" to goal), state())

    fun charter(): Obj? = Json.obj(state()["settings"])["charter"] as? Obj

    fun charterStartPrompt(agentId: String): String {
        val ch = charter() ?: throw ModelError("no accepted Project Charter yet")
        val st = state()
        val ids = Json.obj(ch["task_ids"])
        val lines = State.coll(st, "tasks").values.map { Json.obj(it) }
            .filter { it["owner_agent_id"] == agentId && Json.str(it["task_id"]) in ids.values }
            .map { "${it["task_id"]} ${it["title"]} (${it["status"]})" }
        return Charter.startPrompt(ch, agentId, lines)
    }

    /** `{proposal|null, errors, warnings, fixes, fixPrompt}` as a [Routed]. */
    fun importCharter(text: String, responseId: String = ""): Routed {
        val st = state()
        val r = Charter.parse(text, st)
        if (!r.ok || r.data == null) {
            return Routed("charter_rejected", "The Project Charter is incomplete and was not imported: " +
                r.errors.take(3).joinToString("; ") + (if (r.errors.size > 3) " …" else "") + " A fix prompt is ready to copy.",
                prompt = Charter.fixPrompt(r))
        }
        val proposal = Charter.toProposal(r.data, st)
        val pid = importProposalData(proposal, responseId, "charter", Charter.record(r.data))
        val n = Json.list(proposal["operations"]).size
        var msg = "Project Charter imported as $pid with $n change(s) (agents, tasks, milestones and versions) — review and accept them."
        if (r.warnings.isNotEmpty()) msg += " ${r.warnings.size} warning(s) to check."
        return Routed("proposal", msg, pid)
    }

    fun importProposalData(data: Obj, responseId: String = "", kind: String = "update", charter: Obj? = null): String {
        val ops = data["operations"] as? List<*>
        if (ops == null || ops.isEmpty()) throw ModelError("the proposal has no operations")
        if (ops.size > MAX_OPS) throw ModelError("too many operations (${ops.size} > $MAX_OPS); ask the manager to split the proposal")
        val base = (data["base_state_revision"] as? Number)?.toInt()
            ?: throw ModelError("base_state_revision (integer) is required so Workbench can detect stale proposals")
        val st = state()
        val tasks = State.coll(st, "tasks")
        val normalized = ArrayList<Any?>()
        val problems = ArrayList<Any?>()
        val refs = HashSet<String>()
        ops.forEachIndexed { i, raw ->
            val op = raw as? Map<*, *>
            if (op == null || op["operation"] !in OPERATIONS) {
                problems.add("operation ${i + 1}: unknown or missing 'operation'")
                normalized.add(linkedMapOf("index" to i.toLong(), "operation" to Json.str(op?.get("operation")).ifEmpty { "?" }.take(40),
                    "raw" to (StrictJson.copy(op) ?: linkedMapOf<String, Any?>()), "valid" to false, "problem" to "unknown operation",
                    "decision" to "rejected"))
                return@forEachIndexed
            }
            val e: Obj = linkedMapOf("index" to i.toLong(), "operation" to op["operation"], "raw" to StrictJson.copy(op),
                "valid" to true, "problem" to "", "decision" to "pending", "reason" to Json.str(op["reason"]).take(1000))
            if (op["operation"] in setOf("create_task", "split_task")) {
                val ref = Json.str(op["temporary_ref"]).ifEmpty { "new-${i + 1}" }
                if (ref in refs) { e["valid"] = false; e["problem"] = "duplicate temporary_ref $ref" }
                refs.add(ref); e["temporary_ref"] = ref
            }
            for (r in opTaskRefs(op)) if (r !in tasks) { e["valid"] = false; e["problem"] = "unknown task $r" }
            if (op["operation"] == "create_agent" && !State.validAgentId(op["agent_id"])) {
                e["valid"] = false; e["problem"] = "agent_id must look like 'agent-implementer'"
            }
            normalized.add(e)
        }
        val changed = normalized.flatMap { opTaskRefs(Json.obj(Json.obj(it)["raw"])) }.filter { changedSince(st, it, base) }.distinct().sorted()
        val stale = base < Json.int(st["state_revision"]) && changed.isNotEmpty()
        return store.transaction("import manager proposal") { s ->
            val pid = State.nextId(s, "proposal")
            val now = State.nowUtc()
            State.coll(s, "proposals")[pid] = linkedMapOf("schema_version" to State.SCHEMA_VERSION, "proposal_id" to pid,
                "kind" to kind, "proposal_type" to Json.str(data["proposal_type"]).ifEmpty { "project_plan_update" }.take(60),
                "base_state_revision" to base.toLong(), "imported_at_revision" to Json.int(s["state_revision"]).toLong(),
                "summary" to Json.str(data["summary"]).take(4000), "risks" to ArrayList<Any?>(Json.strs(data["risks"]).take(30)),
                "questions_for_user" to ArrayList<Any?>(Json.strs(data["questions_for_user"]).take(30)),
                "operations" to normalized, "problems" to problems, "stale" to stale, "stale_task_ids" to ArrayList<Any?>(changed),
                "status" to "pending", "source_response_id" to responseId,
                "assumptions" to ArrayList<Any?>(Json.strs(data["assumptions"]).take(30)),
                "team" to (StrictJson.copy(data["team"]) ?: linkedMapOf<String, Any?>()), "team_issues" to ArrayList<Any?>(),
                "team_counts" to linkedMapOf<String, Any?>(), "is_team" to (data["team"] is Map<*, *>),
                "charter" to charter, "created_at" to now, "updated_at" to now, "result" to linkedMapOf<String, Any?>())
            State.emit(s, "proposal_imported", "proposal_id" to pid, "operations" to normalized.size.toLong(), "stale" to stale)
            pid
        }
    }

    fun importProposalText(text: String, responseId: String = ""): String {
        val m = PROPOSAL_RE.find(text) ?: throw ModelError("no AIWB_MANAGER_PROPOSAL block found")
        var body = m.groupValues[1].trim()
        Regex("(?s)^`{3,}\\s*json\\s*\\n(.*?)\\n`{3,}$").find(body)?.let { body = it.groupValues[1] }
        val data = try { Json.parseObj(body) } catch (e: Exception) {
            val fixed = Normalize.normalizeJsonText(body)
            if (!fixed.changed) throw ModelError("AIWB_MANAGER_PROPOSAL is not valid JSON: ${e.message}")
            Json.parseObj(fixed.text)
        }
        return importProposalData(data, responseId)
    }

    /** Accept the operations in [accept] (indices); the rest is rejected. */
    fun reviewProposal(proposalId: String, accept: List<Int>, confirmStale: Boolean = false, note: String = ""): Obj {
        val p0 = State.require(state(), "proposals", proposalId)
        if (p0["status"] != "pending") throw ModelError("proposal $proposalId was already reviewed (${p0["status"]})")
        if (p0["stale"] == true && accept.isNotEmpty() && !confirmStale)
            throw ModelError("this proposal is stale: tasks " + Json.strs(p0["stale_task_ids"]).joinToString(", ") +
                " changed after its base revision. Re-check each operation and confirm explicitly.")
        return store.transaction("review manager proposal") { s ->
            val p = State.require(s, "proposals", proposalId)
            val result = apply(s, p, accept)
            val errors = Json.strs(result["errors"])
            if (errors.isNotEmpty()) throw ModelError("proposal not applied: " + errors.joinToString("; "))
            val accepted = Json.list(result["applied"]).map { Json.int(it) }.toSet()
            for (raw in Json.list(p["operations"])) { val op = Json.obj(raw); op["decision"] = if (Json.int(op["index"]) in accepted) "accepted" else "rejected" }
            val nValid = Json.list(p["operations"]).count { Json.obj(it)["valid"] == true }
            p["status"] = if (accepted.isEmpty()) "rejected" else if (accepted.size == nValid) "accepted" else "partially_accepted"
            result["note"] = note.take(1000); result["reviewed_at"] = State.nowUtc()
            p["result"] = result
            val ch = p["charter"] as? Map<*, *>
            if (accepted.isNotEmpty() && ch != null) {
                val rec = Json.obj(StrictJson.copy(ch))
                rec["proposal_id"] = proposalId; rec["accepted_at"] = State.nowUtc(); rec["task_ids"] = StrictJson.copy(result["created"])
                Json.obj(s["settings"])["charter"] = rec
                State.emit(s, "charter_accepted", "proposal_id" to proposalId)
            }
            p["updated_at"] = State.nowUtc()
            State.emit(s, "proposal_reviewed", "proposal_id" to proposalId, "status" to p["status"],
                "applied" to ArrayList<Any?>(accepted.sorted().map { it.toLong() }))
            p
        }
    }

    fun acceptAllValid(proposalId: String): Obj {
        val p = State.require(state(), "proposals", proposalId)
        return reviewProposal(proposalId, Json.list(p["operations"]).map { Json.obj(it) }.filter { it["valid"] == true }.map { Json.int(it["index"]) }, true)
    }

    private fun apply(s: Obj, p: Obj, accept: List<Int>): Obj {
        val ops = Json.list(p["operations"]).map { Json.obj(it) }.associateBy { Json.int(it["index"]) }
        val errors = ArrayList<Any?>(); val applied = ArrayList<Any?>(); val created = LinkedHashMap<String, Any?>(); val notes = ArrayList<Any?>()
        val order = mapOf("create_agent" to 0, "assign_account" to 1, "create_milestone" to 3)
        val selected = accept.toSortedSet().mapNotNull { ops[it] }.sortedWith(compareBy({ order[it["operation"]] ?: 2 }, { Json.int(it["index"]) }))
        val selectedRefs = selected.mapNotNull { (it["temporary_ref"] as? String) }.toSet()
        val tasks = State.coll(s, "tasks"); val agents = State.coll(s, "agents")
        fun resolve(r: String) = Json.str(created[r]).ifEmpty { r }
        val later = ArrayList<Pair<Obj, List<String>>>()
        val pid = Json.str(p["proposal_id"])
        for (op in selected) {
            val raw = Json.obj(op["raw"]); val name = Json.str(op["operation"]); val idx = Json.int(op["index"])
            if (op["valid"] != true) { errors.add("#${idx + 1} $name: ${op["problem"]}"); continue }
            try {
                when (name) {
                    "create_task", "split_task" -> {
                        var deps = (Json.strs(raw["depends_on_refs"]) + Json.strs(raw["depends_on"])).map { resolve(it) }
                        val pending = deps.filter { !it.startsWith("TASK-") }
                        if (pending.isNotEmpty()) { later.add(op to pending); deps = deps.filter { it.startsWith("TASK-") } }
                        val missing = Json.strs(raw["depends_on_refs"]).filter { !it.startsWith("TASK-") && it !in selectedRefs }
                        if (missing.isNotEmpty()) throw ModelError("depends on ${missing.joinToString(", ")} which is not accepted in this review")
                        var owner = Json.str(raw["owner_agent_id"])
                        if (owner.isEmpty() && raw["owner_role"] != null)
                            owner = agents.values.map { Json.obj(it) }.sortedBy { Json.str(it["agent_id"]) }
                                .firstOrNull { it["role"] == raw["owner_role"] && it["enabled"] != false }?.let { Json.str(it["agent_id"]) } ?: ""
                        val data: Obj = linkedMapOf("title" to raw["title"], "objective" to (raw["objective"] ?: raw["title"]),
                            "acceptance_criteria" to raw["acceptance_criteria"], "depends_on" to ArrayList<Any?>(deps), "scope" to raw["scope"],
                            "deliverables" to raw["deliverables"], "owner_agent_id" to owner, "priority" to raw["priority"],
                            "risk_level" to raw["risk_level"], "task_type" to raw["task_type"], "origin" to "manager_proposal",
                            "acceptance_policy" to raw["acceptance_policy"], "required_approvals" to raw["required_approvals"])
                        if (Json.str(raw["reviewer_agent_id"]).isNotEmpty()) data["reviewer_agent_ids"] = arrayListOf<Any?>(raw["reviewer_agent_id"])
                        val t = createTaskIn(s, data)
                        if (Json.str(raw["parallel_group"]).isNotEmpty()) t["parallel_group"] = Json.str(raw["parallel_group"]).take(20)
                        t["proposal_id"] = pid
                        created[Json.str(op["temporary_ref"])] = t["task_id"]
                    }
                    "update_task", "change_scope", "reorder_priority", "assign_agent" -> {
                        val t = State.require(s, "tasks", Json.str(raw["task_id"]))
                        val fields: Obj = when (name) {
                            "change_scope" -> linkedMapOf("scope" to (raw["scope"] ?: Json.obj(raw["changes"])["scope"]))
                            "reorder_priority" -> linkedMapOf("priority" to raw["priority"])
                            "assign_agent" -> {
                                val aid = Json.str(raw["agent_id"]).ifEmpty { Json.str(raw["owner_agent_id"]) }
                                if (aid !in agents) throw ModelError("agent $aid does not exist")
                                linkedMapOf("owner_agent_id" to aid)
                            }
                            else -> Json.obj(StrictJson.copy(raw["changes"]))
                        }
                        for (k in listOf("status", "task_id", "task_revision")) if (k in fields) throw ModelError("a proposal cannot set $k directly")
                        val editable = LinkedHashMap<String, Any?>(); for (k in TASK_FIELDS) editable[k] = t[k]
                        val merged = normalizeTask(LinkedHashMap(editable).also { it.putAll(fields) })
                        if (REVISION_FIELDS.any { StrictJson.stringify(merged[it], true) != StrictJson.stringify(editable[it], true) }) {
                            Json.list(t.getOrPut("revisions") { ArrayList<Any?>() }).add(linkedMapOf("task_revision" to t["task_revision"],
                                "at" to State.nowUtc(), "fields" to LinkedHashMap<String, Any?>().also { f -> REVISION_FIELDS.forEach { f[it] = StrictJson.copy(t[it]) } },
                                "reason" to "proposal $pid"))
                            t["task_revision"] = (Json.int(t["task_revision"]) + 1).toLong()
                        }
                        t.putAll(merged); t["updated_at"] = State.nowUtc()
                    }
                    "add_dependency" -> {
                        val t = State.require(s, "tasks", Json.str(raw["task_id"]))
                        val dep = resolve(Json.str(raw["depends_on_task_id"]).ifEmpty { Json.str(raw["depends_on_ref"]) })
                        val d = Json.list(t["depends_on"]); if (dep !in d) d.add(dep)
                    }
                    "remove_dependency" -> Json.list(State.require(s, "tasks", Json.str(raw["task_id"]))["depends_on"]).remove(Json.str(raw["depends_on_task_id"]))
                    "close_or_cancel_task" -> {
                        val t = State.require(s, "tasks", Json.str(raw["task_id"]))
                        if ("cancelled" !in State.TASK_FLOW[Json.str(t["status"])].orEmpty()) throw ModelError("task cannot go from '${t["status"]}' to 'cancelled'")
                        t["status"] = "cancelled"; t["cancel_reason"] = Json.str(raw["reason"]).take(500)
                        notes.add("${t["task_id"]} cancelled (history kept)")
                    }
                    "propose_decision" -> {
                        val did = State.nextId(s, "decision"); val now = State.nowUtc()
                        State.coll(s, "decisions")[did] = linkedMapOf("schema_version" to State.SCHEMA_VERSION, "decision_id" to did,
                            "revision" to 1L, "title" to Json.str(raw["title"]).ifEmpty { "Decision" }.take(200),
                            "problem" to Json.str(raw["problem"]).take(4000), "options" to ArrayList<Any?>(Json.strs(raw["options"]).take(20)),
                            "recommendation" to Json.str(raw["recommendation"]).take(2000), "decision" to "", "rationale" to "",
                            "status" to "proposed", "origin" to "proposal $pid", "approved_by" to "", "approved_at" to "",
                            "affected_task_ids" to ArrayList<Any?>(Json.strs(raw["affected_task_ids"]).map { resolve(it) }),
                            "supersedes" to "", "superseded_by" to "", "previously_rejected" to ArrayList<Any?>(), "created_at" to now, "updated_at" to now)
                        notes.add("$did proposed (needs your decision)")
                    }
                    "create_agent" -> {
                        val aid = Json.str(raw["agent_id"])
                        if (aid in agents) throw ModelError("agent $aid already exists")
                        agents[aid] = agent(linkedMapOf("agent_id" to aid, "role" to raw["role"], "name" to (Json.str(raw["name"]).ifEmpty { aid }),
                            "purpose" to Json.str(raw["purpose"]), "instructions" to (raw["instructions"] ?: ArrayList<Any?>()), "template_id" to ""))
                        State.emit(s, "agent_created", "agent_id" to aid, "proposal_id" to pid)
                    }
                    "assign_account" -> throw ModelError("account profiles are managed on the desktop")
                    "create_milestone" -> notes.addAll(applyMilestone(s, raw, created, pid))
                    else -> notes.add("$name: ${(Json.str(raw["reason"]).ifEmpty { Json.str(raw["description"]) }).take(300)}")
                }
                applied.add(idx.toLong())
            } catch (e: ModelError) { errors.add("#${idx + 1} $name: ${e.message}") }
        }
        for ((op, rs) in later) {
            val tid = Json.str(created[Json.str(op["temporary_ref"])])
            if (tid.isEmpty()) continue
            val deps = Json.list(State.coll(s, "tasks").let { Json.obj(it[tid]) }["depends_on"])
            for (r in rs) { val c = Json.str(created[r]); if (c.isNotEmpty() && c !in deps) deps.add(c) }
        }
        val problems = validateGraph(tasks)
        if (problems.isNotEmpty()) errors.add("resulting task graph is invalid: " + problems.joinToString("; "))
        val newIds = created.values.map { Json.str(it) }.toSet()
        for (raw in tasks.values) {
            val t = Json.obj(raw)
            if (Json.str(t["task_id"]) in newIds && t["status"] == "draft" && problems.isEmpty()) {
                val (st, why) = State.readiness(t, tasks)
                t["status"] = st; t["blocked_reason"] = why
                State.emit(s, "task_status", "task_id" to t["task_id"], "old" to "draft", "new" to st, "why" to why.ifEmpty { "plan approved" })
                continue
            }
            if (t["status"] == "ready" && State.readiness(t, tasks).first != "ready") {
                t["status"] = "blocked"; t["blocked_reason"] = State.readiness(t, tasks).second
                notes.add("${t["task_id"]} is now blocked: ${t["blocked_reason"]}")
            }
        }
        return linkedMapOf("applied" to applied, "created" to created, "errors" to errors, "notes" to notes, "dry_run" to false)
    }

    private fun applyMilestone(s: Obj, raw: Obj, created: Map<String, Any?>, pid: String): List<String> {
        val title = Json.str(raw["title"]).trim().take(200)
        if (title.isEmpty()) throw ModelError("milestone title is required")
        val notes = ArrayList<String>()
        val refs = (raw["task_refs"] as? List<*>).orEmpty().map { it.toString() }
        val tasks = State.coll(s, "tasks")
        val ids = ArrayList<Any?>(refs.filter { it in created }.map { created[it] })
        val skipped = refs.filter { it !in created && !it.startsWith("TASK-") }
        ids.addAll(refs.filter { it.startsWith("TASK-") && it in tasks })
        val mid = State.nextId(s, "milestone"); val now = State.nowUtc()
        State.coll(s, "milestones")[mid] = linkedMapOf("schema_version" to State.SCHEMA_VERSION, "milestone_id" to mid, "title" to title,
            "criteria" to ArrayList<Any?>((raw["criteria"] as? List<*>).orEmpty().map { it.toString() }.filter { it.isNotBlank() }.map { it.take(500) }.take(30)),
            "task_ids" to ids, "status" to "planned", "target_date" to "", "accepted_at" to "", "proposal_id" to pid,
            "created_at" to now, "updated_at" to now)
        State.emit(s, "milestone_created", "milestone_id" to mid, "task_ids" to ArrayList<Any?>(ids))
        if (skipped.isNotEmpty()) notes.add("$mid: tasks ${skipped.joinToString(", ")} were not accepted, so they are not linked")
        val label = Json.str(raw["version"]).trim()
        if (label.isNotEmpty()) {
            if (!Charter.SEMVER.matches(label)) throw ModelError("'$label' is not a semantic version")
            if (State.coll(s, "versions").values.any { Json.obj(it)["label"] == label && Json.obj(it)["status"] != "withdrawn" }) {
                notes.add("version $label already exists; $mid is not linked to a new version")
            } else {
                val vid = State.nextId(s, "version")
                State.coll(s, "versions")[vid] = linkedMapOf("schema_version" to State.SCHEMA_VERSION, "version_id" to vid, "label" to label,
                    "policy" to "semver", "status" to "proposed", "source" to "model", "task_ids" to ArrayList<Any?>(ids),
                    "milestone_ids" to arrayListOf<Any?>(mid), "notes" to "Planned by the Project Charter ($pid)", "commit_sha" to "",
                    "tag" to "", "run_id" to "", "artifact" to "", "artifact_sha256" to "", "history" to ArrayList<Any?>(),
                    "created_at" to now, "updated_at" to now)
                State.emit(s, "version_proposed", "version_id" to vid, "label" to label, "source" to "model")
                notes.add("$mid → version $label ($vid, proposed)")
            }
        }
        return notes
    }

    // ------------------------------------------------------------------- tasks

    fun createTask(data: Obj, status: String = "draft"): Obj = store.transaction("create task") { s ->
        val t = createTaskIn(s, data)
        if (status != "draft") transitionIn(s, Json.str(t["task_id"]), status, "created")
        t
    }

    private fun createTaskIn(s: Obj, data: Obj): Obj {
        val f = normalizeTask(data)
        val agents = State.coll(s, "agents")
        val owner = Json.str(f["owner_agent_id"])
        if (owner.isNotEmpty() && owner !in agents) throw ModelError("owner agent $owner does not exist")
        for (r in Json.strs(f["reviewer_agent_ids"])) if (r !in agents) throw ModelError("reviewer agent $r does not exist")
        val tid = State.nextId(s, "task"); val now = State.nowUtc()
        val t: Obj = linkedMapOf("schema_version" to State.SCHEMA_VERSION, "task_id" to tid, "task_revision" to 1L, "project_id" to s["project_id"])
        t.putAll(f)
        t.putAll(linkedMapOf("status" to "draft", "revisions" to ArrayList<Any?>(), "flags" to ArrayList<Any?>(),
            "base_state_revision" to Json.int(s["state_revision"]).toLong(), "base_commit_sha" to Json.str(data["base_commit_sha"]),
            "created_at" to now, "updated_at" to now))
        val tasks = State.coll(s, "tasks")
        val trial = LinkedHashMap(tasks); trial[tid] = t
        val problems = validateGraph(trial)
        if (problems.isNotEmpty()) throw ModelError("task graph rejected: " + problems.joinToString("; "))
        tasks[tid] = t
        State.emit(s, "task_created", "task_id" to tid, "origin" to f["origin"])
        return t
    }

    fun transition(taskId: String, new: String, reason: String = ""): Obj = store.transaction("task $taskId -> $new") { s ->
        transitionIn(s, taskId, new, reason)
        State.refreshReadiness(s)
        State.require(s, "tasks", taskId)
    }

    private fun transitionIn(s: Obj, taskId: String, new: String, reason: String) {
        val t = State.require(s, "tasks", taskId)
        val cur = Json.str(t["status"])
        if (new != cur && new !in State.TASK_FLOW[cur].orEmpty()) throw ModelError("task cannot go from '$cur' to '$new'")
        if (new == "ready") { val (r, why) = State.readiness(t, State.coll(s, "tasks")); if (r != "ready") throw ModelError("$taskId is not ready: $why") }
        if (new == "done") throw ModelError("tasks become done only through the evidence policy (review + validation)")
        if (new == cur) return
        t["status"] = new; t["updated_at"] = State.nowUtc()
        if (new == "blocked" && reason.isNotEmpty()) t["blocked_reason"] = reason.take(500)
        State.emit(s, "task_status", "task_id" to taskId, "old" to cur, "new" to new, "why" to reason.take(300))
    }

    // ------------------------------------------------------- attempts/handoffs

    fun startTask(taskId: String, agentId: String = ""): Obj {
        val st = state()
        val t = State.require(st, "tasks", taskId)
        val agent = agentId.ifEmpty { Json.str(t["owner_agent_id"]).ifEmpty { "agent-implementer" } }
        val a = State.coll(st, "agents")[agent] as? Map<*, *>
        if (a == null || a["enabled"] == false) throw ModelError("target agent $agent does not exist or is disabled")
        if (t["status"] in setOf("draft", "proposed", "blocked", "cancelled", "superseded", "done"))
            throw ModelError("$taskId is ${t["status"]}; it must be ready or in progress for a handoff")
        return store.transaction("prepare handoff") { s ->
            val task = State.require(s, "tasks", taskId)
            val previous = State.coll(s, "handoffs").values.map { Json.obj(it) }
                .filter { it["task_id"] == taskId && it["status"] == "accepted" }.maxByOrNull { Json.str(it["handoff_id"]) }
            val attId = newAttemptId(); val now = State.nowUtc()
            val prev = Json.str(task["active_attempt_id"])
            val attempts = State.coll(s, "attempts")
            attempts[attId] = linkedMapOf("schema_version" to State.SCHEMA_VERSION, "attempt_id" to attId, "task_id" to taskId,
                "task_revision" to task["task_revision"], "agent_id" to agent, "handoff_id" to "", "kind" to "handoff",
                "parent_attempt_id" to Json.str(previous?.get("attempt_id")), "expected_paths" to ArrayList<Any?>(), "status" to "created",
                "base_state_revision" to Json.int(s["state_revision"]).toLong(), "base_revision" to "", "response_ids" to ArrayList<Any?>(),
                "created_at" to now, "updated_at" to now, "legacy" to false)
            task["active_attempt_id"] = attId
            val pa = attempts[prev] as? Obj
            if (pa != null && pa["status"] !in setOf("accepted", "rejected", "abandoned", "stale")) moveAttempt(s, prev, "stale", "superseded by $attId")
            State.emit(s, "attempt_created", "attempt_id" to attId, "task_id" to taskId, "kind" to "handoff")
            if (task["status"] in setOf("ready", "needs_decision", "in_review", "validation_pending")) {
                val old = task["status"]; task["status"] = "in_progress"
                State.emit(s, "task_status", "task_id" to taskId, "old" to old, "new" to "in_progress", "why" to "attempt started")
            }
            val hid = State.nextId(s, "handoff")
            val h: Obj = linkedMapOf("schema_version" to State.SCHEMA_VERSION, "handoff_id" to hid, "project_id" to s["project_id"],
                "task_id" to taskId, "task_revision" to task["task_revision"], "attempt_id" to attId,
                "from_agent_id" to Json.str(previous?.get("to_agent_id")), "to_agent_id" to agent,
                "previous_handoff_id" to Json.str(previous?.get("handoff_id")), "base_state_revision" to (Json.int(s["state_revision"]) + 1).toLong(),
                "base_commit_sha" to "", "status" to "prepared", "outcome" to "", "summary" to "", "completed_items" to ArrayList<Any?>(),
                "unresolved_items" to ArrayList<Any?>(), "assumptions" to ArrayList<Any?>(), "decision_requests" to ArrayList<Any?>(),
                "artifact_refs" to ArrayList<Any?>(), "validation_claims" to ArrayList<Any?>(), "verified_evidence_ids" to ArrayList<Any?>(),
                "recommended_next_action" to "", "source_response_id" to "", "issues" to ArrayList<Any?>(), "note" to "",
                "created_at" to now, "updated_at" to now)
            Json.obj(attempts[attId])["handoff_id"] = hid
            Json.obj(attempts[attId])["status"] = "prompt_ready"
            h["prompt"] = Prompts.handoff(s, h, previous)
            State.coll(s, "handoffs")[hid] = h
            State.emit(s, "handoff_prepared", "handoff_id" to hid, "task_id" to taskId, "to_agent_id" to agent)
            h
        }
    }

    fun markCopied(handoffId: String) {
        store.transaction("prompt copied") { s ->
            val h = State.require(s, "handoffs", handoffId)
            val attId = Json.str(h["attempt_id"])
            if (h["status"] == "prepared") {
                for (step in listOf("exported", "waiting_response")) moveAttemptIfAllowed(s, attId, step, "prompt exported")
                h["status"] = "prompt_exported"; h["exported_at"] = State.nowUtc()
                State.emit(s, "handoff_exported", "handoff_id" to handoffId)
            }
            val a = State.require(s, "attempts", attId)
            val wf = Json.obj(a.getOrPut("workflow") { LinkedHashMap<String, Any?>() })
            wf["copied_at"] = State.nowUtc(); wf["copy_count"] = (Json.int(wf["copy_count"]) + 1).toLong()
            State.emit(s, "prompt_copied", "attempt_id" to attId, "task_id" to a["task_id"], "agent_id" to Json.str(a["agent_id"]), "count" to wf["copy_count"])
        }
    }

    fun confirmSent(handoffId: String) {
        store.transaction("user confirmed sent") { s ->
            val h = State.require(s, "handoffs", handoffId)
            val attId = Json.str(h["attempt_id"])
            val a = State.require(s, "attempts", attId)
            if (a["status"] !in setOf("created", "prompt_ready", "exported", "waiting_response"))
                throw ModelError("attempt $attId is ${a["status"]}; there is nothing to send")
            if (Json.obj(State.coll(s, "tasks")[a["task_id"]])["active_attempt_id"] != attId)
                throw ModelError("attempt $attId is not the active attempt of ${a["task_id"]}; confirm sending for the current prompt instead")
            val wf = Json.obj(a.getOrPut("workflow") { LinkedHashMap<String, Any?>() })
            if (Json.str(wf["copied_at"]).isEmpty()) wf["copied_at"] = ""
            wf["sent_confirmed_at"] = State.nowUtc()
            for (step in listOf("prompt_ready", "exported", "waiting_response")) moveAttemptIfAllowed(s, attId, step, "user confirmed sending")
            State.emit(s, "user_confirmed_sent", "attempt_id" to attId, "task_id" to a["task_id"], "agent_id" to Json.str(a["agent_id"]),
                "chat_binding_id" to "", "account_profile_id" to "")
        }
    }

    private fun moveAttempt(s: Obj, attId: String, status: String, why: String) {
        val a = State.require(s, "attempts", attId)
        val old = Json.str(a["status"])
        if (old == status) return
        if (status !in ATTEMPT_FLOW[old].orEmpty()) throw ModelError("attempt cannot go from '$old' to '$status'")
        a["status"] = status; a["updated_at"] = State.nowUtc()
        State.emit(s, "attempt_status", "attempt_id" to attId, "old" to old, "new" to status, "why" to why.take(300))
    }

    private fun moveAttemptIfAllowed(s: Obj, attId: String, status: String, why: String) {
        val a = State.require(s, "attempts", attId)
        if (a["status"] != status && status in ATTEMPT_FLOW[Json.str(a["status"])].orEmpty()) moveAttempt(s, attId, status, why)
    }

    /** One paste box for every answer: charter, manager proposal or handoff delivery. */
    fun routeAnswer(text: String): Routed {
        if (text.isBlank()) return Routed("rejected", "The answer is empty.")
        val rid = "resp-" + sha256(text).take(12)
        return try {
            when {
                Charter.has(text) -> importCharter(text, rid)
                PROPOSAL_RE.containsMatchIn(text) || PROPOSAL_RE.containsMatchIn(Normalize.normalize(text).text) -> {
                    val src = if (PROPOSAL_RE.containsMatchIn(text)) text else Normalize.normalize(text).text
                    val pid = importProposalText(src, rid)
                    val p = State.require(state(), "proposals", pid)
                    var msg = "Manager proposal $pid with ${Json.list(p["operations"]).size} change(s) is ready for review."
                    if (p["stale"] == true) msg += " It was written for an older project state: review carefully."
                    Routed("proposal", msg, pid)
                }
                HANDOFF_RE.containsMatchIn(text) || HANDOFF_RE.containsMatchIn(Normalize.normalize(text).text) -> {
                    val src = if (HANDOFF_RE.containsMatchIn(text)) text else Normalize.normalize(text).text
                    val hid = matchHandoff(src)
                    if (hid.isEmpty()) return Routed("rejected", "This answer names a task/attempt this project is not waiting for. Nothing was changed.")
                    val hashes = try { Intake.parse(src).fileMap().mapValues { sha256(it.value) } } catch (_: Exception) { emptyMap() }
                    val h = ingest(hid, rid, src, hashes)
                    var msg = "Answer linked to $hid (${h["status"]}, ${Json.str(h["outcome"]).ifEmpty { "no outcome" }})."
                    val open = Json.strs(h["unresolved_items"])
                    if (open.isNotEmpty()) msg += " Still open: " + open.take(5).joinToString("; ")
                    Routed("handoff", msg, hid)
                }
                else -> Routed("inbox_only", "No charter, manager proposal or handoff block found.")
            }
        } catch (e: ModelError) {
            Routed("rejected", "${e.message}")
        }
    }

    private fun findManifest(text: String): Obj? {
        val m = HANDOFF_RE.find(text) ?: return null
        var body = m.groupValues[1].trim()
        Regex("(?s)^`{3,}\\s*json\\s*\\n(.*?)\\n`{3,}$").find(body)?.let { body = it.groupValues[1] }
        return try { Json.parseObj(body) } catch (e: Exception) {
            val f = Normalize.normalizeJsonText(body)
            if (f.changed) Json.parseObj(f.text) else throw ModelError("AIWB_HANDOFF manifest is not valid JSON: ${e.message}")
        }
    }

    private fun matchHandoff(text: String): String {
        val data = try { findManifest(text) ?: linkedMapOf() } catch (_: ModelError) { linkedMapOf() }
        val hs = State.coll(state(), "handoffs")
        val hid = Json.str(data["handoff_id"])
        if (hid in hs) return hid
        val att = Json.str(data["attempt_id"]).ifEmpty { Regex("(?m)^\\s*AIWB_ATTEMPT_ID:\\s*(\\S+)").find(text)?.groupValues?.get(1) ?: "" }
        return hs.values.map { Json.obj(it) }.firstOrNull { att.isNotEmpty() && it["attempt_id"] == att }?.let { Json.str(it["handoff_id"]) } ?: ""
    }

    fun ingest(handoffId: String, responseId: String, text: String, fileHashes: Map<String, String> = emptyMap()): Obj {
        val issues = ArrayList<Any?>()
        var parseOk = true
        val manifest: Obj = try {
            findManifest(text) ?: linkedMapOf<String, Any?>().also { issues.add("no AIWB_HANDOFF manifest; delivery summary unavailable (files are still kept)") }
        } catch (e: ModelError) { parseOk = fileHashes.isNotEmpty(); issues.add(e.message); linkedMapOf() }
        val st = state()
        val h0 = State.require(st, "handoffs", handoffId)
        val claimed = Json.str(manifest["attempt_id"])
        if (claimed.isNotEmpty() && claimed != h0["attempt_id"])
            throw ModelError("this answer belongs to attempt $claimed, not to $handoffId (${h0["attempt_id"]}). Nothing was linked.")
        for ((k, want) in listOf("task_id" to h0["task_id"], "handoff_id" to handoffId))
            if (Json.str(manifest[k]).isNotEmpty() && manifest[k] != want) throw ModelError("manifest $k '${manifest[k]}' does not match '$want'; nothing was linked.")
        return store.transaction("ingest handoff") { s ->
            val h = State.require(s, "handoffs", handoffId)
            val attId = Json.str(h["attempt_id"])
            val a = State.require(s, "attempts", attId)
            val rids = Json.list(a["response_ids"]); if (responseId !in rids) rids.add(responseId)
            val task = State.require(s, "tasks", Json.str(h["task_id"]))
            val active = task["active_attempt_id"] == attId
            if (a["status"] == "created") moveAttempt(s, attId, "prompt_ready", "response arrived")
            if (a["status"] in setOf("prompt_ready", "exported", "waiting_response", "parse_failed")) moveAttempt(s, attId, "response_received", "response $responseId")
            if (a["status"] == "response_received") moveAttempt(s, attId, if (parseOk) "parsed" else "parse_failed", "")
            if (!active && a["status"] !in setOf("accepted", "rejected", "abandoned", "stale") && "stale" in ATTEMPT_FLOW[Json.str(a["status"])].orEmpty())
                moveAttempt(s, attId, "stale", "late answer: a newer attempt is active")
            State.emit(s, "attempt_response", "attempt_id" to attId, "response_id" to responseId, "active" to active)
            val staleReasons = ArrayList<Any?>()
            if (Json.int(task["task_revision"]) != Json.int(h["task_revision"]))
                staleReasons.add("task changed to revision ${task["task_revision"]} after this handoff (revision ${h["task_revision"]})")
            if (manifest["task_revision"] != null && manifest["task_revision"] != "" && manifest["task_revision"].toString() != h["task_revision"].toString())
                staleReasons.add("answer is for task revision ${manifest["task_revision"]}")
            if (!active) staleReasons.add("a newer attempt is active for this task (late answer)")
            val outcome = Json.str(manifest["outcome"]).takeIf { it in OUTCOMES } ?: (if (issues.isNotEmpty()) "partial" else "")
            for (step in listOf("response_received", "parsed")) {
                if (step == "parsed" && !parseOk) break
                if (h["status"] in setOf("prompt_exported", "prepared", "response_received")) {
                    if (h["status"] == "prepared") h["status"] = "prompt_exported"
                    h["status"] = step
                }
            }
            fun lst(k: String) = ArrayList<Any?>((manifest[k] as? List<*>).orEmpty().filter { (it is String || it is Number) && it.toString().isNotBlank() }
                .map { it.toString().take(1000) }.take(50))
            h["source_response_id"] = responseId; h["outcome"] = outcome.ifEmpty { Json.str(h["outcome"]) }
            h["summary"] = Json.str(manifest["summary"]).take(4000)
            for (k in listOf("completed_items", "unresolved_items", "assumptions", "decision_requests", "validation_claims")) h[k] = lst(k)
            h["recommended_next_action"] = Json.str(manifest["recommended_next_action"]).take(1000); h["updated_at"] = State.nowUtc()
            val arts = ArrayList<Any?>()
            for ((path, sha) in fileHashes.toSortedMap()) {
                val aid = State.nextId(s, "artifact")
                val art: Obj = linkedMapOf("artifact_id" to aid, "logical_path" to path, "sha256" to sha, "media_type" to "text/plain",
                    "source_response_id" to responseId, "handoff_id" to handoffId, "attempt_id" to attId)
                State.coll(s, "artifacts")[aid] = art; arts.add(art)
            }
            h["artifact_refs"] = arts
            val claims = Json.strs(h["validation_claims"]).joinToString("; ")
            if (claims.isNotEmpty()) {
                val eid = State.nextId(s, "evidence")
                State.coll(s, "evidence")[eid] = linkedMapOf("schema_version" to State.SCHEMA_VERSION, "evidence_id" to eid, "type" to "model_report",
                    "subject_type" to "task", "subject_id" to h["task_id"], "attempt_id" to attId, "task_revision" to h["task_revision"],
                    "source" to linkedMapOf<String, Any?>("kind" to "model", "run_id" to "", "commit_sha" to ""), "result" to "claimed", "verified" to false,
                    "verification_method" to "unverified model claim", "summary" to claims.take(2000), "observed_at_utc" to State.nowUtc(),
                    "state_revision" to (Json.int(s["state_revision"]) + 1).toLong(), "artifact_sha256" to "",
                    "details" to linkedMapOf<String, Any?>("handoff_id" to handoffId))
                State.emit(s, "evidence_recorded", "evidence_id" to eid, "subject_id" to h["task_id"], "verified" to false, "kind" to "model_report")
            }
            h["issues"] = issues
            if (staleReasons.isNotEmpty() && h["status"] in setOf("parsed", "response_received")) {
                var target = if (staleReasons.any { "late answer" in it.toString() }) "stale" else "reconciliation_required"
                if (h["status"] == "response_received") target = "stale"
                h["status"] = target; h["stale_reasons"] = staleReasons
            } else if (h["status"] == "parsed") h["status"] = "reconciled"
            State.emit(s, "handoff_ingested", "handoff_id" to handoffId, "response_id" to responseId, "status" to h["status"], "artifacts" to arts.size.toLong())
            h
        }
    }

    /** Accepting a delivery never applies files and never marks the task done. */
    fun resolveHandoff(handoffId: String, accept: Boolean, reason: String = ""): Obj = store.transaction("resolve handoff") { s ->
        val h = State.require(s, "handoffs", handoffId)
        if (accept && h["status"] in setOf("stale", "reconciliation_required")) {
            if (reason.isBlank()) throw ModelError("accepting a stale handoff needs an explicit reconciliation note")
            h["status"] = "reconciled"
        }
        val target = if (accept) "accepted" else "rejected"
        if (target !in HANDOFF_FLOW[Json.str(h["status"])].orEmpty()) throw ModelError("handoff cannot go from '${h["status"]}' to '$target'")
        h["status"] = target
        h["resolution"] = linkedMapOf<String, Any?>("accepted" to accept, "reason" to reason.take(2000), "at" to State.nowUtc())
        val att = State.coll(s, "attempts")[h["attempt_id"]] as? Obj
        if (att != null && att["status"] in setOf("parsed", "reconciliation_required", "ready_for_review", "stale")) {
            if (att["status"] in setOf("parsed", "reconciliation_required") && accept) att["status"] = "ready_for_review"
            if (att["status"] == "parsed" && !accept) att["status"] = "rejected"
            else if (att["status"] in setOf("ready_for_review", "stale", "reconciliation_required")) att["status"] = if (accept) "accepted" else "rejected"
        }
        for (raw in State.coll(s, "handoffs").values) {
            val o = Json.obj(raw)
            if (accept && o["task_id"] == h["task_id"] && o["handoff_id"] != handoffId && o["status"] == "accepted") o["status"] = "superseded"
        }
        val t = State.require(s, "tasks", Json.str(h["task_id"]))
        if (accept && t["status"] == "in_progress" && h["outcome"] in setOf("complete", "partial")) {
            t["status"] = "in_review"
            State.emit(s, "task_status", "task_id" to t["task_id"], "old" to "in_progress", "new" to "in_review", "why" to "handoff $handoffId accepted (${h["outcome"]})")
        }
        if (accept && h["outcome"] in setOf("blocked", "needs_decision") && t["status"] == "in_progress") {
            t["status"] = if (h["outcome"] == "blocked") "blocked" else "needs_decision"
            t["blocked_reason"] = (Json.strs(h["unresolved_items"]).ifEmpty { Json.strs(h["decision_requests"]) }).joinToString("; ").take(500)
            State.emit(s, "task_status", "task_id" to t["task_id"], "old" to "in_progress", "new" to t["status"], "why" to "handoff outcome")
        }
        State.emit(s, "handoff_$target", "handoff_id" to handoffId)
        h
    }

    // ---------------------------------------------------------------- evidence

    fun recordEvidence(type: String, taskId: String, result: String, summary: String = "", runId: String = ""): Obj =
        store.transaction("record evidence") { s ->
            if ((type == "test_run" || type == "build_run") && runId.isBlank()) throw ModelError("$type evidence needs the run ID or commit it was observed for")
            val t = State.require(s, "tasks", taskId)
            val eid = State.nextId(s, "evidence")
            val e: Obj = linkedMapOf("schema_version" to State.SCHEMA_VERSION, "evidence_id" to eid, "type" to type, "subject_type" to "task",
                "subject_id" to taskId, "attempt_id" to "", "task_revision" to Json.int(t["task_revision"]).toLong(),
                "source" to linkedMapOf<String, Any?>("kind" to "user", "run_id" to runId.take(120), "commit_sha" to ""),
                "result" to result, "verified" to true, "verification_method" to "user", "summary" to summary.take(2000),
                "observed_at_utc" to State.nowUtc(), "state_revision" to (Json.int(s["state_revision"]) + 1).toLong(),
                "artifact_sha256" to "", "details" to linkedMapOf<String, Any?>())
            State.coll(s, "evidence")[eid] = e
            State.emit(s, "evidence_recorded", "evidence_id" to eid, "subject_id" to taskId, "verified" to true, "kind" to type)
            e
        }

    /** Policy status from evidence (desktop `EvidenceService.evaluate_task`). */
    fun evaluateTask(taskId: String): Pair<String, List<String>> = store.transaction("evaluate $taskId") { s ->
        val t = State.require(s, "tasks", taskId)
        val ev = State.coll(s, "evidence").values.map { Json.obj(it) }
            .filter { it["subject_type"] == "task" && it["subject_id"] == taskId && Json.int(it["task_revision"]) == Json.int(t["task_revision"]) }
        val verified = ev.filter { it["verified"] == true }; val reported = ev.filter { it["verified"] != true }
        val policy = Json.str(t["acceptance_policy"]).ifEmpty { "review_and_evidence" }
        val needsReview = "review" in Json.strs(t["required_approvals"]) || policy in setOf("review_and_evidence", "manual_review")
        val needsValidation = policy in setOf("evidence_required", "review_and_evidence")
        fun last(kinds: Set<String>) = verified.filter { it["type"] in kinds }.sortedBy { Json.str(it["evidence_id"]) }
        val reviews = last(setOf("manual_review")); val validations = last(setOf("test_run", "build_run", "external_artifact"))
        val reasons = ArrayList<String>()
        val reviewOk = reviews.isNotEmpty() && reviews.last()["result"] == "approved"
        val validOk = validations.isNotEmpty() && validations.last()["result"] == "passed"
        if (needsReview && !reviewOk) reasons.add(if (reviews.isNotEmpty() && reviews.last()["result"] == "rejected") "rejected by review" else "review missing")
        if (needsValidation && !validOk) reasons.add(when {
            validations.isNotEmpty() && validations.last()["result"] == "failed" -> "validation failed (${validations.last()["evidence_id"]})"
            reported.isNotEmpty() -> "no verified test/build evidence (model claims do not count)"
            else -> "validation not run"
        })
        val cur = Json.str(t["status"])
        val target = when {
            cur in setOf("cancelled", "superseded", "draft", "proposed", "blocked", "needs_decision", "ready") -> cur
            reasons.isEmpty() -> "done"
            needsReview && !reviewOk && (!needsValidation || validOk) -> "in_review"
            reasons.any { it.startsWith("rejected") || it.startsWith("validation failed") } -> "in_progress"
            needsReview && !reviewOk -> "in_review"
            else -> "validation_pending"
        }
        if (target != cur) {
            if (target !in State.TASK_FLOW[cur].orEmpty()) throw ModelError("task cannot go from '$cur' to '$target'")
            t["status"] = target; t["updated_at"] = State.nowUtc()
            State.emit(s, "task_status", "task_id" to taskId, "old" to cur, "new" to target, "why" to reasons.joinToString("; ").ifEmpty { "policy satisfied" })
            if (target == "done") State.refreshReadiness(s)
        }
        t["evaluation"] = linkedMapOf<String, Any?>("at" to State.nowUtc(), "reasons" to ArrayList<Any?>(reasons),
            "verified" to ArrayList<Any?>(verified.map { it["evidence_id"] }), "reported" to ArrayList<Any?>(reported.map { it["evidence_id"] }))
        target to reasons
    }

    fun reviewTask(taskId: String, approved: Boolean, note: String = ""): Pair<String, List<String>> {
        recordEvidence("manual_review", taskId, if (approved) "approved" else "rejected", note.take(500))
        return evaluateTask(taskId)
    }

    fun recordValidation(taskId: String, passed: Boolean, runId: String): Pair<String, List<String>> {
        recordEvidence("test_run", taskId, if (passed) "passed" else "failed", "recorded in the guided loop",
            runId.ifBlank { "manual-" + State.nowUtc() })
        return evaluateTask(taskId)
    }

    // --------------------------------------------------------------- decisions

    fun proposeDecision(title: String, problem: String, affected: List<String>): String = store.transaction("propose decision") { s ->
        val did = State.nextId(s, "decision"); val now = State.nowUtc()
        State.coll(s, "decisions")[did] = linkedMapOf("schema_version" to State.SCHEMA_VERSION, "decision_id" to did, "revision" to 1L,
            "title" to title.ifBlank { "Decision" }.take(200), "problem" to problem.take(4000), "options" to ArrayList<Any?>(),
            "recommendation" to "", "decision" to "", "rationale" to "", "status" to "proposed", "origin" to "user", "approved_by" to "",
            "approved_at" to "", "affected_task_ids" to ArrayList<Any?>(affected), "supersedes" to "", "superseded_by" to "",
            "previously_rejected" to ArrayList<Any?>(), "created_at" to now, "updated_at" to now)
        State.emit(s, "decision_proposed", "decision_id" to did)
        did
    }

    fun resolveDecision(decisionId: String, accept: Boolean, decision: String = "", rationale: String = ""): Obj = store.transaction("decision") { s ->
        val d = State.require(s, "decisions", decisionId)
        if (d["status"] != "proposed") throw ModelError("decision $decisionId is already ${d["status"]}")
        if (accept && decision.isBlank()) throw ModelError("write what was decided")
        d["status"] = if (accept) "accepted" else "rejected"; d["decision"] = decision.take(2000); d["rationale"] = rationale.take(2000)
        d["approved_by"] = "user"; d["approved_at"] = State.nowUtc(); d["updated_at"] = State.nowUtc()
        State.emit(s, "decision_" + d["status"], "decision_id" to decisionId)
        if (accept) for (tid in Json.strs(d["affected_task_ids"])) {
            val t = State.coll(s, "tasks")[tid] as? Obj ?: continue
            if (t["status"] == "needs_decision") {
                val new = if (Json.str(t["active_attempt_id"]).isNotEmpty()) "in_progress" else State.readiness(t, State.coll(s, "tasks")).first
                State.emit(s, "task_status", "task_id" to tid, "old" to "needs_decision", "new" to new, "why" to "decision $decisionId")
                t["status"] = new; t["blocked_reason"] = ""
            }
        }
        d
    }

    // ---------------------------------------------------------- milestones etc.

    fun acceptMilestone(milestoneId: String): Obj = store.transaction("milestone accepted") { s ->
        val m = State.require(s, "milestones", milestoneId)
        if (m["status"] != "planned") throw ModelError("$milestoneId is already ${m["status"]}")
        val open = Json.strs(m["task_ids"]).filter { Json.obj(State.coll(s, "tasks")[it])["status"] !in setOf("done", "cancelled", "superseded") }
        if (open.isNotEmpty()) throw ModelError("$milestoneId still has open tasks: ${open.joinToString(", ")}")
        m["status"] = "accepted"; m["accepted_at"] = State.nowUtc(); m["updated_at"] = State.nowUtc(); m["accepted_with_open"] = ArrayList<Any?>()
        State.emit(s, "milestone_accepted", "milestone_id" to milestoneId, "open_tasks" to ArrayList<Any?>())
        m
    }

    fun advanceVersion(versionId: String, status: String, commitSha: String = "", tag: String = "", runId: String = ""): Obj =
        store.transaction("version $status") { s ->
            val v = State.require(s, "versions", versionId)
            val cur = Json.str(v["status"])
            if (status !in VERSION_FLOW[cur].orEmpty()) throw ModelError("$versionId cannot go from $cur to $status")
            if (commitSha.isNotBlank()) { if (!SHA.matches(commitSha.lowercase())) throw ModelError("commit_sha must be a hex hash"); v["commit_sha"] = commitSha.trim() }
            if (tag.isNotBlank()) v["tag"] = tag.trim().take(300)
            if (runId.isNotBlank()) v["run_id"] = runId.trim().take(300)
            if (status in setOf("local", "tagged") && Json.str(v["commit_sha"]).isEmpty()) throw ModelError("$status needs the commit SHA it points to")
            if (status == "tagged" && Json.str(v["tag"]).isEmpty()) throw ModelError("tagged needs the tag name")
            if (status == "released" && Json.str(v["run_id"]).isEmpty() && Json.str(v["artifact"]).isEmpty())
                throw ModelError("released needs a real build/run id or artifact; Workbench never assumes a release")
            Json.list(v["history"]).add(linkedMapOf("from" to cur, "to" to status, "at" to State.nowUtc()))
            v["status"] = status; v["updated_at"] = State.nowUtc()
            val etype = mapOf("released" to "release_published", "withdrawn" to "version_withdrawn")[status] ?: "version_created"
            State.emit(s, etype, "version_id" to versionId, "label" to v["label"], "old" to cur, "new" to status,
                "commit_sha" to v["commit_sha"], "run_id" to v["run_id"])
            v
        }

    fun managerUpdate(): String = Prompts.managerUpdate(state())

    companion object {
        val PROPOSAL_RE = Regex("(?s)<<<AIWB_MANAGER_PROPOSAL>>>\\s*(.*?)\\s*<<<AIWB_END_MANAGER_PROPOSAL>>>")
        val HANDOFF_RE = Regex("(?s)<<<AIWB_HANDOFF>>>\\s*(.*?)\\s*<<<AIWB_END_HANDOFF>>>")
        const val MAX_OPS = 60
        val OPERATIONS = setOf("create_task", "update_task", "add_dependency", "remove_dependency", "assign_agent", "propose_decision",
            "reorder_priority", "split_task", "close_or_cancel_task", "request_more_evidence", "change_scope", "report_risk",
            "create_agent", "assign_account", "create_milestone")
        val OUTCOMES = setOf("complete", "partial", "blocked", "needs_decision", "failed")
        val REVISION_FIELDS = listOf("title", "objective", "scope", "acceptance_criteria", "deliverables", "acceptance_policy",
            "required_approvals", "task_type")
        val TASK_FIELDS = listOf("title", "objective", "task_type", "owner_agent_id", "reviewer_agent_ids", "depends_on", "scope",
            "acceptance_criteria", "acceptance_policy", "deliverables", "context_refs", "priority", "risk_level", "required_approvals", "origin")
        private val SHA = Regex("^[0-9a-f]{7,64}$")
        val VERSION_FLOW = mapOf("proposed" to setOf("local", "tagged", "withdrawn"), "local" to setOf("tagged", "withdrawn"),
            "tagged" to setOf("released", "withdrawn"), "released" to emptySet(), "withdrawn" to emptySet<String>())
        val ATTEMPT_FLOW = mapOf(
            "created" to setOf("prompt_ready", "abandoned", "stale"),
            "prompt_ready" to setOf("exported", "response_received", "abandoned", "stale"),
            "exported" to setOf("waiting_response", "response_received", "abandoned", "stale"),
            "waiting_response" to setOf("response_received", "abandoned", "stale"),
            "response_received" to setOf("parse_failed", "parsed", "stale", "abandoned"),
            "parse_failed" to setOf("response_received", "parsed", "abandoned", "stale"),
            "parsed" to setOf("reconciliation_required", "ready_for_review", "stale", "rejected"),
            "reconciliation_required" to setOf("ready_for_review", "rejected", "stale", "abandoned"),
            "ready_for_review" to setOf("accepted", "rejected", "stale"),
            "accepted" to emptySet(), "rejected" to emptySet(), "stale" to setOf("ready_for_review", "rejected", "abandoned"),
            "abandoned" to emptySet<String>())
        val HANDOFF_FLOW = mapOf(
            "prepared" to setOf("prompt_exported", "superseded", "rejected"),
            "prompt_exported" to setOf("response_received", "superseded", "rejected", "stale"),
            "response_received" to setOf("parsed", "rejected", "stale", "superseded"),
            "parsed" to setOf("reconciled", "reconciliation_required", "rejected", "stale", "superseded"),
            "reconciliation_required" to setOf("reconciled", "rejected", "superseded"),
            "stale" to setOf("reconciled", "rejected", "superseded"),
            "reconciled" to setOf("accepted", "rejected", "superseded"),
            "accepted" to setOf("superseded"), "rejected" to emptySet(), "superseded" to emptySet<String>())

        val TEMPLATES: Map<String, Obj> = linkedMapOf(
            "agent-project-manager" to linkedMapOf("name" to "Project Manager", "role" to "project_manager",
                "purpose" to "Plan the project, propose tasks/dependencies/decisions and analyse progress from the published state.",
                "instructions" to arrayListOf<Any?>(
                    "Separate clearly: what you read in the state snapshot, what agents reported, your own inference, and what is unknown.",
                    "If you cannot open the GitHub state file, say so explicitly; never pretend you read it.",
                    "Never declare a task done; only Workbench marks tasks done from verified evidence.",
                    "Return changes only as an AIWB_MANAGER_PROPOSAL block based on the given state_revision."),
                "allowed_task_types" to arrayListOf<Any?>("planning", "analysis"), "output_contract" to "aiwb-manager-proposal-v1",
                "review_policy" to "user_approval_required", "escalation_rules" to arrayListOf<Any?>("conflicting_decision", "missing_information")),
            "agent-architect" to linkedMapOf("name" to "Architect", "role" to "architect",
                "purpose" to "Design contracts and architecture for one approved task; record decisions that need approval.",
                "instructions" to arrayListOf<Any?>("Follow accepted project decisions", "List every assumption and open decision explicitly",
                    "Do not implement unrelated features"),
                "allowed_task_types" to arrayListOf<Any?>("architecture", "design", "analysis"), "output_contract" to "aiwb-handoff-v1",
                "review_policy" to "decisions_need_approval", "escalation_rules" to arrayListOf<Any?>("scope_change", "conflicting_decision")),
            "agent-implementer" to linkedMapOf("name" to "Implementer", "role" to "implementer",
                "purpose" to "Implement one approved task within its scope.",
                "instructions" to arrayListOf<Any?>("Follow the accepted project decisions", "Stay inside the task scope",
                    "Do not claim tests passed unless evidence is present", "Report missing information instead of inventing it"),
                "allowed_task_types" to arrayListOf<Any?>("implementation", "bug_fix", "tests"), "output_contract" to "aiwb-handoff-v1",
                "review_policy" to "required_for_code_changes",
                "escalation_rules" to arrayListOf<Any?>("scope_change", "conflicting_decision", "missing_acceptance_criteria")),
            "agent-reviewer" to linkedMapOf("name" to "Reviewer", "role" to "reviewer",
                "purpose" to "Review a delivered change against the acceptance criteria and report findings with file references.",
                "instructions" to arrayListOf<Any?>("Check each acceptance criterion separately", "Link every finding to a file or criterion",
                    "Do not rewrite the implementation; propose concrete fixes"),
                "allowed_task_types" to arrayListOf<Any?>("review", "tests"), "output_contract" to "aiwb-handoff-v1",
                "review_policy" to "none", "escalation_rules" to arrayListOf<Any?>("missing_evidence")),
        )

        private val rnd = SecureRandom()

        fun newAttemptId(): String {
            val f = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }
            return "att-" + f.format(State.clock()) + "-" + String.format(Locale.US, "%08x", rnd.nextInt())
        }

        fun sha256(text: String): String =
            MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

        private fun opTaskRefs(op: Map<*, *>): List<String> =
            (listOf(op["task_id"]) + (op["depends_on_refs"] as? List<*>).orEmpty() + listOf(op["depends_on_task_id"]))
                .mapNotNull { it as? String }.filter { it.startsWith("TASK-") }

        private fun changedSince(st: Obj, taskId: String, base: Int): Boolean = Json.list(st["events"]).any {
            val e = Json.obj(it)
            e["task_id"] == taskId && Json.int(e["state_revision"]) > base && e["type"] in setOf("task_updated", "task_status", "task_created")
        }

        fun validateGraph(tasks: Map<String, Any?>): List<String> {
            val problems = ArrayList<String>()
            val edges = LinkedHashMap<String, List<String>>()
            for ((tid, raw) in tasks) {
                val deps = Json.strs(Json.obj(raw)["depends_on"])
                if (tid in deps) problems.add("$tid depends on itself")
                for (d in deps) if (d !in tasks) problems.add("$tid depends on unknown task $d")
                edges[tid] = deps.filter { it in tasks && it != tid }
            }
            val color = HashMap<String, Int>()
            var cycle: List<String>? = null
            fun dfs(n: String, path: List<String>) {
                if (cycle != null) return
                color[n] = 1
                for (d in edges[n].orEmpty()) {
                    if (color[d] == 1) { cycle = path.subList(path.indexOf(d), path.size) + n + d; return }
                    if (color[d] == null) dfs(d, path + n)
                }
                color[n] = 2
            }
            for (n in edges.keys) if (color[n] == null) dfs(n, emptyList())
            cycle?.let { c -> problems.add("dependency cycle: " + c.distinct().plus(c.first()).joinToString(" → ")) }
            return problems
        }

        private fun text(v: Any?, name: String, required: Boolean, limit: Int): String {
            if (v == null || v == "") { if (required) throw ModelError("$name is required"); return "" }
            if (v !is String) throw ModelError("$name must be text")
            return v.trim().take(limit)
        }

        private fun strs(v: Any?, name: String, limit: Int, itemLen: Int): ArrayList<Any?> {
            if (v == null) return ArrayList()
            if (v !is List<*> || v.size > limit || !v.all { it is String }) throw ModelError("$name must be a list of strings (max $limit)")
            return ArrayList(v.map { (it as String).trim() }.filter { it.isNotEmpty() }.map { it.take(itemLen) })
        }

        fun agent(d: Obj): Obj {
            val aid = d["agent_id"]
            if (!State.validAgentId(aid)) throw ModelError("agent_id must look like 'agent-implementer' (lowercase letters, digits, '-')")
            if (d["role"] !in State.ROLES) throw ModelError("role must be one of ${State.ROLES.joinToString(", ")}")
            val instr = d["instructions"].let { if (it is String) it.lines() else it }
            val now = State.nowUtc()
            return linkedMapOf("schema_version" to State.SCHEMA_VERSION, "agent_id" to aid, "revision" to (Json.int(d["revision"]).takeIf { it > 0 } ?: 1).toLong(),
                "name" to text(d["name"], "name", true, 120), "role" to d["role"], "purpose" to text(d["purpose"], "purpose", false, 1000),
                "instructions" to strs(instr, "instructions", 60, 1000),
                "preferred_model_label" to text(d["preferred_model_label"], "preferred_model_label", false, 80),
                "input_contract" to text(d["input_contract"], "input_contract", false, 1000),
                "output_contract" to text(d["output_contract"] ?: "aiwb-handoff-v1", "output_contract", false, 120),
                "allowed_task_types" to strs(d["allowed_task_types"], "allowed_task_types", 20, 60),
                "review_policy" to text(d["review_policy"], "review_policy", false, 120),
                "escalation_rules" to strs(d["escalation_rules"], "escalation_rules", 20, 200),
                "template_id" to text(d["template_id"], "template_id", false, 80), "enabled" to (d["enabled"] != false),
                "created_at" to (d["created_at"] as? String ?: now), "updated_at" to (d["updated_at"] as? String ?: now))
        }

        fun normalizeTask(d: Obj): Obj {
            val scope = d["scope"] ?: linkedMapOf<String, Any?>()
            if (scope !is Map<*, *>) throw ModelError("scope must be an object with include/exclude lists")
            val policy = Json.str(d["acceptance_policy"]).ifEmpty { "review_and_evidence" }
            if (policy !in setOf("evidence_required", "review_and_evidence", "manual_review"))
                throw ModelError("acceptance_policy must be one of evidence_required, review_and_evidence, manual_review")
            val pr = Json.str(d["priority"]).ifEmpty { "medium" }; val risk = Json.str(d["risk_level"]).ifEmpty { "medium" }
            if (pr !in setOf("low", "medium", "high", "critical") || risk !in setOf("low", "medium", "high"))
                throw ModelError("priority must be low|medium|high|critical and risk_level low|medium|high")
            val deps = d["depends_on"] ?: ArrayList<Any?>()
            if (deps !is List<*> || !deps.all { it is String }) throw ModelError("depends_on must be a list of task IDs")
            val origin = Json.str(d["origin"]).takeIf { it in setOf("manual", "manager_proposal", "playbook", "migration", "companion") } ?: "manual"
            return linkedMapOf("title" to text(d["title"], "title", true, 200), "objective" to text(d["objective"], "objective", true, 4000),
                "task_type" to text(d["task_type"] ?: "implementation", "task_type", false, 60),
                "owner_agent_id" to text(d["owner_agent_id"], "owner_agent_id", false, 64),
                "reviewer_agent_ids" to strs(d["reviewer_agent_ids"], "reviewer_agent_ids", 10, 64),
                "depends_on" to ArrayList<Any?>(deps.map { (it as String).trim() }.filter { it.isNotEmpty() }.distinct()),
                "scope" to linkedMapOf<String, Any?>("include" to strs(scope["include"], "scope.include", 100, 300),
                    "exclude" to strs(scope["exclude"], "scope.exclude", 100, 300)),
                "acceptance_criteria" to strs(d["acceptance_criteria"], "acceptance_criteria", 50, 1000), "acceptance_policy" to policy,
                "deliverables" to strs(d["deliverables"], "deliverables", 30, 200), "context_refs" to strs(d["context_refs"], "context_refs", 50, 300),
                "priority" to pr, "risk_level" to risk,
                "required_approvals" to strs(d["required_approvals"] ?: arrayListOf<Any?>("review"), "required_approvals", 5, 30),
                "origin" to origin)
        }
    }
}
