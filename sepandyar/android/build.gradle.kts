plugins {
    id("com.android.application") version "9.1.1" apply false
    id("org.jetbrains.kotlin.android") version "2.3.20" apply false
    // KSP برای appfunctions-compiler لازم است: همان متغیری است که از
    // KDoc ابزارِ type-safe می‌سازد و XML متادیتا را برای AppSearch تولید
    // می‌کند. بدون آن هیچ تابعی ثبت نمی‌شود.
    id("com.google.devtools.ksp") version "2.3.12" apply false
}
