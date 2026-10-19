package io.github.golshandvr.aiworkbench.core

/**
 * One paste box for model answers on the phone (roadmap mobile 1.0.0; same rules as desktop 3.2.0).
 *
 * Accepts AIWB file/command blocks (raw or fenced bodies) or a `workbench-v1/v2` JSON object (plain, fenced, or
 * surrounded by prose). The raw text is always tried first; only if it fails is the [Normalize]d copy tried, so an
 * answer that parsed before can never be broken by the cleaning layer. Truncated answers are reported with a
 * ready-to-copy "continue" prompt instead of being half-applied.
 */
object Intake {
    const val END_FILE = "<<<AIWB_END_FILE>>>"
    const val END_COMMAND = "<<<AIWB_END_COMMAND>>>"
    const val MAX_FILES = 200
    const val MAX_BYTES = 12 * 1024 * 1024
    private val PROTOCOLS = setOf("workbench-v1", "workbench-v2")

    class IntakeError(message: String, val continuePrompt: String = "") : Exception(message)

    data class FileOp(val path: String, val action: String, val content: String)
    data class Command(val id: String, val command: String, val timeoutSeconds: Int, val workingDirectory: String)
    data class Parsed(
        val files: List<FileOp>,
        val commands: List<Command>,
        val format: String,
        val fixes: List<String>,
        val summary: String = "",
    ) {
        val cleaned: Boolean get() = fixes.isNotEmpty()
        fun fileMap(): Map<String, String> = files.associate { it.path to it.content }
    }

    private val HEADER = Regex("^\\s*<<<AIWB_FILE\\s+(.*?)\\s*>>>\\s*$")
    private val ATTR = Regex("([A-Za-z_][A-Za-z0-9_-]*)\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)')")
    private val CMD = Regex("^\\s*<<<AIWB_COMMAND\\s+id=\"([A-Za-z0-9_.-]{1,40})\"\\s+timeout_seconds=\"(\\d{1,3})\"" +
        "(?:\\s+working_directory=\"([^\"]{0,240})\")?(?:\\s+body=\"(raw|fenced)\")?\\s*>>>\\s*$")
    private val START = Regex("^\\s*<<<AIWB_(?:FILE|COMMAND)\\b.*>>>\\s*$")
    private val TOP_MARKER = Regex("^\\s*<<<AIWB_(?:FILE|COMMAND)(?:\\s|$)")
    private val FENCE_OPEN = Regex("^\\s*(`{3,}|~{3,})([^\\r\\n]*)$")

    /** Parse [text]: raw first, then the normalized copy. Throws [IntakeError] with a precise, user-facing reason. */
    fun parse(text: String): Parsed {
        if (text.isBlank()) throw IntakeError("The answer is empty.")
        if (text.toByteArray(Charsets.UTF_8).size > MAX_BYTES) throw IntakeError("The answer is larger than 12 MB.")
        val first = try {
            return parseRaw(text, emptyList())
        } catch (e: IntakeError) { e }
        val cleaned = Normalize.normalize(text)
        if (cleaned.changed) {
            try { return parseRaw(cleaned.text, cleaned.fixes) } catch (_: IntakeError) { /* report the raw error */ }
        }
        val cut = Normalize.truncationReport(text)
        if (cut.truncated) {
            throw IntakeError("The answer was cut off (${cut.reason}). Nothing was applied.", Normalize.continuePrompt(cut))
        }
        throw first
    }

    private fun lines(s: String): List<String> {
        val out = s.split(Regex("\r\n|\r|\n"))
        return if (out.isNotEmpty() && out.last().isEmpty()) out.dropLast(1) else out
    }

    fun hasTopLevelMarker(text: String): Boolean {
        val ls = lines(text)
        var fence: String? = null
        for (l in ls) {
            if (fence != null) { if (l.trim() == fence) fence = null; continue }
            if (TOP_MARKER.containsMatchIn(l)) return true
            FENCE_OPEN.find(l)?.let { fence = it.groupValues[1] }
        }
        val ne = ls.indices.filter { ls[it].isNotBlank() }
        if (ne.size >= 3) {
            val outer = FENCE_OPEN.find(ls[ne.first()])
            if (outer != null && ls[ne.last()].trim() == outer.groupValues[1]) {
                val inner = ls.subList(ne.first() + 1, ne.last()).firstOrNull { it.isNotBlank() }
                if (inner != null && TOP_MARKER.containsMatchIn(inner)) return true
            }
        }
        return false
    }

