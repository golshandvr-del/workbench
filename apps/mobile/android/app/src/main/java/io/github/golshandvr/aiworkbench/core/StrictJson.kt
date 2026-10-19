package io.github.golshandvr.aiworkbench.core

/**
 * Strict RFC 8259 JSON parser (roadmap mobile 1.0.0).
 *
 * `org.json` is lenient (it accepts comments, single quotes, unquoted words), which would hide exactly the chat-copy
 * damage the Normalizer must detect. This parser accepts only real JSON, like Python's `json.loads`, and reports the
 * failing offset so truncation detection can tell "cut off at the end" from "broken in the middle".
 *
 * Values: `Map<String, Any?>` (insertion-ordered), `List<Any?>`, `String`, `Long`/`Double`, `Boolean`, `null`.
 */
object StrictJson {
    class ParseError(message: String, val pos: Int) : IllegalArgumentException("$message at offset $pos")

    fun parse(text: String): Any? {
        val p = P(text)
        p.ws()
        val v = p.value()
        p.ws()
        if (p.i != text.length) throw ParseError("extra data", p.i)
        return v
    }

    fun isValid(text: String): Boolean = try { parse(text); true } catch (_: ParseError) { false }

    /**
     * Compact serialization, non-ASCII kept as-is. With [sortKeys] the output is byte-identical to Python's
     * `json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` (the bundle integrity rule).
     */
    fun stringify(v: Any?, sortKeys: Boolean = false): String = StringBuilder().also { write(it, v, sortKeys) }.toString()

    /** Python `float.__repr__` for the doubles found in project state (whole numbers keep ".0"). */
    fun pyFloat(v: Double): String {
        if (v.isNaN()) return "NaN"
        if (v.isInfinite()) return if (v > 0) "Infinity" else "-Infinity"
        if (v == Math.floor(v) && Math.abs(v) < 1e16) return v.toLong().toString() + ".0"
        val t = v.toString()
        val e = t.indexOf('E')
        if (e < 0) return t
        val mant = t.substring(0, e).removeSuffix(".0")
        val exp = t.substring(e + 1).toInt()
        return mant + "e" + (if (exp < 0) "-" else "+") + String.format("%02d", Math.abs(exp))
    }

    /** Deep, mutable copy of a parsed JSON tree. */
    @Suppress("UNCHECKED_CAST")
    fun copy(v: Any?): Any? = when (v) {
        is Map<*, *> -> LinkedHashMap<String, Any?>().also { m -> for ((k, x) in v) m[k.toString()] = copy(x) }
        is List<*> -> ArrayList<Any?>().also { a -> for (x in v) a.add(copy(x)) }
        else -> v
    }

    private fun write(sb: StringBuilder, v: Any?, sortKeys: Boolean) {
        when (v) {
            null -> sb.append("null")
            is String -> quote(sb, v)
            is Boolean -> sb.append(v)
            is Int, is Long -> sb.append(v.toString())
            is Double -> sb.append(pyFloat(v))
            is Float -> sb.append(pyFloat(v.toDouble()))
            is Number -> sb.append(v.toString())
            is Map<*, *> -> {
                sb.append('{')
                var first = true
                val keys = v.keys.map { it.toString() }.let { if (sortKeys) it.sorted() else it }
                for (k in keys) {
                    if (!first) sb.append(',')
                    first = false
                    quote(sb, k); sb.append(':'); write(sb, v[k], sortKeys)
                }
                sb.append('}')
            }
            is List<*> -> {
                sb.append('[')
                v.forEachIndexed { i, x -> if (i > 0) sb.append(','); write(sb, x, sortKeys) }
                sb.append(']')
            }
            else -> quote(sb, v.toString())
        }
    }

