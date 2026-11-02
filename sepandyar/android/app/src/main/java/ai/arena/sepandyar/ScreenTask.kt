package ai.arena.sepandyar

import org.json.JSONArray
import org.json.JSONObject

/**
 * مدل برنامه کنترل صفحه.
 * یک «کار» از یک اپ تأییدشده و فهرستی از گام‌ها تشکیل می‌شود؛ هر گام می‌تواند
 * یک نشانه انتظار (expect) داشته باشد تا اجرا فقط پس از دیدن آن در صفحه ادامه یابد.
 */
data class ScreenStep(
    val type: String,
    val payload: String = "",
    val expect: String = "",
    val timeoutMs: Long = 8000L
)

data class ScreenTask(
    val id: String,
    val title: String,
    val packageName: String,
    val steps: List<ScreenStep>,
    val returnToApp: Boolean = true
) {
    companion object {
        /** قالب پارامتر: `{{ destination }}`. فاصلهٔ اطراف نام مجاز است. */
        private val PARAM_RE = Regex("""\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}""")

        /**
         * نام‌هایی که این کار برای اجرا لازم دارد.
         *
         * رابط وب این را می‌خواند تا «پیش از» شروع، همان‌ها را از سالمند
         * بپرسد. بدون این، رسپی اسنپ فقط می‌توانست مقصد ثابتِ
         * «خیابان ولیعصر» را وارد کند و عملاً بی‌فایده بود.
         */
        fun requiredParams(planJson: String): Set<String> =
            PARAM_RE.findAll(planJson).map { it.groupValues[1] }.toSet()

        private fun fill(value: String, params: Map<String, String>): String =
            PARAM_RE.replace(value) { m -> params[m.groupValues[1]].orEmpty() }

        /** ساخت کار از JSON ارسالی رابط وب. در صورت JSON نامعتبر، null برمی‌گرداند. */
        fun parse(json: String): ScreenTask? = try {
            val o = JSONObject(json)
            // پارامترها از خودِ plan می‌آیند، نه از یک کانال جدا؛ وگرنه دو
            // منبع حقیقت می‌شد و فراموش کردن یکی بی‌صدا رسپی نیمه‌خالی می‌داد.
            val paramsObj = o.optJSONObject("params")
            val params = mutableMapOf<String, String>()
            paramsObj?.keys()?.forEach { k ->
                val v = paramsObj.optString(k, "").trim()
                if (v.isNotEmpty()) params[k] = v
            }
            /*
             * اگر یک پارامتر لازم مقدار «ندارد»، کل کار رد می‌شود (null).
             *
             * چرا fail-fast و نه «با قالب خام ادامه بده»: اگر {{destination}}
             * خالی بماند، input_text رشتهٔ خالی تایپ می‌کند، گام بعد روی
             * صفحهٔ اشتباه دنبال متن می‌گردد، تا timeout تلاش می‌کند و در
             * نهایت «شکست» می‌دهد — یعنی چند ثانیه کنترل گوشی سالمند را
             * بی‌دلیل در دست می‌گیریم. رد کردنِ زودهنگام هم سریع‌تر است هم
             * قابل توضیح.
             */
            val missing = requiredParams(json).filter { it !in params }
            if (missing.isNotEmpty()) null else {
            val arr: JSONArray = o.optJSONArray("steps") ?: JSONArray()
            val steps = (0 until arr.length()).mapNotNull { i ->
                val s = arr.optJSONObject(i) ?: return@mapNotNull null
                val step = ScreenStep(
                    type = s.optString("type", ""),
                    payload = fill(s.optString("payload", ""), params),
                    expect = fill(s.optString("expect", ""), params),
                    timeoutMs = s.optLong("timeout_ms", 8000L)
                )
                if (step.type.isBlank()) null else step
            }
            ScreenTask(
                id = o.optString("id", ""),
                title = o.optString("title", "کنترل اپ"),
                packageName = o.optString("package", ""),
                steps = steps,
                returnToApp = o.optBoolean("return_to_app", true)
            )
            }
        } catch (e: Exception) {
            null
        }
    }
}

/** نتیجه اجرای کار؛ هم به رابط وب برمی‌گردد و هم در سرور برای مراقب ثبت می‌شود. */
data class ScreenTaskResult(
    val taskId: String,
    val packageName: String,
    val title: String,
    val status: String,
    val stepsTotal: Int,
    val stepsDone: Int,
    val error: String = "",
    val durationMs: Long = 0L
) {
    fun toJson(): String = JSONObject().apply {
        put("task_id", taskId)
        put("package", packageName)
        put("title", title)
        put("status", status)
        put("steps_total", stepsTotal)
        put("steps_done", stepsDone)
        put("error", error)
        put("duration_ms", durationMs)
    }.toString()
}
