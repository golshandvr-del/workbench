package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.TaskMenu
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Roadmap 6.1.0 / mobile 3.1.0: long press = the desktop's four-item menu, enabled only when the Guide allows it. */
class TaskMenuTest {
    private fun step(key: String, vararg ids: String, ref: String = "") =
        Guide.Step(key, "prompt", key, "", ids.map { Guide.Action(it, "do $it", if (it == "paste") listOf("text") else emptyList()) }, ref = ref)

    @Test fun sameItemsAsTheDesktop() {
        assertEquals(listOf("COPY PROMPT", "SEND PROMPT", "GET AI RESPONSE", "MARK AS DONE"), TaskMenu.ITEMS.map { it.label })
        assertEquals(listOf("copy", "send", "sparkle", "check"), TaskMenu.ITEMS.map { it.icon })
    }

    @Test fun nothingOfferedMeansEverythingDisabledWithAHint() {
        val rows = TaskMenu.items(listOf(step("task:T-2", "copy")), "T-1")
        assertTrue(rows.none { it.enabled })
        assertEquals("Copy the prompt first.", rows[1].hint)
        assertEquals(-1, TaskMenu.firstEnabled(rows))
        assertEquals(-1, TaskMenu.move(rows, 0, 1))
    }

    @Test fun taskStepEnablesMatchingItems() {
        val rows = TaskMenu.items(listOf(step("task:T-1", "prepare", "approve")), "T-1")
        assertEquals(listOf(true, false, false, true), rows.map { it.enabled })
        assertEquals("prepare", rows[0].action)
        assertEquals("task:T-1", rows[0].step)
        assertEquals("approve", rows[3].action)
        assertEquals(0, TaskMenu.firstEnabled(rows))
        assertEquals(3, TaskMenu.move(rows, 0, 1))
        assertEquals(0, TaskMenu.move(rows, 3, 1))
        assertEquals(3, TaskMenu.move(rows, 0, -1))
    }

    @Test fun copyIsPreferredOverPrepareAndHandoffStepsBelongToTheirTask() {
        val steps = listOf(step("task:T-1", "prepare"), step("handoff:H-1", "copy", "sent", "paste", ref = "H-1"))
        val state = mapOf("handoffs" to mapOf("H-1" to mapOf("task_id" to "T-1")))
        val rows = TaskMenu.items(steps, "T-1", TaskMenu.handoffTask(state))
        assertEquals(listOf(true, true, true, false), rows.map { it.enabled })
        assertEquals("copy", rows[0].action)
        assertEquals("handoff:H-1", rows[0].step)
        assertEquals(listOf("text"), rows[2].needs)
        assertFalse(TaskMenu.items(steps, "T-2", TaskMenu.handoffTask(state)).any { it.enabled })
    }
}
