package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Shell5
import io.github.golshandvr.aiworkbench.core.Tokens5
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Roadmap 6.0.0 / mobile 3.0.0: the bottom bar is the desktop rail; the theme switch flips Midnight ↔ Daylight. */
class Shell5Test {
    @Test fun bottomBarIsTheDesktopRail() {
        assertEquals(listOf("home", "projects", "agents", "history", "settings"), Shell5.KEYS)
        assertEquals(Shell5.KEYS, Shell5.CONTENT.keys.toList())
        for ((k, v) in Shell5.CONTENT) assertTrue(k, v.isNotEmpty())
    }

    @Test fun unknownTabStartsOnHome() {
        assertEquals("home", Shell5.tab(null))
        assertEquals("home", Shell5.tab("prompt"))
        assertEquals("agents", Shell5.tab("agents"))
    }

    @Test fun themeSwitchFlips() {
        assertEquals(Tokens5.DAYLIGHT, Shell5.toggled(null))
        assertEquals(Tokens5.DAYLIGHT, Shell5.toggled(Tokens5.MIDNIGHT))
        assertEquals(Tokens5.MIDNIGHT, Shell5.toggled(Tokens5.DAYLIGHT))
        assertEquals(Tokens5.MIDNIGHT, Shell5.toggled("light"))
    }
}
