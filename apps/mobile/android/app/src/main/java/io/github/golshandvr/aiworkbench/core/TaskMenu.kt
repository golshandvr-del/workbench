package io.github.golshandvr.aiworkbench.core

/**
 * Long-press menu of a Mission Map task circle on the phone (roadmap 6.1.0 / mobile 3.1.0), as data.
 * Port of the desktop `aiwb/ui/task_menu.py`: the same four items (COPY PROMPT · SEND PROMPT · GET AI RESPONSE ·
 * MARK AS DONE), each enabled only when the [Guide] offers a matching action for that task right now.
 */
object TaskMenu {
    data class Item(val id: String, val label: String, val icon: String, val allowed: List<String>)

    data class Row(val id: String, val label: String, val icon: String, val enabled: Boolean, val step: String,
                   val action: String, val needs: List<String>, val hint: String)

    /** Same ids, labels, icons and allowed Guide actions as the desktop `structure5.TASK_MENU`. */
    val ITEMS = listOf(
        Item("copy_prompt", "COPY PROMPT", "copy", listOf("copy", "prepare")),
        Item("send_prompt", "SEND PROMPT", "send", listOf("sent")),
        Item("get_response", "GET AI RESPONSE", "sparkle", listOf("paste")),
        Item("mark_done", "MARK AS DONE", "check", listOf("accept_handoff", "approve", "validation_passed", "waive_validation")),
    )

    val DISABLED_HINT = mapOf(
        "copy_prompt" to "No prompt to copy for this task now.",
        "send_prompt" to "Copy the prompt first.",
        "get_response" to "No prompt is waiting for an answer.",
        "mark_done" to "Nothing to accept for this task yet.",
    )

    /** The task a Guide step belongs to ('' when it is not about one task). */
    fun stepTask(step: Guide.Step): String = if (step.key.startsWith("task:")) step.key.substringAfter(":") else ""

    /** The task of a `handoff:<id>` step, read from the project state (the desktop step carries `task_id`). */
    fun handoffTask(state: Map<*, *>): (Guide.Step) -> String = { step ->
        if (step.key.startsWith("handoff:")) Json.str(Json.obj(Json.obj(state["handoffs"])[step.ref])["task_id"]) else ""
    }

    /** Menu rows for [taskId] of the project behind [guide] right now. */
    fun forTask(guide: Guide, taskId: String): List<Row> = items(guide.steps(), taskId, handoffTask(guide.project.state()))

    /** Steps about [taskId]: its own `task:` step, plus handoff steps whose ref names a handoff of that task. */
    fun items(steps: List<Guide.Step>, taskId: String, handoffTask: (Guide.Step) -> String = { "" }): List<Row> {
        val mine = steps.filter { stepTask(it) == taskId || (stepTask(it).isEmpty() && handoffTask(it) == taskId) }
        return ITEMS.map { item ->
            var found: Pair<Guide.Step, Guide.Action>? = null
            loop@ for (actionId in item.allowed) {
                for (s in mine) {
                    val act = s.actions.firstOrNull { it.id == actionId }
                    if (act != null) { found = s to act; break@loop }
                }
            }
            val f = found
            if (f == null) Row(item.id, item.label, item.icon, false, "", "", emptyList(), DISABLED_HINT.getValue(item.id))
            else Row(item.id, item.label, item.icon, true, f.first.key, f.second.id, f.second.needs, f.second.label)
        }
    }

    /** Index of the first enabled row (-1 when none). */
    fun firstEnabled(rows: List<Row>): Int = rows.indexOfFirst { it.enabled }

    /** Next enabled row from [index] in direction [delta] (wraps; -1 when nothing is enabled). */
    fun move(rows: List<Row>, index: Int, delta: Int): Int {
        val n = rows.size
        if (n == 0 || rows.none { it.enabled }) return -1
        var i = index
        repeat(n) {
            i = ((i + delta) % n + n) % n
            if (rows[i].enabled) return i
        }
        return index
    }
}
