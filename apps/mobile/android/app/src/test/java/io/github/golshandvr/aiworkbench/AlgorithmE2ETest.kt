package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Closeout
import io.github.golshandvr.aiworkbench.core.Files
import io.github.golshandvr.aiworkbench.core.Flow
import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.ModelError
import io.github.golshandvr.aiworkbench.core.Obj
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.State
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.nio.file.Files as NioFiles

/**
 * Roadmap 4.7.0 gate (phone half, mobile 2.0.0): the whole owner's algorithm, end to end, through the Guide only —
 * the same story as desktop `test_algorithm_e2e.py`. Three scripted AIs (core, desktop, mobile) work in parallel under a
 * scripted project manager; every edge of `project-flow.v1` must be observed (troubleshooting, emergency, release,
 * "no release needed", next stage, completion, expansion and archive).
 */
class AlgorithmE2ETest {
    private val repo: File = run {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        requireNotNull(dir)
    }
    private val p = Project(ProjectStore(File(NioFiles.createTempDirectory("aiwb").toFile(), "todo"))).also { it.installTemplates() }
    private val g = Guide(p)
    private val edges = LinkedHashSet<Pair<String, String>>()
    private var seen = 0

    // ---------------------------------------------------------------- observation
    private fun st(): Obj = p.state()
    private fun node(): String = p.flow().id
    private fun at(expected: String) = assertEquals(expected, node())
    private fun events(): List<String> {
        val ev = Json.list(st()["events"])
        val out = ev.drop(seen).map { Json.str(Json.obj(it)["type"]) }
        seen = ev.size
        return out
    }
    private fun edge(a: String, b: String, ok: Boolean = true) {
        assertTrue("no evidence for edge $a -> $b", ok)
        edges.add(a to b)
    }
    private fun fs(): Obj = Flow.settings(st())
    private fun tasks(): Map<String, Any?> = State.coll(st(), "tasks")
    private fun status(tid: String) = Json.str(Json.obj(tasks()[tid])["status"])

    // ---------------------------------------------------------------- scripted chats
    private fun keys() = g.steps().map { it.key }
    private fun first(prefix: String) = keys().first { it.startsWith(prefix) }
    private fun act(key: String, action: String, vararg kv: Pair<String, String>) = g.perform(key, action, mapOf(*kv))
    private fun hstep(tid: String): String = g.steps().first { s ->
        s.key.startsWith("handoff:") && Json.obj(State.coll(st(), "handoffs")[s.ref])["task_id"] == tid
    }.key

    private fun answer(tid: String, files: List<String>, bad: Boolean = false): String {
        val h = State.coll(st(), "handoffs").values.map { Json.obj(it) }
            .first { it["task_id"] == tid && it["status"] in setOf("prepared", "prompt_exported") }
        val man = JSONObject().put("schema_version", "1.0").put("handoff_id", h["handoff_id"]).put("task_id", tid)
            .put("task_revision", Json.int(h["task_revision"])).put("attempt_id", h["attempt_id"]).put("outcome", "complete")
            .put("summary", "done").put("completed_items", JSONArray().put("x")).put("unresolved_items", JSONArray())
            .put("validation_claims", JSONArray().put("all tests pass"))
        val f4 = "````"
        val body = (if (bad) listOf("../outside.py") else files).joinToString("") {
            "<<<AIWB_FILE path=\"$it\" action=\"write\">>>\n$f4\nX = 1\n$f4\n<<<AIWB_END_FILE>>>\n"
        }
        return "AIWB_ATTEMPT_ID: ${h["attempt_id"]}\n$body<<<AIWB_HANDOFF>>>\n$man\n<<<AIWB_END_HANDOFF>>>\n"
    }

    private fun plan(ops: JSONArray, remaining: Boolean, emergency: JSONArray = JSONArray()): String {
        val o = JSONObject().put("schema_version", "1.0").put("base_state_revision", Json.int(st()["state_revision"]))
            .put("summary", "next").put("operations", ops).put("roadmap_remaining", remaining).put("emergency_tasks", emergency)
        return "Status read.\n<<<AIWB_MANAGER_PROPOSAL>>>\n$o\n<<<AIWB_END_MANAGER_PROPOSAL>>>"
    }

    private fun newTask(ref: String, title: String, include: String) = JSONObject().put("operation", "create_task")
        .put("temporary_ref", ref).put("title", title).put("objective", title).put("owner_role", "implementer")
        .put("acceptance_criteria", JSONArray().put("works")).put("scope", JSONObject().put("include", JSONArray().put(include)))

    /** F11 → F12 → F13 yes → F16 → F17 for one task. */
    private fun deliver(tid: String, files: List<String>) {
        val k = hstep(tid)
        act(k, "copy"); act(k, "sent")
        act(k, "paste", "text" to answer(tid, files))
        assertTrue(Json.list(Json.obj(State.coll(st(), "handoffs")[k.substringAfter(":")])["staged_files"]).isNotEmpty())
        act(k, "accept_handoff")
        act("task:$tid", "approve")
        act("task:$tid", "validation_passed", "run_id" to "ci-$tid")
        assertEquals("done", status(tid))
    }

