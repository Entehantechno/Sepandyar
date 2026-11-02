package ai.arena.sepandyar

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.PixelFormat
import android.os.Handler
import android.os.Looper
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

    private val main = Handler(Looper.getMainLooper())
    private var confirmView: View? = null
    private var confirmTimer: Runnable? = null

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
        dismissConfirm()
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
    /**
     * کارت تأیید برای گام‌های «تعهدآور» — همان‌هایی که یک تعهد واقعی یا
     * مالی ثبت می‌کنند.
     *
     * **چرا لازم است:** پیش‌تر رسپی اسنپ روی «درخواست خودرو» بدون هیچ
     * `expect` و بدون هیچ تأییدی ضربه می‌زد و **یک سفر واقعی ثبت می‌شد**.
     * هیچ اتوماسیونی نباید تعهد واقعی را بدون تأیید صریح انسان ثبت کند؛
     * این همان «تحویل کنترل در نقطهٔ پرداخت» است که همهٔ ابزارهای این
     * حوزه انجام می‌دهند.
     *
     * سه تصمیم عمدی:
     *  - **پیش‌فرض «نه».** تایم‌اوت، نبودِ اجازهٔ overlay، یا هر استثنا ⇒
     *    `false`. شکست باید به سمت «انجام نشد» برود، نه «انجام شد».
     *  - **دکمه‌ها ۵۶dp** — بزرگ‌تر از کف ۴۸dp خودِ پروژه، چون این
     *    مهم‌ترین تصمیم روی صفحه است.
     *  - **تأیید با لمس است نه با صدا.** تشخیص گفتار در محیط شلوغ خطا
     *    دارد و یک «بله»ی اشتباه شنیده‌شده نباید سفر ثبت کند.
     *
     * `onDone` **دقیقاً یک بار** صدا زده می‌شود — تایم‌اوت و لمس با هم
     * مسابقه می‌دهند و بدون این محافظ، گام اجراکننده دو بار ادامه می‌داد.
     */
    @SuppressLint("ClickableViewAccessibility")
    fun showConfirm(context: Context, heading: String, detail: String,
                    timeoutMs: Long, onDone: (Boolean) -> Unit) {
        val app = context.applicationContext
        val fired = java.util.concurrent.atomic.AtomicBoolean(false)
        val deny = Runnable {
            if (!fired.compareAndSet(false, true)) return@Runnable
            dismissConfirm()
            onDone(false)
        }
        if (!canDrawOverlays(app)) { onDone(false); return }
        val density = app.resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()
        try {
            if (wm == null) wm = app.getSystemService(WindowManager::class.java)
            val panel = LinearLayout(app).apply {
                orientation = LinearLayout.VERTICAL
                background = GradientDrawable().apply {
                    cornerRadius = dp(20).toFloat()
                    setColor(0xF71B3B36.toInt())
                }
                setPadding(dp(18), dp(18), dp(18), dp(16))
                layoutParams = LinearLayout.LayoutParams(dp(300), LinearLayout.LayoutParams.WRAP_CONTENT)
            }
            panel.addView(TextView(app).apply {
                text = heading
                textSize = 17f
                setTextColor(0xFFFFFFFF.toInt())
                typeface = android.graphics.Typeface.DEFAULT_BOLD
            })
            panel.addView(TextView(app).apply {
                text = detail
                textSize = 14f
                setTextColor(0xEEFFFFFF.toInt())
                setPadding(0, dp(8), 0, dp(14))
            })
            val row = LinearLayout(app).apply {
                orientation = LinearLayout.HORIZONTAL
            }
            // «نه» اول و سمت راست (راست‌چین): گزینهٔ بی‌خطر باید دمِ دست باشد.
            row.addView(Button(app).apply {
                text = "نه، لغو کن"
                textSize = 15f
                setTextColor(0xFFFFFFFF.toInt())
                background = GradientDrawable().apply {
                    cornerRadius = dp(14).toFloat(); setColor(0x40FFFFFF)
                }
                layoutParams = LinearLayout.LayoutParams(0, dp(56), 1f)
                setOnClickListener { deny.run() }
            })
            row.addView(Button(app).apply {
                text = "بله، تأیید می‌کنم"
                textSize = 15f
                setTextColor(0xFFFFFFFF.toInt())
                background = GradientDrawable().apply {
                    cornerRadius = dp(14).toFloat(); setColor(0xFF3E8E7E.toInt())
                }
                layoutParams = LinearLayout.LayoutParams(0, dp(56), 1f).apply { marginStart = dp(10) }
                setOnClickListener {
                    if (fired.compareAndSet(false, true)) { dismissConfirm(); onDone(true) }
                }
            })
            panel.addView(row)
            val params = WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                PixelFormat.TRANSLUCENT
            ).apply { gravity = Gravity.CENTER }
            wm?.addView(panel, params)
            confirmView = panel
            confirmTimer = deny
            main.postDelayed(deny, if (timeoutMs > 0) timeoutMs else 30000L)
        } catch (e: Exception) {
            if (fired.compareAndSet(false, true)) onDone(false)
        }
    }

    /** بستن کارت تأیید و لغو تایم‌اوت. از هر نخی امن است. */
    private fun dismissConfirm() {
        val run = Runnable {
            confirmTimer?.let { main.removeCallbacks(it) }
            confirmTimer = null
            val v = confirmView ?: return@Runnable
            try { wm?.removeView(v) } catch (e: Exception) { }
            confirmView = null
        }
        if (Looper.myLooper() == Looper.getMainLooper()) run.run() else main.post(run)
    }

}
