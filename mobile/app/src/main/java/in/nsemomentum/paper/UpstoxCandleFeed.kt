package com.nsemomentum.paper

import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import java.time.Instant
import java.time.LocalDate
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Only GET requests to candle and exchange-calendar endpoints. Never logs response bodies or tokens. */
class UpstoxCandleFeed(
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS)
        .callTimeout(25, TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).build(),
    private val baseUrl: String = "https://api.upstox.com",
    private val spacingMillis: Long = 200
) : CandleFeed {
    private val gate = Mutex()
    private var nextRequestNanos = 0L

    private suspend fun pace() = gate.withLock {
        val wait = (nextRequestNanos - System.nanoTime()) / 1_000_000
        if (wait > 0) delay(wait + 1)
        nextRequestNanos = System.nanoTime() + spacingMillis * 1_000_000
    }

    private suspend fun deferRequests(millis: Long) = gate.withLock {
        nextRequestNanos = maxOf(nextRequestNanos, System.nanoTime() + millis * 1_000_000)
    }

    private data class Reply(val code: Int, val retryAfter: String?, val body: String?)

    private suspend fun execute(request: Request): Reply = suspendCancellableCoroutine { continuation ->
        val call = client.newCall(request)
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                continuation.resumeWithException(IOException("NETWORK_ERROR"))
            }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    try {
                        val body = if (response.code == 200) response.body?.string() else null
                        continuation.resume(Reply(response.code, response.header("Retry-After"), body))
                    } catch (_: IOException) { continuation.resumeWithException(IOException("NETWORK_ERROR")) }
                }
            }
        })
    }

    private suspend fun request(token: String, path: String): JSONObject {
        for (attempt in 0..2) {
            pace()
            val request = Request.Builder().url("$baseUrl$path").get()
                .header("Accept", "application/json").header("Authorization", "Bearer $token").build()
            try {
                execute(request).let { response ->
                    if (response.code == 200) {
                        // Body reads remain cancellable via the active call and total call timeout.
                        val body = response.body ?: throw IOException("INVALID_RESPONSE")
                        val root = try { JSONObject(body) } catch (_: Exception) { throw IOException("INVALID_RESPONSE") }
                        if (root.optString("status") != "success") throw IOException("INVALID_RESPONSE")
                        return root
                    }
                    if (response.code == 401 || response.code == 403) throw IOException("UPSTOX_AUTH_REQUIRED")
                    if (response.code == 429) {
                        val retry = response.retryAfter?.toLongOrNull()?.coerceIn(1, 60) ?: 2L
                        deferRequests(retry * 1000)
                        if (attempt == 2) throw IOException("RATE_LIMITED")
                    } else if (response.code in 500..599) {
                        if (attempt == 2) throw IOException("UPSTOX_SERVER_ERROR")
                    } else throw IOException("UPSTOX_HTTP_${response.code}")
                }
            } catch (error: IOException) {
                if (error.message !in setOf("NETWORK_ERROR") || attempt == 2) throw error
            }
            delay(500L * (1L shl attempt))
        }
        throw IOException("FETCH_FAILED")
    }

    override suspend fun candles(token: String, path: String): List<Candle> = parseCandles(request(token, path))

    override suspend fun session(token: String, date: LocalDate): MarketSession? {
        val data = request(token, "/v2/market/timings/$date").getJSONArray("data")
        val entries = (0 until data.length()).map { data.getJSONObject(it) }.filter { it.getString("exchange") == "NSE" }
        if (entries.isEmpty()) return null // Exchange calendar explicitly says NSE is closed.
        if (entries.size != 1) throw IOException("UNVERIFIED_MARKET_CALENDAR")
        val entry = entries.single()
        val result = MarketSession(date, Instant.ofEpochMilli(entry.getLong("start_time")), Instant.ofEpochMilli(entry.getLong("end_time")))
        if (!result.isRegular()) throw IOException("UNSUPPORTED_SPECIAL_SESSION")
        return result
    }

    companion object {
        fun parseCandles(root: JSONObject): List<Candle> {
            val rows = root.getJSONObject("data").getJSONArray("candles")
            val bars = (0 until rows.length()).map { i ->
                try {
                    val row = rows.getJSONArray(i)
                    Candle(java.time.OffsetDateTime.parse(row.getString(0)).toInstant(),
                        row.getDouble(1), row.getDouble(2), row.getDouble(3), row.getDouble(4), row.getDouble(5))
                } catch (_: Exception) { throw IOException("INVALID_CANDLE") }
            }
            if (bars.any { !PaperStrategy.validCandle(it) }) throw IOException("INVALID_CANDLE")
            if (bars.map { it.timestamp }.distinct().size != bars.size) throw IOException("DUPLICATE_CANDLE")
            return bars.sortedBy { it.timestamp }
        }
    }
}
