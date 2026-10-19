package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Charter
import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.ModelError
import io.github.golshandvr.aiworkbench.core.Obj
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectBundle
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.State
import io.github.golshandvr.aiworkbench.core.StrictJson
import io.github.golshandvr.aiworkbench.core.Timeline
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.nio.file.Files

/**
 * Gate mobile 1.0.0: the phone runs the whole guided loop on its own — charter, plan review, prompts, answers,
 * review, validation, milestone, release — with the same document shapes as the desktop, and never reaches a
 * dead end (every state has at least one step).
 */
class StandaloneLoopTest {
    private fun contracts(): File {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        return File(requireNotNull(dir), "packages/contracts")
    }

    private fun charterText(): String {
        val body = File(contracts(), "fixtures/valid/project-charter.v1.todo.json").readText()
        return "Here is the plan.\n<<<AIWB_PROJECT_CHARTER>>>\n$body\n<<<AIWB_END_PROJECT_CHARTER>>>\n"
    }

    private fun project(): Project {
        val p = Project(ProjectStore(File(Files.createTempDirectory("aiwb").toFile(), "todo")))
        p.installTemplates()
        return p
    }

    private fun answer(h: Obj, outcome: String = "complete", unresolved: List<String> = emptyList()): String {
        val m = linkedMapOf<String, Any?>("schema_version" to "1.0", "handoff_id" to h["handoff_id"], "task_id" to h["task_id"],
            "task_revision" to h["task_revision"], "attempt_id" to h["attempt_id"], "outcome" to outcome, "summary" to "done",
            "completed_items" to listOf("a"), "unresolved_items" to unresolved, "assumptions" to emptyList<Any?>(),
            "decision_requests" to emptyList<Any?>(), "validation_claims" to listOf("tests pass"), "recommended_next_action" to "review")
        return "AIWB_ATTEMPT_ID: ${h["attempt_id"]}\n<<<AIWB_FILE path=\"src/core/a.py\" action=\"write\" body=\"raw\">>>\nx=1\n" +
            "<<<AIWB_END_FILE>>>\n<<<AIWB_HANDOFF>>>\n${StrictJson.stringify(m)}\n<<<AIWB_END_HANDOFF>>>\n"
    }

    @Test fun charterFixtureIsValid() {
        val r = Charter.parse(charterText(), State.empty("todo"))
        assertTrue(r.errors.toString(), r.ok)
    }

    @Test fun brokenCharterGetsFixPrompt() {
        val r = Charter.parse("<<<AIWB_PROJECT_CHARTER>>>\n{\"schema_version\": \"1.0\"}\n<<<AIWB_END_PROJECT_CHARTER>>>")
        assertFalse(r.ok)
        assertTrue(r.errors.contains("architecture: section missing"))
        assertTrue(Charter.fixPrompt(r).contains("architecture: section missing"))
        val cut = Charter.parse("<<<AIWB_PROJECT_CHARTER>>>\n{\"schema_version\": ")
        assertTrue(cut.errors.single().contains("not closed"))
        val invalid = File(contracts(), "fixtures/invalid/project-charter.v1.no-coordination.json").readText()
        val r2 = Charter.parse("<<<AIWB_PROJECT_CHARTER>>>\n$invalid\n<<<AIWB_END_PROJECT_CHARTER>>>")
        assertTrue(r2.errors.toString(), r2.errors.contains("coordination: section missing"))
    }

    @Test fun chatCopyDamagedCharterIsRepaired() {
        val damaged = "\u200b" + charterText().replace("\"schema_version\"", "“schema_version”")
        val r = Charter.parse(damaged)
        assertTrue(r.errors.toString(), r.ok)
        assertTrue(r.fixes.isNotEmpty())
    }

