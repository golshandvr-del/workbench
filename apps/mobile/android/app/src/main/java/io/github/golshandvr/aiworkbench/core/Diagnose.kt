package io.github.golshandvr.aiworkbench.core

/**
 * Smart problem detection and the troubleshooting prompt (roadmap 4.2.0 / mobile 1.3.0, flowchart F13–F15).
 *
 * Port of desktop `aiwb/v2/diagnose.py`; both are checked against
 * `packages/contracts/fixtures/diagnose/diagnose-corpus.v1.json` (same codes, same order).
 */
object Diagnose {
    data class Problem(val code: String, val severity: String, val message: String, val path: String = "") {
        fun toMap(): Obj = linkedMapOf("code" to code, "severity" to severity, "message" to message, "path" to path)
    }

    data class Result(val acceptable: Boolean, val problems: List<Problem>)

    data class FileBlock(val path: String, val body: String, val fenced: Boolean, val fenceBalanced: Boolean)

    const val TROUBLESHOOT_ATTEMPTS = 3

    private val FILE_HEAD = Regex("^\\s*<<<AIWB_FILE\\s+(.*?)\\s*>>>\\s*$")
    private const val FILE_END = "<<<AIWB_END_FILE>>>"
    private val ATTR = Regex("(\\w+)=\"([^\"]*)\"")
    private val ATTEMPT = Regex("(?m)^\\s*AIWB_ATTEMPT_ID:\\s*(\\S+)")
    private const val MAN_OPEN = "<<<AIWB_HANDOFF>>>"
    private const val MAN_END = "<<<AIWB_END_HANDOFF>>>"
    private val FENCE = Regex("^\\s*(`{3,}|~{3,})")
    private val TEST_CLAIM = Regex("\\b(all\\s+)?tests?\\s+(pass(ed|es)?|green|succeed(ed|s)?)\\b|\\bbuild\\s+(passed|succeeded)\\b",
        RegexOption.IGNORE_CASE)
    private val BLOCK_LINE = Regex("^\\s*(def|class|if|for|while|with|try|elif|else|except|finally)\\b.*:\\s*$")
    private val CODE_EXT = listOf(".py", ".kt", ".kts", ".java", ".js", ".ts", ".tsx", ".jsx", ".dart", ".go", ".rs", ".c", ".cpp", ".h",
        ".cs", ".swift", ".rb", ".php", ".gradle", ".yml", ".yaml")
    val SEVERITY = mapOf("truncated" to "error", "no_manifest" to "error", "wrong_attempt" to "error", "unsafe_path" to "error",
        "out_of_scope" to "error", "empty_file" to "error", "missing_deliverable" to "error", "failed_outcome" to "error",
        "copy_damage" to "warning", "unverified_test_claim" to "warning")

    /** AIWB file blocks, and whether the last block was left open. */
    fun parseFiles(text: String): Pair<List<FileBlock>, Boolean> {
        val files = ArrayList<FileBlock>()
        var path: String? = null
        var lines = ArrayList<String>()
        for (line in text.replace("\r\n", "\n").split("\n")) {
            if (path == null) {
                val m = FILE_HEAD.find(line) ?: continue
                path = ATTR.findAll(m.groupValues[1]).associate { it.groupValues[1] to it.groupValues[2] }["path"] ?: ""
                lines = ArrayList()
                continue
            }
            if (line.trim() == FILE_END) { files.add(close(path, lines)); path = null } else lines.add(line)
        }
        val open = path != null
        if (path != null) files.add(close(path, lines))
        return files to open
    }

    private fun close(path: String, raw: List<String>): FileBlock {
        var lines = raw.dropWhile { it.isBlank() }.dropLastWhile { it.isBlank() }
        val m = lines.firstOrNull()?.let { FENCE.find(it) }
        var balanced = true
        if (m != null) {
            val mark = m.groupValues[1]
            balanced = lines.size > 1 && lines.last().trim() == mark
            lines = if (balanced) lines.subList(1, lines.size - 1) else lines.drop(1)
        }
        return FileBlock(path, lines.joinToString("\n"), m != null, balanced)
    }

    private fun inScope(path: String, allowed: List<String>): Boolean {
        if (allowed.isEmpty()) return true
        for (raw in allowed) {
            val a = raw.trim()
            val base = a.trimEnd('*').trimEnd('/')
            if (base.isEmpty() || path == base || path.startsWith("$base/") || (a.endsWith("*") && path.startsWith(a.trimEnd('*')))) return true
        }
        return false
    }

    private fun indent(s: String) = s.length - s.trimStart().length

    private fun pythonIndentLost(body: String): Boolean {
        val lines = body.split("\n").filter { it.isNotBlank() && !it.trim().startsWith("#") }
        for (i in 0 until lines.size - 1) {
            if (BLOCK_LINE.matches(lines[i]) && indent(lines[i + 1]) <= indent(lines[i])) return true
        }
        return false
    }

    /** (manifest or null, opened-but-not-closed). An unreadable manifest is an empty map. */
    private fun manifest(text: String): Pair<Obj?, Boolean> {
        val i = text.indexOf(MAN_OPEN)
        if (i < 0) return null to false
        val j = text.indexOf(MAN_END, i)
        if (j < 0) return null to true
        var body = text.substring(i + MAN_OPEN.length, j).trim().trim('`').trim()
        if (body.startsWith("json")) body = body.substring(4)
        return try { Json.parseObj(body) to false } catch (_: Exception) { LinkedHashMap<String, Any?>() to false }
    }