    private fun parseRaw(text: String, fixes: List<String>): Parsed {
        if (hasTopLevelMarker(text)) return parseBlocks(text, fixes)
        val obj = findJson(text) ?: throw IntakeError(
            "No complete AI Workbench blocks or JSON response were found. Each file needs " +
                "<<<AIWB_FILE path=\"...\" action=\"write\">>> and $END_FILE on its own line.")
        return fromJson(obj, fixes)
    }

    fun safePath(raw: String): String {
        var p = raw.trim().replace('\\', '/')
        if (p.startsWith("`") && p.endsWith("`") && p.length > 2) p = p.substring(1, p.length - 1)
        while (p.startsWith("./")) p = p.substring(2)
        if (p.isEmpty() || p.startsWith("/") || Regex("^[A-Za-z]:").containsMatchIn(p) ||
            p.split('/').any { it == ".." || it.isEmpty() } || p.length > 400) {
            throw IntakeError("Unsafe or empty file path '$raw'. Paths must be relative to the project folder.")
        }
        return p
    }

    private fun parseBlocks(text: String, fixes: List<String>): Parsed {
        val ls = lines(text)
        val files = ArrayList<FileOp>()
        val cmds = ArrayList<Command>()
        fun nextEnd(from: Int, marker: String): Int? = (from until ls.size).firstOrNull { ls[it].trim() == marker }
        fun nextHeader(from: Int, stop: Int): Int? = (from until stop).firstOrNull { START.matches(ls[it]) }
        fun body(start: Int, marker: String, what: String, mode: String): Pair<String, Int> {
            var probe = start
            while (probe < ls.size && ls[probe].isBlank()) probe++
            val opened = if (mode == "raw" || probe >= ls.size) null else FENCE_OPEN.find(ls[probe])
            if (mode == "fenced" && opened == null) throw IntakeError("$what declares body=\"fenced\" but has no opening fence.")
            val bodyStart = if (opened != null) probe + 1 else start
            val end = nextEnd(bodyStart, marker)
            val other = nextHeader(bodyStart, end ?: ls.size)
            if (other != null) throw IntakeError("$what is missing $marker before another block starts on line ${other + 1}. Nothing was applied.")
            if (end == null) throw IntakeError("$what is missing $marker. Ask the model to resend the full block.")
            if (opened != null) {
                var close = end - 1
                while (close >= bodyStart && ls[close].isBlank()) close--
                if (close < bodyStart || ls[close].trim() != opened.groupValues[1]) {
                    throw IntakeError("$what must close its outer fence right before $marker.")
                }
                val b = ls.subList(bodyStart, close)
                return (b.joinToString("\n") + if (b.isEmpty()) "" else "\n") to end + 1
            }
            val b = ls.subList(bodyStart, end)
            return (b.joinToString("\n") + if (b.isEmpty()) "" else "\n") to end + 1
        }
        var i = 0
        while (i < ls.size) {
            val line = ls[i]
            if ("<<<AIWB_FILE" in line) {
                val m = HEADER.matchEntire(line) ?: throw IntakeError("Malformed file header on line ${i + 1}. " +
                    "Expected <<<AIWB_FILE path=\"relative/path.ext\" action=\"write\">>>")
                val attrsText = m.groupValues[1]
                val attrs = LinkedHashMap<String, String>()
                val rest = StringBuilder(attrsText)
                for (a in ATTR.findAll(attrsText)) {
                    val k = a.groupValues[1].lowercase()
                    if (attrs.containsKey(k)) throw IntakeError("Duplicate '$k' in the header on line ${i + 1}.")
                    attrs[k] = a.groups[2]?.value ?: a.groups[3]?.value ?: ""
                    for (p in a.range) rest.setCharAt(p, ' ')
                }
                if (rest.isNotBlank() || "path" !in attrs || (attrs.keys - setOf("path", "action", "body")).isNotEmpty()) {
                    throw IntakeError("Malformed file header on line ${i + 1}: use path=\"...\" and optional action/body.")
                }
                val path = safePath(attrs.getValue("path"))
                val action = attrs["action"]?.trim()?.ifEmpty { null } ?: "write"
                if (action !in setOf("write", "delete")) throw IntakeError("Unsupported action '$action' for '$path'.")
                val mode = attrs["body"]?.trim()?.lowercase()?.ifEmpty { null } ?: "auto"
                if (mode !in setOf("auto", "raw", "fenced")) throw IntakeError("Unsupported body mode '$mode' on line ${i + 1}.")
                val (content, next) = body(i + 1, END_FILE, "File block for '$path'", mode)
                files.add(FileOp(path, action, content))
                if (files.size > MAX_FILES) throw IntakeError("At most $MAX_FILES files per answer.")
                i = next
                continue
            }
            if ("<<<AIWB_COMMAND" in line) {
                val m = CMD.matchEntire(line) ?: throw IntakeError("Malformed command header on line ${i + 1}.")
                val (content, next) = body(i + 1, END_COMMAND, "Command block '${m.groupValues[1]}'", m.groupValues[4].ifEmpty { "auto" })
                if (content.isBlank()) throw IntakeError("Command block '${m.groupValues[1]}' is empty.")
                cmds.add(Command(m.groupValues[1], content.trim(), m.groupValues[2].toInt(), m.groupValues[3].ifEmpty { "." }))
                i = next
                continue
            }
            i++
        }
        if (files.isEmpty() && cmds.isEmpty()) throw IntakeError("No complete AI Workbench file/command blocks were found.")
        val dup = files.groupBy { it.path.lowercase() }.filter { it.value.size > 1 }.keys
        if (dup.isNotEmpty()) throw IntakeError("The same file appears twice: ${dup.joinToString()}.")
        return Parsed(files, cmds, "AIWB blocks", fixes)
    }

