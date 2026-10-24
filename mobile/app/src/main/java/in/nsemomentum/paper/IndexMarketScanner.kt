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
        val age = java.time.Duration.between(bar.timestamp.plusSeconds(900), now).seconds
        if (age < 0 || !PaperStrategy.validCandle(bar)) return IndexReading(symbol, reason = "INVALID_INDEX_SNAPSHOT")
        val local = now.atZone(MarketSession.ZONE)
        if (state in setOf(IndexDataState.LIVE, IndexDataState.STALE) &&
            (local.toLocalDate() > bar.timestamp.atZone(MarketSession.ZONE).toLocalDate() || local.toLocalTime() >= java.time.LocalTime.of(15, 30)))
            return copy(state = IndexDataState.HISTORICAL, signal = "WAIT", reason = "HISTORICAL_CONTEXT_ONLY")
        if (state == IndexDataState.LIVE && age > 1080) return copy(state = IndexDataState.STALE, signal = "WAIT", reason = "INDEX_SNAPSHOT_EXPIRED")
        return if (state != IndexDataState.LIVE) copy(signal = "WAIT") else this
    }
}
data class IndexMarketReport(val rows: List<IndexReading>, val checkedAt: Instant) {
    fun at(now: Instant) = copy(rows = rows.map { it.at(now) })
}

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
                val today = session(exchange, date)
                var snapshotSession = today?.takeIf { now >= it.start.plusSeconds(900) }
                var cursor = date.minusDays(1)
                repeat(90) {
                    if (snapshotSession == null) {
                        snapshotSession = session(exchange, cursor)
                        cursor = cursor.minusDays(1)
                    }
                }
                val current = snapshotSession ?: throw IOException("UNVERIFIED_MARKET_CALENDAR")
                val target = current.slots().lastOrNull { it.plusSeconds(900) <= now }
                    ?: throw IOException("NO_COMPLETED_MARKET_CANDLE")
                val live = current.date == date && now < current.end
                val prior = mutableListOf<MarketSession>()
                cursor = current.date.minusDays(1)
                repeat(90) {
                    if (prior.size < 21) {
                        session(exchange, cursor)?.let { prior += it }
                        cursor = cursor.minusDays(1)
                    }
                }
                if (prior.size != 21) throw IOException("UNVERIFIED_MARKET_CALENDAR")
                rows += readOne(token, instrument, current, target, prior, now, live)
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) {
                if (error.message in setOf("UPSTOX_AUTH_REQUIRED", "LOCAL_RATE_BUDGET_EXHAUSTED")) throw error
                rows += IndexReading(instrument.symbol, reason = safeReason(error))
            }
            onProgress(rows.size, StockCatalog.indices.size, instrument.symbol)
        }
        IndexMarketReport(rows, now)
    }

    private suspend fun readOne(token: String, instrument: Stock, current: MarketSession, target: Instant,
                                prior: List<MarketSession>, now: Instant, live: Boolean): IndexReading {
        val key = instrument.instrumentKey
        val encoded = URLEncoder.encode(key, "UTF-8").replace("+", "%20")
        val useIntraday = current.date == now.atZone(MarketSession.ZONE).toLocalDate()
        val requiredSlots = current.slots().filter { it <= target }
        var cache = database.bars(key)
        fun currentBars(bars: List<Candle>) = bars.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() == current.date }
        fun validCurrent(bars: List<Candle>): Boolean = bars.size == requiredSlots.size &&
            bars.all { PaperStrategy.validCandle(it) && it.high > it.low } &&
            bars.map { it.timestamp }.toSet() == requiredSlots.toSet()
        if (!IndexPaperStrategy.verifiedHistory(cache, prior) || !useIntraday && !validCurrent(currentBars(cache))) {
            var end = if (useIntraday) current.date.minusDays(1) else current.date
            val oldest = prior.minOf { it.date }
            val expectedSessions = (prior + current).associateBy { it.date }
            val history = mutableListOf<Candle>()
            while (end >= oldest) {
                val start = maxOf(oldest, end.minusDays(27))
                val downloaded = feed.indexCandles(token, "/v3/historical-candle/$encoded/minutes/15/$end/$start")
                if (downloaded.any { bar ->
                        val day = bar.timestamp.atZone(MarketSession.ZONE).toLocalDate()
                        day !in start..end || expectedSessions[day]?.slots()?.contains(bar.timestamp) != true || !PaperStrategy.validCandle(bar)
                    }) throw IOException("INVALID_INDEX_HISTORY")
                history += downloaded
                end = start.minusDays(1)
            }
            if (history.map { it.timestamp }.distinct().size != history.size || !IndexPaperStrategy.verifiedHistory(history, prior))
                throw IOException("NO_VERIFIED_21_SESSION_HISTORY")
            if (!useIntraday && !validCurrent(currentBars(history))) throw IOException("MISSING_COMPLETED_INDEX_CANDLE")
            database.save(key, history)
            cache = database.bars(key)
        }
        val complete = if (useIntraday) {
            val raw = feed.indexCandles(token, "/v3/historical-candle/intraday/$encoded/minutes/15")
            if (raw.any { it.timestamp !in current.slots() || it.timestamp > now || !PaperStrategy.validCandle(it) } ||
                raw.map { it.timestamp }.distinct().size != raw.size) throw IOException("INVALID_INDEX_CANDLE")
            raw.filter { it.timestamp <= target }
        } else currentBars(cache)
        if (!validCurrent(complete)) throw IOException("MISSING_COMPLETED_INDEX_CANDLE")
        val historyDates = prior.map { it.date }.toSet()
        val history = cache.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() in historyDates }
        if (!IndexPaperStrategy.verifiedHistory(history, prior)) throw IOException("NO_VERIFIED_21_SESSION_HISTORY")
        val bars = (history + complete).sortedBy { it.timestamp }
        val technicals = PaperStrategy.context(bars) ?: throw IOException("INSUFFICIENT_INDEX_HISTORY")
        val sma21 = prior.map { s -> history.single { it.timestamp == s.slots().last() }.close }.average()
        val latest = complete.single { it.timestamp == target }
        val previousClose = history.single { it.timestamp == prior.first().slots().last() }.close
        val change = (latest.close / previousClose - 1) * 100
        if (!sma21.isFinite() || sma21 <= 0 || !change.isFinite() ||
            listOf(technicals.ema20, technicals.ema50, technicals.stochK, technicals.stochD).any { !it.isFinite() })
            throw IOException("INVALID_INDEX_HISTORY")
        val signal = if (live) IndexPaperStrategy.evaluate(bars, prior, now) else PaperSignal(reason = "HISTORICAL_CONTEXT_ONLY")
        database.save(key, complete)
        return IndexReading(instrument.symbol, if (live) IndexDataState.LIVE else IndexDataState.HISTORICAL,
            latest, technicals, sma21, change,
            if (live) signal.signal else "WAIT", signal.reason)
    }

    private fun safeReason(error: Exception): String = error.message?.takeIf {
        it in setOf("UNSUPPORTED_SPECIAL_SESSION", "UNVERIFIED_MARKET_CALENDAR", "NO_COMPLETED_MARKET_CANDLE",
            "INVALID_INDEX_HISTORY", "NO_VERIFIED_21_SESSION_HISTORY", "MISSING_COMPLETED_INDEX_CANDLE",
            "INVALID_INDEX_CANDLE", "INSUFFICIENT_INDEX_HISTORY", "NETWORK_ERROR", "RATE_LIMITED",
            "UPSTOX_SERVER_ERROR", "DUPLICATE_CANDLE", "INVALID_CANDLE", "INVALID_RESPONSE") ||
            it.matches(Regex("UPSTOX_HTTP_[0-9]{3}"))
    } ?: "INDEX_FETCH_FAILED"
}
