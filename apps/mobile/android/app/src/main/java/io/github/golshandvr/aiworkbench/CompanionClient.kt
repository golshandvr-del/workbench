package io.github.golshandvr.aiworkbench

import org.json.JSONObject

/**
 * Pairing code v2 (roadmap 3.7.0 / mobile 0.4.0), same rules as aiwb/companion/pairing.py:
 * a 10-byte secret shown as a 16-character Base32 code (`ABCD-EFGH-IJKL-MNOP`) or inside the QR /
 * deep link `aiwb://pair?h=<ipv4>&p=<port>&k=<code>`. The phone derives
 *   secret (envelope key) = HMAC-SHA256(raw, "aiwb-pair-key-v2")
 *   pairingId            = "pair-" + hex(HMAC-SHA256(raw, "aiwb-pair-id-v2"))[:12]
 * so the raw code itself never travels over the network.
 */
data class PairingCode(val host: String, val port: Int, val pairingId: String, val secret: ByteArray) {
    companion object {
        private val HOST = Regex("""^(\d{1,3}\.){3}\d{1,3}$""")
        const val CODE_LEN = 16
        private const val ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

        /** Parses a scanned/opened `aiwb://pair?...` link. Only private-LAN / loopback IPv4 hosts are accepted. */
        fun parse(text: String): PairingCode? {
            val t = text.trim()
            if (!t.startsWith("aiwb://pair?")) return null
            val q = HashMap<String, String>()
            for (part in t.removePrefix("aiwb://pair?").split("&")) {
                val i = part.indexOf('=')
                if (i <= 0) return null
                q[part.substring(0, i)] = java.net.URLDecoder.decode(part.substring(i + 1), "UTF-8")
            }
            return manual(q["h"] ?: return null, q["p"] ?: return null, q["k"] ?: return null)
        }

        /** Manual entry: desktop address (`192.168.1.20` + port) and the 16-character code. */
        fun manual(host: String, port: String, code: String): PairingCode? {
            val h = host.trim()
            if (!HOST.matches(h) || !isPrivateLan(h)) return null
            val p = port.trim().toIntOrNull()?.takeIf { it in 1..65535 } ?: return null
            val raw = secretFromCode(code) ?: return null
            return fromSecret(h, p, raw)
        }

        /** Accepts `host:port` in one field (what the desktop window shows). */
        fun manual(address: String, code: String): PairingCode? {
            val a = address.trim()
            val i = a.lastIndexOf(':')
            if (i <= 0) return null
            return manual(a.substring(0, i), a.substring(i + 1), code)
        }

        fun fromSecret(host: String, port: Int, raw: ByteArray): PairingCode {
            val id = CompanionCrypto.hmac(raw, "aiwb-pair-id-v2".toByteArray()).joinToString("") { "%02x".format(it) }.take(12)
            return PairingCode(host, port, "pair-$id", CompanionCrypto.hmac(raw, "aiwb-pair-key-v2".toByteArray()))
        }

        /** Case, spaces and dashes are ignored; 0→O, 1→I, 8→B are accepted as typing mistakes. */
        fun normalizeCode(text: String): String? {
            val c = text.uppercase().filter { it !in " -_\t\r\n" }
                .map { when (it) { '0' -> 'O'; '1' -> 'I'; '8' -> 'B'; else -> it } }.joinToString("")
            return if (c.length == CODE_LEN && c.all { it in ALPHABET }) c else null
        }

        fun secretFromCode(text: String): ByteArray? {
            val c = normalizeCode(text) ?: return null
            val out = ByteArray(10)
            var buf = 0L
            var bits = 0
            var n = 0
            for (ch in c) {
                buf = (buf shl 5) or ALPHABET.indexOf(ch).toLong()
                bits += 5
                if (bits >= 8) {
                    bits -= 8
                    out[n++] = ((buf shr bits) and 0xFF).toByte()
                }
            }
            return out
        }

        fun formatCode(code: String): String? = normalizeCode(code)?.chunked(4)?.joinToString("-")

        fun isPrivateLan(ip: String): Boolean {
            val o = ip.split(".").map { it.toIntOrNull() ?: return false }
            if (o.size != 4 || o.any { it !in 0..255 }) return false
            return o[0] == 10 || o[0] == 127 || (o[0] == 172 && o[1] in 16..31) || (o[0] == 192 && o[1] == 168)
        }
    }
}

/** Paired desktop as stored on the phone (device key never leaves this app's private storage). */
data class Pairing(val host: String, val port: Int, val deviceId: String, val key: ByteArray) {
    fun encode(): String = JSONObject().put("host", host).put("port", port).put("device_id", deviceId)
        .put("key", B64Url.encode(key)).toString()

