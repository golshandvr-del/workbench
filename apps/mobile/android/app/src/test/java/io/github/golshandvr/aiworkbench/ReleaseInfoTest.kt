package io.github.golshandvr.aiworkbench

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReleaseInfoTest {
    private fun rel(tag: String, pre: Boolean = false, draft: Boolean = false, assets: String = "[]", url: String? = null) =
        """{"tag_name":"$tag","name":"$tag","draft":$draft,"prerelease":$pre,
            "html_url":"${url ?: "https://github.com/o/r/releases/tag/$tag"}",
            "published_at":"2026-10-17T00:00:00Z","assets":$assets}"""

    @Test fun semverParsingAndOrdering() {
        assertEquals(SemVer(1, 14, 5), SemVer.parse("v1.14.5"))
        assertEquals(SemVer(0, 1, 0), SemVer.parse("0.1.0"))
        assertNull(SemVer.parse("1.14"))
        assertNull(SemVer.parse("1.14.5-rc1"))
        assertNull(SemVer.parse("x1.2.3"))
        assertTrue(SemVer(1, 14, 10) > SemVer(1, 14, 9))   // numeric, not lexical
        assertTrue(SemVer(2, 0, 0) > SemVer(1, 99, 99))
    }

    @Test fun parsesOnlyMonorepoTagsAndSkipsDrafts() {
        val json = "[" + listOf(
            rel("desktop-v1.14.4"), rel("desktop-v1.14.5"), rel("mobile-v0.1.0"),
            rel("mobile-v0.2.0", draft = true), rel("v9.9.9"), rel("desktop-v1.15"),
        ).joinToString(",") + "]"
        val releases = ReleaseInfo.parseReleases(json)
        assertEquals(listOf("desktop-v1.14.4", "desktop-v1.14.5", "mobile-v0.1.0"), releases.map { it.tag })
        assertEquals("1.14.5", ReleaseInfo.latest(releases, ReleaseInfo.DESKTOP)!!.version.toString())
        assertEquals("0.1.0", ReleaseInfo.latest(releases, ReleaseInfo.MOBILE)!!.version.toString())
    }

    @Test fun prereleaseIgnoredUnlessRequested() {
        val releases = ReleaseInfo.parseReleases("[" + rel("mobile-v0.1.0") + "," + rel("mobile-v0.2.0", pre = true) + "]")
        assertEquals("0.1.0", ReleaseInfo.latest(releases, ReleaseInfo.MOBILE)!!.version.toString())
        assertEquals("0.2.0", ReleaseInfo.latest(releases, ReleaseInfo.MOBILE, includePrerelease = true)!!.version.toString())
    }

    @Test fun updateDetection() {
        val releases = ReleaseInfo.parseReleases("[" + rel("mobile-v0.2.0") + "]")
        val latest = ReleaseInfo.latest(releases, ReleaseInfo.MOBILE)
        assertTrue(ReleaseInfo.isUpdateAvailable("0.1.0", latest))
        assertTrue(ReleaseInfo.isUpdateAvailable("0.1.0-debug", latest))
        assertFalse(ReleaseInfo.isUpdateAvailable("0.2.0", latest))
        assertFalse(ReleaseInfo.isUpdateAvailable("0.3.0", latest))
        assertFalse(ReleaseInfo.isUpdateAvailable("garbage", latest))
        assertFalse(ReleaseInfo.isUpdateAvailable("0.1.0", null))
    }

    @Test fun untrustedUrlsAreDropped() {
        val assets = """[{"name":"a.apk","size":10,"browser_download_url":"http://github.com/o/r/a.apk"},
            {"name":"b.apk","size":20,"browser_download_url":"https://evil.example/b.apk"},
            {"name":"AIWorkbench-mobile-0.1.0.apk","size":30,"browser_download_url":"https://github.com/o/r/releases/download/mobile-v0.1.0/AIWorkbench-mobile-0.1.0.apk"}]"""
        val releases = ReleaseInfo.parseReleases("[" + rel("mobile-v0.1.0", assets = assets) + "," +
            rel("mobile-v0.3.0", url = "https://evil.example/x") + "]")
        assertEquals(1, releases.size)
        assertEquals(listOf("AIWorkbench-mobile-0.1.0.apk"), releases[0].assets.map { it.name })
        assertFalse(ReleaseInfo.isTrustedReleaseUrl("https://github.com@evil.example/x"))
        assertFalse(ReleaseInfo.isTrustedReleaseUrl("https://github.com/o/r/../../x"))
    }

    @Test fun apkAssetPrefersReleaseOverDebug() {
        val assets = """[{"name":"AIWorkbench-mobile-0.1.0-debug.apk","size":1,"browser_download_url":"https://github.com/o/r/d.apk"},
            {"name":"AIWorkbench-mobile-0.1.0.apk","size":2,"browser_download_url":"https://github.com/o/r/r.apk"},
            {"name":"SHA256SUMS.txt","size":3,"browser_download_url":"https://github.com/o/r/s.txt"}]"""
        val release = ReleaseInfo.parseReleases("[" + rel("mobile-v0.1.0", assets = assets) + "]").single()
        assertEquals("AIWorkbench-mobile-0.1.0.apk", ReleaseInfo.apkAsset(release)!!.name)
    }

    @Test fun humanSize() {
        assertEquals("512 B", ReleaseInfo.humanSize(512))
        assertEquals("2.0 KB", ReleaseInfo.humanSize(2048))
        assertEquals("1.5 MB", ReleaseInfo.humanSize(1_572_864))
    }
}
