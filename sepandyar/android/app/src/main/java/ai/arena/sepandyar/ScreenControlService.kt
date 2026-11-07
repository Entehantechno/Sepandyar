package ai.arena.sepandyar

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Rect
import android.os.Bundle
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.view.Display
import android.view.accessibility.AccessibilityNodeInfo
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
// Charsets در kotlin.text.* است و پیش‌فرض import می‌شود، ولی صریح
// آوردنش هزینه‌ای ندارد و کد را از «به کدام Charsets؟» بی‌نیاز می‌کند.
import kotlin.text.Charsets

class ScreenControlService : AccessibilityService() {
    companion object {
        var instance: ScreenControlService? = null
        var pendingAction: ScreenAction? = null

        /** مدت ضربهٔ طولانی؛ آستانهٔ سامانه معمولاً ~۵۰۰ms است. */
        const val LONG_PRESS_MS = 600L
        /** مدت یک کشیدن؛ کوتاه‌تر از این، سامانه آن را ضربه تفسیر می‌کند. */
        const val SWIPE_MS = 320L
        /** مدت کشیدنِ drag؛ باید بلند باشد تا سامانه آن را ضربه نبیند. */
        const val DRAG_MS = 700L
        /** مدت نیشگون. */
        const val PINCH_MS = 280L
        /** سقف متن خوانده‌شدهٔ صفحه؛ یک صفحهٔ شلوغ نباید صف گفتار را منفجر کند. */
        const val SCREEN_TEXT_MAX = 4000

        /** کلید رضایت بینایی روی صفحه — **پیش‌فرض خاموش**. */
        const val PREF_VISION = "screenVision"
        /** عرض تصویر ارسالی؛ بزرگ‌تر از این برای خواندن متن بی‌فایده است. */
        const val VISION_MAX_W = 720
        /** کیفیت JPEG — تعادل میان خوانایی رقم‌ها و حجم. */
        const val VISION_JPEG_Q = 72
        /** سقف انتظار برای پاسخ takeScreenshot. */
        const val VISION_TIMEOUT_MS = 3000L
        /**
         * سقف انتظار برای پاسخ `/api/screen/vision`.
         *
         * عمداً بزرگ‌تر از VISION_TIMEOUT_MS است: این یکی یک رفت‌وبرگشت کامل به
         * سرور و سپس یک فراخوانی به مدل بیرونی است، نه یک callback محلی.
         */
        const val VISION_HTTP_TIMEOUT_MS = 20000
        /** مدت نمایش نشانگر «دارم صفحه را می‌بینم». */
        const val VISION_INDICATOR_MS = 1600L

        /**
         * رضایت بینایی. جدا از دسترسی دسترس‌پذیری است: داشتن سرویس دسترس‌پذیری
         * به هیچ وجه مجوز گرفتن تصویر نیست.
         */
        fun visionAllowed(ctx: Context): Boolean =
            ctx.getSharedPreferences("assistant", Context.MODE_PRIVATE)
                .getBoolean(PREF_VISION, false)

        /**
         * برچسب‌های رایج دکمهٔ «ارسال». فقط در مسیر جایگزین imeEnter برای
         * API < 30 استفاده می‌شود و هیوریستیک است.
         */
        val SUBMIT_LABELS = listOf(
            "جست‌وجو", "جستجو", "ارسال", "تأیید", "تایید", "ثبت", "برو", "ادامه",
            "search", "go", "enter", "submit", "done", "next"
        )
    }

    private val main = Handler(Looper.getMainLooper())

    override fun onServiceConnected() { super.onServiceConnected(); instance = this }
    override fun onDestroy() { instance = null; super.onDestroy() }
    override fun onAccessibilityEvent(event: android.view.accessibility.AccessibilityEvent?) { }
    override fun onInterrupt() { }

    fun executePendingAction() {
        main.postDelayed({
            val action = pendingAction ?: return@postDelayed
            pendingAction = null
            when (action.type) {
                "tap_text" -> smartTap(action.payload, 0)
                "input_text" -> smartInput(action.payload)
                "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
                "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
                "tap_xy" -> action.payload.split(',').mapNotNull { it.trim().toFloatOrNull() }
                    .takeIf { it.size == 2 }?.let { tap(it[0], it[1]) }
            }
        }, 450)
    }

    private fun smartTap(query: String, attempt: Int): Boolean {
        val target = SmartSelector.find(rootInActiveWindow, query)
        if (target?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true) return true
        if (attempt < 8) main.postDelayed({ smartTap(query, attempt + 1) }, 350)
        return false
    }

