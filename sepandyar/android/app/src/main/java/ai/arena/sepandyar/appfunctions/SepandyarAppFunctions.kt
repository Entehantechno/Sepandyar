package ai.arena.sepandyar.appfunctions

import androidx.appfunctions.AppFunctionDeclaration
import androidx.appfunctions.AppFunctionServiceEntryPoint
import androidx.appfunctions.AppFunctionSerializable
import android.app.appfunctions.AppFunctionService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * لایهٔ ۱ معماری چهارلایهٔ دستیارها: AppFunctions.
 *
 * این فایل اپ را به یک «سرور MCP روی‌دستگاهی» تبدیل می‌کند. یک عامل
 * دارای مجوز (Gemini یا دستیار OEM) فهرست این توابع را از AppSearch
 * می‌خواند، KDoc هر کدام را به‌عنوان توصیف ابزار به مدل می‌دهد، و تابع را
 * از طریق system_server با Binder صدا می‌زند.
 *
 * **چرا این لایه از لایهٔ ۴ (خراشیدن UI) بهتر است؟**
 *  - semantic است نه پیکسلی: تغییر طرح اپ، قرارداد را باطل نمی‌کند
 *  - خطای type-safe برمی‌گرداند، پس عامل می‌تواند خودش را اصلاح کند
 *  - از AccessibilityService استفاده نمی‌کند، پس مشمول سیاست
 *    دسترس‌پذیری Play (اجرایی ۲۸ ژانویهٔ ۲۰۲۶) و محدودیت
 *    Android 17 Advanced Protection نیست
 *
 * **قاعدهٔ ایمنی حاکم بر این فایل:**
 * هیچ تابعی کارِ بازگشت‌ناپذیر «انجام» نمی‌دهد. توابع یا فقط می‌خوانند،
 * یا یک درخواست را در «صف تأیید» می‌گذارند و شناسهٔ آن را برمی‌گردانند.
 * تصمیم نهایی با خودِ سالمند است — همان قاعده‌ای که در گام `confirm`
 * مسیر کنترل صفحه هم پاس داشته می‌شود. یک عامل اشتباه می‌کند؛ این
 * معماری کاری می‌کند که اشتباهش برگشت‌پذیر بماند.
 *
 * **سه دام مستند API که اینجا رعایت شده‌اند:**
 *  ۱. از alpha10 هر @AppFunctionDeclaration باید «داخل» کلاسی باشد که
 *     @AppFunctionServiceEntryPoint دارد و از AppFunctionService ارث
 *     می‌برد. بیرونِ آن ⇒ build سبز، صفر تابع ثبت‌شده.
 *  ۲. از alpha13 نام @AppFunction به @AppFunctionDeclaration تغییر کرد و
 *     نام قدیمی «کامپایل می‌شود» ولی KSP بی‌صدا XML خالی می‌سازد.
 *  ۳. از beta01 پارامتر isDescribedByKDoc مقدار پیش‌فرض ندارد و باید
 *     صریح نوشته شود.
 */
@AppFunctionServiceEntryPoint(
    serviceName = "SepandyarAppFunctionService",
    appFunctionXmlFileName = "sepandyar_app_functions"
)
abstract class SepandyarAppFunctions : AppFunctionService() {

    /**
     * Lists the medications the senior is due to take now or has missed today.
     *
     * Returns an empty list when nothing is due. Never returns medication
     * advice — only the senior's own recorded schedule.
     */
    @AppFunctionDeclaration(isDescribedByKDoc = true)
    suspend fun getMedicationsDue(): List<MedicationItem> = withContext(Dispatchers.IO) {
        val body = getJson("/api/medications")
        val arr = body.optJSONArray("items") ?: JSONArray()
        (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            MedicationItem(
                name = o.optString("name", ""),
                dose = o.optString("dose", ""),
                scheduledTime = o.optString("scheduled_time", ""),
                taken = o.optBoolean("taken_today", false)
            )
        }.filter { it.name.isNotBlank() && !it.taken }
    }

