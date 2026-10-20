package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Diagnose
import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.State
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** Roadmap 4.2.0 gate (phone half): smart problem detection matches the shared corpus (same codes as desktop). */
class DiagnoseTest {
    private fun corpus(): JSONObject {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        return JSONObject(File(requireNotNull(dir), "packages/contracts/fixtures/diagnose/diagnose-corpus.v1.json").readText())
    }

    private fun strs(a: JSONArray?): List<String> = if (a == null) emptyList() else (0 until a.length()).map { a.getString(it) }

    @Test fun corpusMatchesDesktop() {
        val cases = corpus().getJSONArray("cases")
        assertTrue(cases.length() >= 17)
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val ctx = c.getJSONObject("context")
            val r = Diagnose.diagnose(c.getString("text"), ctx.optString("attempt_id"), strs(ctx.optJSONArray("allowed_paths")),
                strs(ctx.optJSONArray("expected_paths")))
            assertEquals(c.getString("id"), strs(c.getJSONArray("codes")), r.problems.map { it.code })
            assertEquals(c.getString("id"), c.getBoolean("acceptable"), r.acceptable)
        }
    }

    @Test fun troubleshootPromptListsOnlyTheProblems() {
        val st: MutableMap<String, Any?> = linkedMapOf("tasks" to linkedMapOf<String, Any?>("T-1" to linkedMapOf<String, Any?>(
            "task_id" to "T-1", "title" to "Calc", "allowed_paths" to arrayListOf<Any?>("src/"), "acceptance_criteria" to arrayListOf<Any?>("adds"))))
        val h: MutableMap<String, Any?> = linkedMapOf("task_id" to "T-1")
        val n: MutableMap<String, Any?> = linkedMapOf("attempt_id" to "ATT-2", "handoff_id" to "HO-2", "task_id" to "T-1", "task_revision" to 1L)
        val probs = listOf(Diagnose.Problem("empty_file", "error", "src/calc.py is empty").toMap(),
            Diagnose.Problem("unverified_test_claim", "warning", "claims").toMap())
        val p = Diagnose.troubleshootPrompt(st, h, n, probs, 2)
        assertTrue(p.startsWith("AIWB_ATTEMPT_ID: ATT-2"))
        assertTrue("troubleshooting request 2" in p)
        assertTrue("- [empty_file] src/calc.py is empty" in p)
        assertTrue("## Also check" in p)
        assertTrue("- src/" in p)
    }

    /** F13 -> F15 -> F11 loop: at most three troubleshooting prompts, then the project manager (same as desktop). */
    @Test fun troubleshootLoopThenEscalate() {
        val p = Project(ProjectStore(File(Files.createTempDirectory("aiwb").toFile(), "calc")))
        p.installTemplates()
        val tid = Json.str(p.createTask(linkedMapOf("title" to "Calc", "objective" to "add", "allowed_paths" to arrayListOf<Any?>("src/"),
            "acceptance_criteria" to arrayListOf<Any?>("adds")))["task_id"])
        p.transition(tid, "ready", "test")
        val g = Guide(p)
        fun broken(): String {
            val h = State.coll(p.state(), "handoffs").values.map { Json.obj(it) }
                .first { it["task_id"] == tid && it["status"] in setOf("prepared", "prompt_exported") }
            val man = "{\"schema_version\": \"1.0\", \"handoff_id\": \"${h["handoff_id"]}\", \"task_id\": \"$tid\", " +
                "\"task_revision\": ${Json.int(h["task_revision"])}, \"attempt_id\": \"${h["attempt_id"]}\", \"outcome\": \"complete\", " +
                "\"summary\": \"done\", \"completed_items\": [\"x\"], \"unresolved_items\": [], \"validation_claims\": []}"
            return "AIWB_ATTEMPT_ID: ${h["attempt_id"]}\n<<<AIWB_FILE path=\"../evil.py\" action=\"write\">>>\n````\nx=1\n````\n" +
                "<<<AIWB_END_FILE>>>\n<<<AIWB_HANDOFF>>>\n$man\n<<<AIWB_END_HANDOFF>>>\n"
        }
        fun hstep() = g.steps().first { it.key.startsWith("handoff:") }
        g.perform("task:$tid", "prepare")
        for (n in 1..Diagnose.TROUBLESHOOT_ATTEMPTS) {
            val out = g.perform(hstep().key, "paste", mapOf("text" to broken()))
            assertTrue(out.message, "unsafe_path" in out.message)
            val st = hstep()
            assertEquals("troubleshoot", st.actions[0].id)
            val o2 = g.perform(st.key, "troubleshoot")
            assertTrue("troubleshooting request $n" in o2.prompt)
            assertTrue("[unsafe_path]" in o2.prompt)
        }
        g.perform(hstep().key, "paste", mapOf("text" to broken()))
        val st = hstep()
        assertEquals("escalate", st.actions[0].id)
        assertTrue(g.perform(st.key, "escalate").prompt.isNotEmpty())
        val s = p.state()
        assertEquals("blocked", State.require(s, "tasks", tid)["status"])
        val types = Json.list(s["events"]).map { Json.str(Json.obj(it)["type"]) }
        assertEquals(Diagnose.TROUBLESHOOT_ATTEMPTS, types.count { it == "troubleshooting_prompt" })
        assertTrue("task_escalated" in types)
    }
}
