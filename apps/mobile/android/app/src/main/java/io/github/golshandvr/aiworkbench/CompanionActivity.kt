package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Tokens5
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * Mobile Companion (Integration Spec §11, P3.1–P3.3): pair with the desktop over the local network with a
 * one-time code, view project/tasks/builds, and — when the desktop allowed it — create a task or submit a
 * model answer. Every request is end-to-end sealed and handled by the desktop's central services.
 */
class CompanionActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val client = CompanionClient(::httpPost)
    private lateinit var status: TextView
    private lateinit var stateText: TextView
    private var pairing: Pairing? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        Ui5.apply(this)  // 6.0.0: Midnight / Daylight
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_companion)
        status = findViewById(R.id.companion_status)
        stateText = findViewById(R.id.state_text)
        stateText.background = Ui5.shape(this, Ui5.c(this, "field"), Tokens5.GEOMETRY.getValue("radius_ctl"), Ui5.c(this, "line"))
        pairing = Pairing.decode(prefs().getString(KEY_PAIRING, null))
        findViewById<Button>(R.id.pair_button).setOnClickListener {
            val code = PairingCode.manual(findViewById<EditText>(R.id.pair_address).text.toString(),
                findViewById<EditText>(R.id.pair_code).text.toString())
            if (code == null) status.setText(R.string.bad_pair_code) else pair(code)
        }
        findViewById<Button>(R.id.scan_button).setOnClickListener {
            startActivityForResult(Intent(this, ScanActivity::class.java), REQ_SCAN)
        }
        findViewById<Button>(R.id.refresh_button).setOnClickListener { refresh() }
        findViewById<Button>(R.id.create_task_button).setOnClickListener {
            val title = findViewById<EditText>(R.id.task_title).text.toString().trim()
            val objective = findViewById<EditText>(R.id.task_objective).text.toString().trim()
            if (title.isEmpty() || objective.isEmpty()) { status.setText(R.string.task_fields_required); return@setOnClickListener }
            run("create_task", JSONObject().put("title", title).put("objective", objective)) { out ->
                status.text = getString(R.string.task_created, out.optString("task_id"))
                refresh()
            }
        }
        findViewById<Button>(R.id.submit_answer_button).setOnClickListener {
            val text = findViewById<EditText>(R.id.answer_text).text.toString()
            if (text.isBlank()) return@setOnClickListener
            run("submit_response", JSONObject().put("text", text)) { out ->
                status.text = out.optString("message")
                refresh()
            }
        }
        findViewById<Button>(R.id.unpair_button).setOnClickListener {
            prefs().edit().remove(KEY_PAIRING).apply()
            pairing = null
            stateText.text = ""
            status.setText(R.string.unpaired)
            showSections()
        }
        showSections()
        if (pairing != null) refresh()
        handleLink(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleLink(intent)
    }

    @Deprecated("startActivityForResult is used for API 24 compatibility without AndroidX")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_SCAN && resultCode == RESULT_OK) {
            val code = PairingCode.parse(data?.getStringExtra(ScanActivity.EXTRA_LINK) ?: "")
            if (code == null) status.setText(R.string.bad_pair_code) else pair(code)
        }
    }

    /** Deep link `aiwb://pair?...` opened from the system camera. */
    private fun handleLink(intent: Intent?) {
        val link = intent?.takeIf { it.action == Intent.ACTION_VIEW }?.dataString ?: return
        intent.data = null
        if (pairing != null) return
        val code = PairingCode.parse(link)
        if (code == null) status.setText(R.string.bad_pair_code) else pair(code)
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }

    private fun prefs() = getSharedPreferences("companion", Context.MODE_PRIVATE)

    private fun showSections() {
        val paired = pairing != null
        findViewById<View>(R.id.pair_section).visibility = if (paired) View.GONE else View.VISIBLE
        findViewById<View>(R.id.paired_section).visibility = if (paired) View.VISIBLE else View.GONE
        if (paired) status.text = getString(R.string.paired_with, pairing!!.host, pairing!!.port)
    }

    private fun pair(code: PairingCode) {
        val key = CompanionCrypto.randomBytes(32)
        status.setText(R.string.pairing_wait)
        background({
            client.requestPairing(code, Build.MODEL ?: "Android", key)
            var result: Pairing? = null
            val deadline = System.currentTimeMillis() + 5 * 60_000
            while (result == null && System.currentTimeMillis() < deadline) {
                Thread.sleep(2000)
                result = client.pairingStatus(code, key)
            }
            result ?: throw CompanionException("timeout", getString(R.string.pairing_timeout))
        }) { p ->
            prefs().edit().putString(KEY_PAIRING, p.encode()).apply()
            pairing = p
            showSections()
            refresh()
        }
    }

    private fun refresh() = run("get_state", JSONObject()) { out -> stateText.text = CompanionView.summary(out) }

    private fun run(op: String, extra: JSONObject, done: (JSONObject) -> Unit) {
        val p = pairing ?: return
        background({ client.request(p, op, extra) }, done)
    }

    private fun <T> background(work: () -> T, done: (T) -> Unit) {
        executor.execute {
            val r = try { Result.success(work()) } catch (e: Exception) { Result.failure(e) }
            main.post {
                if (isFinishing || isDestroyed) return@post
                r.fold(done) { e ->
                    status.text = when ((e as? CompanionException)?.code) {
                        "device_not_paired" -> getString(R.string.device_revoked)
                        "forbidden" -> getString(R.string.not_allowed, e.message ?: "")
                        "pairing_expired" -> getString(R.string.pairing_expired)
                        else -> getString(R.string.companion_error, e.message ?: e.javaClass.simpleName)
                    }
                }
            }
        }
    }

    private fun httpPost(host: String, port: Int, body: String): Pair<Int, String> {
        if (!PairingCode.isPrivateLan(host)) throw IOException("not a local-network address")
        val conn = URL("http", host, port, "/aiwb/v1").openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 8_000
            conn.readTimeout = 20_000
            conn.instanceFollowRedirects = false
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            val bytes = body.toByteArray(Charsets.UTF_8)
            conn.setFixedLengthStreamingMode(bytes.size)
            conn.outputStream.use { it.write(bytes) }
            val code = conn.responseCode
            val stream = if (code >= 400) conn.errorStream else conn.inputStream
            val text = stream?.use { s -> s.readBytes().also { if (it.size > MAX_REPLY) throw IOException("reply too large") } }
            return code to String(text ?: ByteArray(0), Charsets.UTF_8)
        } finally {
            conn.disconnect()
        }
    }

    companion object {
        private const val KEY_PAIRING = "pairing"
        private const val REQ_SCAN = 42
        private const val MAX_REPLY = 4 * 1024 * 1024
    }
}
