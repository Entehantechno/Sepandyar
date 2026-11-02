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
        // گام تأیید پیش از هر ضربهٔ تعهدآور: تصمیم با خودِ سالمند است.
        // عمداً از attempt() عبور نمی‌کند، چون performStep هیچ کاری برای آن
        // ندارد و ورود به حلقهٔ تلاش فقط تایم‌اوت بی‌مصرف می‌ساخت.
        if (step.type == "confirm") {
            askConfirm(step, current.steps.size)
            return
        }
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
        val acted = svc.performStep(step)
        /*
         * معیار موفقیت گام:
         *  - اگر «expect» داده شده، همان متن مرجع نهایی است.
         *  - در غیر این صورت نتیجهٔ واقعی performStep ملاک است.
         *
         * پیش‌تر نتیجهٔ performStep دور ریخته می‌شد و موفقیت فقط با
         * isTextVisible(step.payload) سنجیده می‌شد. دو پیامد اشتباه داشت:
         *  ۱) گام‌های scroll (پی‌لود «up»/«down») و tap_xy (پی‌لود «x,y»)
         *     هیچ‌گاه متنِ پی‌لود را روی صفحه ندارند، پس با اینکه درست
         *     اجرا شده بودند، ۶ بار تکرار و سپس «failed» می‌شدند.
         *  ۲) در tap_text، تپِ موفق معمولاً صفحه را عوض می‌کند و همان متن
         *     ناپدید می‌شود؛ پس موفقیت به‌شکل شکست گزارش می‌شد.
         */
        val satisfied = if (step.expect.isNotBlank()) {
            svc.isTextVisible(step.expect)
        } else {
            acted || step.type == "wait" || step.type == "launch"
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

    /**
     * گام «confirm»: اجرا را متوقف می‌کند تا سالمند صریحاً تأیید کند.
     *
     * سه تصمیم عمدی:
     *  - **تأییدِ کور ممنوع.** اگر `expect` داده شده ولی آن متن الان روی
     *    صفحه نیست، گام «شکست» می‌خورد. تأیید چیزی که هنوز نیامده — مثلاً
     *    مبلغی که هنوز محاسبه نشده — بی‌معناست.
     *  - **متن صفحه هم نشان داده می‌شود** تا سالمند بداند دارد چه چیزی را
     *    تأیید می‌کند، نه فقط یک جملهٔ کلی.
     *  - **تایم‌اوت ⇒ لغو**، نه ادامه. پیش‌فرض همیشه «نه» است.
     */
    private fun askConfirm(step: ScreenStep, total: Int) {
        val app = appContext ?: return
        val svc = ScreenControlService.instance
        if (step.expect.isNotBlank() && (svc == null || !svc.isTextVisible(step.expect))) {
            finish("failed", "پیش از تأیید، «${step.expect}» روی صفحه دیده نشد")
            return
        }
        OverlayController.update("نیازمند تأیید شما", step.payload, index, total.coerceAtLeast(1))
        // خواندن متن صفحه برای نشان دادن «چه چیزی» دارد تأیید می‌شود.
        // خطا اینجا مجاز است: نبودِ متن نباید جلوی خودِ تأیید را بگیرد.
        val onScreen = try { svc?.readScreenText()?.take(220) ?: "" } catch (e: Exception) { "" }
        val prompt = if (step.payload.isBlank()) "ادامهٔ این کار را تأیید می‌کنید؟" else step.payload
        val detail = if (onScreen.isBlank()) prompt else "$prompt\n\nروی صفحه: $onScreen"
        OverlayController.showConfirm(
            app, "تأیید شما لازم است", detail,
            if (step.timeoutMs > 0) step.timeoutMs else 45000L
        ) { approved ->
            // اگر در فاصلهٔ انتظار لغو شده باشد، ادامه نمی‌دهیم.
            if (cancelled) return@showConfirm
            if (approved) {
                index += 1
                main.postDelayed({ runStep() }, 500)
            } else {
                finish("cancelled", "سالمند تأیید نکرد")
            }
        }
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
        "tap_id" -> "لمس کردن"
        "ime_enter", "submit" -> "ارسال کردن"
        "confirm" -> "نیازمند تأیید شما"
        "long_click" -> "نگه‌داشتن انگشت"
        "swipe" -> "کشیدن صفحه"
        "notifications" -> "اعلان‌ها"
        "quick_settings" -> "تنظیمات سریع"
        "power_dialog" -> "گزینه‌های خاموش کردن"
        "lock_screen" -> "قفل کردن صفحه"
        "screenshot" -> "گرفتن تصویر صفحه"
        "focus", "a11y_focus" -> "انتخاب کردن"
        "next_node", "prev_node" -> "رفتن به مورد بعدی"
        "select_text", "select_all" -> "انتخاب متن"
        "copy" -> "کپی کردن"
        "cut" -> "بریدن"
        "paste" -> "چسباندن"
        "clear_text" -> "پاک کردن متن"
        "append_text" -> "افزودن متن"
        "expand" -> "باز کردن فهرست"
        "collapse" -> "بستن فهرست"
        "set_progress" -> "تنظیم لغزنده"
        "double_tap" -> "دو بار لمس"
        "pinch" -> "بزرگ‌نمایی"
        "drag" -> "جابه‌جا کردن"
        "dismiss_notifications" -> "بستن اعلان‌ها"
        "split_screen" -> "تقسیم صفحه"
        "headset_hook" -> "دکمهٔ هدفون"
        "a11y_all_apps" -> "همهٔ برنامه‌ها"
        "a11y_home" -> "صفحه اصلی"
        "a11y_back" -> "بازگشت"
        "a11y_recents" -> "اپ‌های اخیر"
        "wait" -> "کمی صبر کنید"
        else -> "در حال اجرا"
    }
}