    fun quote(sb: StringBuilder, s: String) {
        sb.append('"')
        for (c in s) {
            when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                '\b' -> sb.append("\\b")
                '\u000c' -> sb.append("\\f")
                else -> if (c < ' ') sb.append(String.format("\\u%04x", c.code)) else sb.append(c)
            }
        }
        sb.append('"')
    }

    private class P(val s: String) {
        var i = 0

        fun ws() {
            while (i < s.length && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) i++
        }

        fun value(): Any? {
            if (i >= s.length) throw ParseError("unexpected end", i)
            return when (val c = s[i]) {
                '{' -> obj()
                '[' -> arr()
                '"' -> str()
                't' -> lit("true", true)
                'f' -> lit("false", false)
                'n' -> lit("null", null)
                else -> if (c == '-' || c in '0'..'9') num() else throw ParseError("unexpected '$c'", i)
            }
        }

        fun lit(word: String, v: Any?): Any? {
            if (!s.startsWith(word, i)) throw ParseError("invalid literal", i)
            i += word.length
            return v
        }

        fun obj(): Map<String, Any?> {
            val m = LinkedHashMap<String, Any?>()
            i++
            ws()
            if (i < s.length && s[i] == '}') { i++; return m }
            while (true) {
                ws()
                if (i >= s.length) throw ParseError("unexpected end", i)
                if (s[i] != '"') throw ParseError("expected a property name", i)
                val k = str()
                ws()
                if (i >= s.length || s[i] != ':') throw ParseError("expected ':'", i)
                i++
                ws()
                m[k] = value()
                ws()
                if (i >= s.length) throw ParseError("unexpected end", i)
                when (s[i]) {
                    ',' -> i++
                    '}' -> { i++; return m }
                    else -> throw ParseError("expected ',' or '}'", i)
                }
            }
        }

        fun arr(): List<Any?> {
            val a = ArrayList<Any?>()
            i++
            ws()
            if (i < s.length && s[i] == ']') { i++; return a }
            while (true) {
                ws()
                a.add(value())
                ws()
                if (i >= s.length) throw ParseError("unexpected end", i)
                when (s[i]) {
                    ',' -> i++
                    ']' -> { i++; return a }
                    else -> throw ParseError("expected ',' or ']'", i)
                }
            }
        }

        fun str(): String {
            val start = i
            i++
            val sb = StringBuilder()
            while (true) {
                if (i >= s.length) throw ParseError("unterminated string", start)
                val c = s[i]
                when {
                    c == '"' -> { i++; return sb.toString() }
                    c == '\\' -> {
                        if (i + 1 >= s.length) throw ParseError("unterminated string", start)
                        when (val e = s[i + 1]) {
                            '"' -> sb.append('"'); '\\' -> sb.append('\\'); '/' -> sb.append('/')
                            'b' -> sb.append('\b'); 'f' -> sb.append('\u000c'); 'n' -> sb.append('\n')
                            'r' -> sb.append('\r'); 't' -> sb.append('\t')
                            'u' -> {
                                if (i + 6 > s.length) throw ParseError("bad \\u escape", i)
                                val hex = s.substring(i + 2, i + 6)
                                sb.append(hex.toIntOrNull(16)?.toChar() ?: throw ParseError("bad \\u escape", i))
                                i += 4
                            }
                            else -> throw ParseError("invalid escape '\\$e'", i)
                        }
                        i += 2
                    }
                    c < ' ' -> throw ParseError("invalid control character", i)
                    else -> { sb.append(c); i++ }
                }
            }
        }

        fun num(): Any {
            val start = i
            if (s[i] == '-') i++
            if (i >= s.length) throw ParseError("bad number", start)
            if (s[i] == '0') i++ else if (s[i] in '1'..'9') { while (i < s.length && s[i].isDigit()) i++ } else throw ParseError("bad number", start)
            var frac = false
            if (i < s.length && s[i] == '.') {
                frac = true; i++
                if (i >= s.length || !s[i].isDigit()) throw ParseError("bad number", start)
                while (i < s.length && s[i].isDigit()) i++
            }
            if (i < s.length && (s[i] == 'e' || s[i] == 'E')) {
                frac = true; i++
                if (i < s.length && (s[i] == '+' || s[i] == '-')) i++
                if (i >= s.length || !s[i].isDigit()) throw ParseError("bad number", start)
                while (i < s.length && s[i].isDigit()) i++
            }
            val t = s.substring(start, i)
            return if (frac) t.toDouble() else (t.toLongOrNull() ?: t.toDouble())
        }
    }
}
