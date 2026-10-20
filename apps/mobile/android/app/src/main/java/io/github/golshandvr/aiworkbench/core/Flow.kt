package io.github.golshandvr.aiworkbench.core

/**
 * The owner's algorithm on the phone (roadmap 4.x / mobile 1.1.0, contract `project-flow.v1`).
 *
 * Port of desktop `aiwb/v2/flow.py`: the flowchart's nodes and edges (identical to
 * `packages/contracts/fixtures/flow/project-flow.v1.json`; a JVM test keeps them in sync) and [current], which derives
 * where the project is in the flowchart from the state alone. Node kinds: app, user, github.
 */
object Flow {
    data class Node(val id: String, val title: String, val kind: String, val phase: String)
    data class Edge(val from: String, val to: String, val `when`: String = "")
    data class Position(val node: Node, val why: String, val cycle: Int) {
        val id: String get() = node.id
    }

    val PHASES = listOf("start", "repo", "brief", "charter_prompt", "charter_review", "split", "dispatch", "collect", "check",
        "troubleshoot", "approve", "integrate", "status_report", "pm_decision", "publish", "complete", "expand_or_archive", "archived")

    val NODES = listOf(
        Node("F1", "Start project", "user", "start"),
        Node("F2", "Start timeline", "app", "start"),
        Node("F3", "Create repository or update the existing one", "github", "repo"),
        Node("F4", "Get name, specification and number of available AIs", "app", "brief"),
        Node("F5", "Design the project-manager prompt", "app", "charter_prompt"),
        Node("F6", "Give the prompt to the project-manager AI", "user", "charter_prompt"),
        Node("F7", "Bring the project-manager output back", "user", "charter_prompt"),
        Node("F8", "Check the project-manager output (roadmap) carefully", "app", "charter_review"),
        Node("F9", "Split the project into parallel paths", "app", "split"),
        Node("F10", "Generate a suitable prompt for every AI", "app", "dispatch"),
        Node("F11", "Give every AI its prompt", "user", "dispatch"),
        Node("F12", "Bring every AI's output back", "user", "collect"),
        Node("F13", "Is the output acceptable?", "app", "check"),
        Node("F14", "Smart problem detection", "app", "troubleshoot"),
        Node("F15", "Build the troubleshooting prompt", "app", "troubleshoot"),
        Node("F16", "User approval", "user", "approve"),
        Node("F17", "Add to the project files and update the timeline", "app", "integrate"),
        Node("F18", "Design the status prompt for the project manager", "app", "status_report"),
        Node("F19", "Give the status prompt to the project manager", "user", "status_report"),
        Node("F20", "Bring the project-manager output back", "user", "status_report"),
        Node("F21", "Did the project manager define an emergency task?", "app", "pm_decision"),
        Node("F22", "Save the changes on GitHub", "github", "publish"),
        Node("F23", "Is a release needed?", "github", "publish"),
        Node("F24", "Publish the new version", "github", "publish"),
        Node("F25", "Is any roadmap stage left?", "app", "pm_decision"),
        Node("F26", "Announce completion and update the timeline", "app", "complete"),
        Node("F27", "Expand the project?", "user", "expand_or_archive"),
        Node("F28", "Archive the project", "app", "archived"),
    )

    val EDGES = listOf(
        Edge("F1", "F2"), Edge("F1", "F3"), Edge("F1", "F4"), Edge("F4", "F5"), Edge("F5", "F6"), Edge("F6", "F7"),
        Edge("F7", "F8"), Edge("F8", "F9"), Edge("F9", "F10"), Edge("F10", "F11"), Edge("F11", "F12"), Edge("F12", "F13"),
        Edge("F13", "F14", "no"), Edge("F14", "F15"), Edge("F15", "F11"), Edge("F13", "F16", "yes"), Edge("F16", "F17"),
        Edge("F17", "F18"), Edge("F18", "F19"), Edge("F19", "F20"), Edge("F20", "F21"), Edge("F21", "F10", "yes"),
        Edge("F21", "F22", "no"), Edge("F22", "F23"), Edge("F23", "F24", "yes"), Edge("F23", "F25", "no"), Edge("F24", "F25"),
        Edge("F25", "F10", "yes"), Edge("F25", "F26", "no"), Edge("F26", "F27"), Edge("F27", "F1", "yes"), Edge("F27", "F28", "no"),
    )

    const val TROUBLESHOOT_ATTEMPTS = 3
    private val OPEN_H = setOf("prepared", "prompt_exported", "response_received", "parsed")
    private val CHECK_H = setOf("reconciled", "stale", "reconciliation_required")

    fun node(id: String): Node = NODES.first { it.id == id }

    fun settings(st: Obj): Obj = Json.obj(Json.obj(st["settings"])["flow"])

    private fun sent(st: Obj, h: Obj): Boolean =
        Json.str(Json.obj(Json.obj(State.coll(st, "attempts")[h["attempt_id"]])["workflow"])["sent_confirmed_at"]).isNotEmpty()