    /** Index just past the balanced JSON object starting at [start], or -1. */
    private fun balancedEnd(s: String, start: Int): Int {
        var depth = 0
        var inStr = false
        var esc = false
        for (k in start until s.length) {
            val c = s[k]
            if (inStr) {
                if (esc) esc = false else if (c == '\\') esc = true else if (c == '"') inStr = false
                continue
            }
            when (c) {
                '"' -> inStr = true
                '{' -> depth++
                '}' -> { depth--; if (depth == 0) return k + 1 }
            }
        }
        return -1
    }

    /** The single protocol object in [text] (plain, fenced or inside prose), or null. */
    fun findJson(text: String): Map<String, Any?>? {
        val t = text.trimStart('\ufeff').trim()
        try {
            (StrictJson.parse(t) as? Map<*, *>)?.let { @Suppress("UNCHECKED_CAST") return it as Map<String, Any?> }
        } catch (_: StrictJson.ParseError) { /* search inside */ }
        val found = ArrayList<Map<String, Any?>>()
        var attempts = 0
        var i = t.indexOf('{')
        while (i >= 0 && attempts < 500) {
            attempts++
            val e = balancedEnd(t, i)
            if (e > 0) {
                try {
                    val v = StrictJson.parse(t.substring(i, e))
                    if (v is Map<*, *> && v["protocol"] is String) {
                        @Suppress("UNCHECKED_CAST")
                        found.add(v as Map<String, Any?>)
                        i = t.indexOf('{', e)
                        continue
                    }
                } catch (_: StrictJson.ParseError) { /* keep looking */ }
            }
            i = t.indexOf('{', i + 1)
        }
        if (found.size > 1) throw IntakeError("The answer contains ${found.size} response objects; send exactly one.")
        return found.firstOrNull()
    }

    private fun fromJson(obj: Map<String, Any?>, fixes: List<String>): Parsed {
        val protocol = obj["protocol"] as? String
        if (protocol !in PROTOCOLS) throw IntakeError("Unsupported protocol '${protocol ?: ""}'. Expected workbench-v2.")
        val unknown = obj.keys - setOf("protocol", "task_id", "summary", "files", "actions", "next_steps", "completion_status")
        if (unknown.isNotEmpty()) throw IntakeError("Unknown response fields were rejected: ${unknown.sorted().joinToString()}")
        val list = obj["files"] as? List<*> ?: throw IntakeError("'files' must be a list.")
        val files = list.mapIndexed { idx, f ->
            val m = f as? Map<*, *> ?: throw IntakeError("files[$idx] must be an object.")
            val path = safePath(m["path"] as? String ?: throw IntakeError("files[$idx].path is missing."))
            val action = (m["action"] as? String) ?: "write"
            if (action !in setOf("write", "delete")) throw IntakeError("Unsupported action '$action' for '$path'.")
            val content = m["content"] as? String ?: if (action == "delete") "" else throw IntakeError("files[$idx].content must be text.")
            FileOp(path, action, content)
        }
        if (files.size > MAX_FILES) throw IntakeError("At most $MAX_FILES files per answer.")
        val cmds = (obj["actions"] as? List<*>).orEmpty().mapIndexed { idx, a ->
            val m = a as? Map<*, *> ?: throw IntakeError("actions[$idx] must be an object.")
            Command((m["id"] as? String) ?: "action-${idx + 1}", (m["command"] as? String).orEmpty(),
                ((m["timeout_seconds"] as? Number)?.toInt()) ?: 120, (m["working_directory"] as? String) ?: ".")
        }
        return Parsed(files, cmds, "$protocol JSON", fixes, (obj["summary"] as? String).orEmpty())
    }
}
