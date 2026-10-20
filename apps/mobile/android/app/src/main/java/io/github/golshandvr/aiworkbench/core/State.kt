package io.github.golshandvr.aiworkbench.core

import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * The V2 project state document on the phone (roadmap mobile 1.0.0).
 *
 * Exactly the same JSON document as the desktop's `.workbench/v2/state.json` (`aiwb/v2/store.py`), kept as a plain
 * JSON tree so fields this app does not know survive every round trip. All writes go through [transaction]: one
 * write per change, `state_revision + 1`, events stamped with that revision (same rules as the desktop store).
 */
typealias Obj = MutableMap<String, Any?>

class ModelError(message: String) : Exception(message)

object Json {
    @Suppress("UNCHECKED_CAST")
    fun obj(v: Any?): Obj = v as? Obj ?: LinkedHashMap()
    @Suppress("UNCHECKED_CAST")
    fun list(v: Any?): MutableList<Any?> = v as? MutableList<Any?> ?: ArrayList()
    fun str(v: Any?): String = v as? String ?: ""
    fun int(v: Any?): Int = when (v) { is Number -> v.toInt(); is String -> v.toIntOrNull() ?: 0; else -> 0 }
    fun strs(v: Any?): List<String> = (v as? List<*>).orEmpty().mapNotNull { (it as? String)?.trim()?.ifEmpty { null } }
    fun parseObj(text: String): Obj {
        val v = StrictJson.copy(StrictJson.parse(text))
        @Suppress("UNCHECKED_CAST")
        return v as? Obj ?: throw ModelError("expected a JSON object")
    }
}

object State {
    const val SCHEMA_VERSION = "1.0"
    const val DB_VERSION = 1
    const val MAX_EVENTS = 2000
    val COLLECTIONS = listOf("agents", "tasks", "attempts", "handoffs", "decisions", "evidence", "proposals", "artifacts",
        "account_profiles", "chat_bindings", "milestones", "versions")
    val PREFIX = linkedMapOf("task" to "TASK", "handoff" to "HO", "decision" to "DEC", "evidence" to "EV",
        "proposal" to "PROP", "artifact" to "ART", "account_profile" to "ACC", "chat_binding" to "CHAT",
        "milestone" to "MS", "version" to "VER")
    val ROLES = listOf("project_manager", "architect", "implementer", "reviewer", "researcher")
    val TERMINAL_TASK = setOf("done", "cancelled", "superseded")
    private val AGENT_ID = Regex("^agent-[a-z0-9][a-z0-9-]{0,62}$")
    val PROJECT_ID = Regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")

    /** Task state machine — identical to desktop `models._T`. */
    val TASK_FLOW: Map<String, Set<String>> = mapOf(
        "draft" to setOf("proposed", "ready", "blocked", "needs_decision", "cancelled"),
        "proposed" to setOf("draft", "ready", "blocked", "needs_decision", "cancelled"),
        "ready" to setOf("in_progress", "blocked", "needs_decision", "cancelled", "superseded", "draft"),
        "in_progress" to setOf("in_review", "validation_pending", "blocked", "needs_decision", "ready", "cancelled", "superseded"),
        "blocked" to setOf("ready", "needs_decision", "cancelled", "superseded"),
        "needs_decision" to setOf("ready", "blocked", "in_progress", "cancelled", "superseded"),
        "in_review" to setOf("in_progress", "validation_pending", "done", "needs_decision", "blocked", "cancelled"),
        "validation_pending" to setOf("done", "in_progress", "in_review", "needs_decision", "blocked", "cancelled"),
        "done" to setOf("in_progress", "superseded"),
        "cancelled" to emptySet(),
        "superseded" to emptySet(),
    )

    var clock: () -> Date = { Date() }

    fun nowUtc(): String = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
        .apply { timeZone = TimeZone.getTimeZone("UTC") }.format(clock())

    fun validAgentId(v: Any?): Boolean = v is String && AGENT_ID.matches(v)

    fun defaultSettings(): Obj = linkedMapOf(
        "repair_round_limit" to 3L,
        "publish" to linkedMapOf<String, Any?>("enabled" to false, "branch" to "aiwb-state", "path" to ".aiwb",
            "interval_minutes" to 15L, "include_task_details" to true),
    )

    fun empty(projectId: String): Obj {
        val s: Obj = linkedMapOf("schema_version" to SCHEMA_VERSION, "db_version" to DB_VERSION.toLong(),
            "project_id" to projectId, "created_at" to nowUtc(), "state_revision" to 0L)
        s["counters"] = LinkedHashMap<String, Any?>().also { c -> PREFIX.values.forEach { c[it] = 0L } }
        COLLECTIONS.forEach { s[it] = LinkedHashMap<String, Any?>() }
        s["events"] = ArrayList<Any?>()
        s["settings"] = defaultSettings()
        s["migrations"] = ArrayList<Any?>()
        return s
    }