    private fun unsafe(p: String): Boolean = p.isEmpty() || p.startsWith("/") || p.startsWith("\\") ||
        Regex("^[A-Za-z]:").containsMatchIn(p) || ".." in p.replace('\\', '/').split("/")

    fun diagnose(text: String?, attemptId: String = "", allowedPaths: List<String> = emptyList(),
                 expectedPaths: List<String> = emptyList()): Result {
        val probs = ArrayList<Problem>()
        fun add(code: String, message: String, path: String = "") { probs.add(Problem(code, SEVERITY.getValue(code), message, path)) }
        val t = text.orEmpty()
        val (files, openFile) = parseFiles(t)
        val (man, manOpen) = manifest(t)
        if (openFile) add("truncated", "the file block ${files.last().path.ifEmpty { "(no path)" }} was never closed — the answer was cut off", files.last().path)
        else if (manOpen) add("truncated", "the AIWB_HANDOFF manifest was opened and never closed — the answer was cut off")
        if (man == null && !manOpen) add("no_manifest", "there is no AIWB_HANDOFF manifest (summary, outcome, open items)")
        val claimed = ATTEMPT.find(t)?.groupValues?.get(1).orEmpty().ifEmpty { man?.get("attempt_id")?.toString().orEmpty() }
        if (attemptId.isNotEmpty() && claimed.isNotEmpty() && claimed != attemptId)
            add("wrong_attempt", "the answer is for attempt $claimed, this prompt was $attemptId")
        for (f in files) {
            val p = f.path
            if (unsafe(p)) { add("unsafe_path", "unsafe file path '$p'", p); continue }
            if (!inScope(p, allowedPaths)) add("out_of_scope", "$p is outside this task's allowed paths (${allowedPaths.joinToString(", ")})", p)
            if (f.fenced && !f.fenceBalanced && !openFile) add("truncated", "the code fence in $p was never closed", p)
            if (f.body.isBlank()) { add("empty_file", "$p is empty", p); continue }
            val low = p.lowercase()
            if (CODE_EXT.any { low.endsWith(it) } && !f.fenced)
                add("copy_damage", "$p is not inside a four-backtick fence; indentation or backticks may be lost", p)
            else if (low.endsWith(".py") && pythonIndentLost(f.body))
                add("copy_damage", "$p lost its indentation (a block line is not followed by an indented line)", p)
        }
        val delivered = files.map { it.path }.toSet()
        for (p in expectedPaths) if (p !in delivered) add("missing_deliverable", "expected file $p was not delivered", p)
        val outcome = man?.get("outcome")?.toString().orEmpty()
        if (outcome == "failed" || outcome == "blocked") add("failed_outcome", "the AI reports the outcome '$outcome'")
        if (Json.list(man?.get("validation_claims")).isNotEmpty() || TEST_CLAIM.containsMatchIn(t))
            add("unverified_test_claim", "the AI claims tests/build passed — that is not evidence; run them or record NOT RUN")
        return Result(probs.none { it.severity == "error" }, probs)
    }

    /** F15: ask the same AI to fix exactly the problems found — nothing else. */
    fun troubleshootPrompt(state: Obj, h: Obj, n: Obj, problems: List<Obj>, attemptNo: Int): String {
        val t = Json.obj(State.coll(state, "tasks")[h["task_id"]])
        val errs = problems.filter { it["severity"] == "error" }.ifEmpty { problems }
        val lines = mutableListOf("AIWB_ATTEMPT_ID: ${n["attempt_id"]}", "(Repeat the line above as the first line of your answer.)", "",
            "# AI Workbench — troubleshooting request $attemptNo for ${t["task_id"]} ${t["title"]}",
            "Your previous answer could not be accepted. Fix ONLY these problems and send the corrected files " +
                "completely; do not change anything else.", "", "## Problems found")
        lines += errs.map { "- [${it["code"]}] ${it["message"]}" }
        val warns = problems.filter { it["severity"] == "warning" && it !in errs }
        if (warns.isNotEmpty()) lines += listOf("", "## Also check") + warns.map { "- [${it["code"]}] ${it["message"]}" }
        val allowed = Json.strs(t["allowed_paths"])
        if (allowed.isNotEmpty()) lines += listOf("", "## You may only write these paths") + allowed.map { "- $it" }
        lines += listOf("", "## Acceptance criteria") + Json.strs(t["acceptance_criteria"]).map { "- [ ] $it" }.ifEmpty { listOf("- (none)") }
        lines += listOf("", "## Format") + Prompts.FILE_RULES + listOf("- Then one manifest:", MAN_OPEN,
            Prompts.dumpsSpaced(linkedMapOf("schema_version" to "1.0", "handoff_id" to n["handoff_id"], "task_id" to n["task_id"],
                "task_revision" to n["task_revision"], "attempt_id" to n["attempt_id"], "outcome" to "complete|partial", "summary" to "…",
                "completed_items" to listOf("…"), "unresolved_items" to emptyList<Any?>(), "validation_claims" to emptyList<Any?>())),
            MAN_END)
        return lines.joinToString("\n")
    }
}
