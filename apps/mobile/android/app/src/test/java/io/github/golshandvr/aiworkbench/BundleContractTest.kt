package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.ProjectBundle
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.State
import io.github.golshandvr.aiworkbench.core.StrictJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.nio.file.Files

/**
 * Gate 3.8.0 / mobile 1.0.0: `aiwb-bundle.v1` round trip between desktop and phone.
 *
 * `packages/contracts/fixtures/bundle/todo.aiwb-bundle.json` is produced by the desktop; `todo.mobile.aiwb-bundle.json`
 * by this app (the desktop's test_bundle imports it). Re-exporting the desktop state must give byte-identical
 * `state_json`, so both apps agree on the integrity hash without shared canonicalisation code.
 */
class BundleContractTest {
    private fun contracts(): File {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        return File(requireNotNull(dir), "packages/contracts/fixtures/bundle")
    }

    private fun desktop(): String = File(contracts(), "todo.aiwb-bundle.json").readText()
    private fun tmp(name: String): ProjectStore = ProjectStore(File(Files.createTempDirectory("aiwb").toFile(), name))

    private fun expectError(what: String, f: () -> Unit) {
        try { f(); fail("expected BundleError: $what") } catch (e: ProjectBundle.BundleError) {
            assertTrue("${e.message} should mention $what", e.message!!.contains(what))
        }
    }

    @Test fun desktopFixtureReads() {
        val (b, st) = ProjectBundle.read(desktop())
        assertEquals("ai-workbench-desktop", Json.str(Json.obj(b["producer"])["app"]))
        assertEquals("todo", st["project_id"])
        assertEquals(listOf("TASK-0001", "TASK-0002", "TASK-0003"), Json.obj(st["tasks"]).keys.sorted())
        assertTrue(Json.obj(st["settings"]).containsKey("charter"))
    }

    @Test fun reExportIsByteIdentical() {
        val b = Json.parseObj(desktop())
        val state = Json.parseObj(b["state_json"] as String)
        val again = ProjectBundle.export(state)
        assertEquals(b["state_json"], again["state_json"])
        assertEquals(b["state_sha256"], again["state_sha256"])
    }

    @Test fun roundTripIntoEmptyProject() {
        val store = tmp("todo")
        val (plan, imported) = ProjectBundle.importInto(store, desktop())
        assertEquals("new", plan.kind)
        assertTrue(imported)
        assertEquals("same", ProjectBundle.planImport(store.load(), ProjectBundle.read(desktop()).second).kind)
        val out = ProjectBundle.export(store.load(), app = ProjectBundle.MOBILE_APP, version = "1.0.0")
        val back = ProjectBundle.read(StrictJson.stringify(out)).second
        Json.obj(back["settings"]).remove("sync")
        val orig = ProjectBundle.read(desktop()).second
        assertEquals(StrictJson.stringify(orig, true), StrictJson.stringify(back, true))
    }

    @Test fun newerOlderDivergedAndForce() {
        val a = tmp("todo"); val b = tmp("todo")
        ProjectBundle.importInto(a, desktop()); ProjectBundle.importInto(b, desktop())
        val old = ProjectBundle.dumps(ProjectBundle.export(a.load()))
        a.transaction("start") { s -> State.setTaskStatus(s, "TASK-0001", "in_progress", "test") }
        val newer = ProjectBundle.dumps(ProjectBundle.export(a.load()))
        assertEquals("newer", ProjectBundle.planImport(b.load(), ProjectBundle.read(newer).second).kind)
        assertEquals("older", ProjectBundle.planImport(a.load(), ProjectBundle.read(old).second).kind)
        expectError("older") { ProjectBundle.importInto(a, old) }
        b.transaction("other change") { s -> Json.obj(s["settings"])["goal"] = "changed on b" }
        assertEquals("diverged", ProjectBundle.planImport(b.load(), ProjectBundle.read(newer).second).kind)
        expectError("Both copies changed") { ProjectBundle.importInto(b, newer) }
        assertTrue(ProjectBundle.importInto(b, newer, force = true).second)
        assertTrue(File(b.root, "backups").listFiles()!!.any { it.name.contains("pre-bundle-import") })
        assertEquals("in_progress", Json.obj(Json.obj(b.load()["tasks"])["TASK-0001"])["status"])
    }

    @Test fun damageAndOtherProjectRejected() {
        val good = Json.parseObj(desktop())
        val bad = LinkedHashMap(good).also { it["state_json"] = (good["state_json"] as String).replace("Core library", "Core librarx") }
        expectError("damaged") { ProjectBundle.read(StrictJson.stringify(bad)) }
        expectError("bundle_type") { ProjectBundle.read(StrictJson.stringify(LinkedHashMap(good).also { it["bundle_type"] = "x" })) }
        expectError("bundle_version") { ProjectBundle.read(StrictJson.stringify(LinkedHashMap(good).also { it["bundle_version"] = 2L })) }
        expectError("not valid JSON") { ProjectBundle.read("not json") }
        val st = ProjectBundle.read(desktop()).second
        st["db_version"] = 99L
        expectError("newer") { ProjectBundle.read(StrictJson.stringify(ProjectBundle.export(st))) }
        val other = tmp("other")
        other.write(LinkedHashMap(ProjectBundle.read(desktop()).second).also { it["project_id"] = "other" })
        expectError("not 'other'") { ProjectBundle.importInto(other, desktop(), force = true) }
    }

    /** The committed mobile-produced fixture is a valid bundle of the same project (the desktop imports it too). */
    @Test fun mobileFixtureIsValid() {
        val f = File(contracts(), "todo.mobile.aiwb-bundle.json")
        if (System.getenv("AIWB_WRITE_FIXTURES") == "1") {
            val store = tmp("todo")
            ProjectBundle.importInto(store, desktop())
            store.transaction("start on the phone") { s -> State.setTaskStatus(s, "TASK-0001", "in_progress", "started on the phone") }
            val b = ProjectBundle.export(store.load(), app = ProjectBundle.MOBILE_APP, version = "1.0.0")
            b["created_at"] = "2026-10-19T00:00:00Z"
            f.writeText(ProjectBundle.dumps(b))
        }
        val (b, st) = ProjectBundle.read(f.readText())
        assertEquals(ProjectBundle.MOBILE_APP, Json.str(Json.obj(b["producer"])["app"]))
        assertEquals("in_progress", Json.obj(Json.obj(st["tasks"])["TASK-0001"])["status"])
        assertTrue(ProjectBundle.descends(st, ProjectBundle.read(desktop()).second))
        assertFalse(ProjectBundle.descends(ProjectBundle.read(desktop()).second, st))
    }
}
