package io.github.golshandvr.aiworkbench.core

import java.security.MessageDigest

/**
 * Project bundle `aiwb-bundle.v1` (roadmap 3.8.0 / mobile 1.0.0) — port of desktop `aiwb/v2/bundle.py`.
 *
 * The state travels as the string `state_json`; integrity is `state_sha256` over its exact UTF-8 bytes. Import never
 * merges: [planImport] says new / same / newer / older / diverged / other_project and only the first three are safe.
 */
object ProjectBundle {
    const val TYPE = "aiwb-bundle"
    const val VERSION = 1
    const val MAX_BYTES = 8 * 1024 * 1024
    const val MOBILE_APP = "ai-workbench-mobile"
    const val DESKTOP_APP = "ai-workbench-desktop"

    class BundleError(message: String) : Exception(message)

    data class Plan(val kind: String, val safe: Boolean, val localRevision: Int, val bundleRevision: Int, val message: String)

    fun sha256Hex(text: String): String =
        MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    fun export(state: Obj, name: String = "", app: String = MOBILE_APP, version: String = ""): Obj {
        val st = LinkedHashMap<String, Any?>()
        for ((k, v) in state) if (!k.startsWith("_pending")) st[k] = v
        val pid = Json.str(st["project_id"]).ifEmpty { "project" }
        val text = StrictJson.stringify(st, sortKeys = true)
        return linkedMapOf("schema_version" to "1.0", "bundle_type" to TYPE, "bundle_version" to VERSION.toLong(),
            "created_at" to State.nowUtc(), "producer" to linkedMapOf<String, Any?>("app" to app, "version" to version.ifEmpty { "0" }),
            "project" to linkedMapOf<String, Any?>("project_id" to pid, "name" to name.ifEmpty { pid }.take(120),
                "state_revision" to Json.int(st["state_revision"]).toLong()),
            "state_json" to text, "state_sha256" to sha256Hex(text))
    }

    /** Pretty text (the bundle file the user moves between devices). */
    fun dumps(bundle: Obj): String = ProjectStore.pretty(bundle)

    /** Validate a bundle and return `(bundle, migrated state)`. Throws [BundleError] with a precise reason. */
    fun read(data: String): Pair<Obj, Obj> {
        if (data.toByteArray(Charsets.UTF_8).size > MAX_BYTES) throw BundleError("the bundle is larger than 8 MB")
        val b = try {
            Json.parseObj(data.trimStart('\ufeff'))
        } catch (e: StrictJson.ParseError) {
            throw BundleError("the bundle is not valid JSON (${e.message})")
        } catch (_: ModelError) {
            throw BundleError("the bundle must be a JSON object")
        }
        if (b["bundle_type"] != TYPE) throw BundleError("this file is not an AI Workbench project bundle (bundle_type)")
        val ver = b["bundle_version"]
        if (ver !is Long || ver != VERSION.toLong()) throw BundleError("unsupported bundle_version $ver; update AI Workbench")
        val text = b["state_json"] as? String
        if (text.isNullOrEmpty()) throw BundleError("state_json is missing")
        if (b["state_sha256"] != sha256Hex(text)) throw BundleError("the bundle is damaged: state_sha256 does not match state_json")
        val state = try {
            Json.parseObj(text)
        } catch (e: StrictJson.ParseError) {
            throw BundleError("state_json is not valid JSON (${e.message})")
        } catch (_: ModelError) {
            throw BundleError("state_json must hold a JSON object")
        }
        val pid = state["project_id"] as? String
        if (pid == null || !State.PROJECT_ID.matches(pid)) throw BundleError("the project_id in the bundle is not valid")
        if (Json.obj(b["project"])["project_id"] != pid) throw BundleError("project.project_id does not match the state")
        if (Json.int(state["db_version"]) > State.DB_VERSION) throw BundleError("the bundle was written by a newer AI Workbench; update this app")
        val migrated = try { State.migrate(state, pid) } catch (e: ModelError) { throw BundleError(e.message ?: "invalid state") }
        return b to migrated
    }

    private fun eventKey(e: Any?): Triple<Any?, Any?, Any?> {
        val m = e as? Map<*, *> ?: return Triple(null, null, null)
        return Triple((m["state_revision"] as? Number)?.toLong(), m["type"], m["at"])
    }

    /** True if [child] was derived from [parent] (or parent is empty). */
    fun descends(child: Obj, parent: Obj): Boolean {
        if (Json.int(parent["state_revision"]) == 0) return true
        val last = Json.list(parent["events"]).lastOrNull() ?: return false
        val key = eventKey(last)
        return Json.int(child["state_revision"]) >= Json.int(parent["state_revision"]) &&
            Json.list(child["events"]).any { eventKey(it) == key }
    }

    private fun comparable(state: Obj): String {
        val out = LinkedHashMap<String, Any?>(state)
        out["settings"] = Json.obj(state["settings"]).filterKeys { it != "sync" }
        return StrictJson.stringify(out, sortKeys = true)
    }

    fun planImport(local: Obj?, incoming: Obj): Plan {
        val revIn = Json.int(incoming["state_revision"])
        if (local == null || listOf("tasks", "proposals", "milestones", "handoffs").none { (local[it] as? Map<*, *>)?.isNotEmpty() == true }) {
            return Plan("new", true, 0, revIn, "Import the project (revision $revIn).")
        }
        val revLocal = Json.int(local["state_revision"])
        if (local["project_id"] != incoming["project_id"]) {
            return Plan("other_project", false, revLocal, revIn, "This bundle is project '${incoming["project_id"]}', " +
                "not '${local["project_id"]}'. Import it into an empty project instead.")
        }
        if (comparable(local) == comparable(incoming)) return Plan("same", true, revLocal, revIn, "The project is already up to date.")
        if (revIn > revLocal && descends(incoming, local)) {
            return Plan("newer", true, revLocal, revIn, "Update the project from revision $revLocal to $revIn (a backup is kept).")
        }
        if (descends(local, incoming)) {
            return Plan("older", false, revLocal, revIn, "The bundle (revision $revIn) is older than this project " +
                "(revision $revLocal); importing it would lose local work.")
        }
        return Plan("diverged", false, revLocal, revIn, "Both copies changed since they last matched (here revision $revLocal, " +
            "bundle $revIn). Workbench does not merge: importing replaces this copy (a backup is kept).")
    }

    /** Import into [store]. Unsafe kinds need [force] (older/diverged only); a backup is written before replacing. */
    fun importInto(store: ProjectStore, data: String, force: Boolean = false): Pair<Plan, Boolean> {
        val (b, incoming) = read(data)
        val local = try { if (store.exists()) store.load() else null } catch (_: Exception) { null }
        val plan = planImport(local, incoming)
        if (plan.kind == "same") return plan to false
        if (!plan.safe && !(force && plan.kind in setOf("older", "diverged"))) throw BundleError(plan.message)
        if (store.exists()) store.backup("pre-bundle-import")
        val settings = Json.obj(incoming["settings"])
        val sync = LinkedHashMap<String, Any?>(Json.obj(settings["sync"]))
        sync["last_import_at"] = State.nowUtc()
        sync["last_import_revision"] = Json.int(incoming["state_revision"]).toLong()
        sync["last_import_from"] = Json.str(Json.obj(b["producer"])["app"]).take(40)
        settings["sync"] = sync
        incoming["settings"] = settings
        store.write(incoming)
        return plan to true
    }
}
