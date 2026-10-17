package io.github.golshandvr.aiworkbench

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * AI Workbench Mobile 0.x — proof-of-build app (roadmap v1.14.11).
 *
 * Deliberately small: shows exact build provenance (version, versionCode,
 * commit SHA, ref, channel) and lists the latest Desktop/Mobile GitHub
 * Releases so the user can download the Windows installer or a newer APK.
 * It does not claim Companion features (pairing, remote control) yet.
 */
class MainActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    private lateinit var status: TextView
    private lateinit var results: LinearLayout
    private lateinit var checkButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        status = findViewById(R.id.update_status)
        results = findViewById(R.id.release_list)
        checkButton = findViewById(R.id.check_updates_button)

        findViewById<TextView>(R.id.build_info).text = getString(
            R.string.build_info_template,
            BuildConfig.VERSION_NAME,
            BuildConfig.VERSION_CODE,
            BuildConfig.CHANNEL,
            BuildConfig.COMMIT_SHA.take(12),
            BuildConfig.BUILD_REF,
        )
        checkButton.setOnClickListener { checkReleases() }
        findViewById<Button>(R.id.open_repo_button).setOnClickListener {
            openUrl("https://github.com/${BuildConfig.GITHUB_REPOSITORY}")
        }
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }

    private fun checkReleases() {
        checkButton.isEnabled = false
        status.setText(R.string.checking)
        results.removeAllViews()
        executor.execute {
            val outcome = try {
                Result.success(ReleaseInfo.parseReleases(fetchReleasesJson()))
            } catch (e: Exception) {
                Result.failure(e)
            }
            main.post {
                if (isFinishing || isDestroyed) return@post
                checkButton.isEnabled = true
                outcome.fold(::showReleases) { e ->
                    status.text = getString(R.string.check_failed, e.message ?: e.javaClass.simpleName)
                }
            }
        }
    }

    private fun fetchReleasesJson(): String {
        val url = URL("https://api.github.com/repos/${BuildConfig.GITHUB_REPOSITORY}/releases?per_page=50")
        val conn = url.openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 15_000
            conn.readTimeout = 20_000
            conn.instanceFollowRedirects = false
            conn.setRequestProperty("Accept", "application/vnd.github+json")
            conn.setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            conn.setRequestProperty("User-Agent", "AIWorkbench-Mobile/${BuildConfig.VERSION_NAME}")
            val code = conn.responseCode
            if (code == 403 || code == 429) throw IOException(getString(R.string.rate_limited))
            if (code != 200) throw IOException("HTTP $code")
            val length = conn.contentLengthLong
            if (length > MAX_RESPONSE_BYTES) throw IOException("response too large")
            return conn.inputStream.use { stream ->
                val bytes = stream.readNBytesCompat(MAX_RESPONSE_BYTES + 1)
                if (bytes.size > MAX_RESPONSE_BYTES) throw IOException("response too large")
                String(bytes, Charsets.UTF_8)
            }
        } finally {
            conn.disconnect()
        }
    }

    private fun showReleases(releases: List<Release>) {
        val desktop = ReleaseInfo.latest(releases, ReleaseInfo.DESKTOP)
        val mobile = ReleaseInfo.latest(releases, ReleaseInfo.MOBILE)
        val update = ReleaseInfo.isUpdateAvailable(BuildConfig.VERSION_NAME, mobile)
        status.text = when {
            mobile == null && desktop == null -> getString(R.string.no_releases)
            update -> getString(R.string.mobile_update_available, mobile!!.version.toString())
            else -> getString(R.string.mobile_up_to_date)
        }
        desktop?.let { addReleaseRow(getString(R.string.desktop_label), it, preferredAsset = it.assets.firstOrNull { a -> a.name.endsWith("_Setup.bat") }) }
        mobile?.let { addReleaseRow(getString(R.string.mobile_label), it, preferredAsset = ReleaseInfo.apkAsset(it)) }
    }

    private fun addReleaseRow(label: String, release: Release, preferredAsset: ReleaseAsset?) {
        val row = TextView(this).apply {
            textSize = 15f
            setPadding(0, 24, 0, 8)
            text = getString(R.string.release_row, label, release.version.toString(), release.publishedAt.take(10))
        }
        results.addView(row)
        if (preferredAsset != null) {
            results.addView(Button(this).apply {
                text = getString(R.string.download_asset, preferredAsset.name, ReleaseInfo.humanSize(preferredAsset.size))
                isAllCaps = false
                setOnClickListener { openUrl(preferredAsset.downloadUrl) }
            })
        }
        results.addView(Button(this).apply {
            setText(R.string.open_release_page)
            isAllCaps = false
            setOnClickListener { openUrl(release.htmlUrl) }
        })
    }

    private fun openUrl(url: String) {
        if (!ReleaseInfo.isTrustedReleaseUrl(url)) {
            status.setText(R.string.untrusted_link)
            return
        }
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (e: ActivityNotFoundException) {
            status.setText(R.string.no_browser)
        }
    }

    private fun java.io.InputStream.readNBytesCompat(limit: Int): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (out.size() < limit) {
            val n = read(buffer, 0, minOf(buffer.size, limit - out.size()))
            if (n < 0) break
            out.write(buffer, 0, n)
        }
        return out.toByteArray()
    }

    @Suppress("unused")
    private fun View.gone() { visibility = View.GONE }

    companion object {
        private const val MAX_RESPONSE_BYTES = 2 * 1024 * 1024
    }
}
