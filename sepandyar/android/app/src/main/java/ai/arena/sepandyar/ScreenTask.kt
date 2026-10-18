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
        /** ساخت کار از JSON ارسالی رابط وب. در صورت JSON نامعتبر، null برمی‌گرداند. */
        fun parse(json: String): ScreenTask? = try {
            val o = JSONObject(json)
            val arr: JSONArray = o.optJSONArray("steps") ?: JSONArray()
            val steps = (0 until arr.length()).mapNotNull { i ->
                val s = arr.optJSONObject(i) ?: return@mapNotNull null
                val step = ScreenStep(
                    type = s.optString("type", ""),
                    payload = s.optString("payload", ""),
                    expect = s.optString("expect", ""),
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
