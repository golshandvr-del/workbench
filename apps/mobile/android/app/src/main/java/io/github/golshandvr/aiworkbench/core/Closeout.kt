package io.github.golshandvr.aiworkbench.core

import java.io.File

/**
 * Completion, expansion or archive — the end of the owner's algorithm (roadmap 4.6.0 / mobile 1.7.0,
 * flowchart F26–F28). Port of desktop `aiwb/v2/closeout.py`.
 *
 * * F26 [announce] — only after the project manager's "complete" decision with no open task.
 * * F27 [expand] (yes → F1) — the finished cycle goes to `settings.flow.history`; an expansion prompt is built.
 * * F28 [archive] (no) — the final `aiwb-bundle.v1` is written to `archive/`; the store then refuses every write
 *   except [reopen].
 */
object Closeout {
    const val REOPEN_REASON = "reopen project"

    fun isArchived(st: Obj): Boolean = Json.str(Flow.settings(st)["archived_at"]).isNotEmpty()

    fun canAnnounce(st: Obj): Boolean {
        val fs = Flow.settings(st)
        val tasks = State.coll(st, "tasks")
        return Json.str(fs["completed_at"]).isEmpty() && Json.str(fs["archived_at"]).isEmpty() &&
            Json.str(Json.obj(fs["last_decision"])["route"]) == "complete" && tasks.isNotEmpty() &&
            tasks.values.all { Json.str(Json.obj(it)["status"]) in State.TERMINAL_TASK }
    }

    private fun relField(v: Obj, key: String): String = Json.str(v[key]).ifEmpty { Json.str(Json.obj(v["release"])[key]) }

    fun summary(st: Obj): Obj {
        val tasks = State.coll(st, "tasks").values.map { Json.obj(it) }
        val released = ArrayList<Any?>()
        for (v in State.coll(st, "versions").values.map { Json.obj(it) }.sortedBy { Json.str(it["version_id"]) }) {
            if (Json.str(v["status"]) != "released") continue
            released.add(linkedMapOf<String, Any?>("label" to Json.str(v["label"]), "tag" to relField(v, "tag"),
                "commit_sha" to relField(v, "commit_sha"),
                "evidence" to relField(v, "run_id").ifEmpty { relField(v, "artifact") }))
        }
        val files = ArrayList<String>()
        for (h in State.coll(st, "handoffs").values.map { Json.obj(it) }.sortedBy { Json.str(it["handoff_id"]) })
            for (p in Json.strs(h["integrated_files"])) if (p !in files) files.add(p)
        val fs = Flow.settings(st)
        return linkedMapOf("cycle" to maxOf(1, Json.int(fs["cycle"])).toLong(),
            "goal" to Json.str(Json.obj(st["settings"])["goal"]),
            "tasks_done" to tasks.count { Json.str(it["status"]) == "done" }.toLong(),
            "tasks_cancelled" to tasks.count { Json.str(it["status"]) in setOf("cancelled", "superseded") }.toLong(),
            "milestones_accepted" to State.coll(st, "milestones").values.count { Json.str(Json.obj(it)["status"]) == "accepted" }.toLong(),
            "versions_released" to released, "files" to ArrayList<Any?>(files.take(500)), "file_count" to files.size.toLong(),
            "repo" to Json.str(Json.obj(fs["repo"])["full_name"]))
    }

    fun summaryText(s: Obj): String {
        val rel = Json.list(s["versions_released"]).map { Json.obj(it) }.joinToString(", ") { v ->
            val ev = Json.str(v["evidence"])
            "${Json.str(v["label"])} (${Json.str(v["tag"]).ifEmpty { "no tag" }}${if (ev.isNotEmpty()) "; $ev" else ""})"
        }.ifEmpty { "none" }
        val repo = Json.str(s["repo"])
        return "Cycle ${Json.int(s["cycle"])} is complete: ${Json.int(s["tasks_done"])} task(s) done, " +
            "${Json.int(s["milestones_accepted"])} milestone(s) accepted, ${Json.int(s["file_count"])} file(s) in the project. " +
            "Released: $rel." + (if (repo.isNotEmpty()) " Repository: $repo." else "")
    }

    private fun flowOf(s: Obj): Obj = Json.obj(Json.obj(s["settings"]).getOrPut("flow") { LinkedHashMap<String, Any?>() })

