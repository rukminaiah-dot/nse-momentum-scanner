plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}
android {
    namespace = "com.nsemomentum.paper"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.nsemomentum.paper.scanner"
        minSdk = 26
        targetSdk = 35
        versionCode = 12
        versionName = "0.10.0-candidate"
        resValue("string", "app_name", "Momentum Paper Scanner")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    // Persistent private keystore is supplied outside the repository. No debug-key fallback for release.
    signingConfigs {
        create("persistent") {
            System.getenv("ANDROID_SIGNING_STORE_FILE")?.let { storeFile = file(it) }
            storePassword = System.getenv("ANDROID_SIGNING_STORE_PASSWORD")
            keyAlias = System.getenv("ANDROID_SIGNING_KEY_ALIAS")
            keyPassword = System.getenv("ANDROID_SIGNING_KEY_PASSWORD")
        }
    }
    buildTypes {
        getByName("debug") {
            applicationIdSuffix = ".dev"
            resValue("string", "app_name", "Momentum Scanner Test")
        }
        getByName("release") { signingConfig = signingConfigs.getByName("persistent") }
    }
    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            it.testLogging {
                events("failed")
                exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
            }
        }
    }
    buildFeatures { compose = true }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("org.robolectric:robolectric:4.14.1")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}

// Fail before release packaging if a persistent signing credential is missing.
tasks.configureEach {
    if (name == "preReleaseBuild") doFirst {
        listOf("ANDROID_SIGNING_STORE_FILE", "ANDROID_SIGNING_STORE_PASSWORD",
            "ANDROID_SIGNING_KEY_ALIAS", "ANDROID_SIGNING_KEY_PASSWORD").forEach {
            check(!System.getenv(it).isNullOrBlank()) { "Persistent Android signing is not configured." }
        }
    }
}
