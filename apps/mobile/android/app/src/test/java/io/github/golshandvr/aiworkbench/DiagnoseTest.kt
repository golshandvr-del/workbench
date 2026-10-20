package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Diagnose
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

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
}
