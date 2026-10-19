package io.github.golshandvr.aiworkbench.core

/**
 * Normalize model output copied from chat UIs (port of desktop `aiwb/intake/normalize.py`, roadmap 3.2.0 / 1.0.0).
 *
 * Conservative: only structural lines (AIWB headers / end markers, the outer fence) and, for JSON, characters outside
 * string literals are touched. File bodies are never rewritten except for line endings and invisible characters.
 * Callers always try the raw text first and fall back to the normalized text. Both apps are tested against the same
 * corpus `packages/contracts/fixtures/intake/chat-copy-corpus.v1.json`.
 */
object Normalize {
    const val ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff\u00ad"
    const val NBSP = "\u00a0\u202f\u2007"
    const val SMART_DOUBLE = "\u201c\u201d\u201e\u201f\u2033\u00ab\u00bb"
    const val SMART_SINGLE = "\u2018\u2019\u201a\u201b\u2032"

    private const val MARKER_WORDS =
        "AIWB_(?:FILE|COMMAND|END_FILE|END_COMMAND|CONTEXT_REQUEST|END_CONTEXT_REQUEST|DELETE|RENAME|MOVE)"
    private val STRUCTURAL = Regex("^\\s*(?:\\\\?<|&lt;|&#60;|‹|＜){3}\\s*\\\\?" + MARKER_WORDS.replace("_", "\\\\?_"))
    private val FENCE = Regex("^\\s*(`{3,}|~{3,})([^\\r\\n`]*)$")
    private val LEAD_EMPH = Regex("^\\s*(?:\\*\\*|__|`)+")
    private val AIWB_OPEN = Regex("^\\s*<<<AIWB_(?:FILE|COMMAND)\\b")
    private val AIWB_END = Regex("^\\s*<<<AIWB_END_(?:FILE|COMMAND)>>>\\s*$")

    data class Result(val text: String, val fixes: List<String> = emptyList()) {
        val changed: Boolean get() = fixes.isNotEmpty()
    }

    data class Truncation(
        val truncated: Boolean,
        val reason: String = "",
        val lastCompletePath: String = "",
        val openPath: String = "",
        val completedPaths: List<String> = emptyList(),
    )

    // ------------------------------------------------------------------ helpers

    fun htmlUnescape(s: String): String {
        if ('&' !in s) return s
        val named = mapOf("lt" to "<", "gt" to ">", "amp" to "&", "quot" to "\"", "apos" to "'", "nbsp" to "\u00a0",
            "#39" to "'")
        return Regex("&(#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z]{2,8});").replace(s) { m ->
            val k = m.groupValues[1]
            when {
                named.containsKey(k) -> named.getValue(k)
                k.startsWith("#x") || k.startsWith("#X") -> k.substring(2).toIntOrNull(16)?.let { String(Character.toChars(it)) } ?: m.value
                k.startsWith("#") -> k.substring(1).toIntOrNull()?.let { String(Character.toChars(it)) } ?: m.value
                else -> m.value
            }
        }
    }

    private fun translate(s: String, chars: String, to: String?): String {
        val sb = StringBuilder(s.length)
        for (c in s) if (c in chars) { if (to != null) sb.append(to) } else sb.append(c)
        return sb.toString()
    }

    private fun stripInvisible(input: String, fixes: MutableList<String>): String {
        var out = input
        if (out.startsWith("\ufeff")) {
            out = out.trimStart('\ufeff'); fixes.add("bom")
        }
        val zw = out.count { it in ZERO_WIDTH }
        if (zw > 0) { out = translate(out, ZERO_WIDTH, null); fixes.add("zero_width:$zw") }
        val nb = out.count { it in NBSP }
        if (nb > 0) { out = translate(out, NBSP, " "); fixes.add("nbsp:$nb") }
        if ('\r' in out) { out = out.replace("\r\n", "\n").replace("\r", "\n"); fixes.add("line_endings") }
        return out
    }

