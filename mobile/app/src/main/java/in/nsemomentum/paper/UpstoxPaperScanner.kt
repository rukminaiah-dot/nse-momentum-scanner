package com.nsemomentum.paper

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.time.LocalDate
import java.util.concurrent.Callable
import java.util.concurrent.Executors

data class ScanRow(
    val symbol: String,
    val candleTime: String? = null,
    val relativeVolume: Double? = null,
    val signal: String = "WAIT",
    val reason: String
)

data class ScanReport(
    val rows: List<ScanRow>,
    val scanTime: String,
    val failedRequests: Int,
    val requestCount: Int
)

/** Read-only Upstox candle fetcher. This class intentionally has no order endpoints. */
class UpstoxPaperScanner(private val database: CandleDatabase) {
    private val zone = java.time.ZoneId.of("Asia/Kolkata")
    private val pool = Executors.newFixedThreadPool(4)

    fun scan(
        token: String,
        universe: List<Pair<String, String>>,
        favourites: Set<String>,
        now: java.time.Instant = java.time.Instant.now()
    ): ScanReport {
        require(token.isNotBlank())
        val sessionDate = now.atZone(zone).toLocalDate()
        val jobs = universe.map { (symbol, instrumentKey) ->
            Callable { scanOne(token, symbol, instrumentKey, favourites, sessionDate, now) }
        }
        val futures = pool.invokeAll(jobs)
        val rows = futures.mapIndexed { index, future ->
            runCatching { future.get() }.getOrElse {
                ScanRow(universe[index].first, reason = "FETCH_FAILED")
            }
        }.sortedWith(compareByDescending<ScanRow> { it.relativeVolume ?: -1.0 }.thenBy { it.symbol })
        return ScanReport(
            rows = rows,
            scanTime = now.atZone(zone).toString(),
            failedRequests = rows.count { it.reason.startsWith("FETCH_") || it.reason == "RATE_LIMITED" },
            requestCount = rows.size
        )
    }

    private fun scanOne(
        token: String,
        symbol: String,
        instrumentKey: String,
        favourites: Set<String>,
        sessionDate: LocalDate,
        now: java.time.Instant
    ): ScanRow {
        if (!database.hasTwentyPriorSessions(symbol, sessionDate)) {
            try {
                val end = sessionDate.minusDays(1)
                val start = end.minusMonths(1)
                database.save(symbol, requestCandles(token,
                    historicalPath(instrumentKey, end, start)))
            } catch (error: Exception) {
                return ScanRow(symbol, reason = apiReason(error))
            }
        }
        val intraday = try {
            requestCandles(token, intradayPath(instrumentKey))
        } catch (error: Exception) {
            return ScanRow(symbol, reason = apiReason(error))
        }
        val complete = intraday.filter { it.timestamp.plusSeconds(15 * 60).isBefore(now) ||
            it.timestamp.plusSeconds(15 * 60) == now }
        database.save(symbol, complete)
        val allBars = database.bars(symbol)
        val latest = allBars.lastOrNull() ?: return ScanRow(symbol, reason = "NO_CANDLES")
        val baseline = PaperStrategy.sameSlotAverage(latest, allBars)
            ?: return ScanRow(symbol, latest.timestamp.toString(), reason = "NO_VERIFIED_20_SESSION_BASELINE")
        val rvol = PaperStrategy.relativeVolume(latest.volume, baseline)
            ?: return ScanRow(symbol, latest.timestamp.toString(), reason = "INVALID_VOLUME")
        if (favourites.contains(symbol)) {
            val result = PaperStrategy.evaluate(allBars, now, baseline)
            return ScanRow(symbol, latest.timestamp.toString(), rvol, result.signal, result.reason)
        }
        return ScanRow(
            symbol = symbol,
            candleTime = latest.timestamp.toString(),
            relativeVolume = rvol,
            signal = if (rvol >= 1.5) "VOLUME_QUALIFIED" else "WAIT",
            reason = if (rvol >= 1.5) "FAVOURITE_ONLY_FOR_TECHNICALS" else "VOLUME_BELOW_THRESHOLD"
        )
    }

    private fun historicalPath(key: String, to: LocalDate, from: LocalDate): String =
        "/v3/historical-candle/${encode(key)}/minutes/15/${to}/${from}"

    private fun intradayPath(key: String): String =
        "/v3/historical-candle/intraday/${encode(key)}/minutes/15"

    private fun encode(value: String): String =
        URLEncoder.encode(value, StandardCharsets.UTF_8.name()).replace("+", "%20")

    private fun requestCandles(token: String, path: String): List<Candle> {
        var lastStatus = 0
        for (attempt in 0..2) {
            val connection = (URL("https://api.upstox.com$path").openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 10_000
                readTimeout = 15_000
                setRequestProperty("Accept", "application/json")
                setRequestProperty("Authorization", "Bearer $token")
            }
            try {
                lastStatus = connection.responseCode
                if (lastStatus == 200) {
                    val body = connection.inputStream.bufferedReader().use { it.readText() }
                    return parseCandles(body)
                }
                if (lastStatus != 429 && lastStatus < 500) throw IOException("HTTP_$lastStatus")
            } finally {
                connection.disconnect()
            }
            if (attempt < 2) Thread.sleep(500L * (1L shl attempt))
        }
        throw IOException(if (lastStatus == 429) "RATE_LIMITED" else "UPSTOX_HTTP_ERROR")
    }

    private fun parseCandles(body: String): List<Candle> {
        val root = JSONObject(body)
        if (root.optString("status") != "success") throw IOException("UPSTOX_RESPONSE_ERROR")
        val candles = root.optJSONObject("data")?.optJSONArray("candles") ?: return emptyList()
        return (0 until candles.length()).mapNotNull { index ->
            runCatching {
                val row = candles.getJSONArray(index)
                Candle(
                    timestamp = java.time.OffsetDateTime.parse(row.getString(0)).toInstant(),
                    open = row.getDouble(1), high = row.getDouble(2), low = row.getDouble(3),
                    close = row.getDouble(4), volume = row.getDouble(5)
                )
            }.getOrNull()
        }.distinctBy { it.timestamp }.sortedBy { it.timestamp }
    }

    private fun apiReason(error: Throwable): String = when (error.message) {
        "HTTP_401", "HTTP_403" -> "UPSTOX_AUTH_REQUIRED"
        "RATE_LIMITED" -> "RATE_LIMITED"
        else -> "FETCH_FAILED"
    }
}
