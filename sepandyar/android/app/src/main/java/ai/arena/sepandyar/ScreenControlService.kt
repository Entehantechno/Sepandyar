package ai.arena.sepandyar

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.os.Bundle
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityNodeInfo

class ScreenControlService : AccessibilityService() {
    companion object {
        var instance: ScreenControlService? = null
        var pendingAction: ScreenAction? = null

        /** مدت ضربهٔ طولانی؛ آستانهٔ سامانه معمولاً ~۵۰۰ms است. */
        const val LONG_PRESS_MS = 600L
        /** مدت یک کشیدن؛ کوتاه‌تر از این، سامانه آن را ضربه تفسیر می‌کند. */
        const val SWIPE_MS = 320L

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
}
