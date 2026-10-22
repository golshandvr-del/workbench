package io.github.golshandvr.aiworkbench

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
import android.provider.Settings
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.animation.LinearInterpolator
import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.MissionModel
import io.github.golshandvr.aiworkbench.core.Obj
import io.github.golshandvr.aiworkbench.core.Tokens5
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/**
 * Mission Map on the phone (roadmap 6.1.0 / mobile 3.1.0): the desktop Home timeline drawn on an anti-aliased Canvas.
 *
 * A green PROJECT START capsule, a glowing gold source node, curved branches to one numbered green hexagon per AI,
 * one lane per AI with a circle per task in its version's column (done = green tick, active = glowing blue, blocked,
 * attention, idle = grey), dashed version columns with monospace labels and a chevron at each lane's end.
 * Pinch to zoom, drag to pan, tap a circle for details ([onTap]), long press for the four-item menu ([onLongPress]).
 * Active circles pulse softly; the pulse stops when the system "Remove animations" setting is on (Reduce motion).
 */
class MissionMapView(context: Context) : View(context) {
    var model: Obj = MissionModel.build(null)
        set(value) { field = value; lay = MissionModel.layout(value); requestLayout(); updatePulse(); invalidate() }
    var onTap: ((Obj) -> Unit)? = null
    var onLongPress: ((Obj) -> Unit)? = null

    private var lay = MissionModel.layout(model)
    private val d = resources.displayMetrics.density
    private var zoom = 1f
    private var panX = 0f
    private var panY = 0f
    private var pulse = 0f
    private var animator: ValueAnimator? = null

    private fun tok(role: String) = Ui5.c(context, role)
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private val path = Path()
    private val rect = RectF()

    /** True when the system asks for no animation (Settings → Accessibility → Remove animations). */
    fun reduceMotion(): Boolean = try {
        Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
    } catch (_: Exception) { false }

    private fun lanes() = Json.list(model["lanes"]).map { Json.obj(it) }
    private fun hasLive() = lanes().any { it["live"] == true }

    private fun updatePulse() {
        val want = isAttachedToWindow && hasLive() && !reduceMotion()
        if (want && animator == null) {
            animator = ValueAnimator.ofFloat(0f, 1f).apply {
                duration = Tokens5.MOTION.getValue("pulse_ms").toLong()
                repeatCount = ValueAnimator.INFINITE
                interpolator = LinearInterpolator()
                addUpdateListener { pulse = it.animatedValue as Float; invalidate() }
                start()
            }
        } else if (!want) { animator?.cancel(); animator = null; pulse = 0f }
    }

