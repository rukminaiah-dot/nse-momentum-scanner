package com.nsemomentum.paper

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withTimeout
import java.io.IOException
import java.net.URLEncoder
import java.time.Instant
import java.time.LocalDate

/** Fixed market indices are independent of the user's stock list and stock RVOL ranking. */
enum class IndexDataState { LIVE, HISTORICAL, STALE, UNAVAILABLE }
data class IndexReading(
    val symbol: String,
    val state: IndexDataState = IndexDataState.UNAVAILABLE,
    val candle: Candle? = null,
    val technicals: TechnicalContext? = null,
    val sma21: Double? = null,
    val dayChangePercent: Double? = null,
    val signal: String = "WAIT",
    val reason: String = "NO_INDEX_SCAN"
) {
    fun at(now: Instant): IndexReading {
        val bar = candle ?: return copy(state = IndexDataState.UNAVAILABLE, signal = "WAIT")
        val age = java.time.Duration.between(bar.timestamp.plusSeconds(300), now).seconds
        if (age < 0 || !PaperStrategy.validCandle(bar)) return IndexReading(symbol, reason = "INVALID_INDEX_SNAPSHOT")
        val local = now.atZone(MarketSession.ZONE)
        if (state in setOf(IndexDataState.LIVE, IndexDataState.STALE) &&
            (local.toLocalDate() > bar.timestamp.atZone(MarketSession.ZONE).toLocalDate() || local.toLocalTime() >= java.time.LocalTime.of(15, 30)))
            return copy(state = IndexDataState.HISTORICAL, signal = "WAIT", reason = "HISTORICAL_CONTEXT_ONLY")
        if (state == IndexDataState.LIVE && age > 480) return copy(state = IndexDataState.STALE, signal = "WAIT", reason = "INDEX_SNAPSHOT_EXPIRED")
        return if (state != IndexDataState.LIVE) copy(signal = "WAIT") else this
    }
}
data class IndexMarketReport(val rows: List<IndexReading>, val checkedAt: Instant) {
    fun at(now: Instant) = copy(rows = rows.map { it.at(now) })
}

object IndexDirectionStrategy {
    fun evaluate(minutes: List<Candle>, target: Instant): String {
        val expected = (0 until 15).map { target.minusSeconds(600).plusSeconds(it * 60L) }
        val selected = minutes.filter { it.timestamp in expected }
        if (selected.size != 15 || selected.map { it.timestamp }.toSet() != expected.toSet() ||
            selected.any { !PaperStrategy.validCandle(it) }) return "WAIT"
        val byTime = selected.associateBy { it.timestamp }
        val closes = listOf(4, 9, 14).map { byTime.getValue(expected[it]).close }
        return when {
            closes[0] < closes[1] && closes[1] < closes[2] -> "BULLISH"
            closes[0] > closes[1] && closes[1] > closes[2] -> "BEARISH"
            else -> "NEUTRAL"
        }
    }
}

