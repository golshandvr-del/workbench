package io.github.golshandvr.aiworkbench.core

/**
 * Status report to the project manager and routing of the manager's decision (roadmap 4.4.0 / mobile 1.5.0,
 * flowchart F18–F21, F25).
 *
 * Port of desktop `aiwb/v2/report.py`; both are checked against
 * `packages/contracts/fixtures/report/pm-decision.v1.json`.
 * Emergency → back to F10 with the emergency first; a stage left (or open work) → next wave; otherwise → F26.
 */
object Report {
    val ROUTES = listOf("emergency", "next_stage", "complete")
    private val TRUE = setOf("true", "yes", "y", "1")
    private val FALSE = setOf("false", "no", "n", "0", "none")

    const val DECISION_FORMAT = """## Your decision (required in the block)
Add two fields to the AIWB_MANAGER_PROPOSAL JSON:
- "roadmap_remaining": true if any roadmap stage is still left after this plan, false if the project is complete.
- "emergency_tasks": [] normally. Only for an urgent fix that must happen before anything else, list it as
  {"ref": "<temporary_ref of a create_task in this block, or an existing TASK- id>", "blocks": ["TASK-…"]} where
  "blocks" are the running tasks that must wait for it. Workbench gives it top priority and pauses those tasks."""

    fun parseRemaining(v: Any?): Boolean? = when (v) {
        is Boolean -> v
        is Number -> v.toDouble() != 0.0
        else -> {
            val s = (v?.toString() ?: "").trim().lowercase()
            if (s in TRUE) true else if (s in FALSE) false else null
        }
    }

    fun parseEmergency(v: Any?): List<Obj> {
        val out = ArrayList<Obj>()
        for (x in (v as? List<*>).orEmpty().take(20)) {
            if (x is String && x.isNotBlank()) out.add(linkedMapOf("ref" to x.trim().take(60), "blocks" to ArrayList<Any?>()))
            else if (x is Map<*, *>) {
                val ref = (Json.str(x["ref"]).ifBlank { Json.str(x["task_id"]) }).trim()
                if (ref.isEmpty()) continue
                val blocks = (x["blocks"] as? List<*>).orEmpty().map { (it?.toString() ?: "").trim().take(60) }.filter { it.isNotEmpty() }.take(40)
                out.add(linkedMapOf("ref" to ref.take(60), "blocks" to ArrayList<Any?>(blocks)))
            }
        }
        return out
    }

    fun route(emergency: Int, remaining: Boolean?, openTasks: Int): String = when {
        emergency > 0 -> "emergency"
        remaining == false && openTasks == 0 -> "complete"
        else -> "next_stage"
    }

    fun openTasks(st: Obj): List<String> =
        State.coll(st, "tasks").filterValues { Json.str(Json.obj(it)["status"]) !in State.TERMINAL_TASK }.keys.sorted()

    /** F18: facts for the status prompt, all from Workbench's own state. */
    fun sections(st: Obj): Map<String, List<String>> {
        val since = Json.str(Json.obj(Json.obj(st["settings"])["guide"])["manager_seen_at"])
        val integrated = ArrayList<String>(); val finished = ArrayList<String>(); val stuck = ArrayList<String>(); val github = ArrayList<String>()
        for (h in State.coll(st, "handoffs").values.map { Json.obj(it) }.sortedBy { Json.str(it["handoff_id"]) }) {
            val at = Json.str(h["integrated_at"])
            if (at.isNotEmpty() && at > since) {
                val files = Json.strs(h["integrated_files"])
                integrated.add("${h["task_id"]} (${h["handoff_id"]}): ${files.size} file(s)" + if (files.isNotEmpty()) " — " + files.take(8).joinToString(", ") else "")
            }
        }
        for ((tid, raw) in State.coll(st, "tasks").toSortedMap()) {
            val t = Json.obj(raw); val s = Json.str(t["status"]); val reason = Json.str(t["blocked_reason"])
            if (s == "done" && Json.str(t["updated_at"]) > since) finished.add("$tid — ${Json.str(t["title"])}")
            if (s == "needs_decision" || (s == "blocked" && !reason.startsWith("waiting for")))
                stuck.add("$tid — ${Json.str(t["title"])} ($s): ${reason.ifEmpty { "no reason recorded" }}")
        }
        val repo = Json.obj(Flow.settings(st)["repo"])
        val name = Json.str(repo["full_name"]).ifEmpty { Json.str(repo["url"]) }
        if (name.isNotEmpty()) github.add("Repository: $name" + (Json.str(repo["branch"]).takeIf { it.isNotEmpty() }?.let { " (branch $it)" } ?: ""))
        for (v in State.coll(st, "versions").values.map { Json.obj(it) }.sortedBy { Json.str(it["version_id"]) }) {
            if (v["status"] != "released") continue
            val rel = Json.obj(v["release"])
            github.add("Released ${v["label"]}" + (Json.str(rel["tag"]).takeIf { it.isNotEmpty() }?.let { " — tag $it" } ?: "") +
                (Json.str(rel["commit_sha"]).takeIf { it.isNotEmpty() }?.let { ", commit ${it.take(12)}" } ?: ""))
        }
        if (github.isEmpty()) github.add("No repository or release recorded yet.")
        return linkedMapOf("integrated" to integrated, "finished" to finished, "stuck" to stuck, "github" to github)
    }