    private fun fixMarkerLine(line: String): String {
        var s = htmlUnescape(line.trim())
        s = s.replace("\\<", "<").replace("\\>", ">").replace("\\_", "_").replace("\\=", "=").replace("\\\"", "\"")
        s = s.replace("‹", "<").replace("›", ">").replace("＜", "<").replace("＞", ">")
        s = translate(s, SMART_DOUBLE, "\"")
        s = translate(s, SMART_SINGLE, "'")
        s = Regex("^(?:\\*\\*|__|`)+|(?:\\*\\*|__|`)+$").replace(s, "").trim()
        s = Regex("\\s+").replace(s, " ")
        s = Regex("<<<\\s+").replace(s, "<<<")
        s = Regex("\\s+>>>$").replace(s, ">>>")
        s = Regex("\\s*=\\s*\"").replace(s, "=\"")
        return s
    }

    private fun fixStructuralLines(s: String, fixes: MutableList<String>): String {
        val lines = s.split("\n").toMutableList()
        var n = 0
        for (i in lines.indices) {
            val line = lines[i]
            val probe = LEAD_EMPH.replace(line, "")
            val t = probe.trimStart()
            if (STRUCTURAL.containsMatchIn(probe) && STRUCTURAL.find(probe)!!.range.first == 0 ||
                ("AIWB" in probe && (t.startsWith("<<<") || t.startsWith("&lt;") || t.startsWith("\\<")))) {
                val fixed = fixMarkerLine(line)
                if (fixed != line) { lines[i] = fixed; n++ }
            }
        }
        if (n > 0) fixes.add("marker_lines:$n")
        return lines.joinToString("\n")
    }

    private fun unwrapOuterFence(s: String, fixes: MutableList<String>): String {
        val lines = s.split("\n")
        val out = ArrayList<String>()
        var i = 0
        var removed = 0
        while (i < lines.size) {
            val m = FENCE.find(lines[i])
            if (m != null) {
                var j = i + 1
                while (j < lines.size && lines[j].isBlank()) j++
                if (j < lines.size && AIWB_OPEN.containsMatchIn(lines[j])) {
                    val fence = m.groupValues[1]
                    var close = -1
                    var k = lines.size - 1
                    while (k > j) {
                        if (lines[k].trim() == fence) {
                            var prev = k - 1
                            while (prev > j && lines[prev].isBlank()) prev--
                            if (AIWB_END.matches(lines[prev])) close = k
                            break
                        }
                        k--
                    }
                    if (close >= 0) {
                        out.addAll(lines.subList(i + 1, close))
                        removed++
                        i = close + 1
                        continue
                    }
                }
            }
            out.add(lines[i])
            i++
        }
        if (removed == 0) return s
        fixes.add("outer_fence")
        return out.joinToString("\n")
    }

    /** A cleaned copy of [text] plus the fixes applied (empty → unchanged). */
    fun normalize(text: String?): Result {
        var s = text ?: ""
        val fixes = ArrayList<String>()
        s = stripInvisible(s, fixes)
        s = fixStructuralLines(s, fixes)
        s = unwrapOuterFence(s, fixes)
        if (looksJsonish(s)) {
            val js = normalizeJsonText(s)
            if (js.changed) { s = js.text; fixes.addAll(js.fixes) }
        }
        return Result(s, fixes)
    }

    // --------------------------------------------------------------------- JSON

    private fun looksJsonish(s: String): Boolean {
        if (Regex("(?m)^\\s*<<<AIWB_(?:FILE|COMMAND)\\b").containsMatchIn(s)) return false
        val t = s.trim()
        return t.startsWith("{") || Regex("(?im)^\\s*`{3,}\\s*json\\b").containsMatchIn(t) ||
            Regex("[\"“”']protocol[\"“”']\\s*:").containsMatchIn(t)
    }

