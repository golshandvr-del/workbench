package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.Obj
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.Waves
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** Roadmap 4.1.0 / mobile 1.2.0: parallel paths and the dispatch desk (same cases as desktop `test_waves.py`). */
class WavesTest {
    private fun t(id: String, status: String = "ready", deps: List<String> = emptyList(), owner: String = "agent-implementer"): Pair<String, Any?> =
        id to linkedMapOf<String, Any?>("task_id" to id, "status" to status, "depends_on" to ArrayList<Any?>(deps), "owner_agent_id" to owner)

    private fun state(vararg tasks: Pair<String, Any?>, limit: Int = 2, handoffs: Map<String, Any?> = emptyMap()): Obj = linkedMapOf(
        "tasks" to linkedMapOf(*tasks), "handoffs" to LinkedHashMap(handoffs),
        "agents" to linkedMapOf<String, Any?>("agent-implementer" to linkedMapOf<String, Any?>(), "agent-ui" to linkedMapOf<String, Any?>(),
            "agent-tester" to linkedMapOf<String, Any?>()),
        "settings" to linkedMapOf<String, Any?>("team" to linkedMapOf<String, Any?>("max_parallel_chats" to limit.toLong())))

    @Test fun wavesFollowDependencies() {
        val st = state(t("T-1"), t("T-2"), t("T-3", "blocked", listOf("T-1")), t("T-4", "blocked", listOf("T-3", "T-2")), t("T-5", "done"))
        assertEquals(listOf(listOf("T-1", "T-2"), listOf("T-3"), listOf("T-4")), Waves.waves(st).waves)
    }

    @Test fun cycleAndDeadPrerequisitesAreReported() {
        val st = state(t("T-1", deps = listOf("T-2")), t("T-2", deps = listOf("T-1")), t("T-3", deps = listOf("T-9")),
            t("T-4", deps = listOf("T-5")), t("T-5", "cancelled"), t("T-6"))
        val w = Waves.waves(st)
        assertEquals(listOf(listOf("T-6")), w.waves)
        assertEquals(listOf("T-1", "T-2"), w.cycle)
        assertEquals(listOf("T-3", "T-4"), w.dead)
    }

    @Test fun lanesGroupByOwner() {
        val st = state(t("T-1"), t("T-2", owner = "agent-ui"), t("T-3", owner = "agent-ui"), t("T-4", owner = "nobody"))
        assertEquals(mapOf("agent-implementer" to listOf("T-1", "T-4"), "agent-ui" to listOf("T-2", "T-3")), Waves.lanes(st))
    }

    @Test fun chatLimitAndLaneFairness() {
        val d = Waves.dispatch(state(t("T-1"), t("T-2"), t("T-3", owner = "agent-ui"), t("T-4", owner = "agent-tester"), limit = 3))
        assertEquals(listOf("T-1", "T-3", "T-4"), d.next)
        assertEquals(listOf("T-2"), d.queued)
    }

    @Test fun openChatsUseSlots() {
        val hs = mapOf<String, Any?>("H-1" to linkedMapOf<String, Any?>("handoff_id" to "H-1", "task_id" to "T-1", "status" to "prompt_exported"))
        val d = Waves.dispatch(state(t("T-1", "in_progress"), t("T-2"), t("T-3"), limit = 2, handoffs = hs))
        assertEquals(listOf("H-1"), d.active)
        assertEquals(listOf("T-2"), d.next)
        assertEquals(listOf("T-3"), d.queued)
    }

