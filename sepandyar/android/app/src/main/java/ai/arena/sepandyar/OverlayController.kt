package ai.arena.sepandyar

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import kotlin.math.abs

/**
 * پاپ‌آپ کوچک و شناور سپندیار.
 *
 * وقتی سپندیار کنترل یک اپ دیگر را به دست می‌گیرد، این کارت کوچک روی صفحه
 * اپ مقصد می‌نشیند تا سالمند ببیند چه کاری در حال انجام است، بتواند آن را
 * جابه‌جا کند و در هر لحظه لغو کند. با پایان کار حذف می‌شود.
 */
object OverlayController {
    private var wm: WindowManager? = null
    private var card: View? = null
    private var titleView: TextView? = null
    private var detailView: TextView? = null
    private var bar: ProgressBar? = null
    private var cancelHandler: (() -> Unit)? = null

    var visible: Boolean = false
        private set

    fun canDrawOverlays(context: Context): Boolean = Settings.canDrawOverlays(context)

    @SuppressLint("ClickableViewAccessibility")
    fun show(context: Context, heading: String, onCancel: (() -> Unit)? = null) {
        if (visible) {
            update(heading, "", 0, 1)
            return
        }
        if (!canDrawOverlays(context)) return
        val app = context.applicationContext
        val density = app.resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        wm = app.getSystemService(WindowManager::class.java)
        cancelHandler = onCancel

        val cardBg = GradientDrawable().apply {
            cornerRadius = dp(18).toFloat()
            setColor(0xF2214E4A.toInt())
        }
        val panel = LinearLayout(app).apply {
            orientation = LinearLayout.VERTICAL
            background = cardBg
            setPadding(dp(14), dp(11), dp(12), dp(12))
            layoutParams = LinearLayout.LayoutParams(dp(228), LinearLayout.LayoutParams.WRAP_CONTENT)
        }

        val header = LinearLayout(app).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        titleView = TextView(app).apply {
            text = heading
            textSize = 13f
            setTextColor(0xFFFFFFFF.toInt())
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }
        val stop = Button(app).apply {
            text = "لغو"
            textSize = 11f
            setTextColor(0xFFFFFFFF.toInt())
            background = GradientDrawable().apply {
                cornerRadius = dp(11).toFloat()
                setColor(0x33FFFFFF)
            }
            setPadding(dp(9), dp(3), dp(9), dp(3))
            minimumWidth = 0
            minWidth = 0
            minimumHeight = 0
            minHeight = 0
            isAllCaps = false
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            setOnClickListener { cancelHandler?.invoke() }
        }
        header.addView(titleView)
        header.addView(stop)

        detailView = TextView(app).apply {
            text = ""
            textSize = 11f
            setTextColor(0xFFC4E5DA.toInt())
            setPadding(0, dp(5), 0, dp(7))
        }
        bar = ProgressBar(app, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            progress = 0
        }
        panel.addView(header)
        panel.addView(detailView)
        panel.addView(bar)

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = dp(14)
            y = dp(76)
        }

        // کارت با کشیدن جابه‌جا می‌شود تا جلوی محتوای اپ مقصد را نگیرد.
        var startX = 0
        var startY = 0
        var touchX = 0f
        var touchY = 0f
        var moved = false
        panel.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = params.x
                    startY = params.y
                    touchX = event.rawX
                    touchY = event.rawY
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (event.rawX - touchX).toInt()
                    val dy = (event.rawY - touchY).toInt()
                    if (abs(dx) > 6 || abs(dy) > 6) moved = true
                    params.x = startX + dx
                    params.y = startY + dy
                    wm?.updateViewLayout(panel, params)
                    true
                }
                else -> moved
            }
        }

        try {
            wm?.addView(panel, params)
            card = panel
            visible = true
        } catch (e: Exception) {
            card = null
            visible = false
        }
    }

    /** به‌روزرسانی متن وضعیت و نوار پیشرفت، از هر نخی امن است. */
    fun update(status: String, detail: String, done: Int, total: Int) {
        val run = Runnable {
            titleView?.text = status
            detailView?.text = detail
            detailView?.visibility = if (detail.isBlank()) View.GONE else View.VISIBLE
            val max = if (total <= 0) 1 else total
            bar?.max = 100
            bar?.progress = ((done.coerceIn(0, max)) * 100) / max
        }
        if (android.os.Looper.myLooper() == android.os.Looper.getMainLooper()) run.run()
        else android.os.Handler(android.os.Looper.getMainLooper()).post(run)
    }

    fun hide() {
        val view = card ?: return
        try {
            wm?.removeView(view)
        } catch (e: Exception) {
            // پنجره پیش‌تر حذف شده است
        }
        card = null
        titleView = null
        detailView = null
        bar = null
        cancelHandler = null
        visible = false
    }
}
