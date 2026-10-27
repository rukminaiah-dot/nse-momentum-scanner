package com.nsemomentum.paper

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withTimeout
import java.io.IOException
import java.net.URLEncoder
import java.time.Instant
import java.time.LocalDate


data class ScanRow(
    val symbol: String,
    val candleTime: String? = null,
    val relativeVolume: Double? = null,
    val signal: String = "WAIT",
    val reason: String,
    val candle: Candle? = null,
    val technicals: TechnicalContext? = null,
    val averageSlotVolume: Double? = null,
    val dailyChangePercent: Double? = null
)

data class ScanReport(val rows: List<ScanRow>, val scanTime: String, val failedRequests: Int, val requestCount: Int)

/** Snapshot scan of one completed candle for the entire universe. No order capability. */
class UpstoxPaperScanner(
    private val database: CandleStore,
    private val feed: CandleFeed = UpstoxCandleFeed(),
    private val timeoutMillis: Long = 10 * 60_000L
) {
    suspend fun scan(
        token: String,
        universe: List<Pair<String, String>>,
        favourites: Set<String>,
        now: Instant = Instant.now(),
        onProgress: suspend (completed: Int, total: Int, symbol: String) -> Unit = { _, _, _ -> }
    ): ScanReport = withTimeout(timeoutMillis) {
        require(token.isNotBlank())
        require(universe.map { it.first }.distinct().size == universe.size)
        require(universe.map { it.second }.distinct().size == universe.size)
        val date = now.atZone(MarketSession.ZONE).toLocalDate()
        val calendars = universe.map { it.second.substringBefore('_') }.distinct().associateWith { exchange ->
            val today = feed.session(token, date, exchange) ?: throw IOException("MARKET_CLOSED")
            val target = today.completedSlot(now) ?: throw IOException("NO_COMPLETED_MARKET_CANDLE")
            val required = if (universe.any { it.second.startsWith("${exchange}_INDEX|") }) 21 else 20
            val sessions = mutableListOf<MarketSession>()
            var previous = date.minusDays(1)
            repeat(60) {
                if (sessions.size < required) {
                    feed.session(token, previous, exchange)?.let { session ->
                        if (!session.isRegular()) throw IOException("UNSUPPORTED_SPECIAL_SESSION")
                        sessions += session
                    }
                    previous = previous.minusDays(1)
                }
            }
            if (sessions.size != required) throw IOException("UNVERIFIED_MARKET_CALENDAR")
            Triple(today, target, sessions)
        }
        val permits = Semaphore(4)
        val progressLock = Mutex()
        var completed = 0
        val rows = coroutineScope {
            universe.map { (symbol, key) -> async {
                permits.withPermit {
                    val (today, target, prior) = calendars.getValue(key.substringBefore('_'))
                    val sessions = prior.take(if (key.contains("_INDEX|")) 21 else 20)
                    val row = try { scanOne(token, symbol, key, favourites, today, target, sessions, now) }
                    catch (error: CancellationException) { throw error }
                    catch (error: Exception) {
                        if (error.message in setOf("UPSTOX_AUTH_REQUIRED", "LOCAL_RATE_BUDGET_EXHAUSTED")) throw error
                        ScanRow(symbol, reason = safeReason(error))
                    }
                    progressLock.withLock {
                        completed++
                        onProgress(completed, universe.size, symbol)
                    }
                    row
                }
            } }.awaitAll()
        }.sortedWith(compareByDescending<ScanRow> { it.relativeVolume ?: -1.0 }.thenBy { it.symbol })
        ScanReport(rows, now.atZone(MarketSession.ZONE).toString(), rows.count { isFeedError(it.reason) }, rows.size)
    }

    private suspend fun scanOne(
        token: String, symbol: String, key: String, favourites: Set<String>,
        today: MarketSession, target: Instant, sessions: List<MarketSession>, now: Instant
    ): ScanRow {
        val encoded = URLEncoder.encode(key, "UTF-8").replace("+", "%20")
        val isIndex = key.contains("_INDEX|")
        // Cache by instrument key: deleting/re-adding a label must not reuse another instrument's data.
        var cached = database.bars(key)
        fun historyReady(bars: List<Candle>): Boolean = if (isIndex)
            IndexPaperStrategy.verifiedHistory(bars, sessions)
        else PaperStrategy.sameSlotAverage(Candle(target, 1.0, 1.0, 1.0, 1.0, 0.0), bars, sessions) != null
        if (!historyReady(cached)) {
            // At most 28 calendar days per request, safely inside V3's one-month limit.
            var end = today.date.minusDays(1)
            val oldest = sessions.minOf { it.date }
            val history = mutableListOf<Candle>()
            while (end >= oldest) {
                val start = maxOf(oldest, end.minusDays(27))
                val bars = feed.candles(token, "/v3/historical-candle/$encoded/minutes/15/$end/$start")
                if (bars.any { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() !in start..end })
                    throw IOException("INVALID_CANDLE_DATE")
                history += bars
                end = start.minusDays(1)
            }
            // Validate the raw response before cache upserts can conceal duplicates or missing slots.
            if (!historyReady(history))
                return ScanRow(symbol, reason = if (isIndex) "NO_VERIFIED_21_SESSION_HISTORY" else "NO_VERIFIED_20_SESSION_BASELINE")
            database.save(key, history)
            cached = database.bars(key)
        }
        val intraday = feed.candles(token, "/v3/historical-candle/intraday/$encoded/minutes/15")
        if (intraday.any { !PaperStrategy.validCandle(it) || it.timestamp !in today.slots() } ||
            intraday.map { it.timestamp }.distinct().size != intraday.size) throw IOException("INVALID_INTRADAY_CANDLES")
        val complete = intraday.filter { it.timestamp <= target }
        if (complete.map { it.timestamp }.toSet() != today.slots().filter { it <= target }.toSet())
            return ScanRow(symbol, reason = "MISSING_COMPLETED_15M_CANDLE")
        // Only fresh intraday input can establish today's latest bar; cache cannot mask feed gaps.
        val latest = complete.single { it.timestamp == target }
        val baseline = if (isIndex) null else PaperStrategy.sameSlotAverage(latest, cached, sessions)
        if (!isIndex && baseline == null) return ScanRow(symbol, reason = "NO_VERIFIED_20_SESSION_BASELINE")
        database.save(key, complete)
        val allBars = cached.filter { bar -> sessions.any { it.date == bar.timestamp.atZone(MarketSession.ZONE).toLocalDate() } } + complete
        val ordered = allBars.sortedBy { it.timestamp }
        val rvol = baseline?.let { PaperStrategy.relativeVolume(latest.volume, it) }
        if (!isIndex && rvol == null) return ScanRow(symbol, reason = "INVALID_VOLUME")
        val context = if (symbol in favourites) PaperStrategy.context(ordered) else null
        val result = if (isIndex) IndexPaperStrategy.evaluate(ordered, sessions, now)
        else if (symbol in favourites) {
            val evaluated = PaperStrategy.evaluate(ordered, now, baseline,
                qualifiedToday = database.qualifiedOn(symbol, today.date),
                hasActiveBuy = database.hasActivePaperBuy(symbol))
            val recorded = database.recordedPaperSignal(symbol, target)
            if (recorded != null && evaluated.reason in setOf("UPTREND_BULLISH_CROSS", "BEARISH_CROSS_EXIT", "BUY_ACTIVE_WAITING_BEARISH_CROSS", "EMA_TREND_NOT_UP", "NO_BULLISH_CROSS", "NOT_SHORTLISTED_TODAY"))
                evaluated.copy(signal = recorded, reason = if (recorded == "PAPER_BUY") "UPTREND_BULLISH_CROSS" else "BEARISH_CROSS_EXIT")
            else evaluated
        } else PaperSignal(
            signal = if ((rvol ?: 0.0) >= 1.5) "VOLUME_QUALIFIED" else "WAIT",
            reason = if ((rvol ?: 0.0) >= 1.5) "FAVOURITE_ONLY_FOR_TECHNICALS" else "VOLUME_BELOW_THRESHOLD")
        val previousCloseTime = sessions.first().slots().last()
        val previousClose = cached.singleOrNull { it.timestamp == previousCloseTime }?.close
        val dailyChange = previousClose?.takeIf { it > 0.0 }?.let { ((latest.close - it) / it) * 100.0 }
            ?.takeIf { it.isFinite() }
        return ScanRow(
            symbol = symbol,
            candleTime = target.atZone(MarketSession.ZONE).toString(),
            relativeVolume = rvol,
            signal = result.signal,
            reason = result.reason,
            candle = latest,
            technicals = context,
            averageSlotVolume = baseline,
            dailyChangePercent = dailyChange
        )
    }

    private fun safeReason(error: Throwable): String = error.message?.takeIf {
        it.matches(Regex("(UPSTOX_HTTP_[0-9]{3}|INVALID_[A-Z_]+|DUPLICATE_CANDLE|RATE_LIMITED|NETWORK_ERROR|UPSTOX_SERVER_ERROR)"))
    } ?: "FETCH_FAILED"

    private fun isFeedError(reason: String): Boolean = reason == "FETCH_FAILED" || reason == "RATE_LIMITED" ||
        reason == "NETWORK_ERROR" || reason.startsWith("UPSTOX_") || reason.startsWith("INVALID_") ||
        reason == "DUPLICATE_CANDLE" || reason == "MISSING_COMPLETED_15M_CANDLE"
}
