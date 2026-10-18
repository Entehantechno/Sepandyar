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
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 40)
        else startListeningService()
    }

    private fun startListeningService() { val intent = Intent(this, ListeningService::class.java); if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent) }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) { super.onRequestPermissionsResult(requestCode, permissions, grantResults); if (requestCode == 40 && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) startListeningService() }

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
        @JavascriptInterface fun saveServerUrl(url: String) {
            val candidate = url.trim()
            if (candidate.isEmpty()) return
            val parsed = Uri.parse(candidate)
            val schemeOk = parsed.scheme.equals("https", ignoreCase = true)
            val host = parsed.host
            val hostOk = !host.isNullOrBlank() && host.contains('.') && !host.contains(' ')
            if (!schemeOk || !hostOk) return
            getSharedPreferences("assistant", MODE_PRIVATE).edit().putString("server_url", candidate).apply()
        }
        @JavascriptInterface fun saveVoiceProfile(samples: String) { getSharedPreferences("assistant", MODE_PRIVATE).edit().putString("voice_samples", samples).putLong("voice_enrolled_at", System.currentTimeMillis()).apply() }
        @JavascriptInterface fun callCaregiver(phone: String) { if (phone.isNotBlank()) startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$phone"))) }
        @JavascriptInterface fun tvCommand(command: String): Boolean { return TvCommandRouter.execute(this@MainActivity, command) }
        @JavascriptInterface fun launchApprovedPackage(packageName: String) {
            if (!ApprovedApps.contains(packageName)) return
            packageManager.getLaunchIntentForPackage(packageName)?.let { startActivity(it) }
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
