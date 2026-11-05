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

    @Test fun bf076DirectRouteStagesAndDiagnosesBeforeAccepting() {
        val (p, tid) = project()
        val g = Guide(p)
        g.perform("task:$tid", "prepare")
        val routed = p.routeAnswer(answer(p, tid))
        assertEquals("handoff", routed.kind)
        val h = State.require(p.state(), "handoffs", routed.ref)
        assertEquals(2, Json.list(h["staged_files"]).size)
        assertTrue("diagnosis" in h)
        assertEquals("old\n", Files.read(p.store, "src/calc.py"))
        g.perform("handoff:${routed.ref}", "accept_handoff")
        assertEquals("X = 1\n", Files.read(p.store, "src/util/__init__.py"))
    }

    @Test fun bf078RepairWritesPartialFilesBeforeExcludingThem() {
        val (p, tid) = project()
        val g = Guide(p)
        g.perform("task:$tid", "prepare")
        val key = g.steps().first { it.key.startsWith("handoff:") }.key
        g.perform(key, "paste", mapOf("text" to answer(p, tid).replace("\"complete\"", "\"partial\"")
            .replace("\"unresolved_items\": []", "\"unresolved_items\": [\"missing tests\"]")))
        val out = g.perform(key, "repair")
        assertTrue(out.prompt, "src/calc.py" in out.prompt)
        assertEquals("X = 1\n", Files.read(p.store, "src/util/__init__.py"))
        val h = State.require(p.state(), "handoffs", key.substringAfter(":"))
        assertEquals("accepted", h["status"])
        assertEquals(2, Json.list(h["integrated_files"]).size)
    }

    @Test fun bf079TroubleshootKeepsGoodFilesForManifestOnlyCorrection() {
        val (p, tid) = project()
        val g = Guide(p)
        g.perform("task:$tid", "prepare")
        val key = g.steps().first { it.key.startsWith("handoff:") }.key
        g.perform(key, "paste", mapOf("text" to answer(p, tid, b = "README.md")))
        val out = g.perform(key, "troubleshoot")
        assertTrue(out.prompt, "src/calc.py" in out.prompt)
        val next = g.steps().first { it.key.startsWith("handoff:") }
        val h = State.require(p.state(), "handoffs", next.ref)
        val manifest = "<<<AIWB_HANDOFF>>>\n" + io.github.golshandvr.aiworkbench.core.StrictJson.stringify(linkedMapOf<String, Any?>(
            "schema_version" to "1.0", "handoff_id" to next.ref, "task_id" to tid,
            "task_revision" to h["task_revision"], "attempt_id" to h["attempt_id"],
            "outcome" to "complete", "summary" to "Removed out-of-scope README")) + "\n<<<AIWB_END_HANDOFF>>>\n"
        g.perform(next.key, "paste", mapOf("text" to manifest))
        g.perform(next.key, "accept_handoff")
        assertTrue("return a + b" in Files.read(p.store, "src/calc.py"))
        assertFalse(File(Files.dir(p.store), "README.md").exists())
    }

    @Test fun bf079ManifestOnlyFileTaskIsNotCleanAcceptance() {
        val (p, tid) = project()
        val g = Guide(p)
        g.perform("task:$tid", "prepare")
        val key = g.steps().first { it.key.startsWith("handoff:") }.key
        val text = answer(p, tid).substringAfter("<<<AIWB_HANDOFF>>>")
        g.perform(key, "paste", mapOf("text" to "<<<AIWB_HANDOFF>>>" + text))
        val h = State.require(p.state(), "handoffs", key.substringAfter(":"))
        assertTrue(Json.list(h["diagnosis"]).any { Json.obj(it)["code"] == "missing_deliverable" })
    }

    @Test fun integrationFailureDoesNotAcceptOrDiscardPayload() {
        val (p, tid) = project()
        val g = Guide(p)
        g.perform("task:$tid", "prepare")
        val key = g.steps().first { it.key.startsWith("handoff:") }.key
        g.perform(key, "paste", mapOf("text" to answer(p, tid)))
        // A backup destination which is a file must fail before publishing any file.
        File(p.store.root, "backups").writeText("locked")
        val before = p.state()
        try { g.perform(key, "accept_handoff"); fail("integration succeeded with blocked backup") } catch (_: Exception) { }
        assertEquals(before["handoffs"], p.state()["handoffs"])
        assertEquals(before["attempts"], p.state()["attempts"])
        assertEquals(before["tasks"], p.state()["tasks"])
        assertEquals("old\n", Files.read(p.store, "src/calc.py"))
        assertFalse(File(Files.dir(p.store), "src/util/__init__.py").exists())
    }

    @Test fun staleRetainedPreviewRefusesAndPreservesUserEdit() {
        val (p, tid) = project()
        val g = Guide(p)
        g.perform("task:$tid", "prepare")
        val key = g.steps().first { it.key.startsWith("handoff:") }.key
        g.perform(key, "paste", mapOf("text" to answer(p, tid, b = "README.md")))
        g.perform(key, "troubleshoot")
        val next = g.steps().first { it.key.startsWith("handoff:") }
        File(Files.dir(p.store), "src/calc.py").writeText("user edit\r\n")
        val h = State.require(p.state(), "handoffs", next.ref)
        val manifest = "<<<AIWB_HANDOFF>>>\n" + io.github.golshandvr.aiworkbench.core.StrictJson.stringify(
            linkedMapOf<String, Any?>("handoff_id" to next.ref, "task_id" to tid, "attempt_id" to h["attempt_id"], "outcome" to "complete")) +
            "\n<<<AIWB_END_HANDOFF>>>"
        assertEquals("handoff", p.routeAnswer(manifest).kind)
        val staged = State.require(p.state(), "handoffs", next.ref)
        assertTrue(Json.list(staged["diagnosis"]).any { Json.obj(it)["code"] == "file_conflict" })
        try { g.perform(next.key, "accept_handoff"); fail("stale preview accepted") } catch (_: ModelError) { }
        assertEquals("user edit\r\n", Files.read(p.store, "src/calc.py"))
        assertEquals("reconciled", State.require(p.state(), "handoffs", next.ref)["status"])
    }

    @Test fun correctedFileReplacesRetainedPayloadAndRepairFailureKeepsDeliveryOpen() {
        val (p, tid) = project()
        val g = Guide(p)
        g.perform("task:$tid", "prepare")
        val key = g.steps().first { it.key.startsWith("handoff:") }.key
        g.perform(key, "paste", mapOf("text" to answer(p, tid, b = "README.md")))
        g.perform(key, "troubleshoot")
        val next = g.steps().first { it.key.startsWith("handoff:") }
        val nh = State.require(p.state(), "handoffs", next.ref)
        val old = State.require(p.state(), "handoffs", key.substringAfter(":"))
        val correction = answer(p, tid).replace(Json.str(old["handoff_id"]), next.ref)
            .replace(Json.str(old["attempt_id"]), Json.str(nh["attempt_id"]))
            .replace("return a + b", "return a + b + 1")
            .replace("\"unresolved_items\": []", "\"unresolved_items\": [\"missing tests\"]")
        g.perform(next.key, "paste", mapOf("text" to correction))
        File(p.store.root, "backups").writeText("blocked")
        val before = p.state()
        try { g.perform(next.key, "repair"); fail("repair accepted with blocked backup") } catch (_: ModelError) { }
        assertEquals(before, p.state())
        File(p.store.root, "backups").delete()
        g.perform(next.key, "repair")
        assertTrue("return a + b + 1" in Files.read(p.store, "src/calc.py"))
        assertEquals("X = 1\n", Files.read(p.store, "src/util/__init__.py"))
    }

    @Test fun stateWriteFailureRollsBackAllPublishedFilesAndIsRetryable() {
        val (p, tid) = project()
        val h = p.startTask(tid, "agent-implementer")
        val hid = Json.str(h["handoff_id"])
        p.routeAnswer(answer(p, tid))
        val before = p.store.path.readBytes()
        val saved = File(p.store.root, "saved-state.json")
        try {
            try {
                Files.integrate(p.store, hid) { _ ->
                    check(p.store.path.renameTo(saved))
                    check(p.store.path.mkdir())
                    File(p.store.path, "blocker").writeText("force rename failure")
                }
                fail("state publication succeeded")
            } catch (_: ModelError) { }
            assertTrue(saved.readBytes().contentEquals(before))
            assertEquals("old\n", Files.read(p.store, "src/calc.py"))
            assertFalse(File(Files.dir(p.store), "src/util/__init__.py").exists())
        } finally {
            p.store.path.deleteRecursively()
            check(saved.renameTo(p.store.path))
        }
        assertEquals("reconciled", State.require(p.state(), "handoffs", hid)["status"])
        val originalBackup = File(p.store.root, "backups/$hid/src/calc.py").readBytes()
        Files.integrate(p.store, hid)
        assertTrue(File(p.store.root, "backups/$hid/src/calc.py").readBytes().contentEquals(originalBackup))
        assertEquals("X = 1\n", Files.read(p.store, "src/util/__init__.py"))
    }

    @Test fun emptyFileIsWrittenAndOversizeOrLinkedDestinationsNeverSilentlyPass() {
        val (p, tid) = project()
        val h = p.startTask(tid, "agent-implementer")
        val hid = Json.str(h["handoff_id"])
        p.routeAnswer(answer(p, tid).replace("X = 1", ""))
        Files.integrate(p.store, hid)
        assertEquals(0L, File(Files.dir(p.store), "src/util/__init__.py").length())
        val nh = p.startTask(tid, "agent-implementer")
        val nid = Json.str(nh["handoff_id"])
        val oversized = answer(p, tid).replace(hid, nid).replace(Json.str(h["attempt_id"]), Json.str(nh["attempt_id"]))
            .replace("X = 1", "x".repeat(Files.MAX_FILE + 1))
        p.routeAnswer(oversized)
        assertTrue(Json.list(State.require(p.state(), "handoffs", nid)["diagnosis"]).any { Json.obj(it)["code"] == "too_large" })
        try { Files.integrate(p.store, nid); fail("oversize accepted") } catch (_: ModelError) { }
        val outside = NioFiles.createTempDirectory("aiwb-outside").toFile()
        File(Files.dir(p.store), "src/util/__init__.py").delete()
        NioFiles.createSymbolicLink(File(Files.dir(p.store), "src/util/__init__.py").toPath(), File(outside, "x").toPath())
        Files.stage(p.store, nid, oversized.replace("x".repeat(Files.MAX_FILE + 1), "X = 2"))
        try { Files.integrate(p.store, nid); fail("linked destination accepted") } catch (_: ModelError) { }
        assertFalse(File(outside, "x").exists())
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
