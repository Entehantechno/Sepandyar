plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android { namespace = "ai.arena.sepandyar"; compileSdk = 35
    defaultConfig { applicationId = "ai.arena.sepandyar"; minSdk = 26; targetSdk = 35; versionCode = 1; versionName = "0.1.0" }
}

android.buildFeatures.buildConfig = true
