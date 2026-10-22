package io.github.golshandvr.aiworkbench.core

/**
 * Mission Map model on the phone (roadmap 6.1.0 / mobile 3.1.0): parallel timelines, one lane per AI, one circle per
 * task in its version's column. Port of the desktop `aiwb/ui/mission_model.py`; `MissionModelTest` builds every case of
 * the shared fixture `packages/contracts/fixtures/mission/mission-map.v1.json` and must get the desktop's exact map.
 *
 * [build] returns plain JSON-like data (maps, lists, strings, longs, booleans) with the same keys as the desktop;
 * [layout] turns it into positions in dp. Reading the state never writes it.
 */
object MissionModel {
    val HIDDEN_TASK = setOf("cancelled", "superseded")
    val ACTIVE_TASK = setOf("ready", "in_progress", "in_review", "validation_pending")
    val OPEN_HANDOFF = setOf("prepared", "prompt_exported", "response_received", "parsed", "reconciled", "stale",
        "reconciliation_required")
    val NODE_STATES = listOf("done", "active", "blocked", "attention", "idle")
    const val LATER = "Later"
    const val NEXT = "Next"

    private val NUM = Regex("\\d+")

    /** Sort key of a version label: numbered labels in semantic order first, the rest by text. */
    private class SemKey(label: String) : Comparable<SemKey> {
        val nums: List<Long> = NUM.findAll(label).take(3).map { it.value.toBigInteger().toLong() }.toList()
        val group = if (nums.isEmpty()) 1 else 0
        val parts = (nums + listOf(0L, 0L, 0L)).take(3)
        val text = label
        override fun compareTo(other: SemKey): Int {
            if (group != other.group) return group.compareTo(other.group)
            for (i in 0 until 3) if (parts[i] != other.parts[i]) return parts[i].compareTo(other.parts[i])
            return text.compareTo(other.text)
        }
    }

    /** How a task circle looks: done (green tick) · active (glowing blue) · blocked · attention · idle (grey). */
    fun nodeState(task: Map<*, *>, handoffOpen: Boolean = false): String {
        val st = task["status"]
        return when {
            st == "done" -> "done"
            st == "blocked" -> "blocked"
            st == "needs_decision" -> "attention"
            st in ACTIVE_TASK || handoffOpen -> "active"
            else -> "idle"
        }
    }

    private fun s(v: Any?, default: String = ""): String = when (v) {
        null -> default
        is String -> v
        else -> v.toString()
    }

    private fun truthy(v: Any?): Boolean = when (v) {
        null -> false
        is Boolean -> v
        is String -> v.isNotEmpty()
        is Number -> v.toDouble() != 0.0
        is Map<*, *> -> v.isNotEmpty()
        is List<*> -> v.isNotEmpty()
        else -> true
    }

    private fun strOr(v: Any?, fallback: Any?): String = s(if (truthy(v)) v else fallback)

    private fun columns(state: Map<*, *>): Pair<MutableList<Obj>, Map<String, Int>> {
        val versions = Json.obj(state["versions"]).values.map { Json.obj(it) }.filter { it["status"] != "withdrawn" }
        val milestones = LinkedHashMap<Any?, Obj>()
        for (m in Json.obj(state["milestones"]).values.map { Json.obj(it) }) if (m["status"] != "dropped") milestones[m["milestone_id"]] = m
        val cols = ArrayList<Obj>()
        val ids = ArrayList<List<String>>()
        if (versions.isNotEmpty()) {
            for (v in versions.sortedBy { SemKey(s(it["label"])) }) {
                val t = ArrayList<String>(Json.list(v["task_ids"]).map { s(it) })
                for (mid in Json.list(v["milestone_ids"])) t += Json.list(milestones[mid]?.get("task_ids")).map { s(it) }
                cols.add(linkedMapOf("key" to s(v["version_id"]), "label" to s(v["label"]), "kind" to "version",
                    "status" to s(v["status"])))
                ids.add(t)
            }
        } else if (milestones.isNotEmpty()) {
            for (m in milestones.values.sortedBy { s(it["milestone_id"]) }) {
                cols.add(linkedMapOf("key" to s(m["milestone_id"]), "label" to strOr(m["title"], m["milestone_id"]),
                    "kind" to "milestone", "status" to s(m["status"])))
                ids.add(Json.list(m["task_ids"]).map { s(it) })
            }
        }
        val owner = LinkedHashMap<String, Int>()
        ids.forEachIndexed { i, t -> for (tid in t) owner.putIfAbsent(tid, i) }
        return cols to owner
    }

    private fun emptyCounts(): Obj = LinkedHashMap<String, Any?>().also { m -> for (k in NODE_STATES) m[k] = 0L }

