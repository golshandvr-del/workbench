package io.github.golshandvr.aiworkbench

import android.app.Activity
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import io.github.golshandvr.aiworkbench.core.Flow
import io.github.golshandvr.aiworkbench.core.Guide
import io.github.golshandvr.aiworkbench.core.Project
import io.github.golshandvr.aiworkbench.core.ProjectBundle
import io.github.golshandvr.aiworkbench.core.ProjectStore
import io.github.golshandvr.aiworkbench.core.Timeline
import java.io.File

/**
 * Standalone mode (roadmap mobile 1.0.0): the whole guided loop runs on the phone, without the
 * desktop. Projects live in the app's private storage, use the same V2 document as the desktop,
 * and move between devices only as aiwb-bundle.v1 files chosen by the user (never merged).
 */
class StandaloneActivity : Activity() {
    private lateinit var body: LinearLayout
    private lateinit var status: TextView
    private var current: Project? = null
    private var pendingExport: String? = null

    private val projectsDir: File get() = File(filesDir, "projects").apply { mkdirs() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32, 32, 32, 32) }
        status = TextView(this).apply { textSize = 14f; setPadding(0, 8, 0, 16) }
        body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(status)
        root.addView(body)
        setContentView(ScrollView(this).apply { addView(root) })
        title = getString(R.string.standalone_title)
        showProjects()
    }

    // ---------------------------------------------------------------- project list
    private fun projectIds(): List<String> =
        projectsDir.listFiles().orEmpty().filter { File(it, "state.json").isFile }.map { it.name }.sorted()

    private fun showProjects() {
        current = null
        body.removeAllViews()
        heading(getString(R.string.standalone_projects))
        val ids = projectIds()
        if (ids.isEmpty()) text(getString(R.string.standalone_no_projects))
        for (id in ids) button(id) { open(id) }
        button(getString(R.string.standalone_new_project)) { newProject() }
        button(getString(R.string.standalone_import_bundle)) { pickImport() }
    }

    private fun newProject() {
        val name = EditText(this).apply { hint = getString(R.string.standalone_project_name); inputType = InputType.TYPE_CLASS_TEXT }
        val goal = EditText(this).apply { hint = getString(R.string.standalone_goal); minLines = 3 }
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; addView(name); addView(goal) }
        AlertDialog.Builder(this).setTitle(R.string.standalone_new_project).setView(box)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                val id = safeId(name.text.toString())
                if (id.isEmpty()) { say(getString(R.string.standalone_name_required)); return@setPositiveButton }
                val dir = File(projectsDir, id)
                if (File(dir, "state.json").isFile) { say(getString(R.string.standalone_exists, id)); return@setPositiveButton }
                dir.mkdirs()
                guard {
                    val p = Project(ProjectStore(dir, id))
                    p.installTemplates()
                    if (goal.text.isNotBlank()) p.setGoal(goal.text.toString())
                    open(id)
                }
            }.setNegativeButton(android.R.string.cancel, null).show()
    }

    // ---------------------------------------------------------------- one project
    private fun open(id: String) {
        current = Project(ProjectStore(File(projectsDir, id), id))
        render()
    }

    private fun render(message: String = "") {
        val p = current ?: return showProjects()
        body.removeAllViews()
        if (message.isNotEmpty()) say(message)
        heading(p.store.projectId)
        // Phase bar (roadmap 4.0.0): where the project is in the owner's flowchart.
        try { text(Flow.label(p.flow())) } catch (e: Exception) { say(e.message ?: e.toString()) }
        val steps = try { Guide(p).steps() } catch (e: Exception) { say(e.message ?: e.toString()); emptyList() }
        steps.firstOrNull()?.let { stepCard(p, it, true) }
        if (steps.size > 1) {
            heading(getString(R.string.standalone_other_steps))
            steps.drop(1).take(6).forEach { stepCard(p, it, false) }
        }
        heading(getString(R.string.standalone_paste_answer))
        val paste = EditText(this).apply { minLines = 4; hint = getString(R.string.standalone_paste_hint) }
        body.addView(paste)
        button(getString(R.string.standalone_route)) {
            guard { val r = p.routeAnswer(paste.text.toString()); render(r.message) }
        }
        heading(getString(R.string.standalone_timeline))
        val info = TextView(this)
        val tl = TimelineView(this).apply {
            model = Timeline.build(p.state())
            onSelect = { info.text = it }
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 520)
        }
        body.addView(tl)
        body.addView(info)
        button(getString(R.string.standalone_overview)) { showOverview(p) }
        button(getString(R.string.standalone_settings)) { editSettings(p) }
        button(getString(R.string.standalone_export_bundle)) { pickExport(p) }
        button(getString(R.string.standalone_back)) { showProjects() }
    }

    private fun stepCard(p: Project, s: Guide.Step, first: Boolean) {
        body.addView(TextView(this).apply {
            text = s.title; textSize = if (first) 18f else 15f; setTypeface(null, Typeface.BOLD); setPadding(0, 16, 0, 4)
        })
        text(s.explain)
        for (a in s.actions) {
            button(a.label) {
                if (a.id == "copy" && s.prompt.isNotEmpty()) copy(s.prompt)
                val needs = a.needs.filter { it != "text" || a.id != "paste" }
                if (a.id == "paste") ask(s, a, listOf("text") + needs, p) else if (needs.isEmpty()) run(p, s, a, emptyMap()) else ask(s, a, needs, p)
            }
        }
    }

    private fun ask(s: Guide.Step, a: Guide.Action, needs: List<String>, p: Project) {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 8, 24, 8) }
        val fields = needs.distinct().associateWith { n ->
            EditText(this).apply {
                hint = Guide.INPUT_HINTS[n] ?: n.replace('_', ' ')
                inputType = when (n) { "text" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
                    "ais" -> InputType.TYPE_CLASS_NUMBER; else -> InputType.TYPE_CLASS_TEXT }
                if (n == "text") minLines = 4
            }.also { box.addView(it) }
        }
        AlertDialog.Builder(this).setTitle(a.label).setView(box)
            .setPositiveButton(android.R.string.ok) { _, _ -> run(p, s, a, fields.mapValues { it.value.text.toString() }) }
            .setNegativeButton(android.R.string.cancel, null).show()
    }

    private fun run(p: Project, s: Guide.Step, a: Guide.Action, inp: Map<String, String>) = guard {
        val out = Guide(p).perform(s.key, a.id, inp)
        if (out.prompt.isNotEmpty()) copy(out.prompt)
        render(out.message)
    }

    // ---------------------------------------------------------------- bundles (SAF, user-chosen files only)
    private fun pickExport(p: Project) = guard {
        pendingExport = ProjectBundle.dumps(ProjectBundle.export(p.state(), p.store.projectId, version = BuildConfig.VERSION_NAME))
        startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE); type = "application/json"
            putExtra(Intent.EXTRA_TITLE, "${p.store.projectId}.aiwb-bundle.json")
        }, REQ_EXPORT)
    }

    private fun pickImport() {
        startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE); type = "*/*"
        }, REQ_IMPORT)
    }

    @Deprecated("Activity result API is not available without AndroidX")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (resultCode != RESULT_OK || uri == null) return
        when (requestCode) {
            REQ_EXPORT -> guard {
                val text = pendingExport ?: return@guard
                contentResolver.openOutputStream(uri)?.use { it.write(text.toByteArray(Charsets.UTF_8)) }
                pendingExport = null
                say(getString(R.string.standalone_exported))
            }
            REQ_IMPORT -> guard {
                val bytes = contentResolver.openInputStream(uri)?.use { s -> s.readBytes().also { if (it.size > MAX_BUNDLE) error("bundle too large") } }
                    ?: return@guard
                val text = String(bytes, Charsets.UTF_8)
                val (b, st) = ProjectBundle.read(text)
                val id = safeId(Json(st["project_id"]).ifEmpty { Json((b["project"] as? Map<*, *>)?.get("name")) }).ifEmpty { "imported" }
                val store = ProjectStore(File(projectsDir, id).apply { mkdirs() }, id)
                val plan = ProjectBundle.planImport(if (store.exists()) store.load() else null, st)
                if (plan.safe || plan.kind == "same") {
                    ProjectBundle.importInto(store, text)
                    open(id); say(plan.message)
                } else {
                    AlertDialog.Builder(this).setTitle(R.string.standalone_import_bundle).setMessage(plan.message)
                        .setPositiveButton(R.string.standalone_replace) { _, _ ->
                            guard { ProjectBundle.importInto(store, text, force = true); open(id); say(plan.message) }
                        }.setNegativeButton(android.R.string.cancel, null).show()
                }
            }
        }
    }

    // ---------------------------------------------------------------- helpers
    private fun Json(v: Any?): String = (v as? String).orEmpty()

    private fun safeId(raw: String): String =
        raw.trim().lowercase().replace(Regex("[^a-z0-9._-]+"), "-").trim('-', '.').take(60)

    private fun guard(block: () -> Unit) {
        try { block() } catch (e: Exception) { say(getString(R.string.standalone_error, e.message ?: e.javaClass.simpleName)) }
    }

    private fun copy(text: String) {
        (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("AI Workbench", text))
    }

    private fun say(msg: String) {
        status.text = msg; status.visibility = View.VISIBLE
        status.setTextColor(if (msg.startsWith(getString(R.string.standalone_error, "").trimEnd())) 0xFFC42B1C.toInt() else 0xFF1C1C1C.toInt())
        (status.parent?.parent as? ScrollView)?.post { (status.parent?.parent as? ScrollView)?.smoothScrollTo(0, 0) }
    }

    // ---------------------------------------------------------------- settings + overview
    private fun editSettings(p: Project) {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 8, 24, 8) }
        box.addView(TextView(this).apply { text = getString(R.string.standalone_goal_label) })
        val goal = EditText(this).apply { setText(Json(p.state()["settings"].let { (it as? Map<*, *>)?.get("goal") })); minLines = 2 }
        box.addView(goal)
        box.addView(TextView(this).apply { text = getString(R.string.standalone_chats_label); setPadding(0, 16, 0, 0) })
        val chats = EditText(this).apply { inputType = InputType.TYPE_CLASS_NUMBER; setText(p.maxParallelChats().toString()) }
        box.addView(chats)
        box.addView(TextView(this).apply { text = getString(R.string.standalone_chats_help); textSize = 12f })
        AlertDialog.Builder(this).setTitle(R.string.standalone_settings).setView(box)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                guard {
                    p.setMaxParallelChats(chats.text.toString().trim().toIntOrNull() ?: error("1–12"))
                    if (goal.text.isNotBlank()) p.setGoal(goal.text.toString())
                    render(getString(R.string.standalone_saved))
                }
            }.setNegativeButton(android.R.string.cancel, null).show()
    }

    private fun showOverview(p: Project) {
        val st = p.state()
        fun coll(k: String) = (st[k] as? Map<*, *>).orEmpty().values.mapNotNull { it as? Map<*, *> }
        val sb = StringBuilder()
        sb.append(getString(R.string.standalone_chats_label)).append(' ').append(p.maxParallelChats()).append("\n\n")
        sb.append("AI team\n")
        for (a in coll("agents").filter { it["enabled"] != false }.sortedBy { Json(it["agent_id"]) })
            sb.append("• ").append(Json(a["agent_id"])).append(" (").append(Json(a["role"])).append(")\n")
        sb.append("\nTasks\n")
        for (t in coll("tasks").sortedBy { Json(it["task_id"]) })
            sb.append("• ").append(Json(t["task_id"])).append(" [").append(Json(t["status"])).append("] ").append(Json(t["title"]))
                .append(" — ").append(Json(t["owner_agent_id"])).append("\n")
        sb.append("\nVersions\n")
        for (v in coll("versions").sortedBy { Json(it["version_id"]) })
            sb.append("• ").append(Json(v["label"])).append(" [").append(Json(v["status"])).append("]\n")
        val ch = (st["settings"] as? Map<*, *>)?.get("charter") as? Map<*, *>
        val qs = (ch?.get("questions_for_user") as? List<*>).orEmpty().mapNotNull { it as? String }
        if (qs.isNotEmpty()) { sb.append("\nQuestions for you\n"); qs.forEach { sb.append("• ").append(it).append("\n") } }
        AlertDialog.Builder(this).setTitle(R.string.standalone_overview)
            .setMessage(sb.toString().trim()).setPositiveButton(android.R.string.ok, null).show()
    }

    private fun heading(t: String) = body.addView(TextView(this).apply {
        text = t; textSize = 16f; setTypeface(null, Typeface.BOLD); setPadding(0, 24, 0, 8)
    })

    private fun text(t: String) = body.addView(TextView(this).apply { text = t; textSize = 14f })

    private fun button(label: String, onClick: () -> Unit) = body.addView(Button(this).apply {
        text = label; isAllCaps = false; setOnClickListener { onClick() }
    })

    companion object {
        private const val REQ_EXPORT = 41
        private const val REQ_IMPORT = 42
        private const val MAX_BUNDLE = 25 * 1024 * 1024
    }
}
