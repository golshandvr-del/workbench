package io.github.golshandvr.aiworkbench

import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Companion envelope v1 — byte-for-byte the same construction as the desktop
 * (apps/desktop/src/aiwb/companion/crypto.py), verified against
 * packages/contracts/vectors/companion-envelope.v1.json:
 * HMAC-SHA256 keystream (CTR) for confidentiality, encrypt-then-MAC for integrity.
 */
data class Envelope(val v: Int, val kid: String, val ts: Long, val nonce: String, val re: String, val ct: String, val mac: String)

class EnvelopeException(message: String) : Exception(message)

object CompanionCrypto {
    const val VERSION = 1
    const val MAX_SKEW_SECONDS = 300L
    private val random = SecureRandom()

    fun randomBytes(n: Int): ByteArray = ByteArray(n).also { random.nextBytes(it) }

    fun hmac(key: ByteArray, msg: ByteArray): ByteArray =
        Mac.getInstance("HmacSHA256").run { init(SecretKeySpec(key, "HmacSHA256")); doFinal(msg) }

    private fun keys(master: ByteArray) =
        hmac(master, "aiwb-companion-enc-v1".toByteArray()) to hmac(master, "aiwb-companion-mac-v1".toByteArray())

    private fun xorStream(key: ByteArray, nonce: ByteArray, data: ByteArray): ByteArray {
        val out = ByteArray(data.size)
        var i = 0
        var pos = 0
        while (pos < data.size) {
            val block = hmac(key, nonce + byteArrayOf((i ushr 24).toByte(), (i ushr 16).toByte(), (i ushr 8).toByte(), i.toByte()))
            for (b in block) {
                if (pos >= data.size) break
                out[pos] = (data[pos].toInt() xor b.toInt()).toByte()
                pos++
            }
            i++
        }
        return out
    }

    private fun macInput(kid: String, ts: Long, nonce: String, re: String, ct: String) =
        "v1|$kid|$ts|$nonce|$re|$ct".toByteArray(Charsets.UTF_8)

    fun seal(master: ByteArray, kid: String, plaintext: ByteArray, ts: Long, nonce: ByteArray = randomBytes(16), re: String = ""): Envelope {
        require(nonce.size == 16) { "nonce must be 16 bytes" }
        val (ek, mk) = keys(master)
        val n = B64Url.encode(nonce)
        val ct = B64Url.encode(xorStream(ek, nonce, plaintext))
        return Envelope(VERSION, kid, ts, n, re, ct, B64Url.encode(hmac(mk, macInput(kid, ts, n, re, ct))))
    }

    fun open(master: ByteArray, env: Envelope, nowSeconds: Long): ByteArray {
        if (env.v != VERSION || env.kid.isEmpty() || env.kid.length > 80) throw EnvelopeException("bad envelope")
        val (ek, mk) = keys(master)
        val expected = hmac(mk, macInput(env.kid, env.ts, env.nonce, env.re, env.ct))
        if (!MessageDigest.isEqual(expected, B64Url.decode(env.mac))) throw EnvelopeException("authentication failed")
        if (kotlin.math.abs(nowSeconds - env.ts) > MAX_SKEW_SECONDS) throw EnvelopeException("message too old or clock skew too large")
        val nonce = B64Url.decode(env.nonce)
        if (nonce.size != 16) throw EnvelopeException("bad nonce")
        return xorStream(ek, nonce, B64Url.decode(env.ct))
    }
}

/** RFC 4648 base64url without padding (java.util.Base64 needs API 26; minSdk is 24). */
object B64Url {
    private const val ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

    fun encode(data: ByteArray): String {
        val sb = StringBuilder((data.size * 4 + 2) / 3)
        var i = 0
        while (i < data.size) {
            val b0 = data[i].toInt() and 0xff
            val b1 = if (i + 1 < data.size) data[i + 1].toInt() and 0xff else 0
            val b2 = if (i + 2 < data.size) data[i + 2].toInt() and 0xff else 0
            sb.append(ALPHABET[b0 ushr 2]).append(ALPHABET[((b0 and 3) shl 4) or (b1 ushr 4)])
            if (i + 1 < data.size) sb.append(ALPHABET[((b1 and 15) shl 2) or (b2 ushr 6)])
            if (i + 2 < data.size) sb.append(ALPHABET[b2 and 63])
            i += 3
        }
        return sb.toString()
    }

    fun decode(text: String): ByteArray {
        if (text.length % 4 == 1) throw EnvelopeException("bad base64url")
        val out = java.io.ByteArrayOutputStream(text.length * 3 / 4)
        var buf = 0
        var bits = 0
        for (c in text) {
            val v = ALPHABET.indexOf(c)
            if (v < 0) throw EnvelopeException("bad base64url")
            buf = (buf shl 6) or v
            bits += 6
            if (bits >= 8) {
                bits -= 8
                out.write((buf ushr bits) and 0xff)
            }
        }
        return out.toByteArray()
    }
}
