package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Files
import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.ModelError
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.State
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.file.Files as NioFiles
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** Roadmap 4.3.0 gate (phone half): user approval and project files (same cases as desktop `test_files.py`). */
class FilesTest {
    private fun fixture(): JSONObject {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        return JSONObject(File(requireNotNull(dir), "packages/contracts/fixtures/files/safe-paths.v1.json").readText())
    }

    @Test fun sharedSafePathFixture() {
        val a = fixture().getJSONArray("cases")
        assertTrue(a.length() >= 18)
        for (i in 0 until a.length()) {
            val c = a.getJSONObject(i)
            assertEquals(c.getString("input"), c.getString("expect"), Files.safePath(c.getString("input")))
        }
    }

    private fun project(): Pair<Project, String> {
        val p = Project(ProjectStore(File(NioFiles.createTempDirectory("aiwb").toFile(), "calc")))
        p.installTemplates()
        val tid = Json.str(p.createTask(linkedMapOf("title" to "Calc", "objective" to "add",
            "scope" to linkedMapOf<String, Any?>("include" to arrayListOf<Any?>("src/"), "exclude" to arrayListOf<Any?>()),
            "acceptance_criteria" to arrayListOf<Any?>("adds")))["task_id"])
        p.transition(tid, "ready", "test")
        File(Files.dir(p.store), "src").mkdirs()
        File(Files.dir(p.store), "src/calc.py").writeText("old\n")
        return p to tid
    }

    private fun answer(p: Project, tid: String, a: String = "src/calc.py", b: String = "src/util/__init__.py"): String {
        val h = State.coll(p.state(), "handoffs").values.map { Json.obj(it) }.first { it["task_id"] == tid }
        val man = "{\"schema_version\": \"1.0\", \"handoff_id\": \"${h["handoff_id"]}\", \"task_id\": \"$tid\", " +
            "\"task_revision\": ${Json.int(h["task_revision"])}, \"attempt_id\": \"${h["attempt_id"]}\", \"outcome\": \"complete\", " +
            "\"summary\": \"done\", \"completed_items\": [\"calc\"], \"unresolved_items\": [], \"validation_claims\": []}"
        fun f(path: String, body: String) = "<<<AIWB_FILE path=\"$path\" action=\"write\">>>\n````\n$body\n````\n<<<AIWB_END_FILE>>>\n"
        return "AIWB_ATTEMPT_ID: ${h["attempt_id"]}\n" + f(a, "def add(a, b):\n    return a + b") + f(b, "X = 1") +
            "<<<AIWB_HANDOFF>>>\n$man\n<<<AIWB_END_HANDOFF>>>\n"
    }

    @Test fun pasteStagesAndAcceptIntegrates() {
        val (p, tid) = project()
        val g = Guide(p)
        g.perform("task:$tid", "prepare")
        g.perform(g.steps().first { it.key.startsWith("handoff:") }.key, "paste", mapOf("text" to answer(p, tid)))
        assertEquals("old\n", Files.read(p.store, "src/calc.py"))
        val st = g.steps().first { it.key.startsWith("handoff:") }
        assertTrue(st.explain, "2 delivered file(s)" in st.explain)
        val out = g.perform(st.key, "accept_handoff")
        assertTrue(out.message, "2 file(s) added" in out.message)
        assertEquals("def add(a, b):\n    return a + b\n", Files.read(p.store, "src/calc.py"))
        assertEquals("old\n", File(p.store.root, "backups/${st.ref}/src/calc.py").readText())
        val h = State.require(p.state(), "handoffs", st.ref)
        assertTrue(Json.list(h["staged_files"]).none { "content" in Json.obj(it) })
        val ev = Json.list(p.state()["events"]).map { Json.obj(it) }.last { it["type"] == "files_integrated" }
        assertEquals(2, Json.int(ev["count"]))
        assertEquals(listOf("src/calc.py", "src/util/__init__.py"), Files.list(p.store).map { it.path })
    }

    @Test fun unsafeAndOutOfScopeAreNeverStaged() {
        val (p, tid) = project()
        val g = Guide(p)
        g.perform("task:$tid", "prepare")
        val key = g.steps().first { it.key.startsWith("handoff:") }.key
        g.perform(key, "paste", mapOf("text" to answer(p, tid, "docs/x.py", "../evil.py")))
        val h = State.coll(p.state(), "handoffs").values.map { Json.obj(it) }.first { it["task_id"] == tid }
        assertTrue(Json.list(h["staged_files"]).isEmpty())
        assertFalse(File(p.store.root, "evil.py").exists())
    }

    @Test fun zipRoundTripAndZipSlip() {
        val (p, _) = project()
        File(Files.dir(p.store), "README.md").writeText("# hi\n")
        val data = Files.zip(p.store)
        val other = ProjectStore(File(NioFiles.createTempDirectory("aiwb").toFile(), "o"))
        assertEquals(listOf("README.md", "src/calc.py"), Files.unzip(other, data).sorted())
        assertEquals("old\n", Files.read(other, "src/calc.py"))
        assertTrue(Files.zip(other).contentEquals(data))
        val bad = ByteArrayOutputStream()
        ZipOutputStream(bad).use { z ->
            z.putNextEntry(ZipEntry("ok2.txt")); z.write("x".toByteArray()); z.closeEntry()
            z.putNextEntry(ZipEntry("../evil.txt")); z.write("x".toByteArray()); z.closeEntry()
        }
        try { Files.unzip(other, bad.toByteArray()); fail("zip-slip accepted") } catch (_: ModelError) { }
        assertFalse(File(Files.dir(other), "ok2.txt").exists())
    }
}