    /**
     * The Mission Map as data: `columns`, `lanes` (each with its `nodes`), `slots` per column, `empty`, `counts`.
     * [hideDone] leaves finished circles out; [openOnly] leaves out lanes with no unfinished task. Lane numbers and
     * counts always describe the whole project (same as the desktop Home view options).
     */
    fun build(state: Map<*, *>?, hideDone: Boolean = false, openOnly: Boolean = false): Obj {
        if (state == null || state.isEmpty()) {
            return linkedMapOf("columns" to ArrayList<Any?>(), "lanes" to ArrayList<Any?>(), "slots" to ArrayList<Any?>(),
                "empty" to true, "counts" to emptyCounts())
        }
        val agents = Json.obj(state["agents"])
        val tasks = LinkedHashMap<String, Obj>()
        for ((tid, t) in Json.obj(state["tasks"])) { val o = Json.obj(t); if (s(o["status"]) !in HIDDEN_TASK) tasks[tid] = o }
        val openH = Json.obj(state["handoffs"]).values.map { Json.obj(it) }.filter { s(it["status"]) in OPEN_HANDOFF }
            .map { it["task_id"] }.toSet()
        val (cols, owner) = columns(state)
        if (cols.isEmpty()) cols.add(linkedMapOf("key" to "next", "label" to NEXT, "kind" to "next", "status" to ""))
        val unplaced = tasks.keys.any { it !in owner }
        if (unplaced && cols.any { it["kind"] != "next" }) {
            cols.add(linkedMapOf("key" to "later", "label" to LATER, "kind" to "later", "status" to ""))
        }
        val fallback = cols.size - 1
        val byLane = LinkedHashMap<String, MutableList<String>>()
        for (tid in tasks.keys.sorted()) {
            var aid = s(tasks.getValue(tid)["owner_agent_id"].takeIf { truthy(it) })
            if (aid.isEmpty() || (agents.isNotEmpty() && aid !in agents)) aid = "unassigned"
            byLane.getOrPut(aid) { ArrayList() }.add(tid)
        }
        if (byLane.isEmpty()) {  // a planned team without tasks still shows its lanes
            for (aid in agents.keys.sorted()) {
                val a = Json.obj(agents[aid])
                if (truthy(a["enabled"] ?: true) && a["role"] != "project_manager") byLane[aid] = ArrayList()
            }
        }
        val slots = MutableList(cols.size) { 1L }
        val lanes = ArrayList<Any?>()
        val counts = emptyCounts()
        val order = byLane.keys.sortedWith(compareBy<String>({ it == "unassigned" }, { it }))
        order.forEachIndexed { i, aid ->
            val ids = byLane.getValue(aid)
            val states = ids.map { nodeState(tasks.getValue(it), it in openH) }
            for (ns in states) counts[ns] = (counts[ns] as Long) + 1
            if (openOnly && ids.isNotEmpty() && states.all { it == "done" }) return@forEachIndexed
            val perCol = HashMap<Int, Int>()
            val nodes = ArrayList<Any?>()
            for ((tid, ns) in ids.zip(states)) {
                if (hideDone && ns == "done") continue
                val t = tasks.getValue(tid)
                val col = owner[tid] ?: fallback
                val slot = perCol[col] ?: 0
                perCol[col] = slot + 1
                slots[col] = maxOf(slots[col], (slot + 1).toLong())
                nodes.add(linkedMapOf("task_id" to tid, "title" to strOr(t["title"], tid), "status" to s(t["status"]),
                    "state" to ns, "column" to col.toLong(), "slot" to slot.toLong()))
            }
            val a = Json.obj(agents[aid])
            lanes.add(linkedMapOf("agent_id" to aid, "number" to (i + 1).toLong(), "name" to strOr(a["name"], aid),
                "role" to s(a["role"]), "nodes" to nodes, "live" to nodes.any { Json.obj(it)["state"] == "active" }))
        }
        return linkedMapOf("columns" to ArrayList<Any?>(cols), "lanes" to lanes, "slots" to ArrayList<Any?>(slots),
            "empty" to lanes.isEmpty(), "counts" to counts)
    }

    /** Positions of [build]'s result, in dp (multiply by density); same geometry as the desktop `layout`. */
    data class Layout(val capsuleX: Float, val capsuleW: Float, val midY: Float, val sourceX: Float, val hexX: Float,
                      val laneY: List<Float>, val colX: List<Float>, val endX: Float, val top: Float,
                      val nodes: Map<String, Pair<Float, Float>>, val width: Float, val height: Float)

    fun layout(model: Map<*, *>, scale: Float = 1f): Layout {
        val laneGap = Tokens5.GEOMETRY.getValue("lane_gap") * scale
        val colGap = Tokens5.GEOMETRY.getValue("col_gap") * scale
        val top = 64 * scale
        val capsuleX = 16 * scale
        val capsuleW = 132 * scale
        val sourceX = capsuleX + capsuleW + 22 * scale
        val hexX = sourceX + 72 * scale
        val firstX = hexX + 48 * scale
        val lanes = Json.list(model["lanes"]).map { Json.obj(it) }
        val n = maxOf(1, lanes.size)
        val laneY = List(n) { top + laneGap * (it + 0.5f) }
        val midY = (laneY.first() + laneY.last()) / 2
        val slots = Json.list(model["slots"]).map { Json.int(it) }
        val colX = ArrayList<Float>()
        var x = firstX
        for (k in slots) { colX.add(x); x += colGap * k }
        val endX = if (slots.isNotEmpty()) x - colGap + 46 * scale else firstX + 46 * scale
        val nodes = LinkedHashMap<String, Pair<Float, Float>>()
        lanes.forEachIndexed { i, lane ->
            for (nd in Json.list(lane["nodes"]).map { Json.obj(it) }) {
                nodes[s(nd["task_id"])] = (colX[Json.int(nd["column"])] + Json.int(nd["slot"]) * colGap) to laneY[i]
            }
        }
        return Layout(capsuleX, capsuleW, midY, sourceX, hexX, laneY, colX, endX, top, nodes, endX + 40 * scale,
            top + laneGap * n + 24 * scale)
    }
}
