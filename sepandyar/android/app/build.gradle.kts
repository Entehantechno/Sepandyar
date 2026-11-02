plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android { namespace = "ai.arena.sepandyar"; compileSdk = 35
    defaultConfig { applicationId = "ai.arena.sepandyar"; minSdk = 26; targetSdk = 35; versionCode = 1; versionName = "0.1.0" }
}

android.buildFeatures.buildConfig = true

dependencies {
    // WebViewAssetLoader: سرو کردن دارایی‌ها روی مبدأ https مجازی تا زمینهٔ امن
    // (میکروفون، service worker و fetch) در دسترس باشد.
    implementation("androidx.webkit:webkit:1.12.1")
    // سند رسمی App Actions: برای تعریف capability در shortcuts.xml به
    // androidx.core >= 1.6.0 نیاز است، وگرنه خطای کامپایل می‌گیرد.
    implementation("androidx.core:core:1.13.1")
}