    /**
     * Reads the senior's most recent recorded blood pressure, blood sugar and
     * pulse.
     *
     * Returns null fields for measurements that have never been recorded, so
     * the agent can say what is missing instead of inventing a number.
     */
    @AppFunctionDeclaration(isDescribedByKDoc = true)
    suspend fun getLatestVitals(): LatestVitals = withContext(Dispatchers.IO) {
        val body = getJson("/api/vitals")
        val arr = body.optJSONArray("items") ?: JSONArray()
        var sys = -1; var dia = -1; var pulse = -1; var at = ""
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val bp = o.optJSONObject("blood_pressure")
            if (bp != null && sys < 0) {
                sys = bp.optInt("systolic", -1); dia = bp.optInt("diastolic", -1)
            }
            if (pulse < 0) pulse = o.optInt("pulse", -1)
            if (at.isBlank()) at = o.optString("measured_at", "")
        }
        LatestVitals(
            systolic = if (sys > 0) sys else null,
            diastolic = if (dia > 0) dia else null,
            pulse = if (pulse > 0) pulse else null,
            measuredAt = at.ifBlank { null }
        )
    }

    /**
     * Reads the senior's wallet balance in Iranian Rial.
     *
     * Read-only: this function can never spend, transfer or top up.
     */
    @AppFunctionDeclaration(isDescribedByKDoc = true)
    suspend fun getWalletBalance(): WalletBalance = withContext(Dispatchers.IO) {
        WalletBalance(balanceIrr = getJson("/api/wallet").optLong("balance", 0L))
    }

    /**
     * Queues a request for the caregiver to call the senior back.
     *
     * This does NOT place a phone call. It only enqueues a call request that
     * the senior can still cancel from the app, and returns the queue id so
     * the agent can tell the user how to undo it.
     *
     * @param reason A short phrase the senior gave for wanting the call.
     */
    @AppFunctionDeclaration(isDescribedByKDoc = true)
    suspend fun requestCaregiverCall(reason: String): EnqueuedAction =
        withContext(Dispatchers.IO) {
            val body = postJson(
                "/api/caregiver/call-request",
                JSONObject().put("reason", reason.take(200))
            )
            EnqueuedAction(
                id = body.optString("id", ""),
                summary = "درخواست تماس با مراقب",
                needsConfirmation = false,
                cancelHint = "از صفحهٔ اصلی سپندیار می‌توانید لغو کنید"
            )
        }

    /**
     * Queues a ride request so the senior can review the destination and fare
     * before anything is booked.
     *
     * IMPORTANT: this does NOT book a ride and does NOT spend money. It only
     * prepares the request and returns it for the senior's explicit approval
     * on screen. Never tell the user a ride has been booked.
     *
     * @param destination Where the senior wants to go, in their own words.
     */
    @AppFunctionDeclaration(isDescribedByKDoc = true)
    suspend fun requestTaxiRide(destination: String): EnqueuedAction =
        withContext(Dispatchers.IO) {
            if (destination.isBlank()) {
                // صادقانه: استثناهای type-safe خودِ AppFunctions (مثل
                // AppFunctionInvalidArgumentException) بهترند چون به عامل
                // می‌گویند «چرا» نشد و می‌تواند خودش را اصلاح کند. اما نام
                // و بستهٔ دقیقشان را برای beta01 راستی‌آزمایی نکرده‌ام و
                // import حدس‌زده خطای کامپایل می‌دهد. پس فعلاً از استثنای
                // استاندارد استفاده می‌شود و این یک شکاف ثبت‌شده است.
                throw IllegalArgumentException("destination must not be blank")
            }
            EnqueuedAction(
                id = "taxi-" + System.currentTimeMillis(),
                summary = "سفر به «${destination.take(120)}»",
                needsConfirmation = true,
                cancelHint = "تا وقتی روی صفحه تأیید نکنید، سفری ثبت نمی‌شود"
            )
        }

    // ---- HTTP ----
    // AppFunctionService یک Service است، پس SharedPreferences در دسترس است
    // حتی وقتی رابط اپ باز نیست — عامل می‌تواند اپِ بسته را بیدار کند.

    private fun serverUrl(ctx: android.content.Context): String =
        ctx.getSharedPreferences("assistant", android.content.Context.MODE_PRIVATE)
            .getString("server_url", "") ?: ""

    private suspend fun getJson(path: String): JSONObject {
        val ctx = applicationContext
        val base = serverUrl(ctx)
        if (base.isBlank()) return JSONObject()
        return try {
            val c = URL(base.trimEnd('/') + path).openConnection() as HttpURLConnection
            c.requestMethod = "GET"; c.connectTimeout = 6000; c.readTimeout = 6000
            val code = c.responseCode
            if (code in 200..299) JSONObject(c.inputStream.bufferedReader().use { it.readText() })
            else JSONObject()
        } catch (e: Exception) { JSONObject() }
    }

    private suspend fun postJson(path: String, body: JSONObject): JSONObject {
        val base = serverUrl(applicationContext)
        if (base.isBlank()) return JSONObject()
        return try {
            val c = URL(base.trimEnd('/') + path).openConnection() as HttpURLConnection
            c.requestMethod = "POST"; c.connectTimeout = 6000; c.readTimeout = 6000
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json")
            c.outputStream.use { it.write(body.toString().toByteArray()) }
            val code = c.responseCode
            val stream = if (code in 200..299) c.inputStream else c.errorStream
            if (stream != null) JSONObject(stream.bufferedReader().use { it.readText() }) else JSONObject()
        } catch (e: Exception) { JSONObject() }
    }
}

/** One medication the senior is due to take. */
@AppFunctionSerializable(isDescribedByKDoc = true)
data class MedicationItem(
    /** The medicine name as recorded for this senior. */
    val name: String,
    /** The dose, for example "one tablet". */
    val dose: String,
    /** The scheduled time of day, HH:MM in the device locale. */
    val scheduledTime: String,
    /** Whether it has already been taken today. */
    val taken: Boolean
)

/** The senior's most recent recorded vital signs. Null means never recorded. */
@AppFunctionSerializable(isDescribedByKDoc = true)
data class LatestVitals(
    /** Systolic blood pressure in mmHg, or null if never recorded. */
    val systolic: Int?,
    /** Diastolic blood pressure in mmHg, or null if never recorded. */
    val diastolic: Int?,
    /** Resting pulse in beats per minute, or null if never recorded. */
    val pulse: Int?,
    /** ISO-8601 timestamp of the reading, or null if never recorded. */
    val measuredAt: String?
)

/** The senior's wallet balance. */
@AppFunctionSerializable(isDescribedByKDoc = true)
data class WalletBalance(
    /** Current balance in Iranian Rial (IRR). */
    val balanceIrr: Long
)

/**
 * An action that has been queued but NOT executed. The senior must still
 * approve it on screen when needsConfirmation is true.
 */
@AppFunctionSerializable(isDescribedByKDoc = true)
data class EnqueuedAction(
    /** Identifier of the queued request, used to cancel it. */
    val id: String,
    /** A short Persian phrase describing what was queued, safe to read aloud. */
    val summary: String,
    /** True when the senior must explicitly approve before anything happens. */
    val needsConfirmation: Boolean,
    /** A Persian sentence telling the senior how to undo this. */
    val cancelHint: String
)
