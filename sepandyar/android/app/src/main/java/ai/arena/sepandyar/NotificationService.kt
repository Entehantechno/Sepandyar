package ai.arena.sepandyar

import android.app.Notification
import android.content.Context
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONArray
import org.json.JSONObject

/**
 * خواندن و ادارهٔ اعلان‌ها.
 *
 * چرا لازم است: برای سالمند، اعلان یعنی «پیامی از پسرم آمده» یا «یادآوری
 * دارو». بدون این سرویس، سپندیار نمی‌توانست بگوید چه اعلانی آمده، آن را
 * بخواند یا بازش کند.
 *
 * ── حریم خصوصی ────────────────────────────────────────────────────────
 * این سرویس می‌تواند محتوای پیامک‌ها و پیام‌های خصوصی را ببیند، پس
 * «پیش‌فرض خاموش» است و سه لایه دارد:
 *   ۱) کاربر باید در تنظیمات اندروید دسترسی Notification را بدهد.
 *   ۲) کلید «readNotifications» در SharedPreferences باید صریحاً روشن شود.
 *   ۳) هر متد عمومی، آن کلید را در زمان فراخوانی می‌سنجد — نه فقط در
 *      onNotificationPosted. یعنی حتی اگر دسترسی سیستمی باقی بماند، با
 *      خاموش کردن کلید، خواندن متوقف می‌شود.
 * هیچ اعلانی به سرور فرستاده نمی‌شود؛ فقط در حافظهٔ همین فرایند می‌ماند.
 *
 * ── چرا onNotificationPosted ذخیره نمی‌کند ────────────────────────────
 * پیش‌نویس این کد اعلان‌ها را در یک صف نگه می‌داشت. آن طراحی دو مشکل داشت:
 * صف با مرگ فرایند از دست می‌رفت و اعلان‌های حذف‌شده در آن می‌ماندند.
 * حالا مستقیماً از activeNotifications سامانه خوانده می‌شود که همیشه
 * وضعیت واقعی است.
 */
class NotificationService : NotificationListenerService() {

    data class Entry(
        val key: String,
        val app: String,
        val title: String,
        val text: String,
        val timeMs: Long
    )

    companion object {
        var instance: NotificationService? = null

        /** کلید رضایت محلی؛ پیش‌فرض «خاموش» است. */
        const val PREF_KEY = "readNotifications"
        private const val PREFS = "assistant"

        fun allowed(context: Context): Boolean =
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getBoolean(PREF_KEY, false)
    }

    override fun onListenerConnected() { instance = this }

    override fun onListenerDisconnected() {
        if (instance === this) instance = null
        super.onListenerDisconnected()
    }

    /**
     * فهرست اعلان‌های فعال.
     *
     * در هر سه حالت «اجازه نیست»، «دسترسی گرفته شده» و «خطای سامانه»
     * فهرست «خالی» برمی‌گردد نه استثنا: این متد از پل جاوااسکریپت صدا
     * زده می‌شود و یک استثنای نگرفته در نخ پل، WebView را در وضعیت
     * نامشخصی رها می‌کند.
     */
    fun snapshot(): List<Entry> {
        if (!allowed(this)) return emptyList()
        return try {
            val active = activeNotifications ?: return emptyList()
            active.mapNotNull { it.toEntry() }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun StatusBarNotification.toEntry(): Entry? = try {
        val n = notification ?: return null
        val ex = n.extras
        Entry(
            key = key,
            app = packageName ?: "",
            title = ex?.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim() ?: "",
            text = ex?.getCharSequence(Notification.EXTRA_TEXT)?.toString()?.trim() ?: "",
            timeMs = postTime
        )
    } catch (e: Exception) {
        null
    }

    /** حذف یک اعلان با کلیدش. */
    fun dismiss(key: String): Boolean {
        if (!allowed(this) || key.isBlank()) return false
        return try {
            cancelNotification(key)
            true
        } catch (e: Exception) {
            false
        }
    }

    /** باز کردن اعلان — همان کاری که لمس کردنش می‌کند. */
    fun open(key: String): Boolean {
        if (!allowed(this) || key.isBlank()) return false
        return try {
            val active = activeNotifications ?: return false
            val sbn = active.firstOrNull { it.key == key } ?: return false
            val pi = sbn.notification?.contentIntent ?: return false
            pi.send()   // ممکن است CanceledException بدهد؛ پایین گرفته می‌شود
            true
        } catch (e: Exception) {
            false
        }
    }

    /** پاک کردن همهٔ اعلان‌ها. */
    fun dismissAll(): Boolean {
        if (!allowed(this)) return false
        return try {
            cancelAllNotifications()
            true
        } catch (e: Exception) {
            false
        }
    }

    fun toJson(): String = JSONArray().apply {
        for (e in snapshot()) {
            put(JSONObject().apply {
                put("key", e.key)
                put("app", e.app)
                put("title", e.title)
                put("text", e.text)
                put("time_ms", e.timeMs)
            })
        }
    }.toString()
}