/** Independent web-compatible index direction; never applies stock volume rules. */
class IndexMarketScanner(private val database: CandleStore, private val feed: CandleFeed = UpstoxCandleFeed(), private val timeoutMillis: Long = 240_000) {
    suspend fun scan(token: String, now: Instant = Instant.now(), onProgress: suspend (Int, Int, String) -> Unit = { _, _, _ -> }): IndexMarketReport = withTimeout(timeoutMillis) {
        require(token.isNotBlank())
        val calendars = mutableMapOf<Pair<String, LocalDate>, MarketSession?>()
        suspend fun session(exchange: String, date: LocalDate): MarketSession? {
            val key = exchange to date
            if (!calendars.containsKey(key)) calendars[key] = feed.session(token, date, exchange)
            return calendars[key]?.also { if (!it.isRegular()) throw IOException("UNSUPPORTED_SPECIAL_SESSION") }
        }
        val rows = mutableListOf<IndexReading>()
        for (instrument in StockCatalog.indices) {
            try {
                val exchange = instrument.instrumentKey.substringBefore('_')
                val date = now.atZone(MarketSession.ZONE).toLocalDate()
                var current = session(exchange, date)?.takeIf { now >= it.start.plusSeconds(300) }
                var cursor = date.minusDays(1)
                repeat(90) { if (current == null) { current = session(exchange, cursor); cursor = cursor.minusDays(1) } }
                val market = current ?: throw IOException("UNVERIFIED_MARKET_CALENDAR")
                val target = (0 until 75).map { market.start.plusSeconds(it * 300L) }.lastOrNull { it.plusSeconds(300) <= now }
                    ?: throw IOException("NO_COMPLETED_MARKET_CANDLE")
                val encoded = URLEncoder.encode(instrument.instrumentKey, "UTF-8").replace("+", "%20")
                suspend fun download(s: MarketSession): List<Candle> {
                    val path = if (s.date == date) "/v3/historical-candle/intraday/$encoded/minutes/1"
                        else "/v3/historical-candle/$encoded/minutes/1/${s.date}/${s.date}"
                    val raw = feed.indexCandles(token, path)
                    if (raw.map { it.timestamp }.toSet().size != raw.size || raw.any {
                        !PaperStrategy.validCandle(it) || it.timestamp < s.start || it.timestamp >= s.end ||
                        java.time.Duration.between(s.start, it.timestamp).seconds % 60L != 0L || it.timestamp > now
                    }) throw IOException("INVALID_INDEX_CANDLE")
                    return raw.filter { it.timestamp.plusSeconds(60) <= now }.sortedBy { it.timestamp }
                }
                val minutes = download(market)
                val five = minutes.filter { it.timestamp >= target && it.timestamp < target.plusSeconds(300) }
                if (five.size != 5 || five.map { it.timestamp } != (0 until 5).map { target.plusSeconds(it * 60L) })
                    throw IOException("MISSING_COMPLETED_INDEX_CANDLE")
                val latest = Candle(target, five.first().open, five.maxOf { it.high }, five.minOf { it.low }, five.last().close, 0.0)
                var previous: MarketSession? = null
                cursor = market.date.minusDays(1)
                repeat(90) { if (previous == null) { previous = session(exchange, cursor); cursor = cursor.minusDays(1) } }
                val previousClose = previous?.let { s ->
                    try { download(s).singleOrNull { it.timestamp == s.end.minusSeconds(60) }?.close }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (error: Exception) {
                        if (error.message in setOf("UPSTOX_AUTH_REQUIRED", "LOCAL_RATE_BUDGET_EXHAUSTED")) throw error
                        null
                    }
                }
                val change = previousClose?.let { ((latest.close / it - 1) * 100).takeIf { value -> value.isFinite() } }
                val live = market.date == date && now < market.end
                val direction = IndexDirectionStrategy.evaluate(minutes, target)
                rows += IndexReading(instrument.symbol, if (live) IndexDataState.LIVE else IndexDataState.HISTORICAL,
                    candle = latest, dayChangePercent = change, signal = if (live) direction else "WAIT",
                    reason = if (!live) "HISTORICAL_CONTEXT_ONLY" else if (direction == "WAIT") "NEED_THREE_COMPLETE_CONSECUTIVE_5M_CANDLES" else "THREE_COMPLETED_5M_CLOSES")
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) {
                if (error.message in setOf("UPSTOX_AUTH_REQUIRED", "LOCAL_RATE_BUDGET_EXHAUSTED")) throw error
                rows += IndexReading(instrument.symbol, reason = safeReason(error))
            }
            onProgress(rows.size, StockCatalog.indices.size, instrument.symbol)
        }
        IndexMarketReport(rows, now)
    }
    private fun safeReason(error: Exception): String = error.message?.takeIf {
        it in setOf("UNSUPPORTED_SPECIAL_SESSION", "UNVERIFIED_MARKET_CALENDAR", "NO_COMPLETED_MARKET_CANDLE",
            "MISSING_COMPLETED_INDEX_CANDLE", "INVALID_INDEX_CANDLE", "NETWORK_ERROR", "RATE_LIMITED",
            "UPSTOX_SERVER_ERROR", "DUPLICATE_CANDLE", "INVALID_CANDLE", "INVALID_RESPONSE") ||
            it.matches(Regex("UPSTOX_HTTP_[0-9]{3}"))
    } ?: "INDEX_FETCH_FAILED"
}