    /** F26: record the completion and its summary on the timeline. */
    fun announce(store: ProjectStore): Obj {
        val st = store.load()
        if (!canAnnounce(st)) throw ModelError("the project is not complete yet: the project manager must decide that no roadmap stage is left and every task must be finished")
        val sum = summary(st)
        store.transaction("project completed") { s ->
            val fs = flowOf(s)
            fs["completed_at"] = State.nowUtc()
            fs["completion"] = sum
            State.emit(s, "project_completed", "cycle" to sum["cycle"], "tasks_done" to sum["tasks_done"],
                "versions" to ArrayList<Any?>(Json.list(sum["versions_released"]).map { Json.str(Json.obj(it)["label"]) }),
                "importance" to "major")
        }
        return sum
    }

    /** F27 "yes": a prompt for the next major cycle, with the whole history. */
    fun expansionPrompt(st: Obj, idea: String = ""): String {
        val fs = Flow.settings(st)
        val lines = mutableListOf("# AI Workbench — Expand the project (next major cycle)",
            "You are the Project Manager. The previous roadmap is complete. Plan the next major cycle on top of what exists; never redo finished work.",
            "", "State revision: ${Json.int(st["state_revision"])}", "Goal so far: ${Json.str(Json.obj(st["settings"])["goal"])}", "",
            "## History (from Workbench)")
        val hist = Json.list(fs["history"]).map { Json.obj(it) } + listOfNotNull((fs["completion"] as? Map<*, *>)?.let { Json.obj(it) })
        for (h in hist) lines.add("- " + summaryText(h))
        lines += listOf("", "## Files in the project") + Json.strs(summary(st)["files"]).take(80).map { "- $it" }
        lines += listOf("", "## The user's expansion idea", idea.trim().ifEmpty { "(none given — propose the most valuable next stage)" },
            "", "## Your task",
            "1. Say what changes in the architecture (new modules, paths each one owns).",
            "2. Create the new milestones (next major version) and the tasks of every AI, with dependencies, scope and acceptance criteria.",
            "3. Set roadmap_remaining to true while any stage of this cycle is left.",
            "", Prompts.MANAGER_FORMAT, "", Report.DECISION_FORMAT)
        return lines.joinToString("\n")
    }

    /** F27 "yes" → F1: keep the finished cycle in the history and open the next one. Returns (cycle, prompt). */
    fun expand(store: ProjectStore, idea: String = ""): Pair<Int, String> {
        val fs0 = Flow.settings(store.load())
        if (Json.str(fs0["completed_at"]).isEmpty() || Json.str(fs0["archived_at"]).isNotEmpty())
            throw ModelError("only a completed (not archived) project can be expanded")
        val cycle = store.transaction("project expanded") { s ->
            val fs = flowOf(s)
            val done: Obj = LinkedHashMap(Json.obj(fs["completion"]).ifEmpty { summary(s) })
            done["completed_at"] = Json.str(fs["completed_at"])
            Json.list(fs.getOrPut("history") { ArrayList<Any?>() }).add(done)
            val c = maxOf(1, Json.int(fs["cycle"])) + 1
            fs["cycle"] = c.toLong()
            fs["expansion"] = linkedMapOf<String, Any?>("open" to true, "idea" to idea.trim().take(2000), "at" to State.nowUtc())
            for (k in listOf("completed_at", "completion", "last_decision")) fs.remove(k)
            fs["roadmap_remaining"] = true
            State.emit(s, "project_expanded", "cycle" to c.toLong(), "importance" to "major")
            c
        }
        return cycle to expansionPrompt(store.load(), idea)
    }

    fun archiveFile(root: File, st: Obj): File =
        File(File(root, "archive"), "${Json.str(st["project_id"]).ifEmpty { "project" }}-final.aiwb-bundle.json")

    /** F28: final bundle + read-only. */
    fun archive(store: ProjectStore, version: String = ""): File {
        val fs = Flow.settings(store.load())
        if (Json.str(fs["archived_at"]).isNotEmpty()) throw ModelError("the project is already archived")
        if (Json.str(fs["completed_at"]).isEmpty()) throw ModelError("announce the completion first (F26)")
        store.transaction("project archived") { s ->
            flowOf(s)["archived_at"] = State.nowUtc()
            State.emit(s, "project_archived", "importance" to "major")
        }
        val final = store.load()
        val f = archiveFile(store.root, final)
        f.parentFile?.mkdirs()
        f.writeText(ProjectBundle.dumps(ProjectBundle.export(final, name = store.root.name, version = version)))
        return f
    }

    /** Leave the read-only state (the only write an archived project accepts). */
    fun reopen(store: ProjectStore) {
        store.transaction(REOPEN_REASON) { s ->
            val fs = flowOf(s)
            if (fs.remove("archived_at") == null) throw ModelError("the project is not archived")
            State.emit(s, "project_reopened", "importance" to "major")
        }
    }
}
