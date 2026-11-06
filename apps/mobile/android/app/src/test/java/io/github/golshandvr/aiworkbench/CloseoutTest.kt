package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Closeout
import io.github.golshandvr.aiworkbench.core.Flow
import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.ModelError
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectBundle
import io.github.golshandvr.aiworkbench.core.ProjectStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** Roadmap 4.6.0 gate (phone half, mobile 1.7.0): F26 announce, F27 expand, F28 archive — same rules as desktop `test_closeout.py`. */
class CloseoutTest {
    private fun project(): Project {
        val p = Project(ProjectStore(File(Files.createTempDirectory("aiwb").toFile(), "r")))
        p.installTemplates()
        p.store.transaction("seed") { s ->
            Json.obj(s["settings"])["goal"] = "A calculator"
            Json.obj(s["tasks"])["TASK-1"] = linkedMapOf<String, Any?>("task_id" to "TASK-1", "title" to "Core", "status" to "done",
                "owner_agent_id" to "agent-implementer")
            Json.obj(s["handoffs"])["H-1"] = linkedMapOf<String, Any?>("handoff_id" to "H-1", "task_id" to "TASK-1", "status" to "accepted",
                "to_agent_id" to "agent-implementer", "integrated_at" to "2026-01-01T00:00:00Z", "integrated_files" to arrayListOf<Any?>("src/calc.kt"))
            Json.obj(s["versions"])["VER-1"] = linkedMapOf<String, Any?>("version_id" to "VER-1", "label" to "1.0.0", "status" to "released",
                "tag" to "v1.0.0", "commit_sha" to "a".repeat(40), "run_id" to "run-7", "milestone_ids" to arrayListOf<Any?>())
        }
        return p
    }

    private fun decideComplete(p: Project) = p.store.transaction("decision") { s ->
        Json.obj(Json.obj(s["settings"]).getOrPut("flow") { LinkedHashMap<String, Any?>() })["last_decision"] =
            linkedMapOf<String, Any?>("route" to "complete", "proposal_id" to "P-1")
    }

    @Test fun notOfferedBeforeTheManagersDecision() {
        val p = project()
        assertFalse(Closeout.canAnnounce(p.state()))
        assertFalse(Guide(p).steps().any { it.key == "closeout:announce" })
        try { Closeout.announce(p.store); fail("announced without decision") } catch (_: ModelError) { }
    }

