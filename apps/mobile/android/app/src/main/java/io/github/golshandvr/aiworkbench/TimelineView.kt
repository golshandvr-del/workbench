package io.github.golshandvr.aiworkbench

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import io.github.golshandvr.aiworkbench.core.Timeline

/**
 * Visual timeline on the phone (roadmap 3.6.0 / mobile 1.0.0): horizontal time axis, one lane per AI, a dot per
 * event sized by importance, a vertical line per version (dashed while planned, solid once released).
 * Pinch to zoom, drag to pan, tap a dot to see what happened ([onSelect]).
 */
class TimelineView(context: Context) : View(context) {
    var model: Timeline.Model = Timeline.Model(emptyList(), emptyList(), emptyList(), 0.0, 1.0)
        set(value) { field = value; requestLayout(); invalidate() }
    var onSelect: ((String) -> Unit)? = null

    private val density = resources.displayMetrics.density
    private val laneH = 40 * density
    private val top = (16 + 13 * LABEL_ROWS) * density
    private val left = 110 * density
    private var zoom = 1f
    private var offset = 0f
    private var lastX = 0f
    private var downX = 0f
    private var downY = 0f

    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF1C1C1C.toInt(); textSize = 12 * density }
    private val muted = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF5C5C5C.toInt(); textSize = 11 * density }
    private val grid = Paint().apply { color = 0xFFE5E5E5.toInt(); strokeWidth = density }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG)
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeWidth = 2 * density }
    private val colors = mapOf("critical" to 0xFFC42B1C.toInt(), "major" to 0xFF8A5300.toInt(),
        "normal" to 0xFF005FB8.toInt(), "minor" to 0xFF8A8A8A.toInt())

    private val scaler = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(d: ScaleGestureDetector): Boolean {
            val before = (d.focusX - left + offset) / zoom
            zoom = (zoom * d.scaleFactor).coerceIn(0.5f, 60f)
            offset = before * zoom - (d.focusX - left)
            clamp(); invalidate(); return true
        }
    })

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val h = (top + laneH * maxOf(1, model.lanes.size) + 24 * density).toInt()
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), h)
    }

    private fun span() = (width - left - 16 * density).coerceAtLeast(1f)
    private fun x(t: Double): Float = left + (((t - model.t0) / (model.t1 - model.t0)).toFloat() * span() * zoom) - offset
    private fun clamp() { offset = offset.coerceIn(0f, maxOf(0f, span() * zoom - span())) }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val lanes = model.lanes
        if (lanes.isEmpty()) { canvas.drawText("No events yet.", left, top + 20 * density, muted); return }
        lanes.forEachIndexed { i, lane ->
            val y = top + laneH * i + laneH / 2
            canvas.drawLine(left, y, width.toFloat(), y, grid)
            canvas.drawText(lane.removePrefix("agent-").take(14), 8 * density, y + 4 * density, text)
        }
        val rowEnd = FloatArray(LABEL_ROWS) { -1e9f }   // labels that would overlap go one row up
        for (v in model.versions.sortedBy { it.t }) {
            val xv = x(v.t)
            if (xv < left || xv > width) continue
            val row = (0 until LABEL_ROWS).firstOrNull { rowEnd[it] < xv } ?: (LABEL_ROWS - 1)
            rowEnd[row] = xv + muted.measureText(v.label) + 6 * density
            line.color = if (v.released) 0xFF0E700E.toInt() else 0xFF005FB8.toInt()
            line.pathEffect = if (v.released) null else DashPathEffect(floatArrayOf(8 * density, 6 * density), 0f)
            canvas.drawLine(xv, top - 6 * density, xv, top + laneH * lanes.size, line)
            canvas.drawText(v.label, xv + 3 * density, top - 10 * density - row * 13 * density, muted)
        }
        for (e in model.events) {
            val xe = x(e.t)
            if (xe < left - 12 * density || xe > width + 12 * density) continue
            val y = top + laneH * lanes.indexOf(e.lane).coerceAtLeast(0) + laneH / 2
            dot.color = colors[e.importance] ?: 0xFF8A8A8A.toInt()
            dot.alpha = if (e.dated) 255 else 120
            canvas.drawCircle(xe, y, (Timeline.RADIUS[e.importance] ?: 4) * density, dot)
        }
    }

    override fun onTouchEvent(ev: MotionEvent): Boolean {
        scaler.onTouchEvent(ev)
        when (ev.actionMasked) {
            MotionEvent.ACTION_DOWN -> { lastX = ev.x; downX = ev.x; downY = ev.y; parent?.requestDisallowInterceptTouchEvent(true) }
            MotionEvent.ACTION_MOVE -> if (!scaler.isInProgress && ev.pointerCount == 1) {
                offset -= ev.x - lastX; lastX = ev.x; clamp(); invalidate()
            }
            MotionEvent.ACTION_UP -> {
                if (Math.abs(ev.x - downX) < 10 * density && Math.abs(ev.y - downY) < 10 * density) select(ev.x, ev.y)
                performClick()
            }
        }
        return true
    }

    override fun performClick(): Boolean = super.performClick()

    private fun select(px: Float, py: Float) {
        var best: Timeline.Event? = null
        var bestD = 24 * density
        for (e in model.events) {
            val y = top + laneH * model.lanes.indexOf(e.lane).coerceAtLeast(0) + laneH / 2
            val d = Math.hypot((x(e.t) - px).toDouble(), (y - py).toDouble()).toFloat()
            if (d < bestD) { bestD = d; best = e }
        }
        best?.let { onSelect?.invoke("${it.label}\n${it.whenText} · revision ${it.revision} · ${it.importance}\nlane: ${it.lane}") }
    }

    private companion object { const val LABEL_ROWS = 3 }
}
