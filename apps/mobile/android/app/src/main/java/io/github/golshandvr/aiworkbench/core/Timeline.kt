package io.github.golshandvr.aiworkbench.core

import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/**
 * Timeline model for the phone (roadmap 3.6.0 / mobile 1.0.0; same rules as desktop `ui/timeline_canvas.build_model`).
 *
 * One lane per AI (plus "project"), every state event is a dot whose size shows its importance, every version is a
 * vertical line (dashed while planned, solid once released). Built from the state document's `events` so it needs
 * no desktop ledger. Pure: the Android view only draws it.
 */
object Timeline {
    val IMPORTANCE = listOf("minor", "normal", "major", "critical")
    val RADIUS = mapOf("minor" to 3, "normal" to 5, "major" to 8, "critical" to 11)
    private val CRITICAL = setOf("release_published", "charter_accepted")
    private val MAJOR = setOf("milestone_accepted", "version_created", "proposal_reviewed", "decision_accepted", "decision_rejected",
        "handoff_accepted", "handoff_rejected", "milestone_created", "version_proposed", "version_withdrawn")
    private val NORMAL_PREFIX = listOf("task_", "handoff_", "evidence_", "decision_", "attempt_", "user_confirmed_sent", "prompt_")

    data class Event(val index: Int, val type: String, val lane: String, var t: Double, val importance: String,
                     val dated: Boolean, val label: String, val whenText: String, val revision: Int)

    data class Version(val id: String, val label: String, val t: Double, val released: Boolean, val status: String)

    data class Model(val events: List<Event>, val versions: List<Version>, val lanes: List<String>, val t0: Double, val t1: Double)

    fun importance(e: Map<*, *>): String {
        val explicit = Json.str(e["importance"])
        if (explicit in IMPORTANCE) return explicit
        val et = Json.str(e["type"])
        if (et in CRITICAL || (et == "task_status" && e["new"] == "done")) return "critical"
        if (et in MAJOR || (et == "task_status" && e["new"] in setOf("blocked", "needs_decision"))) return "major"
        if (NORMAL_PREFIX.any { et.startsWith(it) }) return "normal"
        return "minor"
    }

    fun ts(s: String?): Double? {
        if (s.isNullOrBlank()) return null
        return try {
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }
                .parse(s)?.time?.div(1000.0)
        } catch (_: Exception) { null }
    }

    fun build(state: Obj): Model {
        val tasks = State.coll(state, "tasks")
        val attempts = State.coll(state, "attempts")
        val handoffs = State.coll(state, "handoffs")
        val owner = tasks.mapValues { Json.str(Json.obj(it.value)["owner_agent_id"]) }
        val events = ArrayList<Event>()
        var last: Double? = null
        val undated = ArrayList<Event>()
        Json.list(state["events"]).forEachIndexed { i, raw ->
            val e = Json.obj(raw)
            val taskId = Json.str(e["task_id"]).ifEmpty { Json.str(Json.obj(attempts[e["attempt_id"]])["task_id"]) }
                .ifEmpty { Json.str(Json.obj(handoffs[e["handoff_id"]])["task_id"]) }
            val lane = Json.str(e["agent_id"]).ifEmpty { Json.str(e["to_agent_id"]) }
                .ifEmpty { Json.str(Json.obj(attempts[e["attempt_id"]])["agent_id"]) }
                .ifEmpty { owner[taskId].orEmpty() }.ifEmpty { "project" }
            val t = ts(e["at"] as? String)
            val ref = taskId.ifEmpty { Json.str(e["version_id"]) }.ifEmpty { Json.str(e["milestone_id"]) }.ifEmpty { Json.str(e["proposal_id"]) }
            val extra = if (e["type"] == "task_status") " → ${e["new"]}" else ""
            val ev = Event(i, Json.str(e["type"]), lane, t ?: 0.0, importance(e), t != null, "${e["type"]} $ref$extra".trim(),
                Json.str(e["at"]).ifEmpty { "time unknown (legacy)" }, Json.int(e["state_revision"]))
            if (t == null) { if (last == null) undated.add(ev) else ev.t = last!! }
            else { last = t; undated.forEach { it.t = t }; undated.clear() }
            events.add(ev)
        }
        val versions = ArrayList<Version>()
        for (v in State.coll(state, "versions").values.map { Json.obj(it) }.sortedBy { Json.str(it["version_id"]) }) {
            if (v["status"] == "withdrawn") continue
            val released = Json.list(v["history"]).map { Json.obj(it) }.firstOrNull { it["to"] == "released" }?.let { Json.str(it["at"]) } ?: ""
            val t = if (released.isNotEmpty()) ts(released) else ts(v["created_at"] as? String)
            if (t == null) continue
            versions.add(Version(Json.str(v["version_id"]), Json.str(v["label"]), t, released.isNotEmpty(), Json.str(v["status"])))
        }
        var lanes = listOf("project") + events.map { it.lane }.filter { it != "project" }.toSortedSet()
        if (events.none { it.lane == "project" } && lanes.size > 1) lanes = lanes.drop(1)
        val times = events.map { it.t } + versions.map { it.t }
        var t0 = times.minOrNull() ?: 0.0
        var t1 = times.maxOrNull() ?: 1.0
        if (times.isEmpty()) { t0 = 0.0; t1 = 1.0 }
        if (t1 <= t0) t1 = t0 + 1.0
        return Model(events, versions, lanes, t0, t1)
    }
}
