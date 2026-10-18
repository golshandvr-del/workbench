package io.github.golshandvr.aiworkbench

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Runs the Kotlin consumer against the shared fixtures in packages/contracts. */
class ReleaseManifestContractTest {
    private fun fixtures(kind: String): List<File> {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        val root = requireNotNull(dir) { "packages/contracts not found above the working directory" }
        return File(root, "packages/contracts/fixtures/$kind").listFiles { f -> f.name.startsWith("release-manifest.v1.") }!!
            .sortedBy { it.name }
    }

    @Test fun validFixturesParse() {
        val files = fixtures("valid")
        assertTrue(files.size >= 2)
        for (f in files) assertNotNull(f.name, ReleaseManifest.parse(f.readText()))
    }

    @Test fun invalidFixturesAreRejected() {
        val files = fixtures("invalid")
        assertTrue(files.isNotEmpty())
        for (f in files) assertNull(f.name, ReleaseManifest.parse(f.readText()))
    }

    @Test fun matchesOnlyListedDigest() {
        val m = ReleaseManifest.parse(fixtures("valid").first { it.name.contains("mobile") }.readText())!!
        val a = m.artifacts.first()
        assertEquals("ai-workbench-mobile", m.app)
        assertTrue(m.matches(a.name, a.sha256.uppercase()))
        assertTrue(!m.matches(a.name, "0".repeat(64)))
        assertTrue(!m.matches("other.apk", a.sha256))
    }

    @Test fun unknownFieldsAndWrongVersionRejected() {
        assertNull(ReleaseManifest.parse("""{"schema_version":2,"app":"ai-workbench-mobile","platform":"android","version":"0.1.0","channel":"stable","artifacts":[{"name":"a","size":1,"sha256":"${"a".repeat(64)}"}]}"""))
        assertNull(ReleaseManifest.parse("""{"schema_version":1,"extra":1,"app":"ai-workbench-mobile","platform":"android","version":"0.1.0","channel":"stable","artifacts":[{"name":"a","size":1,"sha256":"${"a".repeat(64)}"}]}"""))
        assertNull(ReleaseManifest.parse("not json"))
    }
}
