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
import android.webkit.WebView
import android.webkit.WebViewClient

class MainActivity : Activity() {
    private lateinit var web: WebView
    override fun onResume() { super.onResume(); if (::web.isInitialized && !isAccessibilityEnabled()) web.postDelayed({ web.evaluateJavascript("toast('برای راه‌اندازی کامل، دسترسی کنترل صفحه را فعال کنید')", null) }, 500) }
    private fun isAccessibilityEnabled(): Boolean { val enabled = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: return false; return enabled.contains(packageName) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            webViewClient = WebViewClient()
            addJavascriptInterface(AppBridge(), "SepandyarNative")
            loadUrl("file:///android_asset/index.html")
        }
        setContentView(web)
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
    }
}

private val ApprovedApps = setOf(
    // Package name واقعی هر اپ پس از تست روی دستگاه در این فهرست ثبت می‌شود.
    "com.snappfood", "cab.snapp.passenger", "com.android.chrome", "com.google.android.apps.chrome", "com.example.store"
)

data class ScreenAction(val type: String, val payload: String)