    /** Split prose/fence around the JSON object: (prefix, body, suffix). */
    fun jsonBody(s: String): Triple<String, String, String> {
        val m = Regex("(?ims)^\\s*(`{3,}|~{3,})\\s*json[^\\n]*\\n(.*?)(?:^\\s*\\1\\s*$|\\z)").find(s)
        if (m != null) {
            val g = m.groups[2]!!
            return Triple(s.substring(0, g.range.first), g.value, s.substring(g.range.last + 1))
        }
        val a = s.indexOf('{')
        if (a < 0) return Triple(s, "", "")
        val b = s.lastIndexOf('}')
        if (b < a) return Triple(s.substring(0, a), s.substring(a), "")
        return Triple(s.substring(0, a), s.substring(a, b + 1), s.substring(b + 1))
    }

    private val LITERAL = Regex("^(True|False|None|undefined)\\b")

    private fun scanJson(body: String, fixes: MutableList<String>): String {
        val out = StringBuilder(body.length)
        var i = 0
        val n = body.length
        var inStr = false
        var quoteFix = 0; var commentFix = 0; var commaFix = 0; var literalFix = 0
        while (i < n) {
            val c = body[i]
            if (inStr) {
                if (c == '\\' && i + 1 < n) { out.append(body, i, i + 2); i += 2; continue }
                if (c == '"') { inStr = false; out.append(c); i++; continue }
                if (c == '\u201c' || c == '\u201d') {
                    val nxt = body.substring(i + 1, minOf(n, i + 40)).trimStart()
                    if (nxt.isEmpty() || nxt[0] in ":,}]") { inStr = false; out.append('"'); quoteFix++; i++; continue }
                }
                if (c == '\n') { out.append("\\n"); i++; continue }
                out.append(c); i++; continue
            }
            if (c == '"' || c == '\u201c' || c == '\u201d' || c == '\u201e') {
                if (c != '"') quoteFix++
                inStr = true; out.append('"'); i++; continue
            }
            if (c == '/' && i + 1 < n && body[i + 1] == '/') {
                val j = body.indexOf('\n', i)
                i = if (j < 0) n else j
                commentFix++; continue
            }
            if (c == '/' && i + 1 < n && body[i + 1] == '*') {
                val j = body.indexOf("*/", i + 2)
                i = if (j < 0) n else j + 2
                commentFix++; continue
            }
            if (c == ',') {
                var k = i + 1
                while (k < n && body[k] in " \t\n") k++
                if (k < n && body[k] in "}]") { commaFix++; i++; continue }
            }
            if (c.isLetter()) {
                val m = LITERAL.find(body.substring(i, minOf(n, i + 12)))
                if (m != null) {
                    val w = m.groupValues[1]
                    out.append(when (w) { "True" -> "true"; "False" -> "false"; else -> "null" })
                    literalFix++; i += w.length; continue
                }
            }
            out.append(c); i++
        }
        for ((name, k) in listOf("json_smart_quotes" to quoteFix, "json_comments" to commentFix,
                "json_trailing_commas" to commaFix, "json_literals" to literalFix)) {
            if (k > 0) fixes.add("$name:$k")
        }
        return out.toString()
    }

    /** Repair a JSON answer only if it does not already parse. */
    fun normalizeJsonText(text: String?): Result {
        val s = text ?: ""
        val (prefix, body, suffix) = jsonBody(s)
        if (body.isBlank()) return Result(s)
        if (StrictJson.isValid(body.trim())) return Result(s)
        val fixes = ArrayList<String>()
        var candidate = body
        if ("\\_" in candidate || "\\*" in candidate) {
            val c2 = Regex("\\\\([_*\\[\\]#])").replace(candidate, "$1")
            if (c2 != candidate) { candidate = c2; fixes.add("markdown_escapes") }
        }
        if ("&quot;" in candidate || "&lt;" in candidate || "&amp;" in candidate) {
            candidate = htmlUnescape(candidate); fixes.add("html_entities")
        }
        candidate = scanJson(candidate, fixes)
        if (!StrictJson.isValid(candidate.trim())) return Result(s)
        return Result(prefix + candidate + suffix, fixes)
    }

    // --------------------------------------------------------------- truncation

