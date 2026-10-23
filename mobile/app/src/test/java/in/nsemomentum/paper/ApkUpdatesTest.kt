package com.nsemomentum.paper
import org.junit.Assert.*
import org.junit.Test

class ApkUpdatesTest {
    private val valid = ApkUpdates.Manifest("com.nsemomentum.paper.preview", 9,
        "https://github.com/rukminaiah-dot/nse-momentum-scanner/releases/download/android-paper-0.8.0/app-release.apk", "a".repeat(64))
    @Test fun acceptsOnlyNewerSamePackageReleaseMetadata() { valid.validate(valid.packageName, 8) }
    @Test fun rejectsDowngradeWrongPackageInvalidHashAndForeignDownloads() {
        val bad = listOf(valid.copy(versionCode = 7), valid.copy(packageName = "other.app"), valid.copy(sha256 = "invalid"),
            valid.copy(apkUrl = "https://evil.example/app.apk"), valid.copy(apkUrl = valid.apkUrl.replace("https:", "http:")),
            valid.copy(apkUrl = valid.apkUrl + "?redirect=evil"))
        bad.forEach { manifest ->
            try { manifest.validate(valid.packageName, 8); fail("Expected rejection") }
            catch (_: IllegalArgumentException) { }
        }
    }
}
