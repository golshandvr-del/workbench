package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Intake
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.ModelError
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.Prompts
import io.github.golshandvr.aiworkbench.core.State
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.nio.file.Files

/**
 * mobile 1.0.1: the "Verify" step can no longer trap the user (reported on a phone: "Error: result is required").
 * One-tap passed/failed, lenient words, an honest "accept on review without tests" (NOT RUN, never passing
 * evidence), the team-size setting, and four-backtick fences that survive a chat copy.
 */
class VerifyStepTest {
    private fun project(): Pair<Project, String> {
        val p = Project(ProjectStore(File(Files.createTempDirectory("aiwb").toFile(), "calc")))
        p.installTemplates()
        val tid = Json.str(p.createTask(linkedMapOf("title" to "Engine", "objective" to "calc",
            "acceptance_criteria" to arrayListOf<Any?>("adds")))["task_id"])
        for (s in listOf("ready", "in_progress", "validation_pending")) p.transition(tid, s, "test")
        return p to tid
    }

    @Test fun verifyStepOffersOneTapChoices() {
        val (p, tid) = project()
        val step = Guide(p).find("task:$tid")
        assertEquals("validation_passed", step.primary?.id)
        assertTrue(step.actions.map { it.id }.containsAll(listOf("validation_failed", "waive_validation", "record_validation")))
        assertTrue(step.explain.contains("NOT RUN"))
        for (a in step.actions) for (n in a.needs) assertTrue("hint for $n", Guide.INPUT_HINTS.containsKey(n))
    }

    @Test fun passedButtonNeedsNoTyping() {
        val (p, tid) = project()
        Guide(p).perform("task:$tid", "validation_passed")
        val ev = State.coll(p.state(), "evidence").values.map { Json.obj(it) }
        assertEquals(listOf("test_run:passed:true"), ev.map { "${it["type"]}:${it["result"]}:${it["verified"]}" })
        assertEquals("in_review", State.require(p.state(), "tasks", tid)["status"])
    }

    @Test fun lenientWordsAndGuidedError() {
        val (p, tid) = project()
        try { Guide(p).perform("task:$tid", "record_validation", mapOf("result" to "maybe")); fail() }
        catch (e: ModelError) { assertTrue(e.message!!.contains("buttons")) }
        Guide(p).perform("task:$tid", "record_validation", mapOf("result" to " OK "))
        assertEquals("passed", Json.obj(State.coll(p.state(), "evidence").values.first())["result"])
    }

    @Test fun waiverAcceptsOnReviewAndStaysHonest() {
        val (p, tid) = project()
        val out = Guide(p).perform("task:$tid", "waive_validation", mapOf("reason" to "no Android Studio on my phone"))
        assertTrue(out.message.contains("NOT RUN"))
        val st = p.state(); val t = State.require(st, "tasks", tid)
        assertEquals("manual_review", t["acceptance_policy"])
        assertEquals("not_run", Json.obj(t["validation_waiver"])["result"])
        assertTrue(Json.strs(t["flags"]).any { "NOT RUN" in it })
        assertFalse(State.coll(st, "evidence").values.any { Json.obj(it)["type"] in setOf("test_run", "build_run") })
        assertTrue(Json.list(st["events"]).any { Json.obj(it)["type"] == "validation_waived" })
        assertEquals("in_review", t["status"])
        Guide(p).perform("task:$tid", "approve")
        assertEquals("done", State.require(p.state(), "tasks", tid)["status"])
        try { p.waiveValidation(tid, "late"); fail() } catch (_: ModelError) { }
    }

    @Test fun teamSizeIsSetOnThePhoneAndReachesTheCharterPrompt() {
        val (p, _) = project()
        assertEquals(2, p.maxParallelChats())
        p.setMaxParallelChats(3)
        assertEquals(3, p.maxParallelChats())
        assertTrue(p.charterPrompt("calc").contains("Maximum chats the user will follow at the same time: 3"))
        try { p.setMaxParallelChats(0); fail() } catch (_: ModelError) { }
        try { p.setMaxParallelChats(13); fail() } catch (_: ModelError) { }
    }

    @Test fun promptsAskForFourBacktickFencesAndTheyParse() {
        val rules = Prompts.FILE_RULES.joinToString("\n")
        assertTrue(rules.contains("````"))
        assertFalse(rules.contains("body=\"raw\""))
        val answer = "<<<AIWB_FILE path=\"core/Engine.kt\" action=\"write\">>>\n````kotlin\nclass E {\n    fun `adds two`() {}\n}\n" +
            "```\ninner\n```\n````\n<<<AIWB_END_FILE>>>\n"
        val f = Intake.parse(answer).files.single()
        assertEquals("class E {\n    fun `adds two`() {}\n}\n```\ninner\n```\n", f.content)
    }
}