    private fun save(sha: Char) {
        act("github:save", "record_save", "commit_sha" to sha.toString().repeat(40))
    }

    private fun release(tag: String, sha: Char) {
        act(first("github:release:"), "record_release", "tag" to tag, "commit_sha" to sha.toString().repeat(40), "run_id" to "ci-$tag")
    }

    /** F18 → F19 → F20 → F21: status prompt to the manager, its decision pasted and accepted. */
    private fun report(ops: JSONArray, remaining: Boolean, emergency: JSONArray = JSONArray()): Obj {
        at("F18")
        val step = g.find("manager_update")
        assertTrue(step.prompt.contains("roadmap_remaining"))
        act("manager_update", "copy")
        edge("F18", "F19", Json.obj(Json.obj(st()["settings"])["guide"]).containsKey("manager_copied_at"))
        act("manager_update", "sent")
        edge("F19", "F20", Json.obj(Json.obj(st()["settings"])["guide"]).containsKey("manager_sent_at"))
        val out = act("manager_update", "paste", "text" to plan(ops, remaining, emergency))
        assertEquals(out.message, "proposal", out.kind)
        at("F21")
        edge("F20", "F21")
        act(first("proposal:"), "accept")
        return Json.obj(fs()["last_decision"])
    }

    // ---------------------------------------------------------------- the walk
    @Test fun everyEdgeOfTheFlowchart() {
        // F1 → F2, F3, F4
        at("F1")
        act("design", "design", "goal" to "An offline todo app for desktop and mobile", "name" to "Todo", "ais" to "3")
        edge("F1", "F2", events().count { it == "project_started" } == 1)
        edge("F1", "F4", p.maxParallelChats() == 3)
        act("github:connect", "record_connect", "owner" to "o", "repo" to "todo")
        edge("F1", "F3", Json.str(Json.obj(fs()["repo"])["branch"]) == "aiwb/todo" && "github_connect" in events())
        // F4 → F5 → F6 → F7 → F8
        at("F5")
        edge("F4", "F5", g.find("charter").prompt.contains("AIWB_PROJECT_CHARTER"))
        act("charter", "copy"); at("F6"); edge("F5", "F6")
        act("charter", "sent"); at("F7"); edge("F6", "F7")
        val charter = JSONObject(File(repo, "packages/contracts/fixtures/valid/project-charter.v1.todo.json").readText())
        charter.put("base_state_revision", Json.int(st()["state_revision"]))
        act("charter", "paste", "text" to "<<<AIWB_PROJECT_CHARTER>>>\n$charter\n<<<AIWB_END_PROJECT_CHARTER>>>")
        at("F8"); edge("F7", "F8")
        assertTrue("nothing is created before the user checks the charter", tasks().isEmpty())
        // F8 → F9 → F10: three parallel paths, core first
        act(keys().first(), "accept")
        val (core, desk, mob) = tasks().keys.sorted()
        edge("F8", "F9", "charter_accepted" in events() && tasks().size == 3)
        at("F10")
        edge("F9", "F10", status(core) == "ready" && status(desk) == "blocked")
        // F10 → F11 → F12 → F13 no → F14 → F15 → F11
        act("task:$core", "prepare")
        at("F11"); edge("F10", "F11", "handoff_prepared" in events())
        var k = hstep(core)
        act(k, "copy"); act(k, "sent")
        at("F12"); edge("F11", "F12", "user_confirmed_sent" in events())
        val bad = act(k, "paste", "text" to answer(core, emptyList(), bad = true))
        assertTrue(bad.message, bad.message.contains("unsafe_path"))
        at("F13"); edge("F12", "F13", "handoff_ingested" in events())
        val s13 = g.find(hstep(core))
        edge("F13", "F14", s13.actions[0].id == "troubleshoot" && s13.explain.contains("Smart check"))
        val ts = act(s13.key, "troubleshoot")
        edge("F14", "F15", ts.prompt.contains("[unsafe_path]") && "troubleshooting_prompt" in events())
        at("F11"); edge("F15", "F11")
        // second try is good: F13 yes → F16 → F17
        k = hstep(core)
        act(k, "sent")
        act(k, "paste", "text" to answer(core, listOf("src/core/todo.py")))
        at("F13")
        act(k, "accept_handoff")
        at("F16")
        var ev = events()
        edge("F13", "F16", "handoff_accepted" in ev)
        edge("F16", "F17", "files_integrated" in ev && File(Files.dir(p.store), "src/core/todo.py").isFile)
        act("task:$core", "approve")
        act("task:$core", "validation_passed", "run_id" to "ci-core")
        save('1')
        assertTrue("github_save" in events())
        act(first("milestone:"), "accept_milestone")
        assertEquals(setOf("ready"), setOf(status(desk), status(mob)))
        release("v0.1.0", '1')
        assertTrue("release_published" in events())
        // the parallel wave: both UI prompts at once
        at("F10")
        val disp = act("dispatch", "prepare_all")
        assertTrue(disp.message, disp.message.startsWith("2 prompts ready"))
        deliver(desk, listOf("src/desktop/app.py"))
        deliver(mob, listOf("mobile/MainActivity.kt"))
        save('2')
        act(first("milestone:"), "accept_milestone")
        release("v0.2.0", '2')
        events()
        // F17 → F18: every planned task is finished
        edge("F17", "F18", g.find("manager_update").kind == "prompt")
        // F21 yes → F10: an emergency
        var d = report(JSONArray().put(newTask("fix", "Hotfix: data loss on rotate", "mobile/**")), true,
            JSONArray().put(JSONObject().put("ref", "fix").put("blocks", JSONArray())))
        assertEquals("emergency", d["route"])
        val fix = Json.strs(d["emergency"])[0]
        at("F10")
        edge("F21", "F10", "pm_decision" in events() && Json.obj(tasks()[fix])["priority"] == "critical")
        act("task:$fix", "prepare")
        deliver(fix, listOf("mobile/Store.kt"))  // not saved yet: GitHub steps never hold the manager update
        events()
        // next report: hotfix release 0.2.1 and a stage (sync) are left
        d = report(JSONArray().put(JSONObject().put("operation", "create_milestone").put("title", "Hotfix").put("version", "0.2.1")
            .put("criteria", JSONArray().put("no data loss")).put("task_refs", JSONArray().put(fix)))
            .put(newTask("sync", "Sync", "src/core/sync/**")), true)
        assertEquals("next_stage", d["route"])
        // F21 no → F22 → F23 yes → F24 → F25
        edge("F21", "F22", "github:save" in keys())
        save('3')
        edge("F22", "F23", "github_save" in events() && Json.str(Json.obj(fs()["repo"])["head"]) == "3".repeat(40))
        act(first("milestone:"), "accept_milestone")
        val rel = first("github:release:")
        edge("F23", "F24", rel == "github:release:VER-0003")
        release("v0.2.1", '3')
        ev = events()
        edge("F24", "F25", "release_published" in ev)
        assertEquals("ci-v0.2.1", Json.str(Json.obj(State.coll(st(), "versions")["VER-0003"])["run_id"]))
        // F25 yes → F10: stage 3 (sync)
        val sync = tasks().keys.max()
        at("F10")
        edge("F25", "F10", fs()["roadmap_remaining"] == true)
        act("task:$sync", "prepare")
        deliver(sync, listOf("src/core/sync/sync.py"))
        save('4')
        events()
        // no stage left: F21 no → F22 (saved) → F23 no → F25 no → F26
        d = report(JSONArray(), false)
        assertEquals("complete", d["route"])
        edge("F23", "F25", keys().none { it.startsWith("github:") })
        at("F26")
        edge("F25", "F26", keys() == listOf("closeout:announce"))
        act("closeout:announce", "announce")
        at("F27")
        val comp = Json.obj(fs()["completion"])
        edge("F26", "F27", "project_completed" in events() && Json.int(comp["tasks_done"]) == 5)
        assertEquals(listOf("0.1.0", "0.2.0", "0.2.1"), Json.list(comp["versions_released"]).map { Json.str(Json.obj(it)["label"]) })
        // F27 yes → F1: expansion opens cycle 2
        val exp = act("closeout:expand", "expand", "idea" to "Shared lists")
        assertTrue(exp.prompt.contains("Cycle 1 is complete"))
        edge("F27", "F1", "project_expanded" in events() && Json.int(fs()["cycle"]) == 2)
        // cycle 2: planned, finished, archived — F27 no → F28
        report(JSONArray().put(newTask("share", "Shared lists", "src/core/share/**")), false)
        val share = tasks().keys.max()
        act("task:$share", "prepare")
        deliver(share, listOf("src/core/share/share.py"))
        save('5')
        report(JSONArray(), false)
        act("closeout:announce", "announce")
        act("closeout:expand", "archive")
        at("F28")
        edge("F27", "F28", Closeout.archiveFile(p.store.root, st()).isFile && "project_archived" in events())
        try { p.createTask(linkedMapOf("title" to "late", "objective" to "x")); fail("archived project accepted a write") } catch (_: ModelError) { }

        // 100% of the shared contract's edges were observed
        val fx = JSONObject(File(repo, "packages/contracts/fixtures/flow/project-flow.v1.json").readText()).getJSONArray("edges")
        val want = (0 until fx.length()).map { fx.getJSONObject(it).let { e -> e.getString("from") to e.getString("to") } }.toSet()
        assertEquals(want, Flow.EDGES.map { it.from to it.to }.toSet())
        assertEquals("edges never walked", emptyList<Pair<String, String>>(), (want - edges).toList())
        assertEquals(32, want.size)
    }
}
