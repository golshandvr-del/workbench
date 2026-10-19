package io.github.golshandvr.aiworkbench

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.graphics.SurfaceTexture
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.ImageReader
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.view.Surface
import android.view.TextureView
import android.widget.TextView
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Built-in QR scanner (mobile 0.4.0): Camera2 preview + ZXing on the luminance plane. Returns the
 * `aiwb://pair?...` link as RESULT_OK with [EXTRA_LINK]; any other QR content is ignored.
 */
class ScanActivity : Activity() {
    private lateinit var preview: TextureView
    private lateinit var hint: TextView
    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    private var camera: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var reader: ImageReader? = null
    private val done = AtomicBoolean(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_scan)
        preview = findViewById(R.id.scan_preview)
        hint = findViewById(R.id.scan_hint)
    }

    override fun onResume() {
        super.onResume()
        if (checkSelfPermissionCompat()) start() else requestPermissions(arrayOf(Manifest.permission.CAMERA), REQ_CAMERA)
    }

    override fun onPause() {
        stop()
        super.onPause()
    }

    private fun checkSelfPermissionCompat() = checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_CAMERA && grantResults.firstOrNull() != PackageManager.PERMISSION_GRANTED) {
            hint.setText(R.string.scan_no_permission)
        }
    }

    private fun start() {
        val t = HandlerThread("aiwb-scan").also { it.start() }
        thread = t
        handler = Handler(t.looper)
        if (preview.isAvailable) open() else preview.surfaceTextureListener = object : TextureView.SurfaceTextureListener {
            override fun onSurfaceTextureAvailable(s: SurfaceTexture, w: Int, h: Int) = open()
            override fun onSurfaceTextureSizeChanged(s: SurfaceTexture, w: Int, h: Int) {}
            override fun onSurfaceTextureDestroyed(s: SurfaceTexture) = true
            override fun onSurfaceTextureUpdated(s: SurfaceTexture) {}
        }
    }

    private fun open() {
        if (!checkSelfPermissionCompat() || camera != null) return
        val mgr = getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val id = try {
            mgr.cameraIdList.firstOrNull { mgr.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK }
                ?: mgr.cameraIdList.firstOrNull()
        } catch (e: Exception) { null } ?: run { hint.setText(R.string.scan_no_camera); return }
        val r = ImageReader.newInstance(WIDTH, HEIGHT, ImageFormat.YUV_420_888, 2)
        reader = r
        r.setOnImageAvailableListener({ ir ->
            val img = ir.acquireLatestImage() ?: return@setOnImageAvailableListener
            try {
                if (done.get()) return@setOnImageAvailableListener
                val plane = img.planes[0]
                val buf = plane.buffer
                val bytes = ByteArray(buf.remaining()).also { buf.get(it) }
                val text = QrDecode.luminance(bytes, img.width, img.height, plane.rowStride)
                if (text != null && QrDecode.pairing(text) != null && done.compareAndSet(false, true)) {
                    runOnUiThread {
                        setResult(RESULT_OK, Intent().putExtra(EXTRA_LINK, text))
                        finish()
                    }
                }
            } catch (e: Exception) {
                // a bad frame is skipped; the next one is tried
            } finally {
                img.close()
            }
        }, handler)
        try {
            mgr.openCamera(id, object : CameraDevice.StateCallback() {
                override fun onOpened(cd: CameraDevice) {
                    camera = cd
                    val tex = preview.surfaceTexture ?: return
                    tex.setDefaultBufferSize(WIDTH, HEIGHT)
                    val surfaces = listOf(Surface(tex), r.surface)
                    @Suppress("DEPRECATION")
                    cd.createCaptureSession(surfaces, object : CameraCaptureSession.StateCallback() {
                        override fun onConfigured(s: CameraCaptureSession) {
                            session = s
                            val req = cd.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
                                surfaces.forEach { addTarget(it) }
                                set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
                            }
                            try { s.setRepeatingRequest(req.build(), null, handler) } catch (e: Exception) { fail() }
                        }
                        override fun onConfigureFailed(s: CameraCaptureSession) = fail()
                    }, handler)
                }
                override fun onDisconnected(cd: CameraDevice) { cd.close(); camera = null }
                override fun onError(cd: CameraDevice, error: Int) { cd.close(); camera = null; fail() }
            }, handler)
        } catch (e: SecurityException) {
            hint.setText(R.string.scan_no_permission)
        } catch (e: Exception) {
            fail()
        }
    }

    private fun fail() = runOnUiThread { hint.setText(R.string.scan_no_camera) }

    private fun stop() {
        try { session?.close() } catch (_: Exception) {}
        try { camera?.close() } catch (_: Exception) {}
        try { reader?.close() } catch (_: Exception) {}
        session = null; camera = null; reader = null
        thread?.quitSafely()
        thread = null; handler = null
    }

    companion object {
        const val EXTRA_LINK = "aiwb_pair_link"
        private const val REQ_CAMERA = 41
        private const val WIDTH = 1280
        private const val HEIGHT = 720
    }
}
