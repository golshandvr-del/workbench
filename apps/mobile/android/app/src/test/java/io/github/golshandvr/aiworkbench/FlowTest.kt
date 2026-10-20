package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Flow
import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.State
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.nio.file.Files

/**
 * Roadmap 4.0.0 / mobile 1.1.0: the owner's algorithm (`project-flow.v1`) on the phone — same fixture as the desktop,
 * and a walk through F1 → F5 → F6 → F7 → F8.
 */
class FlowTest {
    private fun repo(): File {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        return requireNotNull(dir)
    }

    private fun project(): Project {
        val p = Project(ProjectStore(File(Files.createTempDirectory("aiwb").toFile(), "calc")))
        p.installTemplates()
        return p
    }

    @Test fun codeMatchesTheSharedFixture() {
        val f = JSONObject(File(repo(), "packages/contracts/fixtures/flow/project-flow.v1.json").readText())
        val phases = f.getJSONArray("phases")
        assertEquals(Flow.PHASES, (0 until phases.length()).map { phases.getString(it) })
        val nodes = f.getJSONArray("nodes")
        assertEquals(Flow.NODES.size, nodes.length())
        for (i in 0 until nodes.length()) {
            val n = nodes.getJSONObject(i)
            assertEquals(Flow.Node(n.getString("id"), n.getString("title"), n.getString("kind"), n.getString("phase")), Flow.NODES[i])
        }
        val edges = f.getJSONArray("edges")
        assertEquals(Flow.EDGES.size, edges.length())
        for (i in 0 until edges.length()) {
            val e = edges.getJSONObject(i)
            assertEquals(Flow.Edge(e.getString("from"), e.getString("to"), e.optString("when", "")), Flow.EDGES[i])
        }
        assertEquals(Flow.TROUBLESHOOT_ATTEMPTS, f.getJSONObject("limits").getInt("troubleshoot_attempts"))
    }

    @Test fun startToCharterReviewFollowsTheFlowchart() {
        val p = project()
        val g = Guide(p)
        val visited = mutableListOf(p.flow().id)
        val step = g.steps().first()
        assertEquals("design", step.key)
        assertEquals(listOf("goal", "name", "platform", "constraints", "ais"), step.actions.first().needs)
        for (n in step.actions.first().needs) assertTrue("hint for $n", Guide.INPUT_HINTS.containsKey(n))
        val out = g.perform("design", "design", mapOf("goal" to "A simple Android calculator", "name" to "Calc",
            "platform" to "Android, Kotlin", "ais" to "3"))
        assertTrue(out.prompt.contains("- Name: Calc"))
        assertTrue(out.prompt.contains("Platform / technology: Android, Kotlin"))
        assertTrue(out.prompt.contains("Maximum chats the user will follow at the same time: 3"))
        assertEquals(3, p.maxParallelChats())
        visited += p.flow().id
        g.perform("charter", "copy"); visited += p.flow().id
        g.perform("charter", "sent"); visited += p.flow().id
        val charter = JSONObject(File(repo(), "packages/contracts/fixtures/valid/project-charter.v1.todo.json").readText())
        charter.put("base_state_revision", Json.int(p.state()["state_revision"]))
        val r = g.perform("charter", "paste", mapOf("text" to "<<<AIWB_PROJECT_CHARTER>>>\n$charter\n<<<AIWB_END_PROJECT_CHARTER>>>"))
        assertEquals("proposal", r.kind)
        visited += p.flow().id
        assertEquals(listOf("F1", "F5", "F6", "F7", "F8"), visited)
        g.perform(g.steps().first().key, "accept")
        assertTrue(p.flow().id in setOf("F9", "F10"))
        val events = Json.list(p.state()["events"]).map { Json.str(Json.obj(it)["type"]) }
        assertEquals(1, events.count { it == "project_started" })
    }

    @Test fun numberOfAisIsValidatedAndTheTimelineStartsOnce() {
        val p = project()
        val g = Guide(p)
        for (bad in listOf("0", "13", "many")) {
            try { g.perform("design", "design", mapOf("goal" to "x", "ais" to bad)); fail(bad) } catch (e: Exception) { }
        }
        assertEquals("F1", p.flow().id)
        g.perform("design", "design", mapOf("goal" to "x"))
        g.perform("charter", "design", mapOf("goal" to "y", "name" to "Renamed"))
        val st = p.state()
        assertEquals("Renamed", Json.obj(Json.obj(st["settings"])["brief"])["name"])
        assertEquals(1, Json.list(st["events"]).count { Json.obj(it)["type"] == "project_started" })
    }

    @Test fun completedAndArchivedNodes() {
        val p = project()
        p.store.transaction("t") { s ->
            val settings = Json.obj(s["settings"])
            settings["goal"] = "x"
            settings["flow"] = linkedMapOf<String, Any?>("started_at" to "2026-10-20T00:00:00Z", "completed_at" to "2026-10-21T00:00:00Z")
        }
        assertEquals("F27", p.flow().id)
        p.store.transaction("t") { s -> Json.obj(Json.obj(s["settings"])["flow"])["archived_at"] = "2026-10-22T00:00:00Z" }
        assertEquals("F28", p.flow().id)
        assertTrue(Flow.label(p.flow()).startsWith("Flow F28"))
        assertTrue(State.coll(p.state(), "tasks").isEmpty())
    }
}
