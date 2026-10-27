package ai.arena.sepandyar

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityNodeInfo

class ScreenControlService : AccessibilityService() {
    companion object {
        var instance: ScreenControlService? = null
        var pendingAction: ScreenAction? = null
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
        "input_text" -> smartInput(step.payload)
        "tap_xy" -> step.payload.split(',').mapNotNull { it.trim().toFloatOrNull() }
            .takeIf { it.size == 2 }?.let { tap(it[0], it[1]); true } ?: false
        "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
        "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
        "recents" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
        "scroll" -> scrollRoot(step.payload)
        else -> false
    }

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
