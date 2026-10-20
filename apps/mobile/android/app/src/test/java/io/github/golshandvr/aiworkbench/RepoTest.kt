package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.ModelError
import io.github.golshandvr.aiworkbench.core.Obj
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.Repo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** Roadmap 4.5.0 gate (phone half): GitHub blue nodes in manual mode — same fixture as desktop `test_repo.py`. */
class RepoTest {
    private fun fixture(): Obj {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        return Json.parseObj(File(requireNotNull(dir), "packages/contracts/fixtures/repo/github-flow.v1.json").readText())
    }

    @Test fun fixtureBranchNamesAndRefusals() {
        val fx = fixture()
        for (c in Json.list(fx["project_branch"]).map { Json.obj(it) }) {
            val st: Obj = linkedMapOf("project_id" to "p", "settings" to linkedMapOf<String, Any?>("brief" to linkedMapOf<String, Any?>("name" to c["name"])))
            assertEquals(c.toString(), c["out"], Repo.projectBranch(st))
        }
        assertEquals(Json.strs(fx["refused_branches"]).toSet(), Repo.PROTECTED)
        for (c in Json.list(fx["names"]).map { Json.obj(it) }) assertEquals(c.toString(), c["ok"], Repo.validName(Json.str(c["in"])))
    }

    private fun project(): Project {
        val p = Project(ProjectStore(File(Files.createTempDirectory("aiwb").toFile(), "r")))
        p.installTemplates()
        p.store.transaction("goal") { s -> Json.obj(s["settings"])["goal"] = "x" }
        return p
    }

    @Test fun connectSaveManual() {
        val p = project()
        val g = Guide(p)
        assertTrue(g.steps().any { it.key == "github:connect" })
        assertEquals("the optional GitHub step never comes first", "charter", g.next().key)
        try { Repo.recordConnect(p.store, "o", "r", "main"); fail("main accepted") } catch (_: ModelError) { }
        try { Repo.recordSave(p.store, "abc1234"); fail("save before connect") } catch (_: ModelError) { }
        g.perform("github:connect", "record_connect", mapOf("owner" to "o", "repo" to "r"))
        assertEquals("o/r", Repo.info(p.state())["full_name"])
        assertTrue(Json.str(Repo.info(p.state())["branch"]).startsWith("aiwb/"))
        try { Repo.recordSave(p.store, "abc1234"); fail("nothing integrated") } catch (_: ModelError) { }

        p.store.transaction("fake integrate") { s ->
            Json.obj(s["handoffs"])["H-1"] = linkedMapOf<String, Any?>("handoff_id" to "H-1", "integrated_at" to "2026-01-01T00:00:00Z",
                "integrated_files" to arrayListOf<Any?>("src/a.kt"))
        }
        assertEquals(listOf("src/a.kt"), Repo.unsavedFiles(p.state()))
        val save = g.steps().first { it.key == "github:save" }
        assertTrue(save.explain.contains("src/a.kt"))
        try { g.perform("github:save", "record_save", mapOf("commit_sha" to "not-a-sha")); fail("bad sha") } catch (_: ModelError) { }
        g.perform("github:save", "record_save", mapOf("commit_sha" to "abc1234"))
        assertEquals(emptyList<String>(), Repo.unsavedFiles(p.state()))
        assertTrue(g.steps().none { it.key.startsWith("github:") })
    }
}
