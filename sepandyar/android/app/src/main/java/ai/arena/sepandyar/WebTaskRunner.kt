package ai.arena.sepandyar

import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.webkit.WebView
import org.json.JSONArray
import org.json.JSONObject

/**
 * موتور اجرای کار روی «نسخهٔ وب» یک سرویس، داخل WebView خودمان.
 *
 * **چرا این مسیر اصلاً وجود دارد؟** سه دلیل که هر سه از تحقیق مرحلهٔ ۲۴
 * آمدند:
 *  1. اپ‌های فلاتر درخت گرهٔ نازک یا خالی می‌دهند، پس مسیر دسترس‌پذیری
 *     روی همان اسنپ هم ممکن است چیزی پیدا نکند.
 *  2. سیاست Google Play (اجرایی از ۲۸ ژانویهٔ ۲۰۲۶) «دستیارهای
 *     ‹برای من انجامش بده›» را روی Accessibility API ممنوع کرد. این مسیر
 *     **اصلاً** از آن API استفاده نمی‌کند، پس مشمولش نمی‌شود.
 *  3. Android 17 Advanced Protection دسترسی‌پذیری را به ابزارهای
 *     تأییدشده محدود و sideloading را مسدود می‌کند. اینجا هیچ‌کدام لازم نیست.
 *
 * اسنپ و اسنپ‌فود نسخهٔ وب کامل دارند (`app.snapp.ir` و `food.snapp.ir`)
 * که عمداً برای کاربرانی ساخته شده که اپ ندارند. پس می‌توانیم همان را
 * داخل WebView خودمان باز کنیم و با DOM کار کنیم.
 *
 * **تفاوت کلیدی با ScreenTaskRunner:** اینجا سلکتور CSS داریم نه برچسب
 * فارسی، و «خواندن صفحه» یک `querySelector` است نه پیمایش درخت گره‌ها.
 * سریع‌تر و قابل اتکاتر است، ولی فقط برای سرویس‌هایی که نسخهٔ وب دارند.
 */
object WebTaskRunner {
    private val main = Handler(Looper.getMainLooper())

    private data class WebStep(
        val type: String,
        val payload: String = "",
        val value: String = "",
        val timeoutMs: Long = 8000L
    )

    private data class WebPlan(
        val id: String,
        val title: String,
        val url: String,
        val selectorsVerified: Boolean,
        val steps: List<WebStep>,
        val returnToApp: Boolean = true
    )

    /** فاصلهٔ دو تلاش در wait_css؛ کوتاه‌تر از این فقط CPU می‌سوزاند. */
    private const val POLL_MS = 350L
    /** سقف تلاش یک گام؛ مستقل از timeoutMs تا یک عدد بزرگ حلقهٔ بی‌پایان نسازد. */
    private const val MAX_TRIES = 60
    /** صفحهٔ خودمان، برای بازگشت در پایان کار. */
    const val HOME_URL = "file:///android_asset/index.html"

    var running: Boolean = false
        private set

    var onResult: ((ScreenTaskResult) -> Unit)? = null

    private var web: WebView? = null
    private var plan: WebPlan? = null
    private var index = 0
    private var cancelled = false
    private var startedAt = 0L

    /**
     * آیا سلکتورهای این رسپی روی دستگاه واقعی نگاشت شده‌اند؟
     *
     * **این پرچم تشریفاتی نیست.** من DOM اپ‌های اسنپ را ندیده‌ام و از این
     * محیط هم نمی‌توانم ببینم. پس هر سلکتوری که بنویسم حدس است — و حدسِ
     * بی‌صدا بدترین گزینه است: کار اجرا می‌شود، چیزی پیدا نمی‌شود، تا
     * timeout تلاش می‌کند و سالمند فقط می‌بیند «نشد».
     *
     * با `selectorsVerified=false` موتور **اجرا نمی‌کند** و نتیجهٔ صریح
     * «selectors_not_mapped» می‌دهد. به‌جایش گام `probe` هست تا
     * توسعه‌دهنده روی دستگاه واقعی DOM را ببیند و سلکتورها را پر کند.
     */
    private fun parse(json: String): WebPlan? = try {
        val o = JSONObject(json)
        val url = o.optString("url", "").trim()
        if (url.isBlank()) null else {
            val paramsObj = o.optJSONObject("params")
            val params = mutableMapOf<String, String>()
            paramsObj?.keys()?.forEach { k ->
                val v = paramsObj.optString(k, "").trim()
                if (v.isNotEmpty()) params[k] = v
            }
            val arr: JSONArray = o.optJSONArray("steps") ?: JSONArray()
            val steps = (0 until arr.length()).mapNotNull { i ->
                val s = arr.optJSONObject(i) ?: return@mapNotNull null
                val st = WebStep(
                    type = s.optString("type", ""),
                    payload = fill(s.optString("payload", ""), params),
                    value = fill(s.optString("value", ""), params),
                    timeoutMs = s.optLong("timeout_ms", 8000L)
                )
                if (st.type.isBlank()) null else st
            }
            WebPlan(
                id = o.optString("id", ""),
                title = o.optString("title", "کنترل وب"),
                url = url,
                selectorsVerified = o.optBoolean("selectors_verified", false),
                steps = steps,
                returnToApp = o.optBoolean("return_to_app", true)
            )
        }
    } catch (e: Exception) { null }

