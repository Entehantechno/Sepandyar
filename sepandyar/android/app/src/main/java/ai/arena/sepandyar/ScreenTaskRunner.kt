package ai.arena.sepandyar

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import java.util.concurrent.Executors

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

    /**
     * نخِ خواندن با بینایی.
     *
     * چرا جدا؟ `captureForVision` با `CountDownLatch` منتظر می‌ماند و
     * `readScreenViaVision` یک درخواست شبکهٔ blocking است. `attempt()` روی
     * نخ اصلی اجرا می‌شود؛ صدا زدن مستقیم یعنی ANR. عمداً «تک‌نخی» است تا
     * هرگز دو تصویر هم‌زمان از صفحهٔ سالمند گرفته نشود.
     */
    private val worker = Executors.newSingleThreadExecutor { r ->
        Thread(r, "sepandyar-vision").apply { isDaemon = true }
    }

    /**
     * گام‌هایی که بدون گره‌های درختِ دسترس‌پذیری هیچ معنا ندارند.
     *
     * گام‌های سراسری (back/home/scroll/tap_xy/…) عمداً اینجا نیستند: آن‌ها
     * به درخت نیاز ندارند و خالی بودنش برای‌شان «خرابی» نیست. اگر این تفکیک
     * نبود، یک «home» ساده روی اپی با درخت نازک به‌اشتباه «نمی‌بینم» می‌گرفت.
     */
    private val NEEDS_TREE = setOf(
        "tap_text", "tap_id", "input_text", "ime_enter", "submit", "long_click",
        "focus", "a11y_focus", "next_node", "prev_node", "select_text", "select_all",
        "copy", "cut", "paste", "clear_text", "append_text", "expand", "collapse",
        "set_progress", "double_tap"
    )

    /**
     * در چندمین تلاش، خوانایی درخت سنجیده شود.
     *
     * نه در تلاش صفر: میانِ جابه‌جایی صفحه `rootInActiveWindow` می‌تواند
     * موقتاً null باشد و درخت خالی به‌نظر برسد. یک تلاش صبر می‌کنیم.
     */
    private const val READABILITY_PROBE_AT = 1

    /**
     * سقف خواندن‌های بینایی در **یک کار**.
     *
     * چرا کران دارد؟ هر فراخوانی یک تصویر از صفحهٔ سالمند به سرور می‌فرستد
     * که می‌تواند پیامک و موجودی بانکی داشته باشد، و سرور هم
     * `/api/screen/vision` را به ۶ بار در ۶۰ ثانیه محدود کرده. بدون این کران
     * یک کار با چهار گامِ نشدنی، چهار تصویر بی‌فایده می‌فرستاد.
     */
    private const val MAX_VISION_READS = 2

    /**
     * پیامِ شکست وقتی درخت خوانا نیست.
     *
     * عمداً با «پیدا نشد» فرق دارد. «پیدا نشد» یعنی دکمه نیست — که دروغ است:
     * دکمه هست، ما نمی‌بینیمش. این پیام راه‌حل را می‌گوید، نه بن‌بست را.
     */
    private const val UNREADABLE_HINT =
        "متن این صفحه خوانده نمی‌شود. اگر در بخش حریم خصوصی «دیدن صفحه» را روشن کنید، می‌توانم صفحه را ببینم."

    /** شمارشگر خواندن‌های بیناییِ کارِ جاری. در start() صفر می‌شود. */
    private var visionReads = 0

    /**
     * برچسب‌هایی که ضربهٔ بینایی برایشان **هرگز** مجاز نیست.
     *
     * چرا؟ چون ضربهٔ بینایی «حدسِ مختصات» است. اگر مدل جای «پرداخت» را یک
     * سانتی‌متر جابه‌جا بدهد، پول سالمند رفته است و برگشتی نیست. الگو از
     * crew-helper#114: «SEND, payment, purchase, deletion, account, credential
     * and other high-risk/commit targets can never use visual coordinates».
     *
     * عمداً پهن است. ضربهٔ بینایی برای «ناوبری» است — پیدا کردن یک دسته،
     * یک تب، یک گزینه در فهرست — نه برای تعهد. اشتباهِ مثبت هزینه‌اش یک
     * گامِ ناموفق است؛ اشتباهِ منفی هزینه‌اش یک تراکنش بانکی.
     *
     * سرور هم همین فهرست را دارد و رد می‌کند. دو لایه، هر دو لازم: این یکی
     * از درخواستِ بی‌مصرف جلوگیری می‌کند، آن یکی جلوی دور زدن را می‌گیرد.
     */
    private val COMMIT_LABELS = setOf(
        "پرداخت", "ثبت سفارش", "ثبت و پرداخت", "تأیید نهایی", "تایید نهایی",
        "ارسال سفارش", "خرید", "واریز", "انتقال وجه", "برداشت", "تأیید", "تایید",
        "حذف", "ورود", "ثبت نام", "ثبت‌نام", "رمز", "گذرواژه", "کد تأیید",
        "کد تایید", "احراز هویت", "کارت بانکی", "شبا",
        "pay", "payment", "checkout", "place order", "order now", "confirm",
        "submit", "send", "buy", "purchase", "delete", "remove", "login",
        "log in", "sign in", "sign up", "password", "transfer", "withdraw",
        "otp", "verify", "save card"
    )

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
            visionReads = 0
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
        /*
         * ── درخت دسترس‌پذیری اصلاً خوانا هست؟ ──────────────────────────
         * اپ‌های فلاتر، بازی‌های canvas و صفحه‌های FLAG_SECURE هیچ گرهٔ
         * متنی بیرون نمی‌دهند. در آن حالت تلاشِ مجدد **قطعاً** بی‌فایده است،
         * چون همان درختی خالی است که performStep از آن گره پیدا می‌کند.
         *
         * پیش از این، شش بار تلاش می‌کردیم و ««X» پیدا نشد» می‌گفتیم —
         * پیامی که سالمند را به خطا می‌انداخت. حالا یک بار خوانایی سنجیده
         * می‌شود و اگر خالی بود، یا مسیر بینایی می‌رود یا صادقانه و
         * زودهنگام شکست می‌خورد.
         */
        if (step.type in NEEDS_TREE && tries == READABILITY_PROBE_AT &&
            svc.readScreenText().isBlank()
        ) {
            unreadableScreen(step, svc, deadline, tries)
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
     * درخت خالی است: یا با بینایی صفحه را می‌خوانیم، یا صادقانه می‌گوییم
     * که نمی‌بینیم.
     *
     * سه راهی که همه به «شکستِ صادقانه» ختم می‌شوند مگر آن یکی که واقعاً
     * متن می‌دهد — چون حدس زدن روی صفحه‌ای که ندیده‌ایم، همان باگی است که
     * در گام `confirm` عمداً بستیم («تأییدِ کور ممنوع»).
     */
    private fun unreadableScreen(step: ScreenStep, svc: ScreenControlService, deadline: Long, tries: Int) {
        // کران پر شده، یا رضایت نیست، یا چیزی برای مقایسه نداریم.
        if (visionReads >= MAX_VISION_READS || !ScreenControlService.visionAllowed(svc)) {
            finish("failed", UNREADABLE_HINT)
            return
        }
        if (step.expect.isBlank()) {
            // بدون expect هیچ معیاری برای سنجش متنِ بینایی نداریم. بینایی
            // «متن» می‌دهد نه «مختصات»؛ پس نمی‌تواند جای گره را برای ضربه بگیرد.
            finish("failed", UNREADABLE_HINT)
            return
        }
        visionReads += 1
        val total = task?.steps?.size?.coerceAtLeast(1) ?: 1
        /*
         * اگر گام یک «ضربه» است و برچسبش تعهدآور نیست، به‌جای فقط خواندن،
         * «عمل» می‌کنیم. این همان حلقهٔ بسته‌ای است که پیش از این نداشتیم:
         * می‌توانستیم بگوییم روی صفحه چیست، ولی نمی‌توانستیم رویش ضربه
         * بزنیم — یعنی کنترل صفحه دقیقاً در اپ‌های فلاتر و canvas ناقص
         * می‌ماند.
         */
        if (step.type == "tap_text" && step.payload.isNotBlank() && commitLabel(step.payload) == null) {
            OverlayController.update("دارم دکمه را پیدا می‌کنم", step.payload, index, total)
            tryVisualTap(step, svc, deadline, tries)
            return
        }
        OverlayController.update("دارم صفحه را می‌بینم", step.payload, index, total)
        worker.execute {
            // بیرون از نخ اصلی. هر خطا رشتهٔ خالی می‌دهد، نه استثنا.
            val seen = try { svc.readScreenViaVision() } catch (e: Exception) { "" }
            main.post {
                // در فاصلهٔ انتظار ممکن است سالمند لغو کرده یا کار تمام شده باشد.
                if (cancelled || !running) return@post
                if (seen.isBlank()) {
                    finish("failed", "نتوانستم متن این صفحه را بخوانم. کمی بعد دوباره تلاش کنید.")
                    return@post
                }
                if (textHas(seen, step.expect)) {
                    // وضعیتِ مورد انتظار گام روی صفحه هست؛ گام را جلو می‌بریم.
                    index += 1
                    main.postDelayed({ runStep() }, 550)
                } else {
                    // صادقانه: چه می‌خواستیم و چه دیدیم. سالمند می‌تواند
                    // خودش با همان راهنمایی ادامه دهد.
                    finish("failed", "«${step.payload}» پیدا نشد. روی صفحه دیدم: ${seen.take(180)}")
                }
            }
        }
    }

    /**
     * اگر برچسب یک کنش تعهدآور است، همان کلیدواژه را برمی‌گرداند وگرنه null.
     * برچسب خالی «تعهدآور» شمرده می‌شود (رشتهٔ خالی برمی‌گرداند) — ضربهٔ
     * بینایی بدون هدف مشخص یعنی ضربه به نقطهٔ تصادفی.
     */
    private fun commitLabel(label: String): String? {
        val t = label.lowercase().replace("\u200C", " ").trim()
        if (t.isEmpty()) return ""
        for (k in COMMIT_LABELS) if (k in t) return k
        return null
    }

    /**
     * ضربهٔ بینایی با «اجارهٔ یک‌بارمصرف».
     *
     * ترتیب، و چرا هر گام لازم است:
     *  ۱. اثرانگشتِ صفحه «پیش از» مکان‌یابی
     *  ۲. گرفتن مختصات از سرور (که خودش فهرست ممنوعه را چک می‌کند)
     *  ۳. اثرانگشتِ صفحه «پس از» مکان‌یابی
     *  ۴. ضربه **فقط** اگر دو اثرانگشت یکسان باشند
     *
     * بدون گام ۱ و ۳، مختصاتی که برای صفحهٔ دو ثانیه پیش محاسبه شده روی
     * صفحهٔ امروز می‌نشیند. این دقیقاً همان باگی است که در منابع بررسی‌شده
     * به «tapping during the animation hits the wrong coordinates» معروف است.
     *
     * و پس از ضربه، گام «دوباره» با همان attempt سنجیده می‌شود — یعنی
     * اثرِ ضربه راستی‌آزمایی می‌شود، نه اینکه فرض شود کار کرد.
     */
    private fun tryVisualTap(step: ScreenStep, svc: ScreenControlService, deadline: Long, tries: Int) {
        worker.execute {
            val before = try { svc.screenFingerprint() } catch (e: Exception) { "" }
            val point = try { svc.locateViaVision(step.payload) } catch (e: Exception) { null }
            val after = try { svc.screenFingerprint() } catch (e: Exception) { "" }
            main.post {
                if (cancelled || !running) return@post
                if (point == null) {
                    finish("failed", "دکمهٔ «${step.payload}» را روی صفحه پیدا نکردم.")
                    return@post
                }
                // اجاره باطل شد: صفحه در فاصلهٔ مکان‌یابی عوض شده است.
                if (before != after) {
                    finish("failed", "صفحه هنگام پیدا کردن «${step.payload}» عوض شد؛ دوباره تلاش کنید.")
                    return@post
                }
                if (!svc.visualTap(point.x, point.y)) {
                    finish("failed", "ضربه به «${step.payload}» پذیرفته نشد.")
                    return@post
                }
                // راستی‌آزمایی اثر: همان گام دوباره سنجیده می‌شود. tries+1
                // یعنی دروازهٔ خوانایی (که فقط در READABILITY_PROBE_AT است)
                // دوباره فعال نمی‌شود و حلقهٔ بی‌پایان نمی‌سازد.
                main.postDelayed({ attempt(step, svc, deadline, tries + 1) }, 800)
            }
        }
    }

    /**
     * مقایسهٔ متنِ بینایی با `expect` — با همان نرمال‌سازیِ گره‌ها.
     *
     * چرا `SmartSelector.normalize` و نه `contains` ساده؟ مدل بینایی متن را
     * از پیکسل می‌خواند و بی‌نهایت تغییر شکل می‌دهد: «ی» عربی به‌جای فارسی،
     * رقم عربی به‌جای فارسی، نیم‌فاصلهٔ از دست رفته. اگر گره‌ها را
     * نرمال‌سازی می‌کردیم ولی این مقایسه را نه، یک صفحهٔ درست «پیدا نشد»
     * می‌گرفت.
     */
    private fun textHas(haystack: String, needle: String): Boolean {
        val h = SmartSelector.normalize(haystack)
        val n = SmartSelector.normalize(needle)
        return n.isNotEmpty() && h.contains(n)
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
