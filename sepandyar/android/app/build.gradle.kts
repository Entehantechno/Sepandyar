plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.devtools.ksp")
}

android { namespace = "ai.arena.sepandyar"; compileSdk = 37
    defaultConfig { applicationId = "ai.arena.sepandyar"; minSdk = 26; targetSdk = 36; versionCode = 1; versionName = "0.1.0" }
}

android.buildFeatures.buildConfig = true

dependencies {
    // WebViewAssetLoader: سرو کردن دارایی‌ها روی مبدأ https مجازی تا زمینهٔ امن
    // (میکروفون، service worker و fetch) در دسترس باشد.
    implementation("androidx.webkit:webkit:1.12.1")
    // سند رسمی App Actions: برای تعریف capability در shortcuts.xml به
    // androidx.core >= 1.6.0 نیاز است، وگرنه خطای کامپایل می‌گیرد.
    implementation("androidx.core:core:1.13.1")
    // core-ktx برای withContext(Dispatchers.IO): توابع AppFunction روی نخ UI
    // اجرا می‌شوند و فراخوانی شبکه بدون جابه‌جایی نخ، ANR می‌دهد.
    implementation("androidx.core:core-ktx:1.13.1")

    /*
     * لایهٔ ۱ معماری دستیارها: AppFunctions (نسخهٔ 1.0.0-beta01، ۲۰۲۶-۱۰-۲۱).

     * سه دام مستند که اینجا رعایت شده‌اند:
     *  ۱. appfunctions-service از alpha09 به بعد «دیگر منتشر نمی‌شود».
     *     افزودنش خطای حل وابستگی می‌دهد.
     *  ۲. از alpha10 هر @AppFunctionDeclaration باید «داخل» کلاسی باشد که
     *     @AppFunctionServiceEntryPoint دارد و از AppFunctionService ارث
     *     می‌برد. بیرونِ آن ⇒ build سبز، صفر تابع ثبت‌شده.
     *  ۳. از alpha13 نام @AppFunction به @AppFunctionDeclaration تغییر کرد.
     *     نام قدیمی «کامپایل می‌شود» ولی KSP بی‌صدا XML خالی می‌سازد —
     *     بدترین نوع شکست.
     *
     * global aggregation از beta01 به‌طور پیش‌فرض خاموش است، پس آرگومان
     * aggregateAppFunctions دیگر لازم نیست.
     */
    implementation("androidx.appfunctions:appfunctions:1.0.0-beta01")
    ksp("androidx.appfunctions:appfunctions-compiler:1.0.0-beta01")
}
