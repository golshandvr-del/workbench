package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.GitHubApi
import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.ModelError
import io.github.golshandvr.aiworkbench.core.Obj
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.Repo
import io.github.golshandvr.aiworkbench.core.StrictJson
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

    /** Fake GitHub (Git Data API subset): refs, commits with trees, releases. No network. */
    private class FakeHub {
        val refs = linkedMapOf("main" to "c0"); val trees = linkedMapOf("t0" to mapOf<String, String>())
        val commits = linkedMapOf("c0" to "t0"); val blobs = HashMap<String, String>(); val releases = ArrayList<String>()
        val calls = ArrayList<String>(); private var n = 0
        fun files(b: String) = trees[commits[refs[b]]]!!
        fun call(method: String, url: String, h: Map<String, String>, body: String?): Pair<Int, String> {
            val path = url.substringAfter("/repos/o/r"); calls.add("$method $path"); n++
            assertEquals("Bearer tok", h["Authorization"])
            val d = body?.let { Json.obj(StrictJson.parse(it)) } ?: LinkedHashMap()
            return when {
                method == "GET" && path == "" -> 200 to """{"default_branch":"main"}"""
                method == "GET" && path.startsWith("/git/ref/heads/") -> refs[path.removePrefix("/git/ref/heads/")]
                    ?.let { 200 to """{"object":{"sha":"$it"}}""" } ?: (404 to "{}")
                method == "GET" && path.startsWith("/git/commits/") -> 200 to """{"tree":{"sha":"${commits[path.substringAfterLast('/')]}"}}"""
                method == "POST" && path == "/git/blobs" -> { blobs["b$n"] = Json.str(d["content"]); 201 to """{"sha":"b$n"}""" }
                method == "POST" && path == "/git/trees" -> {
                    val f = HashMap(trees[Json.str(d["base_tree"])]!!)
                    for (e in Json.list(d["tree"]).map { Json.obj(it) }) f[Json.str(e["path"])] = blobs[Json.str(e["sha"])]!!
                    trees["t$n"] = f; 201 to """{"sha":"t$n"}"""
                }
                method == "POST" && path == "/git/commits" -> { val sha = "abcdef$n"; commits[sha] = Json.str(d["tree"]); 201 to """{"sha":"$sha"}""" }
                method == "POST" && path == "/git/refs" -> { refs[Json.str(d["ref"]).split("/", limit = 3)[2]] = Json.str(d["sha"]); 201 to "{}" }
                method == "PATCH" && path.startsWith("/git/refs/heads/") -> {
                    assertEquals(false, d["force"]); refs[path.removePrefix("/git/refs/heads/")] = Json.str(d["sha"]); 200 to "{}"
                }
                method == "POST" && path == "/releases" -> { releases.add(Json.str(d["tag_name"])); 201 to """{"html_url":"https://github.com/o/r/releases/x"}""" }
                else -> 404 to "{}"
            }
        }
    }

    @Test fun tokenModeSendsOnlyConfirmedWrites() {
        val p = project()
        val hub = FakeHub()
        val g = Guide(p) { o, r -> GitHubApi("tok", o, r, transport = hub::call) }
        val connect = g.steps().first { it.key == "github:connect" }
        assertEquals("send_connect", connect.primary?.id)
        assertTrue("listing steps sends nothing", hub.calls.isEmpty())
        g.perform("github:connect", "send_connect", mapOf("owner" to "o", "repo" to "r"))
        val br = Json.str(Repo.info(p.state())["branch"])
        assertEquals("c0", hub.refs[br]); assertEquals("c0", hub.refs["main"])

        java.io.File(io.github.golshandvr.aiworkbench.core.Files.dir(p.store), "src").mkdirs()
        java.io.File(io.github.golshandvr.aiworkbench.core.Files.dir(p.store), "src/a.kt").writeText("fun a() = 1\n")
        p.store.transaction("fake integrate") { s ->
            Json.obj(s["handoffs"])["H-1"] = linkedMapOf<String, Any?>("handoff_id" to "H-1", "integrated_at" to "2026-01-01T00:00:00Z",
                "integrated_files" to arrayListOf<Any?>("src/a.kt"))
        }
        g.perform("github:save", "send_save")
        assertEquals(mapOf("src/a.kt" to "fun a() = 1\n"), hub.files(br))
        assertEquals("c0", hub.refs["main"])
        val head = Json.str(Repo.info(p.state())["head"])
        assertEquals(hub.refs[br], head)

        val t = Json.str(p.createTask(linkedMapOf("title" to "A", "objective" to "a", "acceptance_criteria" to arrayListOf<Any?>("ok")))["task_id"])
        val vid = p.store.transaction("version") { s ->
            Json.obj(s["milestones"])["MS-1"] = linkedMapOf<String, Any?>("milestone_id" to "MS-1", "title" to "M", "status" to "accepted",
                "task_ids" to arrayListOf<Any?>(t))
            Json.obj(s["versions"])["VER-1"] = linkedMapOf<String, Any?>("version_id" to "VER-1", "label" to "1.0.0", "status" to "proposed",
                "milestone_ids" to arrayListOf<Any?>("MS-1"), "history" to ArrayList<Any?>())
            "VER-1"
        }
        assertTrue("manual version step replaced by the GitHub one", g.steps().none { it.key == "version:$vid" })
        g.perform("github:release:$vid", "send_release")
        val v = Json.obj(Json.obj(p.state()["versions"])[vid])
        assertEquals("released", v["status"]); assertEquals("v1.0.0", v["tag"])
        assertEquals(head, hub.refs["v1.0.0"]); assertEquals(listOf("v1.0.0"), hub.releases)
        assertTrue(g.steps().none { it.key.startsWith("github:") })
    }
}
