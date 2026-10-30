package ai.arena.sepandyar

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.net.Uri
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat

class MainActivity : Activity() {
    private lateinit var web: WebView
    override fun onResume() { super.onResume(); if (::web.isInitialized && !isAccessibilityEnabled()) web.postDelayed({ web.evaluateJavascript("toast('برای راه‌اندازی کامل، دسترسی کنترل صفحه را فعال کنید')", null) }, 500) }
    private fun isAccessibilityEnabled(): Boolean { val enabled = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false; return enabled.contains(packageName) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // دارایی‌ها را روی مبدأ https مجازی سرو می‌کنیم. بارگذاری از file:///android_asset
        // یک «مبدأ مات» است و fetch/getUserMedia/service worker را می‌بندد.
        val assetLoader = WebViewAssetLoader.Builder()
            .setDomain(WebViewAssetLoader.DEFAULT_DOMAIN)
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.allowFileAccessFromFileURLs = false
            settings.allowUniversalAccessFromFileURLs = false
            webViewClient = object : WebViewClientCompat() {
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                    assetLoader.shouldInterceptRequest(request.url)

                // سیاست ناوبری. addJavascriptInterface روی خودِ WebView ثبت می‌شود و با هر
                // ناوبری باقی می‌ماند؛ پس اگر صفحه به مبدأ بیگانه برود، آن مبدأ به همهٔ
                // ۱۶ متد بومی AppBridge دسترسی می‌گیرد (از جمله saveServerUrl که ماندگار
                // است و runScreenTask که کنترل صفحه را در دست می‌گیرد). فقط مبدأ
                // دارایی‌های خودِ اپ مجاز است.
                // توجه: این فقط ناوبری قاب اصلی را می‌گیرد؛ زیرمنابع مانند
                // <link> فونت از shouldInterceptRequest می‌گذرند و دست‌نخورده می‌مانند.
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val url = request.url ?: return true
                    if (url.scheme.equals("tel", ignoreCase = true)) {
                        // تماس را به dialer سیستم می‌سپاریم؛ کاربر آنجا تأیید می‌کند
                        startActivity(Intent(Intent.ACTION_DIAL, url))
                        return true
                    }
                    val sameOrigin = url.scheme.equals("https", ignoreCase = true) &&
                        url.host == WebViewAssetLoader.DEFAULT_DOMAIN
                    return !sameOrigin   // true یعنی ناوبری انجام نشود
                }
            }
            addJavascriptInterface(AppBridge(), "SepandyarNative")
            loadUrl("https://" + WebViewAssetLoader.DEFAULT_DOMAIN + "/assets/index.html")
        }
        setContentView(web)
        // نتیجه هر کار کنترل صفحه به رابط وب برمی‌گردد
        ScreenTaskRunner.onResult = { result -> reportTaskResult(result) }
        /*
         * POST_NOTIFICATIONS هم درخواست می‌شود: از اندروید ۱۳ به بعد بدون آن،
         * اعلانِ سرویس پیش‌زمینه نشان داده نمی‌شود و سالمند هیچ نشانه‌ای از
         * فعال بودن سپندیار نمی‌بیند. خودِ سرویس اجرا می‌شود، پس این مجوز
         * شرط شروع سرویس نیست و در onRequestPermissionsResult هم مانع نیست.
         */
        val needed = mutableListOf<String>()
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
            needed.add(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            needed.add(Manifest.permission.POST_NOTIFICATIONS)
        if (needed.isNotEmpty()) requestPermissions(needed.toTypedArray(), 40)
        else startListeningService()
    }

    private fun startListeningService() { val intent = Intent(this, ListeningService::class.java); if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent) }

    /**
     * نتیجهٔ مجوزها را با نامِ خودِ مجوز می‌سنجیم، نه با جایگاهش در آرایه.
     * نسخهٔ پیشین grantResults.firstOrNull() را می‌دید؛ با اضافه شدن
     * POST_NOTIFICATIONS، نتیجهٔ میکروفن دیگر لزوماً در خانهٔ اول نیست و
     * سرویس گوش‌دادن هرگز شروع نمی‌شد.
     */
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != 40) return
        val micGranted = permissions.indexOf(Manifest.permission.RECORD_AUDIO)
            .takeIf { it >= 0 }
            ?.let { grantResults.getOrNull(it) == PackageManager.PERMISSION_GRANTED }
        if (micGranted == true) startListeningService()
    }

    inner class AppBridge {
        @JavascriptInterface fun openAccessibilitySettings() {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        @JavascriptInterface fun openAppSettings() { startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName"))) }
        @JavascriptInterface fun setAssistantName(name: String) { getSharedPreferences("assistant", MODE_PRIVATE).edit().putString("name", name).apply() }
        // آدرس سرور سپندیار؛ لایه وب در نخستین اجرا آن را می‌خواند و در localStorage هم نگه می‌دارد
        @JavascriptInterface fun getServerUrl(): String = getSharedPreferences("assistant", MODE_PRIVATE).getString("server_url", "") ?: ""
        // فقط https روی میزبان معتبر پذیرفته می‌شود. این متد ماندگار است: یک مقدار
        // بد، اپ را برای همیشه به سرور مهاجم برمی‌گرداند و چون لایهٔ وب آن را در
        // نخستین اجرا می‌خواند، هیچ بازنشانی آشکاری هم ندارد.
        /**
         * ذخیرهٔ نشانی سرور.
         *
         * https برای هر میزبان عمومی الزامی می‌ماند (تصمیم امنیتی عمدی:
         * نشانی بد، اپ را برای همیشه به سرور مهاجم برمی‌گرداند و چون لایهٔ
         * وب آن را در نخستین اجرا می‌خواند، هیچ بازنشانی آشکاری هم ندارد).
         *
         * اما http برای «حلقهٔ محلی و نشانی‌های خصوصی» مجاز است. پیش‌تر این
         * متد http را بی‌قیدوشرط رد می‌کرد و به‌علاوه host.contains('.')
         * الزامی بود که خودِ «localhost» را هم رد می‌کرد. نتیجه یک بن‌بست
         * بود: سرور MVP روی http و پورت ۴۱۷۴ اجرا می‌شود، پس اپِ نصب‌شده
         * هرگز نمی‌توانست به آن وصل شود، /api/apps/approved خالی می‌ماند و
         * هیچ وظیفهٔ کنترل صفحه‌ای ممکن نبود.
         *
         * نکته: اجازهٔ کلیدرمتن در سطح سیستم‌عامل با
         * res/xml/network_security_config.xml داده می‌شود و آن فایل فقط
         * تطبیق «دقیق» میزبان را پشتیبانی می‌کند (CIDR پشتیبانی نمی‌شود).
         * پس برای یک IP روی شبکهٔ محلی باید همان میزبان به آن فایل اضافه
         * شود؛ این محدودیت در README مستند شده است.
         */
        @JavascriptInterface fun saveServerUrl(url: String): Boolean {
            val candidate = url.trim()
            val editor = getSharedPreferences("assistant", MODE_PRIVATE).edit()
            if (candidate.isEmpty()) { editor.remove("server_url").apply(); return false }
            val parsed = Uri.parse(candidate)
            val host = parsed.host
            if (host.isNullOrBlank() || host.contains(' ')) return false
            val scheme = parsed.scheme?.lowercase()
            val privateHost = host.equals("localhost", ignoreCase = true) ||
                host == "::1" || host == "[::1]" ||
                host.startsWith("127.") || host.startsWith("10.") ||
                host.startsWith("192.168.") ||
                Regex("^172\\.(1[6-9]|2[0-9]|3[01])\\.").containsMatchIn(host)
            val schemeOk = scheme == "https" || (scheme == "http" && privateHost)
            if (!schemeOk) return false
            editor.putString("server_url", candidate).apply()
            return true
        }
        @JavascriptInterface fun saveVoiceProfile(samples: String) { getSharedPreferences("assistant", MODE_PRIVATE).edit().putString("voice_samples", samples).putLong("voice_enrolled_at", System.currentTimeMillis()).apply() }
        @JavascriptInterface fun callCaregiver(phone: String) { if (phone.isNotBlank()) startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$phone"))) }
        @JavascriptInterface fun tvCommand(command: String): Boolean { return TvCommandRouter.execute(this@MainActivity, command) }
        /**
         * باز کردن یک اپ تأییدشده.
         *
         * نوع بازگشت عمداً Boolean است: ScreenTaskRunner.start پارامتر
         * «launch: (String) -> Boolean» می‌گیرد، پس لامبدای
         * «{ pkg -> launchApprovedPackage(pkg) }» باید Boolean برگرداند.
         * با نوع بازگشت Unit، آن lambda از نوع (String) -> Unit می‌شد و
         * کاتلین آن را به (String) -> Boolean تبدیل نمی‌کند — یعنی کل فایل
         * کامپایل نمی‌شد و قابلیت کنترل دستگاه هرگز ساخته نمی‌شد.
         *
         * حالا لایهٔ وب هم می‌تواند بفهمد اپ واقعاً باز شد یا نه.
         */
        @JavascriptInterface fun launchApprovedPackage(packageName: String): Boolean {
            if (!ApprovedApps.contains(packageName)) return false
            val intent = packageManager.getLaunchIntentForPackage(packageName) ?: return false
            return try { startActivity(intent); true } catch (e: Exception) { false }
        }
        @JavascriptInterface fun requestScreenAction(action: String, payload: String) {
            ScreenControlService.pendingAction = ScreenAction(action, payload)
            ScreenControlService.instance?.executePendingAction()
        }
        @JavascriptInterface fun hasOverlayPermission(): Boolean = Settings.canDrawOverlays(this@MainActivity)
        @JavascriptInterface fun openOverlaySettings() { startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName"))) }
        @JavascriptInterface fun accessibilityEnabled(): Boolean = isAccessibilityEnabled()
        /** اجرای کامل یک کار روی اپ تأییدشده، با پاپ‌آپ شناور و بازگشت خودکار به سپندیار. */
        @JavascriptInterface fun runScreenTask(planJson: String): Boolean =
            ScreenTaskRunner.start(this@MainActivity, planJson) { pkg -> launchApprovedPackage(pkg) }
        @JavascriptInterface fun cancelScreenTask() { ScreenTaskRunner.cancel() }
        @JavascriptInterface fun bringAppToFront() { runOnUiThread { returnFromOverlay() } }
    }

    /** نتیجه کار را به جاوااسکریپت داخل WebView برمی‌گرداند. */
    private fun reportTaskResult(result: ScreenTaskResult) {
        runOnUiThread {
            if (!::web.isInitialized) return@runOnUiThread
            val payload = org.json.JSONObject.quote(result.toJson())
            web.evaluateJavascript("window.onScreenTaskResult && window.onScreenTaskResult(JSON.parse($payload))", null)
        }
    }

    /** بازگرداندن سپندیار به حالت تمام‌صفحه پس از پایان کنترل اپ مقصد. */
    private fun returnFromOverlay() {
        val intent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        startActivity(intent)
    }
}

private val ApprovedApps = setOf(
    // Package name واقعی هر اپ پس از تست روی دستگاه در این فهرست ثبت می‌شود.
    "com.snappfood", "cab.snapp.passenger", "com.android.chrome", "com.google.android.apps.chrome", "com.example.store"
)

data class ScreenAction(val type: String, val payload: String)
