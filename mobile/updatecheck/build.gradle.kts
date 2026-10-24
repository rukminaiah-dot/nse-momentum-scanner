plugins { id("com.android.application") }
android {
    namespace = "com.nsemomentum.updatecheck"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.nsemomentum.updatecheck"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
