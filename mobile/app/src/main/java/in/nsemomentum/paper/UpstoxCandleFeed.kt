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

/** Only GET requests to candles, exchange calendars and instrument search. Never logs response bodies or tokens. */
class UpstoxCandleFeed(
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS)
        .callTimeout(25, TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).build(),
    private val baseUrl: String = "https://api.upstox.com",
    private val spacingMillis: Long = 200,
    private val attemptBudget: Int = 1900
) : CandleFeed {
    private val gate = Mutex()
    private var nextRequestNanos = 0L
    private val recentAttempts = java.util.ArrayDeque<Long>()

    private suspend fun pace() = gate.withLock {
        val wait = (nextRequestNanos - System.nanoTime()) / 1_000_000
        if (wait > 0) delay(wait + 1)
        val now = System.nanoTime()
        val window = TimeUnit.MINUTES.toNanos(30)
        while (recentAttempts.isNotEmpty() && now - recentAttempts.first > window) recentAttempts.removeFirst()
        if (recentAttempts.size >= attemptBudget) throw IOException("LOCAL_RATE_BUDGET_EXHAUSTED")
        recentAttempts.addLast(now)
        nextRequestNanos = now + spacingMillis * 1_000_000
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

    suspend fun searchInstruments(token: String, query: String, exchange: String, page: Int = 1): InstrumentSearchPage {
        require(token.isNotBlank()) { "TOKEN_NOT_CONFIGURED" }
        val normalized = InstrumentSearchRules.query(query)
        require(exchange in setOf("NSE", "BSE") && page in 1..100000)
        val encoded = java.net.URLEncoder.encode(normalized, "UTF-8")
        val path = "/v2/instruments/search?query=$encoded&exchanges=$exchange&segments=EQ&page_number=$page&records=30"
        return InstrumentSearchRules.parse(request(token, path), exchange, page)
    }

    override suspend fun candles(token: String, path: String): List<Candle> = parseCandles(request(token, path))

    // The shared Candle model needs a numeric field; zero is an unused placeholder for spot indices.
    // Actual index OHLC is still mandatory. Stock volume parsing remains strict.
    override suspend fun indexCandles(token: String, path: String): List<Candle> = parseCandles(request(token, path), requireVolume = false)

    override suspend fun session(token: String, date: LocalDate): MarketSession? = session(token, date, "NSE")

    override suspend fun session(token: String, date: LocalDate, exchange: String): MarketSession? {
        require(exchange in setOf("NSE", "BSE"))
        val data = request(token, "/v2/market/timings/$date").getJSONArray("data")
        val entries = (0 until data.length()).map { data.getJSONObject(it) }.filter { it.getString("exchange") == exchange }
        if (entries.isEmpty()) return null // Exchange calendar explicitly says NSE is closed.
        if (entries.size != 1) throw IOException("UNVERIFIED_MARKET_CALENDAR")
        val entry = entries.single()
        val result = MarketSession(date, Instant.ofEpochMilli(entry.getLong("start_time")), Instant.ofEpochMilli(entry.getLong("end_time")))
        if (!result.isRegular()) throw IOException("UNSUPPORTED_SPECIAL_SESSION")
        return result
    }

    companion object {
        fun parseCandles(root: JSONObject, requireVolume: Boolean = true): List<Candle> {
            val rows = root.getJSONObject("data").getJSONArray("candles")
            val bars = (0 until rows.length()).map { i ->
                try {
                    val row = rows.getJSONArray(i)
                    Candle(java.time.OffsetDateTime.parse(row.getString(0)).toInstant(),
                        row.getDouble(1), row.getDouble(2), row.getDouble(3), row.getDouble(4), if (requireVolume) row.getDouble(5) else 0.0)
                } catch (_: Exception) { throw IOException("INVALID_CANDLE") }
            }
            if (bars.any { !PaperStrategy.validCandle(it) }) throw IOException("INVALID_CANDLE")
            if (bars.map { it.timestamp }.distinct().size != bars.size) throw IOException("DUPLICATE_CANDLE")
            return bars.sortedBy { it.timestamp }
        }
    }
}
