package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.Obj
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.Report
import io.github.golshandvr.aiworkbench.core.State
import io.github.golshandvr.aiworkbench.core.Waves
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** Roadmap 4.4.0 gate (phone half): status report and the project manager's decision — same cases as desktop `test_report.py`. */
class ReportTest {
    private fun fixture(): Obj {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        return Json.parseObj(File(requireNotNull(dir), "packages/contracts/fixtures/report/pm-decision.v1.json").readText())
    }

    @Test fun fixtureRemaining() {
        for (c in Json.list(fixture()["remaining"]).map { Json.obj(it) }) assertEquals(c.toString(), c["out"], Report.parseRemaining(c["in"]))
    }

    @Test fun fixtureEmergency() {
        for (c in Json.list(fixture()["emergency"]).map { Json.obj(it) }) {
            val got = Report.parseEmergency(c["in"]).map { mapOf("ref" to it["ref"], "blocks" to Json.strs(it["blocks"])) }
            val want = Json.list(c["out"]).map { Json.obj(it) }.map { mapOf("ref" to it["ref"], "blocks" to Json.strs(it["blocks"])) }
            assertEquals(c.toString(), want, got)
        }
    }

    @Test fun fixtureRoute() {
        val cases = Json.list(fixture()["route"]).map { Json.obj(it) }
        for (c in cases) assertEquals(c.toString(), c["out"], Report.route(Json.int(c["emergency"]), c["remaining"] as? Boolean, Json.int(c["open"])))
        assertEquals(Report.ROUTES.toSet(), cases.map { it["out"] }.toSet())
    }

    // ---------------------------------------------------------------- branches on a real project
    private lateinit var p: Project
    private var a = ""; private var b = ""

    private fun setUp() {
        p = Project(ProjectStore(File(Files.createTempDirectory("aiwb").toFile(), "r")))
        p.installTemplates()
        a = Json.str(p.createTask(linkedMapOf("title" to "Core", "objective" to "core", "allowed_paths" to arrayListOf<Any?>("src/a/"),
            "acceptance_criteria" to arrayListOf<Any?>("works")))["task_id"])
        b = Json.str(p.createTask(linkedMapOf("title" to "UI", "objective" to "ui", "allowed_paths" to arrayListOf<Any?>("src/b/"),
            "acceptance_criteria" to arrayListOf<Any?>("works")))["task_id"])
        p.transition(a, "ready", "t"); p.transition(b, "ready", "t")
        p.setMaxParallelChats(1)
        p.store.transaction("goal") { s -> Json.obj(s["settings"])["goal"] = "x" }
    }

    private fun block(ops: JSONArray, remaining: Any?, emergency: JSONArray = JSONArray()): String {
        val o = JSONObject().put("schema_version", "1.0").put("base_state_revision", Json.int(p.state()["state_revision"]))
            .put("summary", "s").put("operations", ops).put("roadmap_remaining", remaining).put("emergency_tasks", emergency)
        return "Analysis.\n<<<AIWB_MANAGER_PROPOSAL>>>\n$o\n<<<AIWB_END_MANAGER_PROPOSAL>>>"
    }

    private fun newTask(ref: String) = JSONObject().put("operation", "create_task").put("temporary_ref", ref).put("title", "T $ref")
        .put("objective", "o").put("owner_role", "implementer").put("acceptance_criteria", JSONArray().put("works"))
        .put("scope", JSONObject().put("include", JSONArray().put("src/$ref/**")))

    private fun pasteAndAccept(text: String): Obj {
        val r = p.routeAnswer(text)
        assertEquals(r.message, "proposal", r.kind)
        return p.acceptAllValid(r.ref)
    }

    @Test fun statusPromptHasSectionsAndContract() {
        setUp()
        p.store.transaction("t") { s ->
            val t = Json.obj(State.coll(s, "tasks")[b]); t["status"] = "blocked"; t["blocked_reason"] = "stuck after 3 troubleshooting prompts"
            Json.obj(s["settings"])["flow"] = linkedMapOf<String, Any?>("repo" to linkedMapOf<String, Any?>("full_name" to "me/app", "branch" to "aiwb/app"))
        }
        val st = p.state()
        State.coll(st, "handoffs")["H-9"] = linkedMapOf<String, Any?>("handoff_id" to "H-9", "task_id" to a, "status" to "accepted",
            "integrated_at" to "2099-01-01T00:00:00Z", "integrated_files" to arrayListOf<Any?>("src/a/x.py"))
        val sec = Report.sections(st)
        assertTrue(sec["integrated"]!!.any { "src/a/x.py" in it })
        assertTrue(sec["stuck"]!!.any { b in it })
        assertTrue("Repository: me/app (branch aiwb/app)" in sec["github"]!!)
        val prompt = Report.statusPrompt(st, p.managerUpdate())
        for (n in listOf("roadmap_remaining", "emergency_tasks", "Stuck tasks", "src/a/x.py", "AIWB_MANAGER_PROPOSAL")) assertTrue(n, n in prompt)
    }

    @Test fun emergencyBranch() {
        setUp()
        p.transition(a, "in_progress", "t")
        val out = pasteAndAccept(block(JSONArray().put(newTask("fix")), true,
            JSONArray().put(JSONObject().put("ref", "fix").put("blocks", JSONArray().put(a).put(b)))))
        val d = Json.obj(Json.obj(out["result"])["decision"])
        assertEquals("emergency", d["route"])
        val fix = Json.strs(d["emergency"]).single()
        val st = p.state(); val tasks = State.coll(st, "tasks")
        assertEquals("critical", Json.obj(tasks[fix])["priority"])
        assertTrue("emergency" in Json.strs(Json.obj(tasks[fix])["flags"]))
        for (tid in listOf(a, b)) {
            assertEquals("blocked", Json.obj(tasks[tid])["status"])
            assertTrue(Json.str(Json.obj(tasks[tid])["blocked_reason"]).startsWith("waiting for $fix"))
        }
        assertEquals(listOf(fix), Waves.dispatch(st).next)
        assertEquals("F10", p.flow().id)
    }

    @Test fun nextStageBranch() {
        setUp()
        val d = Json.obj(Json.obj(pasteAndAccept(block(JSONArray().put(newTask("n1")), true))["result"])["decision"])
        assertEquals("next_stage", d["route"])
        assertEquals("F10", p.flow().id)
    }

    @Test fun completeBranch() {
        setUp()
        p.store.transaction("t") { s -> for (tid in listOf(a, b)) Json.obj(State.coll(s, "tasks")[tid])["status"] = "done" }
        val out = pasteAndAccept(block(JSONArray(), false))
        assertEquals("accepted", out["status"])
        assertEquals("complete", Json.obj(Json.obj(out["result"])["decision"])["route"])
        assertEquals("F26", p.flow().id)
        assertTrue(Guide(p).steps().isNotEmpty())
    }

    @Test fun emptyPlanWithoutDecisionIsRefused() {
        setUp()
        val r = try { p.routeAnswer(block(JSONArray(), true)).kind } catch (e: Exception) { "error" }
        assertNotEquals("proposal", r)
    }
}