    private val PARAM_RE = Regex("""\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}""")
    private fun fill(v: String, params: Map<String, String>): String =
        PARAM_RE.replace(v) { m -> params[m.groupValues[1]].orEmpty() }

    fun start(webView: WebView, planJson: String): Boolean {
        if (running) return false
        val parsed = parse(planJson) ?: return false
        web = webView
        plan = parsed
        index = 0
        cancelled = false
        running = true
        startedAt = SystemClock.elapsedRealtime()
        main.post {
            if (!parsed.selectorsVerified) {
                // صریح و قابل ترجمه، نه یک «شکست» مبهم.
                finish("not_mapped", "سلکتورهای این سرویس هنوز روی دستگاه واقعی نگاشت نشده‌اند")
                return@post
            }
            OverlayController.show(webView.context, "سپندیار در حال انجام کار") { cancel() }
            OverlayController.update("باز کردن صفحه", parsed.title, 0, parsed.steps.size.coerceAtLeast(1))
            webView.webViewClient = ProxyingClient(webView.webViewClient)
            webView.loadUrl(parsed.url)
        }
        return true
    }

    /**
     * پس از هر ناوبری، هلپر DOM دوباره تزریق می‌شود.
     *
     * چرا لازم است: `evaluateJavascript` روی document فعلی اجرا می‌شود و با
     * هر بارگذاری صفحه از بین می‌رود. بدون این، گام دوم هیچ هلپری پیدا
     * نمی‌کرد و بی‌صدا شکست می‌خورد.
     */
    private class ProxyingClient(val inner: android.webkit.WebViewClient?) :
        android.webkit.WebViewClient() {
        override fun onPageFinished(view: WebView, url: String?) {
            inner?.onPageFinished(view, url)
            view.evaluateJavascript(HELPERS, null)
            if (running) main.postDelayed({ runStep() }, 400)
        }
    }

    private fun runStep() {
        val current = plan ?: return
        val wv = web ?: return finish("failed", "WebView در دسترس نیست")
        if (cancelled) return
        if (index >= current.steps.size) { finish("done", ""); return }
        val step = current.steps[index]
        OverlayController.update(labelFor(step), step.payload.take(40), index, current.steps.size)
        if (step.type == "confirm") { askConfirm(step, current.steps.size); return }
        if (step.type == "wait_ms") {
            index += 1
            main.postDelayed({ runStep() }, step.timeoutMs.coerceIn(0, 10000))
            return
        }
        // ناوبری با evaluateJavascript شدنی نیست — باید loadUrl صدا زده شود،
        // پس این گام هم از attempt() عبور نمی‌کند.
        //
        // **index را «پیش از» loadUrl جلو می‌بریم.** onPageFinished خودش
        // runStep() را صدا می‌زند؛ اگر index جلو نرفته باشد، همین گام goto
        // دوباره اجرا می‌شود و حلقهٔ بی‌پایان می‌سازد. این باگ را سنجش
        // «هر گام وب اسکریپت دارد» لو داد: goto هیچ شاخه‌ای در scriptFor
        // نداشت و else -> "false" تا timeout شکست می‌خورد.
        if (step.type == "goto") {
            index += 1
            val target = step.payload.trim()
            if (target.isBlank()) { finish("failed", "گام goto نشانی ندارد"); return }
            // start() همین نشانی را بار کرده؛ بارِ دوباره فقط هدر رفتن
            // زمان سالمند است.
            if (wv.url == target) { main.postDelayed({ runStep() }, 300); return }
            try { wv.loadUrl(target) }
            catch (e: Exception) { finish("failed", "باز کردن صفحه ممکن نشد") }
            return
        }
        attempt(wv, step, SystemClock.elapsedRealtime() + step.timeoutMs, 0)
    }