    /** Where the project is in the owner's flowchart (desktop `flow.current`). */
    fun current(st: Obj): Position {
        val fs = settings(st)
        val settings = Json.obj(st["settings"])
        val tasks = State.coll(st, "tasks").values.map { Json.obj(it) }
        val handoffs = State.coll(st, "handoffs").values.map { Json.obj(it) }
        val guide = Json.obj(settings["guide"])
        val cycle = Json.int(fs["cycle"]).coerceAtLeast(1)
        fun at(id: String, why: String) = Position(node(id), why, cycle)

        if (Json.str(fs["archived_at"]).isNotEmpty()) return at("F28", "The project is archived (read-only).")
        if (Json.str(fs["completed_at"]).isNotEmpty()) return at("F27", "Every roadmap stage is done. Expand the project or archive it.")
        if (Json.str(settings["goal"]).isBlank())
            return at(if (Json.str(fs["started_at"]).isNotEmpty()) "F4" else "F1", "Give the project a name, a goal and the number of AIs you can use.")
        val pending = State.coll(st, "proposals").values.any { Json.obj(it)["status"] == "pending" }
        if (tasks.isEmpty()) {
            return when {
                pending -> at("F8", "The project manager's charter was read; check it before anything is created.")
                Json.str(guide["manager_sent_at"]).isNotEmpty() -> at("F7", "Paste the project manager's whole answer (the charter).")
                Json.str(guide["manager_copied_at"]).isNotEmpty() -> at("F6", "Send the charter prompt to your project-manager chat.")
                else -> at("F5", "The project-manager prompt is ready to copy.")
            }
        }
        if (pending) return at("F21", "The project manager answered; check the plan (emergency tasks first).")
        if (handoffs.any { it["status"] in CHECK_H }) return at("F13", "An AI's answer was read; check whether it is acceptable.")
        if (guide["continue"] is Map<*, *>) return at("F15", "The last answer was cut off; a continue prompt is ready.")
        val open = handoffs.filter { it["status"] in OPEN_H }
        if (open.isNotEmpty()) {
            return if (open.all { sent(st, it) }) at("F12", "Bring every AI's answer back and paste it.")
            else at("F11", "Give every AI its prompt (copy, send, then tap 'I sent it').")
        }
        if (tasks.any { it["status"] in setOf("in_review", "validation_pending") }) return at("F16", "Approve the checked work (review / verification).")
        if (tasks.any { it["status"] in setOf("needs_decision", "blocked") && !Json.str(it["blocked_reason"]).startsWith("waiting for") })
            return at("F21", "A task waits for a decision or is blocked.")
        if (tasks.any { it["status"] in setOf("ready", "in_progress") }) return at("F10", "Prompts for the next parallel tasks can be generated.")
        if (tasks.any { it["status"] in setOf("draft", "proposed") }) return at("F9", "The roadmap was split into tasks; approve them to start the parallel paths.")
        val milestones = State.coll(st, "milestones")
        if (milestones.values.any { Json.obj(it)["status"] == "planned" && Json.strs(Json.obj(it)["task_ids"]).isNotEmpty() })
            return at("F25", "All tasks of a roadmap stage are done; accept the milestone.")
        val readyVersion = State.coll(st, "versions").values.map { Json.obj(it) }.any { v ->
            v["status"] !in setOf("released", "withdrawn") && Json.strs(v["milestone_ids"]).isNotEmpty() &&
                Json.strs(v["milestone_ids"]).all { Json.obj(milestones[it])["status"] == "accepted" }
        }
        if (readyVersion) return at("F24", "A roadmap version is complete; publish it.")
        if (Json.int(st["state_revision"]) > Json.int(guide["manager_seen_revision"])) return at("F18", "Report the new state to the project manager.")
        return at("F25", "Ask the project manager whether any roadmap stage is left.")
    }

    fun label(p: Position): String {
        val kind = when (p.node.kind) { "app" -> "app"; "user" -> "you"; else -> "GitHub" }
        return "Flow ${p.node.id} · ${p.node.title} ($kind)" + if (p.cycle > 1) " · cycle ${p.cycle}" else ""
    }

    /** F1 → F2 → F4: record the start (once per cycle), the brief and the number of AIs; emit `project_started`. */
    fun startProject(store: ProjectStore, brief: Map<String, String>) {
        val goal = brief["goal"].orEmpty().trim()
        if (goal.isEmpty()) throw ModelError("goal is required")
        val aisRaw = brief["ais"].orEmpty().trim()
        var ais = 0
        if (aisRaw.isNotEmpty()) {
            ais = aisRaw.toIntOrNull() ?: throw ModelError("number of AIs must be a whole number")
            if (ais !in 1..Project.MAX_PARALLEL_CHATS) throw ModelError("number of AIs must be between 1 and ${Project.MAX_PARALLEL_CHATS}")
        }
        store.transaction("start project") { s ->
            val settings = Json.obj(s["settings"])
            val fs = Json.obj(settings.getOrPut("flow") { LinkedHashMap<String, Any?>() })
            val first = Json.str(fs["started_at"]).isEmpty()
            if (first) { fs["started_at"] = State.nowUtc(); if ("cycle" !in fs) fs["cycle"] = 1L }
            settings["goal"] = goal.take(2000)
            val b = Json.obj(settings.getOrPut("brief") { LinkedHashMap<String, Any?>() })
            for (k in listOf("name", "platform", "constraints")) {
                val v = brief[k].orEmpty().trim()
                if (v.isNotEmpty()) b[k] = v.take(2000)
            }
            if (ais > 0) Json.obj(settings.getOrPut("team") { LinkedHashMap<String, Any?>() })["max_parallel_chats"] = ais.toLong()
            if (first) State.emit(s, "project_started", "name" to Json.str(b["name"]), "cycle" to Json.int(fs["cycle"]).toLong(),
                "max_parallel_chats" to (if (ais > 0) ais.toLong() else null), "importance" to "major")
            else State.emit(s, "project_settings_updated", "field" to "brief")
        }
    }
}