    @Test fun bf035CancellationRetiresPromptsAndRefusesLatePublication() {
        for (route in listOf("direct", "proposal", "supersede")) for (received in listOf(false, true)) {
            val root = Files.createTempDirectory("aiwb-cancel").toFile()
            try {
                val p = Project(ProjectStore(File(root, "w")))
                p.installTemplates()
                p.setMaxParallelChats(1)
                val ids = (0..1).map { i -> Json.str(p.createTask(linkedMapOf("title" to "Part $i", "objective" to "test",
                    "owner_agent_id" to "agent-implementer", "allowed_paths" to arrayListOf<Any?>("src/p$i/"),
                    "acceptance_criteria" to arrayListOf<Any?>("works")), "ready")["task_id"]) }
                val h = p.startTask(ids[0])
                val hid = Json.str(h["handoff_id"])
                val answer = "AIWB_ATTEMPT_ID: ${h["attempt_id"]}\n" +
                    "<<<AIWB_FILE path=\"src/p0/new.py\" action=\"write\">>>\n````\nVALUE = 1\n````\n<<<AIWB_END_FILE>>>\n" +
                    "<<<AIWB_HANDOFF>>>\n" + io.github.golshandvr.aiworkbench.core.StrictJson.stringify(linkedMapOf<String, Any?>(
                        "handoff_id" to hid, "task_id" to ids[0], "attempt_id" to h["attempt_id"], "outcome" to "complete")) +
                    "\n<<<AIWB_END_HANDOFF>>>"
                if (received) assertEquals("handoff", p.routeAnswer(answer).kind)
                if (route == "proposal") {
                    val pid = p.importProposalData(linkedMapOf("base_state_revision" to p.state()["state_revision"],
                        "operations" to arrayListOf<Any?>(linkedMapOf<String, Any?>("operation" to "close_or_cancel_task",
                            "task_id" to ids[0], "reason" to "not wanted"))))
                    p.reviewProposal(pid, listOf(0))
                } else p.transition(ids[0], if (route == "supersede") "superseded" else "cancelled", "not wanted")
                val st = p.state()
                assertEquals("superseded", Json.obj(Json.obj(st["handoffs"])[hid])["status"])
                assertEquals("abandoned", Json.obj(Json.obj(st["attempts"])[h["attempt_id"]])["status"])
                assertTrue(Json.str(Json.obj(Json.obj(st["tasks"])[ids[0]])["active_attempt_id"]).isEmpty())
                assertEquals(listOf(ids[1]), Waves.dispatch(st).next)
                assertTrue(Guide(p).steps().none { it.key == "handoff:$hid" })
                p.ingest(hid, "late-response", answer)
                io.github.golshandvr.aiworkbench.core.Files.stage(p.store, hid, answer)
                assertTrue("late-response" in Json.strs(Json.obj(Json.obj(p.state()["attempts"])[h["attempt_id"]])["response_ids"]))
                val before = p.state()
                try {
                    io.github.golshandvr.aiworkbench.core.Files.integrate(p.store, hid)
                    org.junit.Assert.fail("cancelled payload published")
                } catch (_: io.github.golshandvr.aiworkbench.core.ModelError) { }
                try {
                    p.resolveHandoff(hid, true, "accept anyway")
                    org.junit.Assert.fail("cancelled delivery accepted")
                } catch (_: io.github.golshandvr.aiworkbench.core.ModelError) { }
                assertEquals(before, p.state())
                assertTrue(!File(io.github.golshandvr.aiworkbench.core.Files.dir(p.store), "src/p0/new.py").exists())
                assertEquals(listOf(ids[1]), Waves.dispatch(p.state()).next)
            } finally { root.deleteRecursively() }
        }
    }

    @Test fun prepareAllOpensOneChatPerTaskWithinTheLimit() {
        val p = Project(ProjectStore(File(Files.createTempDirectory("aiwb").toFile(), "w")))
        p.installTemplates()
        for (i in 0 until 3) {
            val tid = Json.str(p.createTask(linkedMapOf("title" to "Task $i", "objective" to "part $i",
                "allowed_paths" to arrayListOf<Any?>("src/p$i/"), "acceptance_criteria" to arrayListOf<Any?>("works")))["task_id"])
            p.transition(tid, "ready", "test")
        }
        p.setMaxParallelChats(2)
        p.store.transaction("goal") { s -> Json.obj(s["settings"])["goal"] = "x" }
        val g = Guide(p)
        val desk = g.find("dispatch")
        assertEquals(2, desk.taskIds.size)
        assertEquals(2, g.steps().count { it.key.startsWith("task:") && it.kind == "prompt" })
        assertEquals("F10", p.flow().id)
        g.perform("dispatch", "prepare_all")
        assertEquals("F11", p.flow().id)
        assertTrue(g.steps().none { it.key == "dispatch" })
        for (s in g.steps().filter { it.key.startsWith("handoff:") }) g.perform(s.key, "sent")
        assertEquals("F12", p.flow().id)
    }
}