    private fun attempt(wv: WebView, step: WebStep, deadline: Long, tries: Int) {
        if (cancelled) return
        wv.evaluateJavascript(scriptFor(step)) { raw ->
            val ok = raw != null && raw.trim('"') == "true"
            if (ok) { index += 1; main.postDelayed({ runStep() }, 500); return@evaluateJavascript }
            if (SystemClock.elapsedRealtime() < deadline && tries < MAX_TRIES) {
                main.postDelayed({ attempt(wv, step, deadline, tries + 1) }, POLL_MS)
            } else {
                finish("failed", "«${step.payload}» روی صفحه پیدا نشد")
            }
        }
    }

    /**
     * اسکریپت هر گام. همه‌شان `true`/`false` برمی‌گردانند تا یک قرارداد واحد
     * برای موفقیت باشد.
     *
     * نکتهٔ مهم در `set_css`: **انتساب مستقیم `e.value` در React کار
     * نمی‌کند.** React 16+ مقدار را از setter بومی prototype می‌خواند، پس
     * باید همان را صدا زد و بعد رویداد `input` را با `bubbles:true` فرستاد.
     * بدون این، فرم اسنپ «خالی» می‌ماند و گام بعد مقصد را پیدا نمی‌کند.
     */
    private fun scriptFor(step: WebStep): String = when (step.type) {
        "wait_css" -> "!!(window.__sep&&window.__sep.has(${q(step.payload)}))"
        "click_css" -> "!!(window.__sep&&window.__sep.click(${q(step.payload)}))"
        "set_css" -> "!!(window.__sep&&window.__sep.set(${q(step.payload)},${q(step.value)}))"
        "read_css" -> "!!(window.__sep&&window.__sep.read(${q(step.payload)}))"
        "probe" -> "!!(window.__sep&&window.__sep.probe())"
        else -> "false"
    }

    /**
     * رشتهٔ جاوااسکریپت امن. سلکتور و مقدار از رسپی می‌آیند و اگر
     * بی‌محابا داخل اسکریپت گذاشته شوند، یک `'` ساده کل عبارت را می‌شکند
     * — و در بدترین حالت تزریق اسکریپت می‌شود. JSONObject.quote هر دو کار
     * را یک‌جا انجام می‌دهد.
     */
    private fun q(s: String): String = JSONObject.quote(s)

    private fun askConfirm(step: WebStep, total: Int) {
        val ctx = web?.context ?: return
        OverlayController.update("نیازمند تأیید شما", step.payload, index, total.coerceAtLeast(1))
        // برخلاف مسیر دسترس‌پذیری، اینجا متن صفحه را از خودِ DOM می‌خوانیم.
        val wv = web
        val finishConfirm: (String) -> Unit = { onScreen ->
            val prompt = if (step.payload.isBlank()) "ادامهٔ این کار را تأیید می‌کنید؟" else step.payload
            val detail = if (onScreen.isBlank()) prompt else "$prompt\n\nروی صفحه: $onScreen"
            OverlayController.showConfirm(ctx, "تأیید شما لازم است", detail,
                if (step.timeoutMs > 0) step.timeoutMs else 45000L) { approved ->
                if (cancelled) return@showConfirm
                if (approved) { index += 1; main.postDelayed({ runStep() }, 500) }
                else finish("cancelled", "سالمند تأیید نکرد")
            }
        }
        if (wv == null) { finishConfirm(""); return }
        wv.evaluateJavascript(
            "(window.__sep&&window.__sep.summary)?window.__sep.summary():''"
        ) { raw ->
            val text = raw?.trim('"')?.replace("\\n", "\n")?.take(220) ?: ""
            main.post { finishConfirm(text) }
        }
    }

