package io.github.golshandvr.aiworkbench

import org.json.JSONArray

/**
 * Pure (Android-free) release logic so it can be unit-tested on the JVM.
 *
 * Tags follow the monorepo convention: `desktop-vX.Y.Z` and `mobile-vX.Y.Z`
 * (independent version lines for each app).
 */
data class SemVer(val major: Int, val minor: Int, val patch: Int) : Comparable<SemVer> {
    override fun compareTo(other: SemVer): Int =
        compareValuesBy(this, other, SemVer::major, SemVer::minor, SemVer::patch)

    override fun toString(): String = "$major.$minor.$patch"

    companion object {
        private val PATTERN = Regex("""^v?(\d{1,6})\.(\d{1,6})\.(\d{1,6})$""")

        fun parse(text: String): SemVer? {
            val m = PATTERN.matchEntire(text.trim()) ?: return null
            val (a, b, c) = m.destructured
            return SemVer(a.toInt(), b.toInt(), c.toInt())
        }
    }
}

data class ReleaseAsset(val name: String, val size: Long, val downloadUrl: String)

data class Release(
    val tag: String,
    val app: String,
    val version: SemVer,
    val name: String,
    val htmlUrl: String,
    val prerelease: Boolean,
    val publishedAt: String,
    val assets: List<ReleaseAsset>,
)

object ReleaseInfo {
    const val DESKTOP = "desktop"
    const val MOBILE = "mobile"
    private val TAG = Regex("""^(desktop|mobile)-v(\d+\.\d+\.\d+)$""")
    private const val MAX_RELEASES = 200

    /** Parses the GitHub `GET /repos/{owner}/{repo}/releases` JSON array. Drafts and foreign tags are ignored. */
    fun parseReleases(json: String): List<Release> {
        val array = JSONArray(json)
        val out = ArrayList<Release>()
        for (i in 0 until minOf(array.length(), MAX_RELEASES)) {
            val obj = array.optJSONObject(i) ?: continue
            if (obj.optBoolean("draft", false)) continue
            val tag = obj.optString("tag_name", "")
            val match = TAG.matchEntire(tag) ?: continue
            val version = SemVer.parse(match.groupValues[2]) ?: continue
            val htmlUrl = obj.optString("html_url", "")
            if (!isTrustedReleaseUrl(htmlUrl)) continue
            val assetsJson = obj.optJSONArray("assets") ?: JSONArray()
            val assets = (0 until assetsJson.length()).mapNotNull { j ->
                val a = assetsJson.optJSONObject(j) ?: return@mapNotNull null
                val url = a.optString("browser_download_url", "")
                if (!isTrustedReleaseUrl(url)) return@mapNotNull null
                ReleaseAsset(a.optString("name", ""), a.optLong("size", 0L), url)
            }
            out += Release(
                tag = tag,
                app = match.groupValues[1],
                version = version,
                name = obj.optString("name", tag),
                htmlUrl = htmlUrl,
                prerelease = obj.optBoolean("prerelease", false),
                publishedAt = obj.optString("published_at", ""),
                assets = assets,
            )
        }
        return out
    }

    /** Highest version for [app]; pre-releases only when [includePrerelease]. */
    fun latest(releases: List<Release>, app: String, includePrerelease: Boolean = false): Release? =
        releases.filter { it.app == app && (includePrerelease || !it.prerelease) }.maxByOrNull { it.version }

    /** True only when [latest] is strictly newer than the installed [installedVersion]. */
    fun isUpdateAvailable(installedVersion: String, latest: Release?): Boolean {
        val installed = SemVer.parse(installedVersion.substringBefore('-')) ?: return false
        return latest != null && latest.version > installed
    }

    /** The APK asset to offer for a mobile release (release-signed APK preferred). */
    fun apkAsset(release: Release): ReleaseAsset? =
        release.assets.filter { it.name.endsWith(".apk", ignoreCase = true) && !it.name.contains("debug", true) }
            .minByOrNull { it.name.length }

    /** Only https links on github.com for this app's repository are opened. */
    fun isTrustedReleaseUrl(url: String): Boolean =
        url.startsWith("https://github.com/") && !url.contains("..") && !url.contains('@')

    fun humanSize(bytes: Long): String = when {
        bytes >= 1_048_576 -> String.format(java.util.Locale.US, "%.1f MB", bytes / 1_048_576.0)
        bytes >= 1024 -> String.format(java.util.Locale.US, "%.1f KB", bytes / 1024.0)
        else -> "$bytes B"
    }
}
