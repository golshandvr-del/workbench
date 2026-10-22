package io.github.golshandvr.aiworkbench

import android.app.Activity
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import io.github.golshandvr.aiworkbench.core.Shell5
import io.github.golshandvr.aiworkbench.core.Tokens5
import kotlin.math.roundToInt

/**
 * The 5.x look on Android views (roadmap 6.0.0 / mobile 3.0.0): theme preference, colours from [Tokens5],
 * and the few building blocks every screen uses — cards, caps labels, titles, body text and buttons —
 * in the same visual language as the desktop (raised panels, thin lines, blue active, rounded controls).
 */
object Ui5 {
    private const val PREFS = "aiwb_ui"
    private const val KEY_THEME = "theme"
    private const val KEY_TAB = "tab"

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** The stored theme; Midnight (dark) when nothing was chosen yet. */
    fun theme(ctx: Context): String = Tokens5.theme(prefs(ctx).getString(KEY_THEME, null))

    fun setTheme(ctx: Context, name: String) = prefs(ctx).edit().putString(KEY_THEME, Tokens5.theme(name)).apply()

    fun tab(ctx: Context): String = Shell5.tab(prefs(ctx).getString(KEY_TAB, null))

    fun setTab(ctx: Context, key: String) = prefs(ctx).edit().putString(KEY_TAB, Shell5.tab(key)).apply()

    /** Call before `super.onCreate` so the window, status bar and default widgets use the chosen theme. */
    fun apply(activity: Activity) = activity.setTheme(
        if (theme(activity) == Tokens5.DAYLIGHT) R.style.Theme_AIWB_Daylight else R.style.Theme_AIWB_Midnight
    )

    fun c(ctx: Context, role: String): Int = Tokens5.color(theme(ctx), role)

    fun dp(ctx: Context, v: Int): Int = (v * ctx.resources.displayMetrics.density).roundToInt()

    /** Desktop points → phone sp (the desktop type scale, read at arm's length). */
    fun sp(role: String): Float = Tokens5.TYPE.getValue(role).pt * 1.5f

    fun shape(ctx: Context, fill: Int, radiusDp: Int, stroke: Int? = null): GradientDrawable = GradientDrawable().apply {
        setColor(fill)
        cornerRadius = dp(ctx, radiusDp).toFloat()
        if (stroke != null) setStroke(dp(ctx, 1).coerceAtLeast(1), stroke)
    }

    private fun matchWrap(ctx: Context, bottomDp: Int = 0) =
        LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            bottomMargin = dp(ctx, bottomDp)
        }

    /** A raised panel with a thin border (desktop card). */
    fun card(ctx: Context): LinearLayout = LinearLayout(ctx).apply {
        orientation = LinearLayout.VERTICAL
        background = shape(ctx, c(ctx, "raised"), Tokens5.GEOMETRY.getValue("radius_bubble"), c(ctx, "line"))
        val p = dp(ctx, 16)
        setPadding(p, p, p, p)
        layoutParams = matchWrap(ctx, 12)
    }

    /** Small upper-case section label (desktop `label_caps`). */
    fun caps(ctx: Context, text: String): TextView = TextView(ctx).apply {
        this.text = text.uppercase()
        textSize = sp("label_caps")
        setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        letterSpacing = 0.08f
        setTextColor(c(ctx, "text_faint"))
        layoutParams = matchWrap(ctx, 6)
    }

    fun title(ctx: Context, text: String): TextView = TextView(ctx).apply {
        this.text = text
        textSize = sp("title")
        setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        setTextColor(c(ctx, "text"))
        layoutParams = matchWrap(ctx, 4)
    }

    fun body(ctx: Context, text: String, role: String = "body", color: String = "text_dim"): TextView = TextView(ctx).apply {
        this.text = text
        textSize = sp(role)
        setTextColor(c(ctx, color))
        if (role.startsWith("mono")) typeface = Typeface.MONOSPACE
        setLineSpacing(0f, 1.15f)
        layoutParams = matchWrap(ctx, 8)
    }

    /** A rounded button: blue for the main action of a card, a quiet raised one otherwise. */
    fun button(ctx: Context, text: String, primary: Boolean = false, onClick: () -> Unit): Button = Button(ctx).apply {
        this.text = text
        isAllCaps = false
        textSize = sp("body")
        stateListAnimator = null
        val radius = Tokens5.GEOMETRY.getValue("radius_ctl")
        val fill = if (primary) c(ctx, "active") else c(ctx, "raised_hi")
        val press = if (primary) c(ctx, "active_hi") else c(ctx, "selection")
        background = RippleDrawable(ColorStateList.valueOf(press), shape(ctx, fill, radius, if (primary) null else c(ctx, "line")), null)
        setTextColor(if (primary) c(ctx, "active_text") else c(ctx, "text"))
        gravity = Gravity.CENTER
        minHeight = dp(ctx, 44)
        val h = dp(ctx, 14)
        setPadding(h, 0, h, 0)
        layoutParams = matchWrap(ctx, 8)
        setOnClickListener { onClick() }
    }
}
