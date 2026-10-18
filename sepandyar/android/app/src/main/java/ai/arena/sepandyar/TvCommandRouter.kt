package ai.arena.sepandyar

import android.content.Context
import android.content.Intent
import android.media.AudioManager

object TvCommandRouter {
    private val approved = mapOf(
        "یوتیوب" to "com.google.android.youtube.tv",
        "نتفلیکس" to "com.netflix.ninja",
        "کروم" to "com.android.chrome"
    )
    fun execute(context: Context, command: String): Boolean {
        val c=command.trim()
        val audio=context.getSystemService(AudioManager::class.java)
        when {
            c.contains("زیاد") && c.contains("صدا") -> { audio.adjustVolume(AudioManager.ADJUST_RAISE, AudioManager.FLAG_SHOW_UI); return true }
            c.contains("کم") && c.contains("صدا") -> { audio.adjustVolume(AudioManager.ADJUST_LOWER, AudioManager.FLAG_SHOW_UI); return true }
            c.contains("بی صدا") || c.contains("ساکت") -> { audio.adjustVolume(AudioManager.ADJUST_MUTE, AudioManager.FLAG_SHOW_UI); return true }
            c.contains("پخش") -> { sendMedia(context, android.view.KeyEvent.KEYCODE_MEDIA_PLAY); return true }
            c.contains("توقف") || c.contains("مکث") -> { sendMedia(context, android.view.KeyEvent.KEYCODE_MEDIA_PAUSE); return true }
            c.contains("بعدی") -> { sendMedia(context, android.view.KeyEvent.KEYCODE_MEDIA_NEXT); return true }
            c.contains("قبلی") -> { sendMedia(context, android.view.KeyEvent.KEYCODE_MEDIA_PREVIOUS); return true }
        }
        approved.entries.firstOrNull { c.contains(it.key) }?.let { (_,pkg) -> context.packageManager.getLaunchIntentForPackage(pkg)?.let { intent -> context.startActivity(intent); return true } }
        return false
    }
    private fun sendMedia(context: Context, code: Int) {
        val audio=context.getSystemService(AudioManager::class.java)
        audio.dispatchMediaKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_DOWN,code))
        audio.dispatchMediaKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_UP,code))
    }
}
