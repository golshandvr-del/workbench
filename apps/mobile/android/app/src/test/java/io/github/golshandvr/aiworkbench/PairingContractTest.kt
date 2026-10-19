package io.github.golshandvr.aiworkbench

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.File

/**
 * mobile 0.4.0 Gate: the Kotlin side of companion-pairing.v2 (same vectors as the desktop's test_qr_pairing)
 * and ZXing decoding of the QR matrix produced by the desktop's pure-Python encoder.
 */
class PairingContractTest {
    private fun doc(): JSONObject {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        return JSONObject(File(requireNotNull(dir), "packages/contracts/vectors/companion-pairing.v2.json").readText())
    }

    private fun hex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    @Test fun vectorsMatchDesktop() {
        val d = doc()
        assertEquals(600, d.getInt("ttl_seconds"))
        assertEquals(5, d.getInt("max_failed_attempts"))
        val cases = d.getJSONArray("cases")
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val raw = hex(c.getString("secret_hex"))
            assertArrayEquals(raw, PairingCode.secretFromCode(c.getString("code")))
            assertArrayEquals(raw, PairingCode.secretFromCode(c.getString("formatted")))
            assertEquals(c.getString("formatted"), PairingCode.formatCode(c.getString("code")))
            val fromUri = PairingCode.parse(c.getString("uri"))!!
            val manual = PairingCode.manual(c.getString("host") + ":" + c.getInt("port"), c.getString("formatted"))!!
            for (p in listOf(fromUri, manual)) {
                assertEquals(c.getString("host"), p.host)
                assertEquals(c.getInt("port"), p.port)
                assertEquals(c.getString("pairing_id"), p.pairingId)
                assertEquals(c.getString("master_key_b64url"), B64Url.encode(p.secret))
            }
        }
    }

    @Test fun normalizeAndRejectInvalid() {
        val d = doc()
        val norm = d.getJSONArray("normalize")
        for (i in 0 until norm.length()) {
            val n = norm.getJSONObject(i)
            assertEquals(n.getString("code"), PairingCode.normalizeCode(n.getString("input")))
        }
        val badCodes = d.getJSONArray("invalid_codes")
        for (i in 0 until badCodes.length()) assertNull(badCodes.getString(i), PairingCode.normalizeCode(badCodes.getString(i)))
        val badUris = d.getJSONArray("invalid_uris")
        for (i in 0 until badUris.length()) assertNull(badUris.getString(i), PairingCode.parse(badUris.getString(i)))
    }

    @Test fun zxingDecodesTheDesktopQr() {
        val q = doc().getJSONObject("qr")
        val rowsJson = q.getJSONArray("rows")
        val rows = (0 until rowsJson.length()).map { rowsJson.getString(it) }
        for (scale in listOf(3, 5, 8)) {
            val (img, w, h) = QrDecode.render(rows, scale)
            val text = QrDecode.luminance(img, w, h)
            assertEquals("scale $scale", q.getString("text"), text)
            assertNotNull(QrDecode.pairing(text))
        }
        // padded row stride (as camera frames have)
        val (img, w, h) = QrDecode.render(rows, 4)
        val stride = w + 32
        val padded = ByteArray(stride * h) { 0x7F }
        for (r in 0 until h) System.arraycopy(img, r * w, padded, r * stride, w)
        assertEquals(q.getString("text"), QrDecode.luminance(padded, w, h, stride))
        assertNull("blank frame", QrDecode.luminance(ByteArray(w * h) { 0xFF.toByte() }, w, h))
    }
}
