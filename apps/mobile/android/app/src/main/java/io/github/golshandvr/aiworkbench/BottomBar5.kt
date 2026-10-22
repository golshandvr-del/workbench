package io.github.golshandvr.aiworkbench

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityEvent
import io.github.golshandvr.aiworkbench.core.Tokens5

/**
 * The bottom bar of the 5.x shell (roadmap 6.0.0 / mobile 3.0.0): the five destinations of the desktop rail
 * (Home · Projects · Agents · History · Settings), drawn anti-aliased with the same line icons, a blue pill
 * behind the selected one and its label in the active colour.
 */
class BottomBar5(context: Context, private val labels: List<String>) : View(context) {
    var selected: Int = 0
        set(value) { field = value.coerceIn(0, Tokens5.RAIL.lastIndex); invalidate() }
    var onSelect: ((Int) -> Unit)? = null

    private val d = resources.displayMetrics.density
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 1.8f * d; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
    }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER; textSize = 11.5f * d }
    private val path = Path()
    private val rect = RectF()

    init {
        isClickable = true
        isFocusable = true
        contentDescription = labels.getOrElse(0) { "" }
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), (64 * d).toInt())
    }

    override fun onDraw(canvas: Canvas) {
        val ctx = context
        canvas.drawColor(Ui5.c(ctx, "panel"))
        fill.color = Ui5.c(ctx, "line_soft")
        canvas.drawRect(0f, 0f, width.toFloat(), d, fill)
        val n = Tokens5.RAIL.size
        val w = width / n.toFloat()
        for (i in 0 until n) {
            val cx = w * i + w / 2
            val cy = 24 * d
            val on = i == selected
            if (on) {
                fill.color = Ui5.c(ctx, "selection")
                rect.set(cx - 28 * d, cy - 14 * d, cx + 28 * d, cy + 14 * d)
                canvas.drawRoundRect(rect, 14 * d, 14 * d, fill)
            }
            stroke.color = if (on) Ui5.c(ctx, "active_hi") else Ui5.c(ctx, "text_dim")
            icon(canvas, Tokens5.RAIL[i].icon, cx, cy, 9 * d)
            label.color = if (on) Ui5.c(ctx, "text") else Ui5.c(ctx, "text_dim")
            label.isFakeBoldText = on
            canvas.drawText(labels.getOrElse(i) { Tokens5.RAIL[i].label }, cx, 54 * d, label)
        }
    }

    /** Line icons in a 2r × 2r box centred on (cx, cy); same shapes as the desktop rail icons. */
    private fun icon(c: Canvas, name: String, cx: Float, cy: Float, r: Float) {
        path.reset()
        when (name) {
            "home" -> {
                path.moveTo(cx - r, cy - r * 0.05f); path.lineTo(cx, cy - r); path.lineTo(cx + r, cy - r * 0.05f)
                path.moveTo(cx - r * 0.7f, cy - r * 0.3f); path.lineTo(cx - r * 0.7f, cy + r)
                path.lineTo(cx + r * 0.7f, cy + r); path.lineTo(cx + r * 0.7f, cy - r * 0.3f)
                c.drawPath(path, stroke)
            }
            "projects" -> {
                rect.set(cx - r, cy - r * 0.55f, cx + r, cy + r * 0.85f); c.drawRoundRect(rect, r * 0.2f, r * 0.2f, stroke)
                path.moveTo(cx - r, cy - r * 0.55f); path.lineTo(cx - r, cy - r * 0.85f); path.lineTo(cx - r * 0.2f, cy - r * 0.85f)
                path.lineTo(cx, cy - r * 0.55f); c.drawPath(path, stroke)
            }
            "agents" -> {  // a hexagon (the AI lane head) with a dot
                for (k in 0..6) {
                    val a = Math.toRadians(60.0 * k - 90.0)
                    val x = cx + r * Math.cos(a).toFloat(); val y = cy + r * Math.sin(a).toFloat()
                    if (k == 0) path.moveTo(x, y) else path.lineTo(x, y)
                }
                c.drawPath(path, stroke)
                fill.color = stroke.color; c.drawCircle(cx, cy, r * 0.25f, fill)
            }
            "history" -> {
                c.drawCircle(cx, cy, r, stroke)
                path.moveTo(cx, cy - r * 0.55f); path.lineTo(cx, cy); path.lineTo(cx + r * 0.45f, cy + r * 0.3f)
                c.drawPath(path, stroke)
            }
            else -> {  // settings: three sliders
                for ((k, f) in listOf(-0.6f to 0.35f, 0f to -0.4f, 0.6f to 0.1f)) {
                    val y = cy + r * k
                    c.drawLine(cx - r, y, cx + r, y, stroke)
                    fill.color = Ui5.c(context, "panel"); c.drawCircle(cx + r * f, y, r * 0.24f, fill)
                    c.drawCircle(cx + r * f, y, r * 0.24f, stroke)
                }
            }
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_UP) {
            val i = (event.x / (width / Tokens5.RAIL.size.toFloat())).toInt().coerceIn(0, Tokens5.RAIL.lastIndex)
            if (i != selected) {
                selected = i
                contentDescription = labels.getOrElse(i) { "" }
                sendAccessibilityEvent(AccessibilityEvent.TYPE_VIEW_SELECTED)
                onSelect?.invoke(i)
            }
            performClick()
        }
        return true
    }

    override fun performClick(): Boolean = super.performClick()
}
