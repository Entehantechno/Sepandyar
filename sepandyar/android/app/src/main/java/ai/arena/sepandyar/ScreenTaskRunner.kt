package ai.arena.sepandyar

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.os.SystemClock

/**
 * هماهنگ‌کننده کنترل اپ مقصد.
 *
 * ترتیب اجرا:
 * ۱) پاپ‌آپ کوچک سپندیار روی صفحه می‌آید.
 * ۲) اپ تأییدشده باز می‌شود (اپ سپندیار به پس‌زمینه می‌رود).
 * ۳) گام‌ها یکی‌یکی با سرویس دسترس‌پذیری اجرا می‌شوند و پیشرفت روی پاپ‌آپ می‌نشیند.
 * ۴) در پایان (موفق، ناموفق یا لغو کاربر) پاپ‌آپ حذف و اپ سپندیار تمام‌صفحه برمی‌گردد.
 */
object ScreenTaskRunner {
    private val main = Handler(Looper.getMainLooper())

    private var task: ScreenTask? = null
    private var appContext: Context? = null
    private var index = 0
    private var cancelled = false
    private var startedAt = 0L

    var running: Boolean = false
        private set

    /** نتیجه هر کار به رابط وب برمی‌گردد تا روی صفحه و در سرور ثبت شود. */
    var onResult: ((ScreenTaskResult) -> Unit)? = null

    /**
     * @param launch تنها راه باز کردن اپ؛ MainActivity آن را به فهرست اپ‌های
     *               تأییدشده گره می‌زند تا از بیرون نتوان اپ دلخواه باز کرد.
     */
    fun start(context: Context, planJson: String, launch: (String) -> Boolean): Boolean {
        if (running) return false
        val parsed = ScreenTask.parse(planJson) ?: return false
        val app = context.applicationContext
        appContext = app
        main.post {
            if (parsed.packageName.isNotBlank() && !launch(parsed.packageName)) {
                onResult?.invoke(
                    ScreenTaskResult(
                        taskId = parsed.id,
                        packageName = parsed.packageName,
                        title = parsed.title,
                        status = "failed",
                        stepsTotal = parsed.steps.size,
                        stepsDone = 0,
                        error = "این اپ در فهرست تأییدشده نیست یا نصب نشده است"
                    )
                )
                return@post
            }
            task = parsed
            index = 0
            cancelled = false
            running = true
            startedAt = SystemClock.elapsedRealtime()
            OverlayController.show(app, "سپندیار در حال انجام کار") { cancel() }
            OverlayController.update("در حال باز کردن اپ", parsed.title, 0, parsed.steps.size.coerceAtLeast(1))
            main.postDelayed({ runStep() }, 1400)
        }
        return true
    }

    fun cancel() {
        if (!running) return
        cancelled = true
        OverlayController.update("در حال لغو", "", index, task?.steps?.size?.coerceAtLeast(1) ?: 1)
        finish("cancelled", "")
    }

    private fun runStep() {
        val current = task ?: return
        if (cancelled) return
        if (index >= current.steps.size) {
            finish("done", "")
            return
        }
        val step = current.steps[index]
        val svc = ScreenControlService.instance
        if (svc == null) {
            finish("failed", "سرویس کنترل صفحه فعال نیست؛ از تنظیمات، دسترسی دسترس‌پذیری را روشن کنید")
            return
        }
        OverlayController.update(labelFor(step), step.payload, index, current.steps.size)
        attempt(step, svc, SystemClock.elapsedRealtime() + step.timeoutMs, 0)
    }

    private fun attempt(step: ScreenStep, svc: ScreenControlService, deadline: Long, tries: Int) {
        if (cancelled) return
        svc.performStep(step)
        val satisfied = if (step.expect.isBlank()) {
            step.type == "wait" || step.type == "launch" || svc.isTextVisible(step.payload)
        } else {
            svc.isTextVisible(step.expect)
        }
        if (satisfied) {
            index += 1
            main.postDelayed({ runStep() }, 550)
            return
        }
        if (step.type == "wait") {
            index += 1
            main.postDelayed({ runStep() }, 350)
            return
        }
        if (SystemClock.elapsedRealtime() < deadline && tries < 6) {
            OverlayController.update("در جست‌وجوی «${step.payload}»", "تلاش ${tries + 1}", index, task?.steps?.size?.coerceAtLeast(1) ?: 1)
            main.postDelayed({ attempt(step, svc, deadline, tries + 1) }, 650)
            return
        }
        finish("failed", "«${step.payload}» روی صفحه پیدا نشد")
    }

    private fun finish(status: String, error: String) {
        val current = task ?: return
        val done = if (status == "done") current.steps.size else index
        val total = current.steps.size.coerceAtLeast(1)
        val elapsed = SystemClock.elapsedRealtime() - startedAt
        running = false
        val heading = when (status) {
            "done" -> "کار انجام شد"
            "cancelled" -> "لغو شد"
            else -> "کار ناتمام ماند"
        }
        OverlayController.update(heading, error, done, total)
        val result = ScreenTaskResult(
            taskId = current.id,
            packageName = current.packageName,
            title = current.title,
            status = status,
            stepsTotal = current.steps.size,
            stepsDone = done,
            error = error,
            durationMs = elapsed
        )
        // کمی مکث تا سالمند نتیجه را روی پاپ‌آپ ببیند، بعد بازگشت به اپ.
        main.postDelayed({
            OverlayController.hide()
            if (current.returnToApp) returnToApp()
            task = null
            onResult?.invoke(result)
        }, 1500)
    }

    private fun returnToApp() {
        val ctx = appContext ?: return
        try {
            val intent = Intent(ctx, MainActivity::class.java).apply {
                addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK or
                        Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or
                        Intent.FLAG_ACTIVITY_SINGLE_TOP
                )
            }
            ctx.startActivity(intent)
        } catch (e: Exception) {
            // اگر بازگشت ممکن نشد، پاپ‌آپ همچنان حذف شده و کاربر دستی برمی‌گردد
        }
    }

    private fun labelFor(step: ScreenStep): String = when (step.type) {
        "launch" -> "باز کردن اپ"
        "tap_text" -> "لمس کردن"
        "input_text" -> "وارد کردن متن"
        "tap_xy" -> "لمس نقطه"
        "scroll" -> "پیمایش صفحه"
        "back" -> "بازگشت"
        "home" -> "صفحه اصلی"
        "recents" -> "اپ‌های اخیر"
        "wait" -> "کمی صبر کنید"
        else -> "در حال اجرا"
    }
}
