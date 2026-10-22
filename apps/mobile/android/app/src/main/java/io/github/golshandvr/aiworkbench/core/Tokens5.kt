package io.github.golshandvr.aiworkbench.core

/**
 * Design tokens of the "Mission Map" look on the phone (roadmap 6.0.0 / mobile 3.0.0).
 *
 * Same values as the desktop `aiwb/ui/tokens5.py`, shared through `packages/design/tokens5.json`
 * (`Tokens5Test` fails if this file and the JSON differ). Views read tokens; they never hard-code a colour.
 * Midnight (dark) is the default; Daylight mirrors every role.
 */
object Tokens5 {
    const val MIDNIGHT = "midnight"
    const val DAYLIGHT = "daylight"
    val THEMES = listOf(MIDNIGHT, DAYLIGHT)
    const val DEFAULT_THEME = MIDNIGHT

    data class Type(val kind: String, val pt: Int, val weight: String)
    data class Dest(val key: String, val label: String, val icon: String)

    val PALETTES: Map<String, Map<String, Int>> = mapOf(
        MIDNIGHT to linkedMapOf(
            "window" to 0xFF0F131A.toInt(),
            "field" to 0xFF10151C.toInt(),
            "panel" to 0xFF151A23.toInt(),
            "raised" to 0xFF1B2130.toInt(),
            "raised_hi" to 0xFF232A3B.toInt(),
            "line" to 0xFF2A3142.toInt(),
            "line_soft" to 0xFF1D2331.toInt(),
            "text" to 0xFFE6EAF2.toInt(),
            "text_dim" to 0xFF9AA3B5.toInt(),
            "text_faint" to 0xFF5F687B.toInt(),
            "active" to 0xFF2F7BFF.toInt(),
            "active_hi" to 0xFF5B97FF.toInt(),
            "active_glow" to 0xFF1D5FE0.toInt(),
            "active_text" to 0xFFFFFFFF.toInt(),
            "version" to 0xFF5AA9FF.toInt(),
            "go" to 0xFF22C55E.toInt(),
            "go_hi" to 0xFF4ADE80.toInt(),
            "go_deep" to 0xFF0F3D26.toInt(),
            "source" to 0xFFF5C542.toInt(),
            "source_glow" to 0xFFF59E0B.toInt(),
            "idle" to 0xFF2C313D.toInt(),
            "idle_ring" to 0xFF4A5263.toInt(),
            "done" to 0xFF22C55E.toInt(),
            "warn" to 0xFFF59E0B.toInt(),
            "danger" to 0xFFF43F5E.toInt(),
            "bubble_user" to 0xFF1F2738.toInt(),
            "bubble_ai" to 0xFF181E2B.toInt(),
            "menu" to 0xFF1A202D.toInt(),
            "menu_border" to 0xFF2E3647.toInt(),
            "shadow" to 0xFF05070B.toInt(),
            "selection" to 0xFF1E3A6B.toInt(),
        ),
        DAYLIGHT to linkedMapOf(
            "window" to 0xFFF3F5F9.toInt(),
            "field" to 0xFFFBFCFE.toInt(),
            "panel" to 0xFFEEF1F6.toInt(),
            "raised" to 0xFFFFFFFF.toInt(),
            "raised_hi" to 0xFFE7ECF4.toInt(),
            "line" to 0xFFD5DBE6.toInt(),
            "line_soft" to 0xFFE6EAF1.toInt(),
            "text" to 0xFF151A23.toInt(),
            "text_dim" to 0xFF4F5869.toInt(),
            "text_faint" to 0xFF8A93A5.toInt(),
            "active" to 0xFF1F66E5.toInt(),
            "active_hi" to 0xFF3B7BF0.toInt(),
            "active_glow" to 0xFF7AA7F7.toInt(),
            "active_text" to 0xFFFFFFFF.toInt(),
            "version" to 0xFF2563EB.toInt(),
            "go" to 0xFF16A34A.toInt(),
            "go_hi" to 0xFF22C55E.toInt(),
            "go_deep" to 0xFFDCFCE7.toInt(),
            "source" to 0xFFE0A800.toInt(),
            "source_glow" to 0xFFF5C542.toInt(),
            "idle" to 0xFFE3E7EE.toInt(),
            "idle_ring" to 0xFFA8B0BF.toInt(),
            "done" to 0xFF16A34A.toInt(),
            "warn" to 0xFFB45309.toInt(),
            "danger" to 0xFFE11D48.toInt(),
            "bubble_user" to 0xFFE6EEFC.toInt(),
            "bubble_ai" to 0xFFFFFFFF.toInt(),
            "menu" to 0xFFFFFFFF.toInt(),
            "menu_border" to 0xFFD5DBE6.toInt(),
            "shadow" to 0xFF9AA3B5.toInt(),
            "selection" to 0xFFDBE7FD.toInt(),
        ),
    )