    /** Bring an older/partial document up to [DB_VERSION] without dropping fields (desktop `migrate_state`). */
    fun migrate(data: Obj, projectId: String): Obj {
        val st = Json.obj(StrictJson.copy(data))
        val version = st["db_version"]
        val v = if (version == null) 0 else (version as? Number)?.toInt() ?: throw ModelError("invalid db_version $version")
        if (v < 0) throw ModelError("invalid db_version $v")
        if (v > DB_VERSION) throw ModelError("the project was written by a newer AI Workbench (db_version $v); update this app")
        val base = empty(Json.str(st["project_id"]).ifEmpty { projectId })
        for ((k, d) in base) {
            if (k !in st || (k in COLLECTIONS && st[k] !is Map<*, *>)) {
                if (k in st && k in COLLECTIONS) Json.obj(st.getOrPut("_quarantine") { LinkedHashMap<String, Any?>() })[k] = st[k]
                st[k] = d
            }
        }
        val settings = Json.obj(st["settings"])
        for ((k, d) in defaultSettings()) if (k !in settings) settings[k] = d
        if (st["events"] !is List<*>) st["events"] = ArrayList<Any?>()
        val counters = Json.obj(st["counters"])
        PREFIX.values.forEach { if (it !in counters) counters[it] = 0L }
        if (v < 1) st["db_version"] = 1L
        return st
    }

    fun nextId(s: Obj, kind: String): String {
        val prefix = PREFIX.getValue(kind)
        val counters = Json.obj(s["counters"])
        val existing = Json.obj(s[if (kind == "evidence") "evidence" else kind + "s"])
        var n = Json.int(counters[prefix]) + 1
        while (String.format(Locale.US, "%s-%04d", prefix, n) in existing) n++
        counters[prefix] = n.toLong()
        return String.format(Locale.US, "%s-%04d", prefix, n)
    }

    fun coll(s: Obj, name: String): Obj = Json.obj(s[name])
    fun require(s: Obj, coll: String, id: String): Obj =
        Json.obj(coll(s, coll)[id] ?: throw ModelError("${coll.removeSuffix("s")} $id does not exist"))

    fun emit(s: Obj, type: String, vararg fields: Pair<String, Any?>) {
        val e: Obj = linkedMapOf("type" to type)
        for ((k, v) in fields) e[k] = v
        Json.list(s.getOrPut("_pending_events") { ArrayList<Any?>() }).add(e)
    }

    /** Derived readiness for a not-yet-started task (desktop `tasks.readiness`). */
    fun readiness(task: Obj, tasks: Obj): Pair<String, String> {
        val waiting = ArrayList<String>()
        val dead = ArrayList<String>()
        for (d in Json.strs(task["depends_on"])) {
            val dep = tasks[d] as? Map<*, *>
            when {
                dep == null -> dead.add("$d (missing)")
                dep["status"] in setOf("cancelled", "superseded") -> dead.add("$d (${dep["status"]})")
                dep["status"] != "done" -> waiting.add(d)
            }
        }
        if (dead.isNotEmpty()) return "blocked" to "prerequisite no longer valid: ${dead.joinToString(", ")} — re-plan this task"
        if (waiting.isNotEmpty()) return "blocked" to "waiting for ${waiting.joinToString(", ")}"
        return "ready" to ""
    }

    fun setTaskStatus(s: Obj, taskId: String, new: String, why: String) {
        val t = require(s, "tasks", taskId)
        val old = Json.str(t["status"])
        if (old == new) return
        if (new !in TASK_FLOW[old].orEmpty()) throw ModelError("task $taskId cannot move from $old to $new")
        t["status"] = new
        t["updated_at"] = nowUtc()
        if (new != "blocked") t["blocked_reason"] = ""
        emit(s, "task_status", "task_id" to taskId, "old" to old, "new" to new, "why" to why)
    }

    /** After a task finishes or is cancelled: unblock / block its dependants (desktop behaviour). */
    fun refreshReadiness(s: Obj) {
        val tasks = coll(s, "tasks")
        for (raw in tasks.values) {
            val t = Json.obj(raw)
            val st = Json.str(t["status"])
            val (r, why) = readiness(t, tasks)
            if (st == "blocked" && Json.str(t["blocked_reason"]).let { it.startsWith("waiting for") || it.startsWith("prerequisite") } && r == "ready") {
                setTaskStatus(s, Json.str(t["task_id"]), "ready", "prerequisites done")
            } else if (st == "ready" && r == "blocked") {
                setTaskStatus(s, Json.str(t["task_id"]), "blocked", why)
                t["blocked_reason"] = why
            } else if (st == "blocked" && r == "blocked") {
                t["blocked_reason"] = why
            }
        }
    }
}

