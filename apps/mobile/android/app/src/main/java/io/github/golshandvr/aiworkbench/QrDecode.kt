package io.github.golshandvr.aiworkbench

import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.NotFoundException
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.ReaderException
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader

/** QR decoding for the pairing scanner (pure JVM, so it is unit-tested against the desktop's QR output). */
object QrDecode {
    private val hints = mapOf(
        DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE),
        DecodeHintType.TRY_HARDER to true,
        DecodeHintType.CHARACTER_SET to "UTF-8",
    )

    /** Decodes the luminance (Y) plane of a camera frame; returns null if no QR code is found. */
    fun luminance(y: ByteArray, width: Int, height: Int, rowStride: Int = width): String? {
        val data = if (rowStride == width) y else ByteArray(width * height).also {
            for (r in 0 until height) System.arraycopy(y, r * rowStride, it, r * width, width)
        }
        val src = PlanarYUVLuminanceSource(data, width, height, 0, 0, width, height, false)
        return try {
            QRCodeReader().decode(BinaryBitmap(HybridBinarizer(src)), hints).text
        } catch (e: NotFoundException) {
            null
        } catch (e: ReaderException) {
            null
        }
    }

    /** Renders a module matrix ("1" = dark) to a luminance image with a quiet zone (used by tests). */
    fun render(rows: List<String>, scale: Int = 4, quiet: Int = 4): Triple<ByteArray, Int, Int> {
        val n = rows.size
        val side = (n + 2 * quiet) * scale
        val img = ByteArray(side * side) { 0xFF.toByte() }
        for (r in 0 until n) for (c in 0 until n) if (rows[r][c] == '1') {
            for (dy in 0 until scale) for (dx in 0 until scale) img[((r + quiet) * scale + dy) * side + (c + quiet) * scale + dx] = 0
        }
        return Triple(img, side, side)
    }

    /** The pairing link inside a scanned code, if it is one. */
    fun pairing(text: String?): PairingCode? = text?.let { PairingCode.parse(it) }
}
