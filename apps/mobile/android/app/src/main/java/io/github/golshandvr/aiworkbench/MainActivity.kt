package io.github.golshandvr.aiworkbench

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.graphics.Typeface
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import io.github.golshandvr.aiworkbench.core.Shell5
import io.github.golshandvr.aiworkbench.core.Tokens5
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * The 5.x shell of AI Workbench Mobile (roadmap 6.0.0 / mobile 3.0.0).
 *
 * A bottom bar with the five destinations of the desktop rail — Home · Projects · Agents · History · Settings —
 * in the Midnight (default) or Daylight theme from the shared tokens. Home continues the last project,
 * Projects opens Standalone mode, Agents opens the desktop Companion, History lists the published releases,
 * Settings holds the theme switch and the exact build provenance (version, versionCode, commit SHA, ref, channel).
 */
class MainActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    private lateinit var page: LinearLayout
    private lateinit var scroll: ScrollView
    private lateinit var bar: BottomBar5
    private lateinit var status: TextView
    private lateinit var results: LinearLayout
    private lateinit var checkButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        Ui5.apply(this)
        super.onCreate(savedInstanceState)
        val labels = listOf(R.string.tab_home, R.string.tab_projects, R.string.tab_agents, R.string.tab_history,
            R.string.tab_settings).map(::getString)
        page = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val p = Ui5.dp(this@MainActivity, 16)
            setPadding(p, p, p, p)
        }
        scroll = ScrollView(this).apply { isFillViewport = true; addView(page) }
        bar = BottomBar5(this, labels).apply {
            selected = Shell5.KEYS.indexOf(Ui5.tab(this@MainActivity))
            onSelect = { show(Shell5.KEYS[it]) }
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Ui5.c(this@MainActivity, "window"))
            addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(bar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        })
        show(Ui5.tab(this))
    }

    override fun onResume() {
        super.onResume()
        if (Shell5.tab(Ui5.tab(this)) == "home") show("home")  // the last project may have changed
    }

    // ---------------------------------------------------------------- pages
    private fun show(key: String) {
        Ui5.setTab(this, key)
        page.removeAllViews()
        page.addView(header(getString(when (key) {
            "projects" -> R.string.tab_projects
            "agents" -> R.string.tab_agents
            "history" -> R.string.tab_history
            "settings" -> R.string.tab_settings
            else -> R.string.app_name
        })))
        when (key) {
            "projects" -> projectsPage()
            "agents" -> agentsPage()
            "history" -> historyPage()
            "settings" -> settingsPage()
            else -> homePage()
        }
        scroll.scrollTo(0, 0)
    }

    private fun header(text: String) = TextView(this).apply {
        this.text = text
        textSize = 24f
        setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        setTextColor(Ui5.c(this@MainActivity, "text"))
        setPadding(0, Ui5.dp(this@MainActivity, 8), 0, Ui5.dp(this@MainActivity, 16))
    }

    private fun card(caps: String, build: LinearLayout.() -> Unit) {
        page.addView(Ui5.card(this).apply { addView(Ui5.caps(this@MainActivity, caps)); build() })
    }

    private fun lastProject(): String? = File(filesDir, "projects").listFiles().orEmpty()
        .filter { File(it, "state.json").isFile }.maxByOrNull { File(it, "state.json").lastModified() }?.name

    private fun openStandalone(project: String? = null) {
        startActivity(Intent(this, StandaloneActivity::class.java).apply {
            if (project != null) putExtra(StandaloneActivity.EXTRA_OPEN, project)
        })
    }

    private fun homePage() {
        val last = lastProject()
        card(getString(R.string.home_caps)) {
            addView(Ui5.body(this@MainActivity, getString(R.string.home_lead)))
            if (last != null) {
                addView(Ui5.title(this@MainActivity, getString(R.string.home_recent, last)))
                addView(Ui5.button(this@MainActivity, getString(R.string.home_continue, last), primary = true) { openStandalone(last) })
            } else {
                addView(Ui5.button(this@MainActivity, getString(R.string.standalone_open), primary = true) { openStandalone() })
            }
            addView(Ui5.button(this@MainActivity, getString(R.string.companion_open)) {
                startActivity(Intent(this@MainActivity, CompanionActivity::class.java))
            })
        }
    }

    private fun projectsPage() {
        card(getString(R.string.projects_caps)) {
            val ids = File(filesDir, "projects").listFiles().orEmpty().filter { File(it, "state.json").isFile }.map { it.name }.sorted()
            if (ids.isEmpty()) addView(Ui5.body(this@MainActivity, getString(R.string.standalone_no_projects)))
            for (id in ids) addView(Ui5.button(this@MainActivity, id) { openStandalone(id) })
            addView(Ui5.button(this@MainActivity, getString(R.string.projects_manage), primary = true) { openStandalone() })
        }
    }

    private fun agentsPage() {
        card(getString(R.string.agents_caps)) {
            addView(Ui5.body(this@MainActivity, getString(R.string.agents_lead)))
            addView(Ui5.button(this@MainActivity, getString(R.string.companion_open), primary = true) {
                startActivity(Intent(this@MainActivity, CompanionActivity::class.java))
            })
        }
    }

    private fun historyPage() {
        card(getString(R.string.history_caps)) {
            addView(Ui5.body(this@MainActivity, getString(R.string.history_lead)))
            checkButton = Ui5.button(this@MainActivity, getString(R.string.check_updates), primary = true) { checkReleases() }
            addView(checkButton)
            status = Ui5.body(this@MainActivity, "", color = "text")
            addView(status)
            results = LinearLayout(this@MainActivity).apply { orientation = LinearLayout.VERTICAL }
            addView(results)
        }
    }

    private fun settingsPage() {
        val theme = Ui5.theme(this)
        fun name(t: String) = getString(if (t == Tokens5.DAYLIGHT) R.string.theme_daylight else R.string.theme_midnight)
        card(getString(R.string.settings_appearance)) {
            addView(Ui5.title(this@MainActivity, getString(R.string.theme_current, name(theme))))
            addView(Ui5.button(this@MainActivity, getString(R.string.theme_switch, name(Shell5.toggled(theme))), primary = true) {
                Ui5.setTheme(this@MainActivity, Shell5.toggled(theme))
                recreate()
            })
        }
        card(getString(R.string.settings_build)) {
            addView(Ui5.body(this@MainActivity, getString(
                R.string.build_info_template,
                BuildConfig.VERSION_NAME,
                BuildConfig.VERSION_CODE,
                BuildConfig.CHANNEL,
                BuildConfig.COMMIT_SHA.take(12),
                BuildConfig.BUILD_REF,
            ), role = "mono", color = "text").apply { setTextIsSelectable(true) })
            addView(Ui5.button(this@MainActivity, getString(R.string.open_repository)) {
                openUrl("https://github.com/${BuildConfig.GITHUB_REPOSITORY}")
            })
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
        results.addView(Ui5.title(this, getString(R.string.release_row, label, release.version.toString(), release.publishedAt.take(10))))
        if (preferredAsset != null) {
            results.addView(Ui5.button(this, getString(R.string.download_asset, preferredAsset.name, ReleaseInfo.humanSize(preferredAsset.size)), primary = true) {
                openUrl(preferredAsset.downloadUrl)
            })
        }
        results.addView(Ui5.button(this, getString(R.string.open_release_page)) { openUrl(release.htmlUrl) })
    }

    private fun openUrl(url: String) {
        if (!ReleaseInfo.isTrustedReleaseUrl(url)) {
            toast(getString(R.string.untrusted_link))
            return
        }
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (e: ActivityNotFoundException) {
            toast(getString(R.string.no_browser))
        }
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()

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

    companion object {
        private const val MAX_RESPONSE_BYTES = 2 * 1024 * 1024
    }
}
