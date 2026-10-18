package ai.arena.sepandyar

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder

class ListeningService : Service() {
    companion object { const val CHANNEL = "sepandyar_listening"; const val ID = 1001 }
    override fun onCreate() { super.onCreate(); createChannel(); startForeground(ID, notification()) }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY
    override fun onBind(intent: Intent?): IBinder? = null
    private fun createChannel() { if (Build.VERSION.SDK_INT >= 26) getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel(CHANNEL, "گوش‌به‌زنگ سپندیار", NotificationManager.IMPORTANCE_LOW)) }
    private fun notification(): Notification = if (Build.VERSION.SDK_INT >= 26)
        Notification.Builder(this, CHANNEL).setSmallIcon(android.R.drawable.ic_btn_speak_now).setContentTitle("سپندیار فعال است").setContentText("گوش‌به‌فرمان شما هستم").setOngoing(true).build()
    else Notification.Builder(this).setSmallIcon(android.R.drawable.ic_btn_speak_now).setContentTitle("سپندیار فعال است").setContentText("گوش‌به‌فرمان شما هستم").setOngoing(true).build()
}