    companion object {
        fun decode(text: String?): Pairing? {
            if (text == null) return null
            return try {
                val o = JSONObject(text)
                val host = o.getString("host")
                val key = B64Url.decode(o.getString("key"))
                if (!PairingCode.isPrivateLan(host) || key.size != 32) null
                else Pairing(host, o.getInt("port"), o.getString("device_id"), key)
            } catch (e: Exception) {
                null
            }
        }
    }
}

class CompanionException(val code: String, message: String) : Exception(message)

/** Sends one sealed request and opens the sealed reply. [post] does the HTTP POST (body → status, body). */
class CompanionClient(
    private val post: (host: String, port: Int, body: String) -> Pair<Int, String>,
    private val now: () -> Long = { System.currentTimeMillis() / 1000 },
) {
    fun call(host: String, port: Int, kid: String, key: ByteArray, request: JSONObject): JSONObject {
        val env = CompanionCrypto.seal(key, kid, request.toString().toByteArray(Charsets.UTF_8), now())
        val (status, body) = post(host, port, toJson(env).toString())
        if (status != 200) {
            val code = try { JSONObject(body).optString("error", "http_$status") } catch (e: Exception) { "http_$status" }
            throw CompanionException(code, code)
        }
        val reply = fromJson(JSONObject(body))
        if (reply.re != env.nonce || reply.kid != kid) throw CompanionException("bad_reply", "reply does not match the request")
        val out = JSONObject(String(CompanionCrypto.open(key, reply, now()), Charsets.UTF_8))
        if (!out.optBoolean("ok", false)) throw CompanionException(out.optString("error", "error"), out.optString("message", "request refused"))
        return out
    }

    /** Step 1: send our new random device key, sealed with the one-time secret. */
    fun requestPairing(code: PairingCode, deviceName: String, deviceKey: ByteArray): JSONObject =
        call(code.host, code.port, code.pairingId, code.secret,
            JSONObject().put("op", "pair_request").put("device_name", deviceName.take(60)).put("device_key", B64Url.encode(deviceKey)))

    /** Step 2: poll until the desktop user approved (returns the pairing) or denied (throws). */
    fun pairingStatus(code: PairingCode, deviceKey: ByteArray): Pairing? {
        val out = call(code.host, code.port, code.pairingId, code.secret, JSONObject().put("op", "pair_status"))
        return when (out.optString("status")) {
            "approved" -> Pairing(code.host, code.port, out.getString("device_id"), deviceKey)
            "denied" -> throw CompanionException("denied", "pairing was denied on the desktop")
            else -> null
        }
    }

    fun request(p: Pairing, op: String, extra: JSONObject = JSONObject()): JSONObject =
        call(p.host, p.port, p.deviceId, p.key, extra.put("op", op))

    companion object {
        fun toJson(e: Envelope): JSONObject = JSONObject().put("v", e.v).put("kid", e.kid).put("ts", e.ts)
            .put("nonce", e.nonce).put("re", e.re).put("ct", e.ct).put("mac", e.mac)

        fun fromJson(o: JSONObject): Envelope {
            val keys = o.keys().asSequence().toSet()
            if (keys != setOf("v", "kid", "ts", "nonce", "re", "ct", "mac")) throw EnvelopeException("bad envelope fields")
            return Envelope(o.getInt("v"), o.getString("kid"), o.getLong("ts"), o.getString("nonce"), o.getString("re"),
                o.getString("ct"), o.getString("mac"))
        }
    }
}

/** Plain summary of a get_state reply for the phone UI. */
object CompanionView {
    fun summary(state: JSONObject): String {
        val sb = StringBuilder()
        val snap = state.optJSONObject("snapshot")
        val sum = snap?.optJSONObject("summary")
        if (snap != null) sb.append(snap.optString("project_id")).append(" · rev ").append(snap.optInt("state_revision")).append('\n')
        if (sum != null) sb.append("tasks ").append(sum.optInt("total_tasks")).append(" · done ").append(sum.optInt("verified_complete"))
            .append(" · blocked ").append(sum.optInt("blocked_tasks")).append('\n')
        sb.append("→ ").append(state.optString("next_action")).append('\n')
        val warn = state.optJSONArray("warnings")
        for (i in 0 until (warn?.length() ?: 0)) sb.append("⚠ ").append(warn!!.optString(i)).append('\n')
        val tasks = state.optJSONArray("tasks")
        for (i in 0 until (tasks?.length() ?: 0)) {
            val t = tasks!!.optJSONObject(i) ?: continue
            sb.append(t.optString("task_id")).append("  ").append(t.optString("status_text")).append("  ").append(t.optString("title")).append('\n')
        }
        val builds = state.optJSONArray("builds")
        for (i in 0 until (builds?.length() ?: 0)) {
            val b = builds!!.optJSONObject(i) ?: continue
            sb.append("build ").append(b.optLong("run_id")).append(" ").append(b.optString("outcome")).append(" ")
                .append(b.optString("commit_sha").take(12)).append('\n')
        }
        return sb.toString().trimEnd()
    }
}
