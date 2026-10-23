package com.nsemomentum.paper

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.PackageInfo
import android.content.pm.ApplicationInfo
import android.os.Build
import androidx.core.content.FileProvider
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/** User-initiated updates only. Separate HTTP client never receives the Upstox token. */
class ApkUpdates(private val context: Context) {
    private val http = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS).callTimeout(90, TimeUnit.SECONDS).build()
    private val repo = "https://github.com/rukminaiah-dot/nse-momentum-scanner/releases/download/"

    data class Manifest(val packageName: String, val versionCode: Long, val apkUrl: String, val sha256: String) {
        fun validate(installedPackage: String, installedVersion: Long) {
            require(packageName == installedPackage) { "Update belongs to a different app." }
            require(versionCode > installedVersion) { "No newer compatible update is available." }
            require(Regex("^[a-fA-F0-9]{64}$").matches(sha256)) { "Invalid update checksum." }
            val uri = java.net.URI(apkUrl)
            require(uri.scheme == "https" && uri.host == "github.com" && uri.userInfo == null && uri.port == -1 &&
                uri.path.startsWith("/rukminaiah-dot/nse-momentum-scanner/releases/download/android-paper-") &&
                uri.path.endsWith(".apk") && uri.query == null && uri.fragment == null) { "Unapproved update address." }
        }
    }

    private fun body(url: String, limit: Long): ByteArray {
        http.newCall(Request.Builder().url(url).get().build()).execute().use { response ->
            check(response.isSuccessful) { "Update server unavailable. Try again later." }
            val body = response.body ?: error("Empty update response.")
            require(body.contentLength() <= limit) { "Update response is too large." }
            body.byteStream().use { stream ->
                val out = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(16384)
                while (true) {
                    val n = stream.read(buffer)
                    if (n < 0) break
                    require(out.size().toLong() + n <= limit) { "Update response is too large." }
                    out.write(buffer, 0, n)
                }
                return out.toByteArray()
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun packageInfo(path: String? = null): PackageInfo {
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        return if (path == null) context.packageManager.getPackageInfo(context.packageName, flags)
            else context.packageManager.getPackageArchiveInfo(path, flags) ?: error("Downloaded APK is invalid.")
    }
    @Suppress("DEPRECATION")
    private fun version(info: PackageInfo): Long = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()
    @Suppress("DEPRECATION")
    private fun certificates(info: PackageInfo): Set<String> {
        val signatures = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners else info.signatures
        return signatures.orEmpty().map { digest(it.toByteArray()) }.toSet()
    }
    private fun digest(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    /** Called on IO dispatcher after the user taps Download verified update. Returns installer intent. */
    fun prepare(): Intent {
        check(context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE == 0) {
            "Debug builds have no durable update channel. A privately signed release is required."
        }
        val installed = packageInfo()
        val releases = JSONArray(String(body("https://api.github.com/repos/rukminaiah-dot/nse-momentum-scanner/releases?per_page=30", 1_000_000), Charsets.UTF_8))
        val release = (0 until releases.length()).map { releases.getJSONObject(it) }.firstOrNull {
            !it.optBoolean("draft") && it.optString("tag_name").startsWith("android-paper-")
        } ?: error("No approved Android update has been published.")
        val tag = release.getString("tag_name")
        require(Regex("android-paper-[A-Za-z0-9._-]+").matches(tag)) { "Invalid update tag." }
        val json = JSONObject(String(body("${repo}${tag}/android-update.json", 16_384), Charsets.UTF_8))
        val manifest = Manifest(json.getString("packageName"), json.getLong("versionCode"), json.getString("apkUrl"), json.getString("sha256"))
        manifest.validate(context.packageName, version(installed))
        val directory = File(context.cacheDir, "apk-updates").apply { mkdirs() }
        val file = File(directory, "candidate.apk")
        try {
            val sha = MessageDigest.getInstance("SHA-256")
            http.newCall(Request.Builder().url(manifest.apkUrl).get().build()).execute().use { response ->
                check(response.isSuccessful) { "Update download failed. Try again later." }
                val body = response.body ?: error("Empty update response.")
                require(body.contentLength() <= 100_000_000) { "APK is too large." }
                body.byteStream().use { input -> file.outputStream().use { output ->
                    val buffer = ByteArray(16384)
                    var total = 0L
                    while (true) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        total += n
                        require(total <= 100_000_000) { "APK is too large." }
                        sha.update(buffer, 0, n)
                        output.write(buffer, 0, n)
                    }
                } }
            }
            check(sha.digest().joinToString("") { "%02x".format(it) }.equals(manifest.sha256, true)) {
                "Update checksum mismatch; installation blocked."
            }
            val candidate = packageInfo(file.absolutePath)
            check(candidate.packageName == context.packageName && version(candidate) == manifest.versionCode) { "APK version or package mismatch." }
            val signers = certificates(installed)
            check(signers.isNotEmpty() && signers == certificates(candidate)) { "Signing certificate mismatch; old app kept intact." }
            return Intent(Intent.ACTION_VIEW).setDataAndType(
                FileProvider.getUriForFile(context, "${context.packageName}.updates", file),
                "application/vnd.android.package-archive"
            ).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (error: Exception) { file.delete(); throw error }
    }
}
