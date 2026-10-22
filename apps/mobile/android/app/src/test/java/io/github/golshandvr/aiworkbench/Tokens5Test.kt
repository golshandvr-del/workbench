package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Tokens5
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Roadmap 6.0.0 / mobile 3.0.0: the phone's tokens are the desktop's tokens.
 *
 * `packages/design/tokens5.json` is written from the desktop `tokens5.py` (desktop `test_shared_tokens` keeps it equal);
 * this test keeps [Tokens5] equal to the same JSON, so both apps share one palette, type scale, geometry and rail.
 */
class Tokens5Test {
    private fun json(): JSONObject {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/design/tokens5.json").isFile) dir = dir.parentFile
        return JSONObject(File(requireNotNull(dir), "packages/design/tokens5.json").readText())
    }

    @Test fun palettesEqualDesktop() {
        val p = json().getJSONObject("palettes")
        assertEquals(p.keySet(), Tokens5.PALETTES.keys)
        for (theme in Tokens5.THEMES) {
            val want = p.getJSONObject(theme)
            val have = Tokens5.PALETTES.getValue(theme)
            assertEquals(theme, want.keySet(), have.keys)
            for (role in have.keys) assertEquals("$theme.$role", want.getString(role), Tokens5.hex(have.getValue(role)))
        }
    }

    @Test fun defaultIsMidnight() {
        assertEquals(json().getString("default_theme"), Tokens5.DEFAULT_THEME)
        assertEquals(Tokens5.MIDNIGHT, Tokens5.theme(null))
        assertEquals(Tokens5.MIDNIGHT, Tokens5.theme("dark"))
        assertEquals(Tokens5.DAYLIGHT, Tokens5.theme("light"))
        assertEquals(Tokens5.MIDNIGHT, Tokens5.theme("bogus"))
    }

    @Test fun typeGeometryMotionEqualDesktop() {
        val d = json()
        val type = d.getJSONObject("type")
        assertEquals(type.keySet(), Tokens5.TYPE.keys)
        for ((k, t) in Tokens5.TYPE) {
            val o = type.getJSONObject(k)
            assertEquals(k, Tokens5.Type(o.getString("kind"), o.getInt("pt"), o.getString("weight")), t)
        }
        for ((name, map) in listOf("geometry" to Tokens5.GEOMETRY, "motion" to Tokens5.MOTION)) {
            val o = d.getJSONObject(name)
            assertEquals(name, o.keySet(), map.keys)
            for ((k, v) in map) assertEquals("$name.$k", o.getInt(k), v)
        }
    }

    @Test fun bottomBarHasTheDesktopRail() {
        val rail = json().getJSONArray("rail")
        assertEquals(5, Tokens5.RAIL.size)
        assertEquals(rail.length(), Tokens5.RAIL.size)
        for (i in 0 until rail.length()) {
            val r = rail.getJSONObject(i)
            assertEquals(Tokens5.Dest(r.getString("key"), r.getString("label"), r.getString("icon")), Tokens5.RAIL[i])
        }
    }

    @Test fun textIsReadableInBothThemes() {
        for (theme in Tokens5.THEMES) {
            val p = Tokens5.palette(theme)
            for (surface in listOf("window", "panel", "raised")) {
                assertTrue("$theme text/$surface", Tokens5.contrast(p.getValue("text"), p.getValue(surface)) >= 7.0)
                assertTrue("$theme text_dim/$surface", Tokens5.contrast(p.getValue("text_dim"), p.getValue(surface)) >= 4.5)
            }
            assertTrue("$theme active_text", Tokens5.contrast(p.getValue("active_text"), p.getValue("active")) >= 3.0)
        }
    }

    @Test fun mixBlends() {
        assertEquals("#000000", Tokens5.hex(Tokens5.mix(0xFF000000.toInt(), 0xFFFFFFFF.toInt(), 0f)))
        assertEquals("#ffffff", Tokens5.hex(Tokens5.mix(0xFF000000.toInt(), 0xFFFFFFFF.toInt(), 2f)))
        assertEquals("#808080", Tokens5.hex(Tokens5.mix(0xFF000000.toInt(), 0xFFFFFFFF.toInt(), 0.5f)))
    }
}
