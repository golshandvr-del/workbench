package io.github.golshandvr.aiworkbench.core

/**
 * The mobile shell of the 5.x look (roadmap 6.0.0 / mobile 3.0.0), as pure data so it is tested on the JVM.
 *
 * The bottom bar has the same five destinations, in the same order, as the desktop rail ([Tokens5.RAIL]); each
 * destination says what it holds on the phone, mirroring the desktop page of the same key.
 */
object Shell5 {
    /** What each destination opens on the phone (same meaning as the desktop page with that key). */
    val CONTENT: Map<String, List<String>> = linkedMapOf(
        "home" to listOf("active_project", "next_step", "quick_actions"),
        "projects" to listOf("project_list", "new_project", "import_bundle"),
        "agents" to listOf("companion_pairing", "tasks", "answers"),
        "history" to listOf("timeline", "releases"),
        "settings" to listOf("appearance", "build_info", "repository"),
    )

    val KEYS: List<String> get() = Tokens5.RAIL.map { it.key }

    /** A stored tab key, or Home when it is missing or unknown (an old install starts on Home). */
    fun tab(stored: String?): String = if (stored != null && stored in KEYS) stored else KEYS.first()

    /** The other theme (the Settings switch). */
    fun toggled(theme: String?): String =
        if (Tokens5.theme(theme) == Tokens5.MIDNIGHT) Tokens5.DAYLIGHT else Tokens5.MIDNIGHT
}