    override fun onAttachedToWindow() { super.onAttachedToWindow(); updatePulse() }
    override fun onDetachedFromWindow() { animator?.cancel(); animator = null; super.onDetachedFromWindow() }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val h = (lay.height * d).toInt().coerceIn((220 * d).toInt(), (560 * d).toInt())
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), h)
    }

    private fun clamp() {
        val maxX = maxOf(0f, lay.width * d * zoom - width)
        val maxY = maxOf(0f, lay.height * d * zoom - height)
        panX = panX.coerceIn(0f, maxX); panY = panY.coerceIn(0f, maxY)
    }

    // ------------------------------------------------------------------ drawing (model units are dp)
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(tok("window"))
        val lanes = lanes()
        if (model["empty"] == true) {
            text.color = tok("text_dim"); text.textSize = 14 * d; text.typeface = Typeface.DEFAULT
            canvas.drawText("No AI lanes yet — set the team size or add tasks.", width / 2f, height / 2f, text)
            return
        }
        canvas.save()
        canvas.translate(-panX, -panY)
        canvas.scale(zoom * d, zoom * d)
        val l = lay
        val cols = Json.list(model["columns"]).map { Json.obj(it) }
        // version columns: dashed lines and monospace labels
        stroke.strokeWidth = 1f; stroke.color = tok("line"); stroke.pathEffect = DashPathEffect(floatArrayOf(4f, 4f), 0f)
        text.typeface = Typeface.MONOSPACE; text.textSize = 11f
        cols.forEachIndexed { i, c ->
            val x = l.colX[i] - Tokens5.GEOMETRY.getValue("col_gap") / 2f
            canvas.drawLine(x, l.top - 16f, x, l.height - 12f, stroke)
            text.color = if (c["kind"] == "version") tok("version") else tok("text_dim")
            val label = Json.str(c["label"]).let { if (c["kind"] == "version") "V$it" else it.uppercase() }
            canvas.drawText(label, l.colX[i], l.top - 24f, text)
        }
        stroke.pathEffect = null
        // lanes: line from hexagon to the end, chevron
        lanes.forEachIndexed { i, lane ->
            val y = l.laneY[i]
            stroke.color = if (lane["live"] == true) tok("line") else tok("line_soft"); stroke.strokeWidth = 2f
            canvas.drawLine(l.hexX + 14f, y, l.endX, y, stroke)
            stroke.color = tok("text_faint")
            path.reset(); path.moveTo(l.endX + 4f, y - 6f); path.lineTo(l.endX + 10f, y); path.lineTo(l.endX + 4f, y + 6f)
            canvas.drawPath(path, stroke)
        }
        // curved branches from the gold source to each hexagon
        val (sx, sy) = l.sourceX to l.midY
        lanes.forEachIndexed { i, lane ->
            val y = l.laneY[i]
            stroke.color = if (lane["live"] == true) tok("go_hi") else tok("go"); stroke.strokeWidth = 2f
            stroke.alpha = if (lane["live"] == true) 255 else 170
            path.reset(); path.moveTo(sx, sy)
            val mx = (sx + l.hexX) / 2
            path.cubicTo(mx, sy, mx, y, l.hexX - Tokens5.GEOMETRY.getValue("hex_r").toFloat(), y)
            canvas.drawPath(path, stroke)
            stroke.alpha = 255
        }
        // PROJECT START capsule and the gold source with its glow
        fill.color = tok("go_deep"); rect.set(l.capsuleX, l.midY - 15f, l.capsuleX + l.capsuleW, l.midY + 15f)
        canvas.drawRoundRect(rect, 15f, 15f, fill)
        stroke.color = tok("go"); stroke.strokeWidth = 1.5f; canvas.drawRoundRect(rect, 15f, 15f, stroke)
        text.typeface = Typeface.DEFAULT_BOLD; text.textSize = 11f; text.color = tok("go_hi"); text.letterSpacing = 0.08f
        canvas.drawText("PROJECT START", l.capsuleX + l.capsuleW / 2, l.midY + 4f, text)
        text.letterSpacing = 0f
        stroke.color = tok("go"); stroke.strokeWidth = 2f; canvas.drawLine(l.capsuleX + l.capsuleW, l.midY, sx, sy, stroke)
        val sr = Tokens5.GEOMETRY.getValue("source_r").toFloat()
        fill.color = tok("source_glow"); fill.alpha = 70; canvas.drawCircle(sx, sy, sr * 2.2f, fill)
        fill.alpha = 255; fill.color = tok("source"); canvas.drawCircle(sx, sy, sr, fill)
        // hexagons with lane numbers
        val hr = Tokens5.GEOMETRY.getValue("hex_r").toFloat()
        lanes.forEachIndexed { i, lane ->
            val y = l.laneY[i]
            path.reset()
            for (k in 0..6) {
                val a = Math.toRadians(60.0 * k - 90.0)
                val px = l.hexX + hr * cos(a).toFloat(); val py = y + hr * sin(a).toFloat()
                if (k == 0) path.moveTo(px, py) else path.lineTo(px, py)
            }
            path.close()
            fill.color = tok("go_deep"); canvas.drawPath(path, fill)
            stroke.color = tok("go"); stroke.strokeWidth = 1.8f; canvas.drawPath(path, stroke)
            text.typeface = Typeface.DEFAULT_BOLD; text.textSize = 11f; text.color = tok("go_hi")
            canvas.drawText(Json.int(lane["number"]).toString(), l.hexX, y + 4f, text)
            text.typeface = Typeface.DEFAULT; text.textSize = 9f; text.color = tok("text_dim")
            canvas.drawText(Json.str(lane["name"]).take(12), l.hexX, y + hr + 12f, text)
        }
        // task circles
        val tr = Tokens5.GEOMETRY.getValue("task_r").toFloat()
        for (lane in lanes) for (nd in Json.list(lane["nodes"]).map { Json.obj(it) }) {
            val (x, y) = l.nodes[Json.str(nd["task_id"])] ?: continue
            when (Json.str(nd["state"])) {
                "done" -> {
                    fill.color = tok("done"); canvas.drawCircle(x, y, tr, fill)
                    stroke.color = tok("active_text"); stroke.strokeWidth = 2f
                    path.reset(); path.moveTo(x - tr * 0.45f, y); path.lineTo(x - tr * 0.1f, y + tr * 0.35f); path.lineTo(x + tr * 0.45f, y - tr * 0.3f)
                    canvas.drawPath(path, stroke)
                }
                "active" -> {
                    val g = 1.6f + 0.5f * sin(pulse * 2 * Math.PI).toFloat()
                    fill.color = tok("active_glow"); fill.alpha = 80; canvas.drawCircle(x, y, tr * g, fill)
                    fill.alpha = 255; fill.color = tok("active"); canvas.drawCircle(x, y, tr, fill)
                    stroke.color = tok("active_hi"); stroke.strokeWidth = 2f; canvas.drawCircle(x, y, tr, stroke)
                }
                "blocked" -> {
                    fill.color = tok("idle"); canvas.drawCircle(x, y, tr, fill)
                    stroke.color = tok("danger"); stroke.strokeWidth = 2f; canvas.drawCircle(x, y, tr, stroke)
                    canvas.drawLine(x - tr * 0.4f, y - tr * 0.4f, x + tr * 0.4f, y + tr * 0.4f, stroke)
                }
                "attention" -> {
                    fill.color = tok("idle"); canvas.drawCircle(x, y, tr, fill)
                    stroke.color = tok("warn"); stroke.strokeWidth = 2f; canvas.drawCircle(x, y, tr, stroke)
                    text.typeface = Typeface.DEFAULT_BOLD; text.textSize = 12f; text.color = tok("warn")
                    canvas.drawText("!", x, y + 4f, text)
                }
                else -> {
                    fill.color = tok("idle"); canvas.drawCircle(x, y, tr, fill)
                    stroke.color = tok("idle_ring"); stroke.strokeWidth = 2f; canvas.drawCircle(x, y, tr, stroke)
                }
            }
        }
        canvas.restore()
    }

    // ------------------------------------------------------------------ touch: pan, pinch zoom, tap, long press
    private fun nodeAt(px: Float, py: Float): Obj? {
        val mx = (px + panX) / (zoom * d); val my = (py + panY) / (zoom * d)
        var best: Obj? = null
        var bestD = Tokens5.GEOMETRY.getValue("task_r") * 2.2f
        for (lane in lanes()) for (nd in Json.list(lane["nodes"]).map { Json.obj(it) }) {
            val (x, y) = lay.nodes[Json.str(nd["task_id"])] ?: continue
            val dist = hypot(x - mx, y - my)
            if (dist < bestD) { bestD = dist; best = nd }
        }
        return best
    }

    private val scaler = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(det: ScaleGestureDetector): Boolean {
            val before = zoom
            zoom = (zoom * det.scaleFactor).coerceIn(0.5f, 3f)
            val k = zoom / before
            panX = (panX + det.focusX) * k - det.focusX
            panY = (panY + det.focusY) * k - det.focusY
            clamp(); invalidate(); return true
        }
    })

    private val gestures = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onDown(e: MotionEvent): Boolean = true
        override fun onScroll(e1: MotionEvent?, e2: MotionEvent, dx: Float, dy: Float): Boolean {
            panX += dx; panY += dy; clamp(); invalidate(); return true
        }
        override fun onSingleTapUp(e: MotionEvent): Boolean {
            nodeAt(e.x, e.y)?.let { onTap?.invoke(it) }; return true
        }
        override fun onLongPress(e: MotionEvent) {
            nodeAt(e.x, e.y)?.let { performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS); onLongPress?.invoke(it) }
        }
    })

    override fun onTouchEvent(ev: MotionEvent): Boolean {
        if (ev.actionMasked == MotionEvent.ACTION_DOWN) parent?.requestDisallowInterceptTouchEvent(true)
        scaler.onTouchEvent(ev)
        if (!scaler.isInProgress) gestures.onTouchEvent(ev)
        if (ev.actionMasked == MotionEvent.ACTION_UP) performClick()
        return true
    }

    override fun performClick(): Boolean = super.performClick()
}