/**
 * One project on the phone: `<root>/state.json` (+ `backups/`). Single-threaded by design (UI thread); every
 * mutation goes through [transaction].
 */
class ProjectStore(val root: File, projectId: String = "") {
    val path = File(root, "state.json")
    val projectId: String = projectId.ifEmpty { root.name }

    fun exists(): Boolean = path.isFile

    fun load(): Obj = if (!path.isFile) State.empty(projectId) else State.migrate(Json.parseObj(path.readText()), projectId)

    fun revision(): Int = Json.int(load()["state_revision"])

    fun write(state: Obj) {
        root.mkdirs()
        val tmp = File(root, ".state-${System.nanoTime()}.tmp")
        tmp.writeText(pretty(state))
        if (!tmp.renameTo(path)) {
            path.delete()
            if (!tmp.renameTo(path)) { tmp.delete(); throw ModelError("could not write ${path.name}") }
        }
    }

    fun backup(label: String): File? {
        if (!path.isFile) return null
        val dir = File(root, "backups").apply { mkdirs() }
        var target = File(dir, "state-${State.nowUtc().replace(":", "").replace("-", "")}-$label.json")
        var n = 1
        while (target.exists()) target = File(dir, "${target.nameWithoutExtension}-${n++}.json")
        path.copyTo(target)
        return target
    }

    /** Mutate a working copy; on a real change write once with `state_revision + 1` (desktop `transaction`). */
    fun <T> transaction(reason: String, block: (Obj) -> T): T {
        val state = load()
        val before = StrictJson.stringify(state, sortKeys = true)
        val work = Json.obj(StrictJson.copy(state))
        work["_pending_events"] = ArrayList<Any?>()
        val result = block(work)
        val events = Json.list(work.remove("_pending_events"))
        if (StrictJson.stringify(work, sortKeys = true) == before && events.isEmpty()) return result
        // roadmap 4.6.0 (F28): an archived project is read-only; only Closeout.reopen may change it
        if (Json.str(Json.obj(Json.obj(state["settings"])["flow"])["archived_at"]).isNotEmpty() && reason != "reopen project")
            throw ModelError("the project is archived (read-only); reopen it first")
        val rev = Json.int(state["state_revision"]) + 1
        work["state_revision"] = rev.toLong()
        val stamp = State.nowUtc()
        val list = Json.list(work["events"])
        val toAdd = if (events.isEmpty()) listOf<Any?>(linkedMapOf<String, Any?>("type" to "change")) else events
        for (raw in toAdd) {
            val e = Json.obj(raw)
            if ("at" !in e) e["at"] = stamp
            e["state_revision"] = rev.toLong()
            e["reason"] = reason
            list.add(e)
        }
        while (list.size > State.MAX_EVENTS) list.removeAt(0)
        work["events"] = list
        write(work)
        return result
    }

    companion object {
        /** Indented, sorted JSON (same layout idea as the desktop's `indent=1, sort_keys=True`). */
        fun pretty(v: Any?): String {
            val sb = StringBuilder()
            fun w(x: Any?, ind: Int) {
                when (x) {
                    is Map<*, *> -> {
                        if (x.isEmpty()) { sb.append("{}"); return }
                        sb.append("{\n")
                        val keys = x.keys.map { it.toString() }.sorted()
                        keys.forEachIndexed { i, k ->
                            sb.append(" ".repeat(ind + 1)); StrictJson.quote(sb, k); sb.append(": "); w(x[k], ind + 1)
                            if (i < keys.size - 1) sb.append(",")
                            sb.append("\n")
                        }
                        sb.append(" ".repeat(ind)).append("}")
                    }
                    is List<*> -> {
                        if (x.isEmpty()) { sb.append("[]"); return }
                        sb.append("[\n")
                        x.forEachIndexed { i, y ->
                            sb.append(" ".repeat(ind + 1)); w(y, ind + 1)
                            if (i < x.size - 1) sb.append(",")
                            sb.append("\n")
                        }
                        sb.append(" ".repeat(ind)).append("]")
                    }
                    else -> sb.append(StrictJson.stringify(x))
                }
            }
            w(v, 0)
            return sb.append("\n").toString()
        }
    }
}