    @Test fun announceExpandArchiveReopen() {
        val p = project(); val g = Guide(p)
        decideComplete(p)
        assertEquals(listOf("closeout:announce"), g.steps().map { it.key })
        assertTrue(g.steps()[0].explain.contains("1.0.0 (v1.0.0; run-7)"))
        g.perform("closeout:announce", "announce")
        val fs = Flow.settings(p.state())
        assertEquals(1, Json.int(Json.obj(fs["completion"])["tasks_done"]))
        assertEquals(listOf("src/calc.kt"), Json.strs(Json.obj(fs["completion"])["files"]))
        assertTrue(Json.list(p.state()["events"]).any { Json.obj(it)["type"] == "project_completed" })
        assertEquals(listOf("closeout:expand"), g.steps().map { it.key })

        val out = g.perform("closeout:expand", "expand", mapOf("idea" to "Add a scientific mode"))
        for (n in listOf("next major cycle", "Add a scientific mode", "Cycle 1 is complete", "src/calc.kt", "AIWB_MANAGER_PROPOSAL", "roadmap_remaining"))
            assertTrue(n, out.prompt.contains(n))
        val fs2 = Flow.settings(p.state())
        assertEquals(2, Json.int(fs2["cycle"])); assertEquals(1, Json.list(fs2["history"]).size)
        assertFalse("completed_at" in fs2)
        assertFalse(g.steps().any { it.key.startsWith("closeout:") })

        // finish cycle 2 and archive
        decideComplete(p)
        g.perform("closeout:announce", "announce")
        val msg = g.perform("closeout:expand", "archive").message
        assertTrue(msg, msg.contains("Archived"))
        val f = Closeout.archiveFile(p.store.root, p.state())
        assertTrue(f.isFile)
        val (_, st) = ProjectBundle.read(f.readText())
        assertTrue(Closeout.isArchived(st))
        assertEquals(listOf("closeout:archived"), g.steps().map { it.key })
        val rev = p.store.revision()
        try { p.store.transaction("edit") { s -> Json.obj(s["settings"])["goal"] = "changed" }; fail("archived project changed") } catch (_: ModelError) { }
        assertEquals(rev, p.store.revision())
        g.perform("closeout:archived", "reopen")
        assertFalse(Closeout.isArchived(p.state()))
        p.store.transaction("edit") { s -> Json.obj(s["settings"])["goal"] = "changed" }
    }
    // BF-082: open milestones and an unreleased version are offered before the completion is announced
    private fun planOpenItems(p: Project) = p.store.transaction("plan") { s ->
        Json.obj(s["tasks"])["TASK-2"] = linkedMapOf<String, Any?>("task_id" to "TASK-2", "title" to "Second", "status" to "cancelled",
            "owner_agent_id" to "agent-implementer")
        Json.obj(s["milestones"])["MS-1"] = linkedMapOf<String, Any?>("milestone_id" to "MS-1", "title" to "Core ready",
            "criteria" to arrayListOf<Any?>("works"), "task_ids" to arrayListOf<Any?>("TASK-1"), "status" to "planned")
        Json.obj(s["milestones"])["MS-2"] = linkedMapOf<String, Any?>("milestone_id" to "MS-2", "title" to "Both apps usable",
            "criteria" to arrayListOf<Any?>(), "task_ids" to arrayListOf<Any?>("TASK-2"), "status" to "planned")
        Json.obj(s["versions"])["VER-2"] = linkedMapOf<String, Any?>("version_id" to "VER-2", "label" to "0.1.0", "status" to "proposed",
            "policy" to "semver", "milestone_ids" to arrayListOf<Any?>("MS-1"), "history" to arrayListOf<Any?>(),
            "commit_sha" to "", "tag" to "", "run_id" to "", "artifact" to "")
    }

    @Test fun bf082OpenMilestonesAndReleaseComeBeforeTheAnnouncement() {
        val p = project(); val g = Guide(p)
        planOpenItems(p); decideComplete(p)
        val keys = g.steps().map { it.key }
        assertEquals("closeout:announce", keys.last())
        assertTrue(keys.contains("milestone:MS-1"))
        assertFalse(keys.contains("closeout:expand"))
        assertTrue(g.steps().last().explain.contains("Before announcing"))
        val drop = g.steps().first { it.key == "milestone:MS-2" }
        assertTrue(drop.title, drop.title.startsWith("Drop milestone"))
        assertFalse(drop.explain.contains("All its tasks are done"))
        g.perform("milestone:MS-1", "accept_milestone")
        val k2 = g.steps().map { it.key }
        assertTrue(k2.indexOf("version:VER-2") in 0 until k2.indexOf("closeout:announce"))
        g.perform("version:VER-2", "release", mapOf("commit_sha" to "b".repeat(40), "tag" to "v0.1.0", "run_id" to "run-9"))
        g.perform("milestone:MS-2", "drop_milestone")
        assertEquals(listOf("closeout:announce"), g.steps().map { it.key })
        g.perform("closeout:announce", "announce")
        assertEquals(1, Json.int(Json.obj(Flow.settings(p.state())["completion"])["milestones_accepted"]))
    }

    @Test fun bf082ExpansionClosesAMilestoneWhoseTasksWereAllCancelled() {
        val p = project(); val g = Guide(p)
        planOpenItems(p); decideComplete(p)
        g.perform("milestone:MS-1", "accept_milestone")
        g.perform("closeout:announce", "announce")
        g.perform("closeout:expand", "expand", mapOf("idea" to "more"))
        assertEquals("dropped", Json.obj(Json.obj(p.state()["milestones"])["MS-2"])["status"])
        assertFalse(g.steps().any { it.key == "milestone:MS-2" })
    }
}
