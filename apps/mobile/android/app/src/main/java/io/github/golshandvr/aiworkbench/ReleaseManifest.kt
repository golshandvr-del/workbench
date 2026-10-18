package io.github.golshandvr.aiworkbench

import org.json.JSONObject

/**
 * Consumer of the shared contract `packages/contracts/schemas/release-manifest.v1.schema.json`.
 * Strict: anything outside the contract is rejected (returns null), never guessed.
 */
data class ManifestArtifact(val name: String, val size: Long, val sha256: String)

data class ReleaseManifest(
    val app: String,
    val platform: String,
    val version: SemVer,
    val channel: String,
    val tag: String?,
    val commitSha: String?,
    val artifacts: List<ManifestArtifact>,
) {
    /** True only when [sha256] (lowercase hex) is listed for [name] in this manifest. */
    fun matches(name: String, sha256: String): Boolean =
        artifacts.any { it.name == name && it.sha256 == sha256.lowercase() }

    companion object {
        private val APPS = setOf("ai-workbench-desktop", "ai-workbench-mobile")
        private val PLATFORMS = setOf("windows", "android")
        private val CHANNELS = setOf("stable", "beta", "dev")
        private val VERSION = Regex("""^\d+\.\d+\.\d+$""")
        private val TAG = Regex("""^(desktop|mobile)-v\d+\.\d+\.\d+$""")
        private val SHA40 = Regex("""^[0-9a-f]{40}$""")
        private val SHA256 = Regex("""^[0-9a-f]{64}$""")
        private val NAME = Regex("""^[A-Za-z0-9._ -]{1,200}$""")
        private val KEYS = setOf("schema_version", "app", "platform", "version", "channel", "installer", "tag",
            "commit_sha", "repository", "build_run_id", "artifacts")

        fun parse(json: String): ReleaseManifest? = try {
            parseOrThrow(JSONObject(json))
        } catch (e: Exception) {
            null
        }

        private fun parseOrThrow(o: JSONObject): ReleaseManifest? {
            if (o.keys().asSequence().any { it !in KEYS }) return null
            if (o.optInt("schema_version", -1) != 1 || o.opt("schema_version") !is Int) return null
            val app = o.optString("app"); val platform = o.optString("platform"); val channel = o.optString("channel")
            if (app !in APPS || platform !in PLATFORMS || channel !in CHANNELS) return null
            val vText = o.optString("version")
            if (!VERSION.matches(vText)) return null
            val version = SemVer.parse(vText) ?: return null
            val tag: String? = if (o.has("tag")) (o.getString("tag").takeIf { TAG.matches(it) } ?: return null) else null
            val sha: String? = if (o.has("commit_sha")) (o.getString("commit_sha").takeIf { SHA40.matches(it) } ?: return null) else null
            val arr = o.optJSONArray("artifacts") ?: return null
            if (arr.length() == 0) return null
            val artifacts = ArrayList<ManifestArtifact>()
            for (i in 0 until arr.length()) {
                val a = arr.optJSONObject(i) ?: return null
                if (a.keys().asSequence().any { it !in setOf("name", "size", "sha256") }) return null
                val name = a.optString("name"); val digest = a.optString("sha256"); val size = a.optLong("size", 0)
                if (!NAME.matches(name) || !SHA256.matches(digest) || size < 1) return null
                artifacts.add(ManifestArtifact(name, size, digest))
            }
            return ReleaseManifest(app, platform, version, channel, tag, sha, artifacts)
        }
    }
}