    private val HEAD = Regex("(?m)^\\s*<<<AIWB_(FILE|COMMAND)\\b([^\\n]*)>>>\\s*$")
    private val END_LINE = Regex("(?m)^\\s*<<<AIWB_END_(?:FILE|COMMAND)>>>\\s*$")

    /** Detect an answer that was cut off (chat length limit / stopped generation). */
    fun truncationReport(text: String?): Truncation {
        val s = normalize(text).text.trimEnd()
        if (s.isEmpty()) return Truncation(false)
        val heads = HEAD.findAll(s).toList()
        if (heads.isNotEmpty()) {
            val done = ArrayList<String>()
            var openPath = ""
            for ((i, h) in heads.withIndex()) {
                val stop = if (i + 1 < heads.size) heads[i + 1].range.first else s.length
                val seg = s.substring(h.range.last + 1, stop)
                val name = Regex("(?:path|id)=\"([^\"]*)\"").find(h.groupValues[2])?.groupValues?.get(1) ?: "?"
                if (END_LINE.containsMatchIn(seg)) done.add(name) else if (i == heads.size - 1) openPath = name
            }
            if (openPath.isNotEmpty()) return Truncation(true, "unclosed_block", done.lastOrNull() ?: "", openPath, done)
            return Truncation(false, completedPaths = done)
        }
        if (Regex("(?m)^\\s*(?:`{3,}|~{3,})").findAll(s).count() % 2 == 1) return Truncation(true, "unclosed_fence")
        val b = jsonBody(s).second.trim()
        if (b.startsWith("{")) {
            val repaired = normalizeJsonText(b).text
            try {
                StrictJson.parse(repaired.trim())
            } catch (exc: StrictJson.ParseError) {
                var depth = 0
                var inStr = false
                var esc = false
                for (ch in b) {
                    if (inStr) {
                        if (esc) esc = false else if (ch == '\\') esc = true else if (ch == '"') inStr = false
                    } else if (ch == '"') inStr = true
                    else if (ch == '{' || ch == '[') depth++
                    else if (ch == '}' || ch == ']') depth--
                }
                if (depth > 0 || inStr || exc.pos >= b.length - 1) {
                    val paths = Regex("\"path\"\\s*:\\s*\"([^\"]+)\"").findAll(b).map { it.groupValues[1] }.toList()
                    return Truncation(true, "json_cut", if (paths.size > 1) paths[paths.size - 2] else "",
                        paths.lastOrNull() ?: "", if (paths.isEmpty()) emptyList() else paths.dropLast(1))
                }
            }
        }
        return Truncation(false)
    }

    /** Prompt that asks the model to continue exactly where the answer was cut off. */
    fun continuePrompt(report: Truncation, attemptId: String = ""): String {
        val att = if (attemptId.isNotEmpty()) " (attempt $attemptId)" else ""
        val lines = arrayListOf("Your previous answer$att was cut off before it finished.")
        when (report.reason) {
            "unclosed_block" -> {
                if (report.completedPaths.isNotEmpty()) {
                    lines.add("These files arrived complete — do NOT resend them: " + report.completedPaths.joinToString(", ") + ".")
                }
                lines.add("Resend the file \"${report.openPath}\" from its <<<AIWB_FILE ...>>> header, completely, " +
                    "then continue with every remaining file and action.")
            }
            "json_cut" -> lines.add("The JSON object is incomplete. Do not continue mid-object: resend the response using " +
                "AIWB blocks (one <<<AIWB_FILE path=\"...\" action=\"write\">>> ... <<<AIWB_END_FILE>>> per file), " +
                "skipping files that were already complete" +
                (if (report.completedPaths.isNotEmpty()) ": " + report.completedPaths.joinToString(", ") else "") + ".")
            else -> lines.add("Resend the rest of the answer starting from the last complete block.")
        }
        lines.add("Rules: plain text only, no outer Markdown fence around the whole answer, each marker on its own line,")
        lines.add("end every file with <<<AIWB_END_FILE>>>. If the answer would be long, split it and say \"PART 1 of N\".")
        return lines.joinToString("\n")
    }
}
