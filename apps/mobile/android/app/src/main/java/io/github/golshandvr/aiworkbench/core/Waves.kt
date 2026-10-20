package io.github.golshandvr.aiworkbench.core

/**
 * Parallel paths and waves (roadmap 4.1.0 / mobile 1.2.0, flowchart F9–F12) — port of desktop `aiwb/v2/waves.py`.
 *
 * Prompts are generated only for tasks whose prerequisites are done, and never for more chats than the user said
 * they can follow (`max_parallel_chats`). Pure functions of the state.
 */
object Waves {
    val OPEN_HANDOFF = setOf("prepared", "prompt_exported", "response_received", "parsed", "reconciled", "stale",
        "reconciliation_required")
    private val STARTABLE = setOf("ready", "in_progress")

    data class Layers(val waves: List<List<String>>, val cycle: List<String>, val dead: List<String>)

    data class Desk(val limit: Int, val active: List<String>, val slots: Int, val next: List<String>,
                    val queued: List<String>, val owners: Map<String, String>)

    fun owner(st: Obj, t: Obj): String {
        val agents = State.coll(st, "agents")
        val o = Json.str(t["owner_agent_id"])
        if (o.isNotEmpty() && o in agents && Json.obj(agents[o])["enabled"] != false) return o
        return if ("agent-implementer" in agents) "agent-implementer" else agents.keys.firstOrNull() ?: ""
    }

    private fun openTasks(st: Obj): Map<String, Obj> =
        State.coll(st, "tasks").mapValues { Json.obj(it.value) }.filterValues { Json.str(it["status"]) !in State.TERMINAL_TASK }

    fun lanes(st: Obj): Map<String, List<String>> {
        val out = LinkedHashMap<String, MutableList<String>>()
        val open = openTasks(st)
        for (tid in open.keys.sorted()) out.getOrPut(owner(st, open.getValue(tid))) { mutableListOf() }.add(tid)
        return out
    }

    fun waves(st: Obj): Layers {
        val tasks = State.coll(st, "tasks")
        val open = openTasks(st)
        val dead = open.filter { (_, t) ->
            Json.strs(t["depends_on"]).any { d -> d !in tasks || Json.str(Json.obj(tasks[d])["status"]) in setOf("cancelled", "superseded") }
        }.keys.sorted()
        val left = LinkedHashMap<String, MutableSet<String>>()
        for ((tid, t) in open) if (tid !in dead) left[tid] = Json.strs(t["depends_on"]).filter { it in open }.toMutableSet()
        val out = ArrayList<List<String>>()
        while (left.isNotEmpty()) {
            val layer = left.filterValues { it.isEmpty() }.keys.sorted()
            if (layer.isEmpty()) break
            out.add(layer)
            layer.forEach { left.remove(it) }
            left.values.forEach { it.removeAll(layer.toSet()) }
        }
        return Layers(out, left.keys.sorted(), dead)
    }

    fun maxChats(st: Obj): Int =
        ((Json.obj(Json.obj(st["settings"])["team"])["max_parallel_chats"] as? Number)?.toInt() ?: 2).coerceAtLeast(1)

    fun dispatch(st: Obj): Desk {
        val tasks = State.coll(st, "tasks")
        val handoffs = State.coll(st, "handoffs").values.map { Json.obj(it) }.filter { Json.str(it["status"]) in OPEN_HANDOFF }
        val busy = handoffs.map { Json.str(it["task_id"]) }.toSet()
        val limit = maxChats(st)
        val slots = (limit - handoffs.size).coerceAtLeast(0)
        val startable = waves(st).waves.flatten().filter { Json.str(Json.obj(tasks[it])["status"]) in STARTABLE && it !in busy }
        val first = ArrayList<String>(); val rest = ArrayList<String>(); val seen = HashSet<String>()
        val owners = LinkedHashMap<String, String>()
        for (tid in startable) {
            val who = owner(st, Json.obj(tasks[tid])); owners[tid] = who
            if (who in seen) rest.add(tid) else first.add(tid)
            seen.add(who)
        }
        val all = first + rest
        val pick = all.take(slots)
        return Desk(limit, handoffs.map { Json.str(it["handoff_id"]) }.sorted(), slots, pick, all.filter { it !in pick }, owners)
    }
}