    fun statusPrompt(st: Obj, update: String): String {
        val sec = sections(st)
        val lines = mutableListOf(update, "", "## Since your last report (from Workbench, not from model claims)")
        for ((head, key) in listOf("Files added to the project" to "integrated", "Tasks finished" to "finished",
            "Stuck tasks (need your plan)" to "stuck", "GitHub / releases" to "github")) {
            val items = sec[key].orEmpty()
            lines += listOf("", "### $head") + items.take(40).map { "- $it" } + (if (items.isEmpty()) listOf("- none") else emptyList())
        }
        lines += listOf("", "## What I need now",
            "Every planned task is finished or waiting. Propose the next step: fixes for stuck work, tasks for the next roadmap stage, " +
                "or say that the project is complete. Answer with one AIWB_MANAGER_PROPOSAL block (it may contain zero operations " +
                "only if roadmap_remaining is false).", "", DECISION_FORMAT)
        return lines.joinToString("\n")
    }

    /** Inside the review transaction: mark emergencies, pause what they block, record the route. */
    fun applyDecision(s: Obj, p: Obj, created: Map<String, Any?>): Obj {
        val tasks = State.coll(s, "tasks")
        val emergency = ArrayList<Any?>(); val paused = ArrayList<Any?>()
        fun res(r: String) = Json.str(created[r]).ifEmpty { r }
        for (e in Json.list(p["emergency_tasks"]).map { Json.obj(it) }) {
            val tid = res(Json.str(e["ref"]))
            val t = tasks[tid] as? MutableMap<*, *> ?: continue
            val task = Json.obj(t)
            if (Json.str(task["status"]) in State.TERMINAL_TASK) continue
            task["priority"] = "critical"
            val flags = Json.list(task.getOrPut("flags") { ArrayList<Any?>() })
            if ("emergency" !in flags) flags.add("emergency")
            emergency.add(tid)
            for (b in Json.strs(e["blocks"])) {
                val bt = Json.obj(tasks[res(b)] ?: continue)
                val bid = Json.str(bt["task_id"])
                if (bid == tid || Json.str(bt["status"]) !in setOf("ready", "in_progress", "blocked")) continue
                val deps = Json.list(bt.getOrPut("depends_on") { ArrayList<Any?>() })
                if (tid !in deps) deps.add(tid)
                val old = Json.str(bt["status"])
                if (old == "blocked" && !Json.str(bt["blocked_reason"]).startsWith("waiting for")) continue
                bt["status"] = "blocked"; bt["blocked_reason"] = "waiting for $tid (emergency)"; bt["updated_at"] = State.nowUtc()
                paused.add(bid)
                State.emit(s, "task_status", "task_id" to bid, "old" to old, "new" to "blocked", "why" to bt["blocked_reason"])
            }
        }
        val remaining = p["roadmap_remaining"] as? Boolean
        val r = route(emergency.size, remaining, openTasks(s).size)
        val settings = Json.obj(s["settings"])
        val fs = Json.obj(settings.getOrPut("flow") { LinkedHashMap<String, Any?>() })
        val last: Obj = linkedMapOf("route" to r, "proposal_id" to p["proposal_id"], "emergency" to emergency, "paused" to paused,
            "roadmap_remaining" to remaining, "at" to State.nowUtc())
        fs["last_decision"] = last
        if (remaining != null) fs["roadmap_remaining"] = remaining
        State.emit(s, "pm_decision", "proposal_id" to p["proposal_id"], "route" to r, "emergency" to ArrayList<Any?>(emergency),
            "paused" to ArrayList<Any?>(paused), "importance" to "major")
        return last
    }

    /** One sentence for the user after a plan with a decision was accepted (desktop `route_message`). */
    fun routeMessage(decision: Any?): String {
        val d = decision as? Map<*, *> ?: return ""
        return when (d["route"]) {
            "emergency" -> " Emergency: ${Json.strs(d["emergency"]).joinToString(", ")} goes first" +
                (Json.strs(d["paused"]).takeIf { it.isNotEmpty() }?.let { "; paused until it is done: ${it.joinToString(", ")}." } ?: ".")
            "complete" -> " The project manager says no roadmap stage is left — announce completion."
            else -> " Next roadmap stage: prompts for the next tasks can be generated."
        }
    }
}
