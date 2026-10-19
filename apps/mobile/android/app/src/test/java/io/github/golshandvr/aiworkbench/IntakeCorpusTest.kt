package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Intake
import io.github.golshandvr.aiworkbench.core.Normalize
import io.github.golshandvr.aiworkbench.core.StrictJson
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Gate mobile 1.0.0: the phone reads chat answers exactly like the desktop (3.2.0), on the same shared corpus
 * `packages/contracts/fixtures/intake/chat-copy-corpus.v1.json`.
 */
class IntakeCorpusTest {
    private fun corpus(): JSONObject {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        return JSONObject(File(requireNotNull(dir), "packages/contracts/fixtures/intake/chat-copy-corpus.v1.json").readText())
    }

    private fun expected(case: JSONObject): Map<String, String> {
        val e = case.getJSONObject("expect_files")
        return e.keySet().associateWith { e.getString(it) }
    }

    private fun each(group: String, f: (JSONObject) -> Unit) {
        val a = corpus().getJSONArray(group)
        for (i in 0 until a.length()) f(a.getJSONObject(i))
    }

    @Test fun corpusIsLargeEnough() {
        assertTrue(corpus().getJSONArray("broken").length() >= 30)
    }

    @Test fun everyBrokenCaseImports() = each("broken") { c ->
        val id = c.getString("id")
        val p = try { Intake.parse(c.getString("text")) } catch (e: Intake.IntakeError) { throw AssertionError("$id: ${e.message}") }
        assertEquals(id, expected(c), p.fileMap())
    }

    @Test fun healthyCasesUnchanged() = each("healthy") { c ->
        val p = Intake.parse(c.getString("text"))
        assertFalse(c.getString("id"), p.cleaned)
        assertEquals(c.getString("id"), expected(c), p.fileMap())
    }

    @Test fun normalizeOnlyCases() = each("normalize_only") { c ->
        val got = StrictJson.parse(Normalize.normalize(c.getString("text")).text) as Map<*, *>
        val want = c.getJSONObject("expect_json")
        assertEquals(want.keySet(), got.keys)
        for (k in want.keySet()) assertEquals(k, if (want.isNull(k)) null else want.get(k), got[k])
    }

    @Test fun truncatedCasesDetectedWithContinuePrompt() = each("truncated") { c ->
        val id = c.getString("id")
        val r = Normalize.truncationReport(c.getString("text"))
        assertTrue(id, r.truncated)
        assertEquals(id, c.getString("reason"), r.reason)
        if (c.has("open")) {
            assertEquals(id, c.getString("open"), r.openPath)
            val done = c.getJSONArray("done")
            assertEquals(id, (0 until done.length()).map { done.getString(it) }, r.completedPaths)
        }
        val prompt = Normalize.continuePrompt(r, "a1")
        assertTrue(prompt.contains("cut off"))
        assertTrue(prompt.contains("<<<AIWB_END_FILE>>>"))
        val e = try { Intake.parse(c.getString("text")); null } catch (x: Intake.IntakeError) { x }
        assertTrue("$id must not be applied", e != null && e.continuePrompt.contains("cut off"))
    }

    @Test fun completeAnswersAreNotTruncated() {
        each("healthy") { assertFalse(it.getString("id"), Normalize.truncationReport(it.getString("text")).truncated) }
        each("broken") { assertFalse(it.getString("id"), Normalize.truncationReport(it.getString("text")).truncated) }
    }

    @Test fun bodyIsNotRewritten() {
        val body = "He said \u201chi\u201d &amp; \\_x\\_ <<<not a marker"
        val text = "<<<AIWB_FILE path=\"a.md\" action=\"write\" body=\"raw\">>>\n$body\n<<<AIWB_END_FILE>>>\n"
        assertTrue(Normalize.normalize(text).text.contains(body))
        assertFalse(Normalize.normalize("<<<AIWB_FILE path=\"a\" action=\"write\">>>\nx\n<<<AIWB_END_FILE>>>\n").changed)
    }

    @Test fun jsonStringsUntouched() {
        val out = Normalize.normalizeJsonText("{\"a\": \"// not a comment, /* nor this */\", \"b\": [1, 2,],}")
        val m = StrictJson.parse(out.text) as Map<*, *>
        assertEquals("// not a comment, /* nor this */", m["a"])
        assertEquals(listOf(1L, 2L), m["b"])
        assertFalse(Normalize.normalizeJsonText("{\"a\": 1}").changed)
    }

    @Test fun unsafePathsRejected() {
        for (p in listOf("../x", "/etc/passwd", "C:/x", "a//b")) {
            val t = "<<<AIWB_FILE path=\"$p\" action=\"write\">>>\nx\n<<<AIWB_END_FILE>>>\n"
            assertTrue(p, try { Intake.parse(t); false } catch (_: Intake.IntakeError) { true })
        }
    }
}
