package io.github.golshandvr.aiworkbench.core

/**
 * GitHub blue nodes on the phone (roadmap 4.5.0 / mobile 1.6.0, flowchart F3, F22–F24).
 *
 * Port of the rules of desktop `aiwb/v2/repo.py`, checked against `packages/contracts/fixtures/repo/github-flow.v1.json`.
 * The phone keeps **no GitHub token**: every blue node is shown as exact manual steps, then the user records the
 * result (repository, commit SHA). Releases (F24) use the existing version step (tag + run id are recorded facts).
 * Workbench never writes the default branch: files go to the project branch `aiwb/<project>`.
 */
object Repo {
    val PROTECTED = setOf("main", "master", "develop", "development", "trunk")
    private val NAME = Regex("^[A-Za-z0-9_.-]{1,100}$")
    private val SHA = Regex("^[0-9a-f]{7,64}$")

    fun validName(s: String): Boolean = NAME.matches(s)

    fun projectBranch(st: Obj): String {
        val raw = Json.str(Json.obj(Json.obj(st["settings"])["brief"])["name"]).ifEmpty { Json.str(st["project_id"]) }.ifEmpty { "project" }
        val slug = raw.lowercase().replace(Regex("[^a-z0-9-]+"), "-").trim('-').take(40).trim('-').ifEmpty { "project" }
        return "aiwb/$slug"
    }

    fun info(st: Obj): Obj = Json.obj(Json.obj(Json.obj(st["settings"])["flow"])["repo"])

    /** F22: integrated paths not yet recorded as saved on the project branch. */
    fun unsavedFiles(st: Obj): List<String> {
        val saved = Json.strs(info(st)["saved_handoffs"]).toSet()
        val out = ArrayList<String>()
        for (h in State.coll(st, "handoffs").values.map { Json.obj(it) }.sortedBy { Json.str(it["handoff_id"]) }) {
            if (Json.str(h["integrated_at"]).isEmpty() || Json.str(h["handoff_id"]) in saved) continue
            for (p in Json.strs(h["integrated_files"])) if (p !in out) out.add(p)
        }
        return out
    }

    /** F23: versions whose milestones are all accepted and that are not released / withdrawn. */
    fun releaseNeeded(st: Obj): List<Obj> {
        val ms = State.coll(st, "milestones")
        return State.coll(st, "versions").values.map { Json.obj(it) }.sortedBy { Json.str(it["version_id"]) }.filter { v ->
            val ids = Json.strs(v["milestone_ids"])
            v["status"] !in setOf("released", "withdrawn") && ids.isNotEmpty() && ids.all { Json.obj(ms[it])["status"] == "accepted" }
        }
    }

    fun manualSteps(kind: String, st: Obj): List<String> {
        val br = Json.str(info(st)["branch"]).ifEmpty { projectBranch(st) }
        return if (kind == "connect") listOf("Create (or open) the repository on github.com.", "Create the branch $br from the default branch.",
            "Record owner/name here.")
        else listOf("Commit these files to the branch $br (no force push, never to main): " + unsavedFiles(st).take(20).joinToString(", "),
            "Record the commit SHA here.")
    }

    /** F3 (manual): bind owner/name and the project branch. */
    fun recordConnect(store: ProjectStore, owner: String, name: String, branch: String = ""): Obj = store.transaction("GitHub connect") { s ->
        val o = owner.trim(); val n = name.trim()
        if (!validName(o) || !validName(n)) throw ModelError("owner and repository name may only use letters, digits, '-', '_' and '.'")
        val br = branch.trim().ifEmpty { projectBranch(s) }
        if (br in PROTECTED) throw ModelError("the project branch cannot be '$br'; Workbench never writes the default branch")
        val fs = Json.obj(Json.obj(s["settings"]).getOrPut("flow") { LinkedHashMap<String, Any?>() })
        val repo = Json.obj(fs.getOrPut("repo") { LinkedHashMap<String, Any?>() })
        repo["full_name"] = "$o/$n"; repo["branch"] = br; repo["connected_at"] = State.nowUtc(); repo["url"] = "https://github.com/$o/$n"
        State.emit(s, "github_connect", "url" to repo["url"], "manual" to true)
        repo
    }

    /** F22 (manual): the user committed the integrated files and records the commit SHA. */
    fun recordSave(store: ProjectStore, commitSha: String): Obj = store.transaction("GitHub save") { s ->
        val sha = commitSha.trim().lowercase()
        if (!SHA.matches(sha)) throw ModelError("the commit SHA is required (hex)")
        val repo = info(s)
        if (Json.str(repo["full_name"]).isEmpty()) throw ModelError("connect a repository first (F3)")
        if (unsavedFiles(s).isEmpty()) throw ModelError("no integrated file is waiting to be saved")
        val saved = Json.list(repo.getOrPut("saved_handoffs") { ArrayList<Any?>() })
        for (h in State.coll(s, "handoffs").values.map { Json.obj(it) })
            if (Json.str(h["integrated_at"]).isNotEmpty() && h["handoff_id"] !in saved) saved.add(h["handoff_id"])
        repo["head"] = sha; repo["saved_at"] = State.nowUtc()
        State.emit(s, "github_save", "commit_sha" to sha, "manual" to true)
        repo
    }
}