    private fun labelFor(step: WebStep): String = when (step.type) {
        "goto" -> "باز کردن صفحه"
        "wait_ms", "wait_css" -> "کمی صبر کنید"
        "click_css" -> "لمس کردن"
        "set_css" -> "وارد کردن"
        "read_css" -> "خواندن صفحه"
        "confirm" -> "نیازمند تأیید شما"
        "probe" -> "بررسی ساختار صفحه"
        else -> "در حال انجام"
    }

    private fun finish(status: String, error: String) {
        val current = plan ?: return
        val done = if (status == "done") current.steps.size else index
        val total = current.steps.size.coerceAtLeast(1)
        running = false
        val heading = when (status) {
            "done" -> "کار انجام شد"
            "cancelled" -> "لغو شد"
            "not_mapped" -> "هنوز آماده نیست"
            else -> "کار ناتمام ماند"
        }
        OverlayController.update(heading, error, done, total)
        val result = ScreenTaskResult(
            taskId = current.id,
            packageName = current.url,
            title = current.title,
            status = status,
            stepsTotal = current.steps.size,
            stepsDone = done,
            error = error,
            durationMs = SystemClock.elapsedRealtime() - startedAt
        )
        val wv = web
        main.postDelayed({
            OverlayController.hide()
            // سالمند نباید روی صفحهٔ اسنپ رها شود؛ به اپ خودش برمی‌گردد.
            if (current.returnToApp) { try { wv?.loadUrl(HOME_URL) } catch (e: Exception) { } }
            plan = null
            web = null
            onResult?.invoke(result)
        }, 1500)
    }

    fun cancel() {
        if (!running) return
        cancelled = true
        finish("cancelled", "")
    }

    /**
     * هلپرهای DOM. یک‌بار در هر بارگذاری صفحه تزریق می‌شوند.
     *
     * `probe` عمداً اینجاست: من نمی‌توانم DOM اسنپ را ببینم، پس به‌جای
     * حدس زدن سلکتور، ابزاری می‌سازم که توسعه‌دهنده روی دستگاه واقعی
     * فهرست عنصرهای تعاملی را ببیند و سلکتور درست را انتخاب کند.
     */
    private val HELPERS = """
window.__sep = {
  has: function(s){ try{ return !!document.querySelector(s) }catch(e){ return false } },
  text: function(s){ try{ var e=document.querySelector(s); return e?((e.innerText||e.textContent||'').trim()):'' }catch(e){ return '' } },
  click: function(s){ try{ var e=document.querySelector(s); if(!e) return false; e.scrollIntoView({block:'center'}); e.click(); return true }catch(e){ return false } },
  set: function(s,v){
    try{
      var e=document.querySelector(s); if(!e) return false;
      e.scrollIntoView({block:'center'}); e.focus();
      // React 16+ مقدار را از setter بومی prototype می‌خواند؛ انتساب
      // مستقیم e.value وضعیت فرم را به‌روز نمی‌کند.
      var proto = (e.tagName==='TEXTAREA') ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
      var d = Object.getOwnPropertyDescriptor(proto,'value');
      if(d && d.set) d.set.call(e,v); else e.value=v;
      e.dispatchEvent(new Event('input',{bubbles:true}));
      e.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    }catch(e){ return false }
  },
  read: function(s){ try{ var t=this.text(s); return t.length>0 }catch(e){ return false } },
  summary: function(){ try{ return (document.body.innerText||'').replace(/\s+/g,' ').trim().slice(0,600) }catch(e){ return '' } },
  probe: function(){
    try{
      var out=[], sel='a,button,input,select,textarea,[role=button],[onclick]';
      var list=document.querySelectorAll(sel);
      for(var i=0;i<list.length && out.length<120;i++){
        var e=list[i];
        out.push({
          tag:e.tagName.toLowerCase(),
          id:e.id||'',
          cls:(e.className&&e.className.baseVal===undefined)?String(e.className).slice(0,60):'',
          type:e.getAttribute('type')||'',
          ph:e.getAttribute('placeholder')||'',
          txt:((e.innerText||e.value||'')+'').replace(/\s+/g,' ').trim().slice(0,40)
        });
      }
      console.log('SEPANDYAR_PROBE '+JSON.stringify({url:location.href,count:list.length,items:out}));
      return true;
    }catch(e){ return false }
  }
};
""".trimIndent()
}
