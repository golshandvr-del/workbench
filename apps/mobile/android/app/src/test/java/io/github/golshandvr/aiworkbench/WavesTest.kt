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