    @Test fun fullLoopWithoutDeadEnds() {
        val p = project()
        val g = Guide(p)
        assertEquals("design", g.next().key)
        val design = g.perform("design", "design", mapOf("goal" to "A small offline todo app"))
        assertTrue(design.prompt.contains("Project Charter"))
        assertEquals("charter", g.next().key)
        g.perform("charter", "copy"); g.perform("charter", "sent")
        val pasted = g.perform("charter", "paste", mapOf("text" to charterText()))
        assertEquals(pasted.message, "proposal", pasted.kind)
        val plan = g.next()
        assertTrue(plan.key.startsWith("proposal:"))
        g.perform(plan.key, "accept")
        var st = p.state()
        assertEquals(3, State.coll(st, "tasks").size)
        assertEquals(2, State.coll(st, "milestones").size)
        assertEquals(listOf("0.1.0", "0.2.0"), State.coll(st, "versions").values.map { Json.obj(it)["label"] })
        assertEquals("ready", Json.obj(State.coll(st, "tasks")["TASK-0001"])["status"])
        assertEquals("blocked", Json.obj(State.coll(st, "tasks")["TASK-0002"])["status"])
        assertNotNull(p.charter())
        assertTrue(p.charterStartPrompt("agent-core-dev").contains("You may change only: src/core/**"))

        var guard = 0
        while (guard++ < 80) {
            st = p.state()
            val tasks = State.coll(st, "tasks").values.map { Json.obj(it) }
            val versions = State.coll(st, "versions").values.map { Json.obj(it) }
            if (versions.all { it["status"] == "released" }) break
            val s = g.next()
            assertTrue("dead end", g.steps().isNotEmpty())
            when {
                s.key.startsWith("task:") && s.primary?.id == "prepare" -> g.perform(s.key, "prepare")
                s.key.startsWith("handoff:") && s.primary?.id == "copy" -> g.perform(s.key, "copy")
                s.key.startsWith("handoff:") && s.primary?.id == "sent" -> g.perform(s.key, "sent")
                s.key.startsWith("handoff:") && s.primary?.id == "paste" -> {
                    val h = State.require(st, "handoffs", s.ref)
                    val out = g.perform(s.key, "paste", mapOf("text" to answer(h)))
                    assertEquals(out.message, "handoff", out.kind)
                }
                s.key.startsWith("handoff:") && s.primary?.id == "accept_handoff" -> g.perform(s.key, "accept_handoff")
                s.key.startsWith("task:") && s.primary?.id == "record_validation" ->
                    g.perform(s.key, "record_validation", mapOf("result" to "passed", "run_id" to "run-${s.ref}"))
                s.key.startsWith("task:") && s.primary?.id == "approve" -> g.perform(s.key, "approve")
                s.key.startsWith("milestone:") -> g.perform(s.key, "accept_milestone")
                s.key.startsWith("version:") -> g.perform(s.key, "release", mapOf("commit_sha" to "abcdef1234", "tag" to "", "run_id" to "42"))
                else -> fail("unexpected step ${s.key} ${s.primary?.id} with tasks ${tasks.map { it["task_id"].toString() + "=" + it["status"] }}")
            }
        }
        st = p.state()
        assertTrue(State.coll(st, "tasks").values.all { Json.obj(it)["status"] == "done" })
        assertTrue(State.coll(st, "versions").values.all { Json.obj(it)["status"] == "released" })
        assertEquals("manager_update", g.next().key)
        val tl = Timeline.build(st)
        assertTrue(tl.lanes.containsAll(listOf("agent-core-dev", "agent-desktop-dev", "agent-mobile-dev")))
        assertTrue(tl.events.any { it.importance == "critical" })
        assertTrue(tl.versions.all { it.released })
        // the bundle of a phone-run project reads back and the desktop rules see it as the same project
        val text = ProjectBundle.dumps(ProjectBundle.export(st, "todo"))
        val (_, back) = ProjectBundle.read(text)
        assertEquals(Json.int(st["state_revision"]), Json.int(back["state_revision"]))
    }

    @Test fun cutOffAnswerGetsContinuePrompt() {
        val p = project()
        val g = Guide(p)
        g.perform("design", "design", mapOf("goal" to "x"))
        val out = g.perform("charter", "paste", mapOf("text" to "Plan:\n```json\n{\"a\": 1,"))
        assertEquals("truncated", out.kind)
        assertEquals("continue", g.next().key)
        g.perform("continue", "dismiss")
        assertEquals("charter", g.next().key)
    }

    @Test fun repairAsksOnlyForMissing() {
        val p = project()
        p.importCharter(charterText()).ref.let { p.acceptAllValid(it) }
        val g = Guide(p)
        val h = p.startTask("TASK-0001")
        g.perform("handoff:${h["handoff_id"]}", "copy")
        g.perform("handoff:${h["handoff_id"]}", "sent")
        g.perform("handoff:${h["handoff_id"]}", "paste", mapOf("text" to answer(h, "partial", listOf("docs/contracts/core-api.md"))))
        val out = g.perform("handoff:${h["handoff_id"]}", "repair")
        assertTrue(out.prompt.contains("Still missing\n- docs/contracts/core-api.md"))
        assertTrue(out.prompt.contains("do NOT resend"))
    }

    @Test fun wrongAttemptIsRejected() {
        val p = project()
        p.importCharter(charterText()).ref.let { p.acceptAllValid(it) }
        val h = p.startTask("TASK-0001")
        val other = LinkedHashMap(h); other["attempt_id"] = "att-20260101-000000-deadbeef"
        val r = p.routeAnswer(answer(other))
        assertEquals("rejected", r.kind)
    }

    @Test fun releaseNeedsRealFacts() {
        val p = project()
        p.importCharter(charterText()).ref.let { p.acceptAllValid(it) }
        try { p.advanceVersion("VER-0001", "released"); fail() } catch (_: ModelError) {}
        try { p.advanceVersion("VER-0001", "local"); fail() } catch (_: ModelError) {}
    }

    @Test fun modelClaimIsNotEvidence() {
        val p = project()
        p.importCharter(charterText()).ref.let { p.acceptAllValid(it) }
        val h = p.startTask("TASK-0001")
        p.routeAnswer(answer(h))
        p.resolveHandoff(Json.str(h["handoff_id"]), true)
        val (status, reasons) = p.reviewTask("TASK-0001", true)
        assertEquals("validation_pending", status)
        assertTrue(reasons.single().contains("model claims do not count"))
    }
}