    val TYPE: Map<String, Type> = linkedMapOf(
        "title" to Type("ui", 11, "bold"),
        "body" to Type("ui", 10, "normal"),
        "small" to Type("ui", 9, "normal"),
        "caption" to Type("ui", 8, "normal"),
        "label_caps" to Type("ui", 8, "bold"),
        "capsule" to Type("ui", 9, "bold"),
        "mono" to Type("mono", 9, "normal"),
        "mono_small" to Type("mono", 8, "normal"),
        "brand" to Type("ui", 11, "bold"),
    )

    val GEOMETRY: Map<String, Int> = linkedMapOf(
        "rail_w" to 64,
        "toolbar_h" to 44,
        "status_h" to 30,
        "lane_gap" to 68,
        "col_gap" to 66,
        "task_r" to 11,
        "task_ring" to 2,
        "hex_r" to 12,
        "source_r" to 8,
        "radius_ctl" to 6,
        "radius_bubble" to 10,
        "radius_menu" to 10,
        "grid" to 4,
    )

    val MOTION: Map<String, Int> = linkedMapOf(
        "hover_ms" to 120,
        "menu_ms" to 180,
        "page_ms" to 240,
        "grow_ms" to 600,
        "pulse_ms" to 1600,
        "fps" to 60,
    )

    /** The five destinations of the bottom bar, same keys and order as the desktop rail. */
    val RAIL: List<Dest> = listOf(
        Dest("home", "Home", "home"),
        Dest("projects", "Projects", "projects"),
        Dest("agents", "Agents", "agents"),
        Dest("history", "History", "history"),
        Dest("settings", "Settings", "settings"),
    )

    /** Theme for a stored preference; unknown or old values (light/dark) map onto the two 5.x themes. */
    fun theme(name: String?): String = when (name) {
        DAYLIGHT, "light" -> DAYLIGHT
        else -> MIDNIGHT
    }

    fun palette(name: String?): Map<String, Int> = PALETTES.getValue(theme(name))

    fun color(name: String?, role: String): Int = palette(name).getValue(role)

    /** `#rrggbb` text of an ARGB colour (used by tests and the JSON parity check). */
    fun hex(c: Int): String = "#%06x".format(c and 0xFFFFFF)

    /** Linear blend of two colours (t = 0 → a, 1 → b); hover and fades. */
    fun mix(a: Int, b: Int, t: Float): Int {
        val k = t.coerceIn(0f, 1f)
        fun ch(c: Int, s: Int) = (c shr s) and 0xFF
        fun m(s: Int) = Math.round(ch(a, s) + (ch(b, s) - ch(a, s)) * k)
        return (0xFF shl 24) or (m(16) shl 16) or (m(8) shl 8) or m(0)
    }

    /** WCAG contrast ratio of two colours (tests keep text readable in both themes). */
    fun contrast(fg: Int, bg: Int): Double {
        fun lum(c: Int): Double {
            val v = intArrayOf((c shr 16) and 0xFF, (c shr 8) and 0xFF, c and 0xFF).map {
                val x = it / 255.0
                if (x <= 0.03928) x / 12.92 else Math.pow((x + 0.055) / 1.055, 2.4)
            }
            return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
        }
        val (hi, lo) = listOf(lum(fg), lum(bg)).sortedDescending()
        return (hi + 0.05) / (lo + 0.05)
    }
}
