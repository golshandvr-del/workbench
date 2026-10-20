package io.github.golshandvr.aiworkbench.core

/**
 * GitHub blue nodes on the phone (roadmap 4.5.0 / mobile 1.6.0, flowchart F3, F22–F24).
 *
 * Port of the rules of desktop `aiwb/v2/repo.py`, checked against `packages/contracts/fixtures/repo/github-flow.v1.json`.
 * Without a token every blue node is shown as exact manual steps, then the user records the result (repository,
 * commit SHA, release). With a token (kept encrypted by `TokenVault`, Android Keystore) the same steps are sent by
 * [GitHubApi] — but only after the user confirms the exact write in a dialog.
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

    /** F24: mark a ready version released (manual record or after [sendRelease]); same facts as Project.advanceVersion. */
    fun recordRelease(store: ProjectStore, versionId: String, tag: String, commitSha: String = "", url: String = "", runId: String = ""): Obj =
        store.transaction("GitHub release") { s ->
            if (releaseNeeded(s).none { it["version_id"] == versionId }) throw ModelError("$versionId is not ready to release (all its milestones must be accepted)")
            val t = tag.trim().take(60)
            if (t.isEmpty()) throw ModelError("the tag is required")
            val v = State.require(s, "versions", versionId)
            val old = Json.str(v["status"])
            v["tag"] = t
            if (commitSha.isNotBlank()) v["commit_sha"] = commitSha.trim()
            if (runId.isNotBlank()) v["run_id"] = runId.trim().take(300)
            v["artifact"] = url.ifBlank { Json.str(v["artifact"]).ifEmpty { "github-release:$t" } }
            v["release"] = linkedMapOf<String, Any?>("tag" to t, "commit_sha" to v["commit_sha"], "url" to url, "at" to State.nowUtc())
            Json.list(v.getOrPut("history") { ArrayList<Any?>() }).add(linkedMapOf("from" to old, "to" to "released", "at" to State.nowUtc()))
            v["status"] = "released"; v["updated_at"] = State.nowUtc()
            State.emit(s, "release_published", "version_id" to versionId, "label" to v["label"], "old" to old, "new" to "released",
                "commit_sha" to v["commit_sha"], "run_id" to v["run_id"])
            v
        }

    // ---------------------------------------------------------------- with a token (each call = one confirmed write)
    fun sendConnect(store: ProjectStore, api: GitHubApi): Obj {
        val br = projectBranch(store.load())
        api.connect(br)
        return recordConnect(store, api.owner, api.repo, br)
    }

    fun sendSave(store: ProjectStore, api: GitHubApi, filesDir: java.io.File): String {
        val st = store.load()
        val br = Json.str(info(st)["branch"])
        val files = unsavedFiles(st).associateWith { java.io.File(filesDir, it) }.filterValues { it.isFile }.mapValues { it.value.readText() }
        if (files.isEmpty()) throw ModelError("the integrated files are no longer in the project folder")
        val sha = api.commitFiles(br, files, "AI Workbench: ${files.size} file(s)")
        recordSave(store, sha)
        return sha
    }

    fun sendRelease(store: ProjectStore, api: GitHubApi, versionId: String): Obj {
        val st = store.load()
        val v = releaseNeeded(st).firstOrNull { it["version_id"] == versionId } ?: throw ModelError("$versionId is not ready to release")
        val br = Json.str(info(st)["branch"])
        val sha = api.branchHead(br) ?: Json.str(info(st)["head"])
        val tag = "v" + Json.str(v["label"])
        val url = api.release(tag, sha, br, Json.str(v["label"]))
        return recordRelease(store, versionId, tag, sha, url)
    }
}