    /**
     * تایپ در فیلد ورودی.
     *
     * اولویت با فیلدی است که «الان فوکوس ورودی دارد» — یعنی همان فیلدی که
     * گام قبلی (tap_text) روی آن ضربه زد. findEditable روی ریشه، اولین فیلد
     * قابل‌ویرایش را در پیمایش عمق‌اول برمی‌گرداند که در فرم‌های چندفیلدی
     * (مثلاً جست‌وجوی مقصد در اسنپ) لزوماً همان فیلد مقصود نیست و متن در
     * فیلد اشتباه تایپ می‌شد.
     */
    private fun smartInput(value: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.takeIf { it.isEditable }
        val target = focused ?: findEditable(root) ?: return false
        val args = Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value) }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    private fun findEditable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isEditable && node.isVisibleToUser) return node
        for (i in 0 until node.childCount) node.getChild(i)?.let { findEditable(it)?.also { found -> return found } }
        return null
    }

    /**
     * فرستادن یک ضربهٔ واقعی به مختصات صفحه.
     *
     * برگرداندن true یعنی «سیستم ضربه را پذیرفت». نتیجهٔ پایانی
     * (onCompleted/onCancelled) در callback می‌آید و عمداً انتظارش کشیده
     * نمی‌شود: ScreenTaskRunner گام‌ها را روی Handler نخ اصلی اجرا می‌کند،
     * پس بلاک کردن اینجا با CountDownLatch نخ اصلی را می‌خواباند و خودِ
     * callback هم روی همان لوپر تحویل داده می‌شود — یعنی بن‌بست.
     */
    private fun tap(x: Float, y: Float): Boolean = try {
        val path = Path().apply { moveTo(x, y) }
        val stroke = GestureDescription.StrokeDescription(path, 0, 80)
        dispatchGesture(GestureDescription.Builder().addStroke(stroke).build(), null, null)
    } catch (e: Exception) { false }

    // ---- اجرای گام‌های برنامه کنترل صفحه (توسط ScreenTaskRunner) ----

    /** یک گام را دقیقاً یک بار اجرا می‌کند؛ تکرار و انتظار بر عهده ScreenTaskRunner است. */
    fun performStep(step: ScreenStep): Boolean = when (step.type) {
        "launch", "wait" -> true
        "tap_text" -> tapOnce(step.payload)
        "tap_id" -> tapById(step.payload)
        "input_text" -> smartInput(step.payload)
        "ime_enter", "submit" -> imeEnter(step.payload)
        "long_click" -> longClickOnce(step.payload)
        "tap_xy" -> step.payload.split(',').mapNotNull { it.trim().toFloatOrNull() }
            .takeIf { it.size == 2 }?.let { tap(it[0], it[1]); true } ?: false
        "swipe" -> swipe(step.payload)
        "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
        "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
        "recents" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
        "notifications" -> performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS)
        "quick_settings" -> performGlobalAction(GLOBAL_ACTION_QUICK_SETTINGS)
        "power_dialog" -> performGlobalAction(GLOBAL_ACTION_POWER_DIALOG)
        "lock_screen" -> lockScreen()
        "screenshot" -> screenshot()
        "scroll" -> scrollRoot(step.payload)
        // --- پوشش کامل کنش‌های گره (مرحلهٔ ۲۳) ---
        "focus" -> nodeAction(step.payload, AccessibilityNodeInfo.ACTION_FOCUS)
        "a11y_focus" -> nodeAction(step.payload, AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS)
        "next_node" -> movement(step.payload, true)
        "prev_node" -> movement(step.payload, false)
        "select_text" -> selectText(step.payload)
        "select_all" -> selectAll(step.payload)
        "copy" -> nodeAction(step.payload, AccessibilityNodeInfo.ACTION_COPY)
        "cut" -> nodeAction(step.payload, AccessibilityNodeInfo.ACTION_CUT)
        "paste" -> nodeAction(step.payload, AccessibilityNodeInfo.ACTION_PASTE)
        "clear_text" -> clearText(step.payload)
        "append_text" -> appendText(step.payload)
        "expand" -> nodeAction(step.payload, AccessibilityNodeInfo.ACTION_EXPAND)
        "collapse" -> nodeAction(step.payload, AccessibilityNodeInfo.ACTION_COLLAPSE)
        "set_progress" -> setProgress(step.payload)
        "double_tap" -> doubleTap(step.payload)
        "pinch" -> pinch(step.payload)
        "drag" -> drag(step.payload)
        // --- پوشش کامل کنش‌های سراسری ---
        "dismiss_notifications" -> performGlobalAction(GLOBAL_ACTION_DISMISS_NOTIFICATION_PANEL)
        "split_screen" -> toggleSplitScreen()
        "headset_hook" -> headsetHook()
        "a11y_all_apps" -> a11yAllApps()
        "a11y_home" -> a11yNav(GLOBAL_ACTION_ACCESSIBILITY_HOME)
        "a11y_back" -> a11yNav(GLOBAL_ACTION_ACCESSIBILITY_BACK)
        "a11y_recents" -> a11yNav(GLOBAL_ACTION_ACCESSIBILITY_RECENTS)
        else -> false
    }

    // ---- گام‌های افزوده‌شده در مرحلهٔ ۲۲ ----

    /**
     * زدن کلید «ارسال/جست‌وجو» روی صفحه‌کلید مجازی.
     *
     * این گام پیش‌تر وجود نداشت و نتیجه‌اش این بود که هیچ‌کدام از سه رسپی
     * پیش‌فرض نمی‌توانستند یک جست‌وجو را «ارسال» کنند: کروم متن را تایپ
     * می‌کرد و هرگز جست‌وجو نمی‌کرد.
     *
     * ACTION_IME_ENTER در API 30 اضافه شده و minSdk ما ۲۶ است، پس برای
     * اندروید ۸ تا ۱۰ یک مسیر جایگزین لازم است. آن مسیر جایگزین عمداً
     * «هیوریستیک» است و صادقانه به‌عنوان چنین چیزی علامت‌گذاری شده: گره
     * کلیک‌پذیری را پیدا می‌کند که برچسبش یکی از واژه‌های رایج «ارسال»
     * باشد. این روی هر صفحه‌کلیدی جواب نمی‌دهد؛ برای آن دستگاه‌ها رسپی
     * باید به‌جای submit از tap_text با برچسب دقیق همان دکمه استفاده کند.
     */
    private fun imeEnter(query: String): Boolean {
        val root = rootInActiveWindow ?: return false
        if (Build.VERSION.SDK_INT >= 30) {
            val focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            if (focused != null && focused.performAction(AccessibilityNodeInfo.ACTION_IME_ENTER)) return true
            val editable = findEditable(root)
            if (editable != null && editable.performAction(AccessibilityNodeInfo.ACTION_IME_ENTER)) return true
        }
        val candidates = if (query.isNotBlank()) listOf(query) else SUBMIT_LABELS
        for (c in candidates) { if (tapOnce(c)) return true }
        return false
    }

    /** ضربهٔ طولانی؛ برای منوهای زمینه‌ای. */
    private fun longClickOnce(query: String): Boolean {
        val target = SmartSelector.find(rootInActiveWindow, query) ?: return false
        if (target.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK)) return true
        val rect = Rect()
        target.getBoundsInScreen(rect)
        if (rect.isEmpty) return false
        val x = rect.exactCenterX(); val y = rect.exactCenterY()
        if (x <= 0f || y <= 0f) return false
        return pressAt(x, y, LONG_PRESS_MS)
    }

    /** ضربه با مدت دلخواه؛ همان مسیر tap با مدت بلندتر. */
    private fun pressAt(x: Float, y: Float, durationMs: Long): Boolean = try {
        val path = Path().apply { moveTo(x, y) }
        val stroke = GestureDescription.StrokeDescription(path, 0, durationMs)
        dispatchGesture(GestureDescription.Builder().addStroke(stroke).build(), null, null)
    } catch (e: Exception) { false }

    /**
     * کشیدن انگشت.
     *
     * دو قالب payload:
     *   "up" | "down" | "left" | "right"   — کشیدن جهت‌دار روی کل صفحه
     *   "x1,y1,x2,y2[,durationMs]"         — کشیدن بین دو مختصات
     *
     * چرا لازم است: scrollRoot فقط روی گرهی کار می‌کند که isScrollable باشد.
     * فهرست‌های Compose، اسلایدرها، کاروسل‌ها و جابه‌جایی با drag هیچ‌کدام
     * آن پرچم را ندارند، پس پیش از این کاملاً دست‌نیافتنی بودند.
     */
    private fun swipe(payload: String): Boolean {
        val parts = payload.split(',').map { it.trim() }
        val w = resources.displayMetrics.widthPixels.toFloat()
        val h = resources.displayMetrics.heightPixels.toFloat()
        if (w <= 0f || h <= 0f) return false
        val x1: Float; val y1: Float; val x2: Float; val y2: Float
        var dur = SWIPE_MS
        when (parts.size) {
            1 -> when (parts[0]) {
                "up"    -> { x1 = w / 2; y1 = h * 0.75f; x2 = w / 2; y2 = h * 0.25f }
                "down"  -> { x1 = w / 2; y1 = h * 0.25f; x2 = w / 2; y2 = h * 0.75f }
                "left"  -> { x1 = w * 0.85f; y1 = h / 2; x2 = w * 0.15f; y2 = h / 2 }
                "right" -> { x1 = w * 0.15f; y1 = h / 2; x2 = w * 0.85f; y2 = h / 2 }
                else -> return false
            }
            4, 5 -> {
                val n = parts.mapNotNull { it.toFloatOrNull() }
                if (n.size != parts.size) return false
                x1 = n[0]; y1 = n[1]; x2 = n[2]; y2 = n[3]
                if (parts.size == 5) dur = n[4].toLong()
            }
            else -> return false
        }
        if (dur < 1L) dur = 1L
        val path = Path().apply { moveTo(x1, y1); lineTo(x2, y2) }
        val stroke = GestureDescription.StrokeDescription(path, 0, dur)
        return dispatchGesture(GestureDescription.Builder().addStroke(stroke).build(), null, null)
    }

    /**
     * ضربه روی عنصر با شناسهٔ منبع (مثل com.android.chrome:id/url_bar).
     *
     * SmartSelector شناسه را فقط با وزن ۳۰ امتیاز می‌دهد، پس وقتی هم متن و
     * هم شناسه در صفحه باشند ممکن است عنصر دیگری برنده شود. این مسیر
     * تطبیق «دقیق» شناسه است و برای اپ‌هایی با متن تکراری قابل‌اتکاتر است.
     */
    private fun tapById(id: String): Boolean {
        if (id.isBlank()) return false
        val root = rootInActiveWindow ?: return false
        val target = findById(root, id) ?: return false
        val clickTarget = if (target.isClickable) target else findClickableUp(target)
        if (clickTarget != null && clickTarget.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
        val rect = Rect()
        target.getBoundsInScreen(rect)
        if (rect.isEmpty) return false
        return tap(rect.exactCenterX(), rect.exactCenterY())
    }

    private fun findById(node: AccessibilityNodeInfo, id: String): AccessibilityNodeInfo? {
        val own = node.viewIdResourceName
        if (own != null && (own == id || own.endsWith(":id/$id"))) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            findById(child, id)?.also { return it }
        }
        return null
    }

    private fun findClickableUp(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        var current = node
        while (current != null) {
            if (current.isClickable && current.isEnabled) return current
            current = current.parent
        }
        return null
    }

    // ---- پوشش کامل کنش‌های گره (مرحلهٔ ۲۳) ----

    /** یک کنش ساده روی گره‌ای که با متن پیدا شده. */
    private fun nodeAction(query: String, action: Int): Boolean {
        val target = SmartSelector.find(rootInActiveWindow, query) ?: return false
        return target.performAction(action)
    }

    /** حرکت به گره بعدی/پیشین در ترتیب دسترسی‌پذیری. */
    private fun movement(query: String, forward: Boolean): Boolean {
        val target = if (query.isBlank()) {
            rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)
        } else {
            SmartSelector.find(rootInActiveWindow, query)
        } ?: return false
        val action = if (forward) AccessibilityNodeInfo.ACTION_NEXT_AT_MOVEMENT
        else AccessibilityNodeInfo.ACTION_PREVIOUS_AT_MOVEMENT
        return target.performAction(action)
    }

    /**
     * انتخاب بخشی از متن.
     * payload: "start,end" — اگر خالی باشد، کل متن انتخاب می‌شود.
     */
    private fun selectText(payload: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val target = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: findEditable(root) ?: return false
        val len = target.text?.length ?: 0
        val parts = payload.split(',').mapNotNull { it.trim().toIntOrNull() }
        val start = if (parts.size == 2) parts[0].coerceIn(0, len) else 0
        val end = if (parts.size == 2) parts[1].coerceIn(start, len) else len
        val args = Bundle().apply {
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, start)
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, end)
        }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, args)
    }

    private fun selectAll(query: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val target = if (query.isBlank()) {
            root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: findEditable(root)
        } else SmartSelector.find(root, query) ?: return false
        val len = target.text?.length ?: 0
        val args = Bundle().apply {
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, 0)
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, len)
        }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, args)
    }

    /** خالی کردن فیلد؛ ACTION_SET_TEXT با رشتهٔ خالی. */
    private fun clearText(query: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val target = if (query.isBlank()) {
            root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.takeIf { it.isEditable } ?: findEditable(root)
        } else SmartSelector.find(root, query) ?: return false
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, "")
        }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    /** افزودن به انتهای متن موجود به‌جای جایگزینی آن. */
    private fun appendText(value: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val target = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.takeIf { it.isEditable }
            ?: findEditable(root) ?: return false
        val current = target.text?.toString() ?: ""
        val merged = if (current.isEmpty()) value else "$current $value"
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, merged)
        }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    /**
     * تنظیم مقدار یک لغزنده/نوار پیشرفت. payload یک عدد اعشاری است.
     * ACTION_SET_PROGRESS از API 24 است و minSdk ما ۲۶، پس نگهبان نمی‌خواهد.
     */
    private fun setProgress(payload: String): Boolean {
        val value = payload.trim().toFloatOrNull() ?: return false
        val root = rootInActiveWindow ?: return false
        val target = findRangeInfo(root) ?: return false
        val args = Bundle().apply {
            putFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE_FLOAT, value)
        }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_PROGRESS, args)
    }

    private fun findRangeInfo(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val ri = node.rangeInfo
        if (ri != null && node.isVisibleToUser) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            findRangeInfo(child)?.also { return it }
        }
        return null
    }

    // ---- ژست‌های پیشرفته ----

    /** دوبار ضربهٔ سریع روی یک عنصر. */
    private fun doubleTap(query: String): Boolean {
        val target = SmartSelector.find(rootInActiveWindow, query) ?: return false
        val rect = Rect()
        target.getBoundsInScreen(rect)
        if (rect.isEmpty) return false
        val x = rect.exactCenterX(); val y = rect.exactCenterY()
        if (x <= 0f || y <= 0f) return false
        if (!pressAt(x, y, 60L)) return false
        main.postDelayed({ pressAt(x, y, 60L) }, 90)
        return true
    }

    /**
     * نیشگون (بزرگ‌نمایی/کوچک‌نمایی) با دو انگشت.
     * payload: "in" یا "out".
     * ژست چندانگشتی از API 26 پشتیبانی می‌شود که همان minSdk ماست.
     */
    private fun pinch(payload: String): Boolean {
        val w = resources.displayMetrics.widthPixels.toFloat()
        val h = resources.displayMetrics.heightPixels.toFloat()
        if (w <= 0f || h <= 0f) return false
        val cx = w / 2; val cy = h / 2
        val near = minOf(w, h) * 0.06f
        val far = minOf(w, h) * 0.35f
        val (r1, r2) = if (payload.trim() == "in") far to near else near to far
        val pA = Path().apply { moveTo(cx - r1, cy - r1); lineTo(cx - r2, cy - r2) }
        val pB = Path().apply { moveTo(cx + r1, cy + r1); lineTo(cx + r2, cy + r2) }
        val builder = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(pA, 0, PINCH_MS))
            .addStroke(GestureDescription.StrokeDescription(pB, 0, PINCH_MS))
        return dispatchGesture(builder.build(), null, null)
    }

    /**
     * کشیدن آرام یک عنصر به مختصات دیگر (drag).
     * payload: "x1,y1,x2,y2[,durationMs]" — مدت پیش‌فرض بلند است تا سامانه
     * آن را «کشیدن» ببیند نه «ضربه».
     */
    private fun drag(payload: String): Boolean {
        val n = payload.split(',').map { it.trim().toFloatOrNull() }.takeIf { it.all { v -> v != null } }
            ?.mapNotNull { it } ?: return false
        if (n.size < 4) return false
        val dur = if (n.size >= 5) n[4].toLong().coerceAtLeast(1L) else DRAG_MS
        val path = Path().apply { moveTo(n[0], n[1]); lineTo(n[2], n[3]) }
        val stroke = GestureDescription.StrokeDescription(path, 0, dur)
        return dispatchGesture(GestureDescription.Builder().addStroke(stroke).build(), null, null)
    }

    // ---- کنش‌های سراسری با نگهبان نسخه ----

    private fun toggleSplitScreen(): Boolean =
        if (Build.VERSION.SDK_INT >= 24) performGlobalAction(GLOBAL_ACTION_TOGGLE_SPLIT_SCREEN) else false

    private fun headsetHook(): Boolean =
        if (Build.VERSION.SDK_INT >= 26) performGlobalAction(GLOBAL_ACTION_KEYCODE_HEADSETHOOK) else false

    private fun a11yAllApps(): Boolean =
        if (Build.VERSION.SDK_INT >= 31) performGlobalAction(GLOBAL_ACTION_ACCESSIBILITY_ALL_APPS) else false

    private fun a11yNav(action: Int): Boolean =
        if (Build.VERSION.SDK_INT >= 31) performGlobalAction(action) else false

    // ---- خواندن صفحه ----

    /**
     * متن صفحه را به ترتیب خواندن بیرون می‌کشد.
     *
     * این برای سالمند مهم‌ترین قابلیت است: «چی روی صفحه است؟» باید با صدا
     * جواب داده شود. ما درخت گره‌ها را داریم، پس لازم نیست حدس بزنیم.
     *
     * سه نکتهٔ کیفی که عمداً رعایت شده:
     *  - فقط گره‌های isVisibleToUser؛ وگرنه متن پنهان هم خوانده می‌شود.
     *  - text بر contentDescription اولویت دارد، ولی اگر متن خالی بود
     *    توضیح جای آن را می‌گیرد (بسیاری از دکمه‌های تصویری فقط desc دارند).
     *  - تکرارهای «پیاپی» حذف می‌شوند؛ درخت اندروید پر از والد/فرزندی است
     *    که همان متن را دو بار حمل می‌کنند و بدون این، جمله دو بار خوانده
     *    می‌شد.
     *
     * طول خروجی کران دارد تا یک صفحهٔ شلوغ، صف گفتار را منفجر نکند.
     */
    fun readScreenText(): String {
        val root = rootInActiveWindow ?: return ""
        val out = StringBuilder()
        collectText(root, out)
        return dedupeConsecutive(out.toString()).trim()
    }

    private fun collectText(node: AccessibilityNodeInfo?, out: StringBuilder) {
        if (node == null || out.length >= SCREEN_TEXT_MAX) return
        if (node.isVisibleToUser) {
            val t = node.text?.toString()?.trim()
            val d = node.contentDescription?.toString()?.trim()
            val pick = when {
                !t.isNullOrEmpty() -> t
                !d.isNullOrEmpty() -> d
                else -> null
            }
            if (pick != null) {
                if (out.isNotEmpty()) out.append('\n')
                out.append(pick)
            }
        }
        for (i in 0 until node.childCount) collectText(node.getChild(i), out)
    }

    private fun dedupeConsecutive(input: String): String {
        val lines = input.split('\n')
        val sb = StringBuilder()
        var prev: String? = null
        for (raw in lines) {
            val line = raw.trim()
            if (line.isEmpty() || line == prev) continue
            if (sb.isNotEmpty()) sb.append('\n')
            sb.append(line)
            prev = line
        }
        val text = sb.toString()
        return if (text.length <= SCREEN_TEXT_MAX) text else text.substring(0, SCREEN_TEXT_MAX)
    }

    /** قفل کردن صفحه. GLOBAL_ACTION_LOCK_SCREEN از API 28 است و minSdk ما ۲۶. */
    private fun lockScreen(): Boolean =
        if (Build.VERSION.SDK_INT >= 28) performGlobalAction(GLOBAL_ACTION_LOCK_SCREEN) else false

    /**
     * گرفتن تصویر صفحه.
     *
     * انتخاب عمدی: از AccessibilityService.takeScreenshot() (API 30) استفاده
     * «نمی‌کنیم». آن API کاملاً بی‌صداست — نه اعلان، نه toast، نه هیچ
     * نشانه‌ای — که دقیقاً همان الگویی است که بدافزارهای جاسوس استفاده
     * می‌کنند. برای اپی که روی گوشی یک سالمند نصب می‌شود، تصویر گرفتنِ
     * بی‌صدا قابل توجیه نیست حتی با نیت خوب.
     *
     * GLOBAL_ACTION_TAKE_SCREENSHOT همان مسیر استاندارد سیستم است: تصویر در
     * گالری ذخیره می‌شود و کاربر پیش‌نمایشش را می‌بیند. از API 28 در دسترس است.
     */
    private fun screenshot(): Boolean =
        if (Build.VERSION.SDK_INT >= 28) performGlobalAction(GLOBAL_ACTION_TAKE_SCREENSHOT) else false

    /** آیا متن یا توضیح داده‌شده الان روی صفحه دیده می‌شود؟ برای تأیید انجام گام. */
    fun isTextVisible(query: String): Boolean {
        if (query.isBlank()) return true
        return containsText(rootInActiveWindow, SmartSelector.normalize(query))
    }

    private fun containsText(node: AccessibilityNodeInfo?, query: String): Boolean {
        if (node == null) return false
        val text = SmartSelector.normalize(node.text?.toString())
        val desc = SmartSelector.normalize(node.contentDescription?.toString())
        if ((text.isNotBlank() && text.contains(query)) || (desc.isNotBlank() && desc.contains(query))) return true
        for (i in 0 until node.childCount) node.getChild(i)?.let { if (containsText(it, query)) return true }
        return false
    }

    /** یک تلاش برای لمس؛ بدون زمان‌بندی داخلی تا تلاش‌های پشت‌سرهم روی هم تلنبار نشوند. */
    /**
     * ضربه روی عنصری که با متن/توضیحش پیدا شده.
     *
     * اگر ACTION_CLICK جواب نداد، به‌جای شکست، یک ضربهٔ واقعی با
     * dispatchGesture روی مرکز کادر همان عنصر فرستاده می‌شود. این دقیقاً
     * همان راه‌حل جایگزینی است که راهنمای رسمی سرویس دسترس‌پذیری اندروید
     * برای سرویس‌های غیرِ صفحه‌خوان توصیه می‌کند، چون بسیاری از اپ‌ها
     * ACTION_CLICK را درست پیاده‌سازی نکرده‌اند. بدون این fallback، چنین
     * عناصری ۶ بار تلاش ناموفق می‌خوردند و کل وظیفه شکست می‌خورد.
     */
    private fun tapOnce(query: String): Boolean {
        val target = SmartSelector.find(rootInActiveWindow, query) ?: return false
        if (target.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
        if (target.isClickable && target.parent?.isClickable == true &&
            target.parent.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
        val rect = Rect()
        target.getBoundsInScreen(rect)
        if (rect.isEmpty) return false
        val x = rect.exactCenterX()
        val y = rect.exactCenterY()
        if (x <= 0f || y <= 0f) return false
        return tap(x, y)
    }

    private fun scrollRoot(direction: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val action = if (direction == "up") AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        else AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
        return scrollNode(root, action)
    }

    private fun scrollNode(node: AccessibilityNodeInfo, action: Int): Boolean {
        if (node.isScrollable && node.performAction(action)) return true
        for (i in 0 until node.childCount) node.getChild(i)?.let { if (scrollNode(it, action)) return true }
        return false
    }
    // ──────────────────────────────────────────────────────────────────────
    //  بینایی روی اسکرین‌شات
    // ──────────────────────────────────────────────────────────────────────

    /**
     * گرفتن تصویر صفحه برای خوانده‌شدن با مدل بینایی.
     *
     * **چرا اصلاً لازم است؟** درخت گره‌های دسترس‌پذیری برای اپ‌های فلاتر،
     * بازی‌های canvas و برخی WebView ها یا خالی است یا بسیار نازک. در آن حالت
     * `readScreenText()` رشتهٔ خالی می‌دهد و سالمند هیچ کمکی نمی‌گیرد. خواندن
     * متن از روی پیکسل‌ها آخرین راه است.
     *
     * **سه قید حریم که عمداً گذاشته شده:**
     *  1. کلید `screenVision` **پیش‌فرض خاموش** است و هیچ کلید دیگری روشنش
     *     نمی‌کند.
     *  2. `takeScreenshot()` روی API 30 **کاملاً بی‌صداست** — نه اعلان، نه
     *     toast، نه اندیکاتور. پس خودمان **پیش از** گرفتن تصویر یک overlay
     *     نشان می‌دهیم. بی‌صدا بودنِ API مجوز بی‌صدا بودنِ ما نیست.
     *  3. تصویر روی دستگاه کوچک و فشرده می‌شود، هیچ فایلی روی دیسک نوشته
     *     نمی‌شود و تنها به‌صورت رشته در حافظه به پل داده می‌شود.
     *
     * زیر API 30 رشتهٔ خالی برمی‌گردانیم؛ عمداً به MediaProjection نمی‌افتیم
     * چون آن مسیر دیالوگ مجوز جدا می‌خواهد و بیرون از دامنهٔ این سرویس است.
     *
     * @return Base64 یک JPEG کوچک، یا رشتهٔ خالی در **هر** حالت خطا.
     */
    fun captureForVision(): String {
        if (!visionAllowed(this)) return ""
        if (Build.VERSION.SDK_INT < 30) return ""
        announceCapture()
        val done = CountDownLatch(1)
        val out = AtomicReference("")
        try {
            takeScreenshot(Display.DEFAULT_DISPLAY, mainExecutor,
                object : TakeScreenshotCallback {
                    override fun onSuccess(screenshot: TakeScreenshotCallback.ScreenshotResult) {
                        try { out.set(encodeForVision(screenshot)) } catch (e: Exception) { }
                        done.countDown()
                    }
                    override fun onFailure(errorCode: Int) {
                        // FLAG_SECURE همین‌جا می‌شکند؛ خطا را قورت می‌دهیم و
                        // رشتهٔ خالی می‌دهیم تا پل جاوااسکریپت استثنا نبیند.
                        done.countDown()
                    }
                })
        } catch (e: Exception) {
            return ""
        }
        try { done.await(VISION_TIMEOUT_MS, TimeUnit.MILLISECONDS) } catch (e: InterruptedException) { return "" }
        return out.get() ?: ""
    }

    /**
     * خواندن متن صفحه از راه بینایی: تصویر → سرور → متن.
     *
     * **حتماً باید از نخ پس‌زمینه صدا زده شود.** هم `captureForVision` با
     * `CountDownLatch` منتظر می‌ماند و هم این درخواست شبکه blocking است؛
     * صدا زدنش از نخ اصلی یعنی ANR. تنها فراخوانش در
     * `ScreenTaskRunner` است و آن‌جا روی یک executor تک‌نخی می‌نشیند.
     *
     * در **هر** حالت خطا رشتهٔ خالی برمی‌گرداند، نه استثنا — چون در
     * مسیر کنترل صفحه صدا زده می‌شود و یک استثنای نگرفته یعنی کارِ
     * سالمند نصفه‌کاره و بدون گزارش رها شود.
     *
     * توجه: این تابع هیچ قید حریم جدیدی اضافه نمی‌کند و نیازی هم ندارد؛
     * `captureForVision` خودش رضایت و API 30+ را چک می‌کند و سرور هم
     * `consent_granted('screen_vision')` را. دو لایه، هر دو لازم.
     *
     * @return متن خوانده‌شده، یا رشتهٔ خالی در هر حالت خطا.
     */
    fun readScreenViaVision(): String {
        val img = captureForVision()
        if (img.isBlank()) return ""
        // همان کلیدی که AppBridge.saveServerUrl می‌نویسد؛ منبع دوم حقیقت نساختیم.
        val base = getSharedPreferences("assistant", Context.MODE_PRIVATE)
            .getString("server_url", "")?.trim()?.trimEnd('/') ?: ""
        if (base.isEmpty()) return ""
        var conn: HttpURLConnection? = null
        return try {
            val body = JSONObject().put("image", img).toString().toByteArray(Charsets.UTF_8)
            conn = (URL("$base/api/screen/vision").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = VISION_HTTP_TIMEOUT_MS
                readTimeout = VISION_HTTP_TIMEOUT_MS
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
            conn.outputStream.use { it.write(body) }
            // 403 (رضایت)، 413 (بزرگ)، 429 (نرخ)، 502 (مدل) همه همین‌جا
            // رشتهٔ خالی می‌شوند. تفاوتشان برای «ادامهٔ کار» بی‌اهمیت است:
            // در هر چهار حالت ما متنی نداریم.
            if (conn.responseCode !in 200..299) return ""
            val raw = conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            JSONObject(raw).optString("text", "").trim()
        } catch (e: Exception) {
            ""
        } finally {
            try { conn?.disconnect() } catch (e: Exception) { }
        }
    }

    /**
     * نشانگر بصری پیش از گرفتن تصویر. اگر این نبود، سالمند هرگز نمی‌فهمید
     * که از صفحه‌اش تصویر گرفته شده است.
     */
    private fun announceCapture() {
        OverlayController.show(this, "دارم صفحه را می‌بینم", null)
        OverlayController.update("دارم صفحه را می‌بینم", "تصویر فقط برای خواندن متن است", 0, 0)
        main.postDelayed({ OverlayController.hide() }, VISION_INDICATOR_MS)
    }

    /** تبدیل ScreenshotResult به JPEG کوچک Base64. */
    private fun encodeForVision(screenshot: TakeScreenshotCallback.ScreenshotResult): String {
        val buffer = screenshot.hardwareBuffer
        val hardware = Bitmap.wrapHardwareBuffer(buffer, screenshot.colorSpace) ?: return ""
        // روی Bitmap سخت‌افزاری نمی‌توان مقیاس داد؛ اول باید نرم شود.
        val software = hardware.copy(Bitmap.Config.ARGB_8888, false)
        hardware.recycle()
        if (software == null) { buffer.close(); return "" }
        val w = if (software.width > VISION_MAX_W) VISION_MAX_W else software.width
        val scaled = if (w < software.width)
            Bitmap.createScaledBitmap(software, w, software.height * w / software.width, true)
        else software
        val bytes = ByteArrayOutputStream()
        scaled.compress(Bitmap.CompressFormat.JPEG, VISION_JPEG_Q, bytes)
        if (scaled !== software) scaled.recycle()
        software.recycle()
        buffer.close()
        return Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP)
    }

}
