package com.nsemomentum.paper

import java.net.URLEncoder
import java.time.Instant
import java.time.LocalDate
import java.util.Locale
import kotlinx.coroutines.CancellationException
import org.json.JSONArray
import org.json.JSONObject

internal enum class WatchSide { BUY, SELL }
internal data class WatchRow(
    val symbol: String,
    val side: WatchSide,
    val close: Double,
    val previousHigh: Double,
    val previousLow: Double,
    val result: String = "",
    val dailyRelativeVolume: Double? = null
)

internal data class SavedWatch(val source: LocalDate, val target: LocalDate, val rows: List<WatchRow>, val skipped: Int, val missing: Int = 0,
    val upstoxVolume: Boolean = false) {
    fun encode(): String = JSONObject()
        .put("source", source.toString()).put("target", target.toString()).put("skipped", skipped).put("missing", missing).put("upstoxVolume", upstoxVolume)
        .put("rows", JSONArray(rows.map {
            JSONObject().put("symbol", it.symbol).put("side", it.side.name).put("close", it.close)
                .put("high", it.previousHigh).put("low", it.previousLow).put("result", it.result).put("dailyRelativeVolume", it.dailyRelativeVolume ?: JSONObject.NULL)
        })).toString()

    companion object {
        fun decode(text: String?): SavedWatch? = runCatching {
            val json = JSONObject(requireNotNull(text))
            val items = json.getJSONArray("rows")
            SavedWatch(LocalDate.parse(json.getString("source")), LocalDate.parse(json.getString("target")),
                (0 until items.length()).map { i ->
                    val item = items.getJSONObject(i)
                    WatchRow(item.getString("symbol"), WatchSide.valueOf(item.getString("side")),
                        item.getDouble("close"), item.getDouble("high"), item.getDouble("low"), item.getString("result"),
                        item.optDouble("dailyRelativeVolume").takeIf { it.isFinite() })
                }, json.getInt("skipped"), json.optInt("missing"), json.optBoolean("upstoxVolume"))
        }.getOrNull()
    }
}

internal class TomorrowWatch(private val feed: CandleFeed) {
    suspend fun prepare(token: String, stocks: List<Stock>, date: LocalDate,
                        now: Instant, onProgress: suspend (Int) -> Unit = {}): SavedWatch {
        val today = now.atZone(MarketSession.ZONE).toLocalDate()
        require(date <= today) { "Use a completed NSE session date." }
        val source = requireNotNull(feed.session(token, date)) { "No NSE session on the selected date." }
        require(now >= source.end) { "Build the watchlist after market close." }
        val target = sessions(token, date, 1, 1).single().date
        require(target >= today) { "The watchlist's next session has already passed." }
        val baselineDates = sessions(token, date, -1, 20).map { it.date }
        val previous = baselineDates.first()
        val rows = mutableListOf<WatchRow>()
        var skipped = 0
        var missing = 0
        for ((index, stock) in stocks.withIndex()) {
            val daily = try {
                feed.candles(token, "/v3/historical-candle/${encoded(stock)}/days/1/$date/${baselineDates.last()}")
            } catch (error: java.io.IOException) {
                if (error.message !in setOf("INVALID_CANDLE", "DUPLICATE_CANDLE")) throw error
                emptyList()
            }
            val byDate = daily.groupBy { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() }
            fun bar(day: LocalDate) = byDate[day]?.singleOrNull()?.takeIf(PaperStrategy::validCandle)
            val current = bar(date)
            val prior = bar(previous)
            val history = baselineDates.mapNotNull(::bar)
            val average = history.map { it.volume }.average()
            val ratio = if (current != null && history.size == 20 && average > 0.0)
                (current.volume / average).takeIf { it.isFinite() } else null
            if (current == null || prior == null || ratio == null) {
                missing++
            } else {
                val side = when {
                    ratio < 1.5 -> null
                    current.close > prior.high -> WatchSide.BUY
                    current.close < prior.low -> WatchSide.SELL
                    else -> null
                }
                if (side == null) skipped++ else rows += WatchRow(
                    stock.symbol, side, current.close, prior.high, prior.low, dailyRelativeVolume = ratio
                )
            }
            onProgress(index + 1)
        }
        require(missing < stocks.size) { "Daily data is not ready. Try again after Upstox publishes the session candles." }
        return SavedWatch(date, target, rows, skipped, missing, upstoxVolume = true)
    }

    suspend fun validate(token: String, watch: SavedWatch, stocks: List<Stock>, now: Instant): SavedWatch {
        val local = now.atZone(MarketSession.ZONE)
        require(local.toLocalDate() == watch.target) { "This watchlist applies to ${watch.target}." }
        require(!local.toLocalTime().isBefore(java.time.LocalTime.of(9, 35))) { "First validation candle closes at 09:35 IST." }
        val today = requireNotNull(feed.session(token, watch.target))
        require(today.isRegular()) { "Validation requires a regular NSE session." }
        val prior = sessions(token, watch.target, -1, 20)
        val bySymbol = stocks.associateBy { it.symbol }
        return watch.copy(rows = watch.rows.map { row ->
            if (row.result.startsWith("Passed")) return@map row
            try {
                val key = encoded(bySymbol.getValue(row.symbol))
                val current = feed.candles(token, "/v3/historical-candle/intraday/$key/minutes/5")
                val history = mutableListOf<Candle>()
                var end = prior.first().date
                val oldest = prior.last().date
                while (end >= oldest) {
                    val start = maxOf(oldest, end.minusDays(27))
                    history += feed.candles(token, "/v3/historical-candle/$key/minutes/5/$end/$start")
                    end = start.minusDays(1)
                }
                row.copy(result = validateWatch(row.side, today, prior, current, history, now))
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                if (error.message in setOf("UPSTOX_AUTH_REQUIRED", "LOCAL_RATE_BUDGET_EXHAUSTED", "RATE_LIMITED")) throw error
                row.copy(result = "Waiting for verified data")
            }
        })
    }

    private suspend fun sessions(token: String, date: LocalDate, direction: Long, count: Int): List<MarketSession> {
        val result = mutableListOf<MarketSession>()
        for (offset in 1L..60L) {
            feed.session(token, date.plusDays(offset * direction))?.let(result::add)
            if (result.size == count) return result
        }
        error("Could not verify the NSE calendar.")
    }

    private fun encoded(stock: Stock) = URLEncoder.encode(stock.instrumentKey, "UTF-8")
}

internal fun validateWatch(side: WatchSide, session: MarketSession, prior: List<MarketSession>,
                           current: List<Candle>, history: List<Candle>, now: Instant): String {
    val waiting = "Waiting for verified data"
    val expected = generateSequence(session.start) { it.plusSeconds(300) }
        .takeWhile { it.plusSeconds(300) <= minOf(now, session.end) }.toList()
    if (expected.size < 4 || prior.size != 20 || prior.map { it.date }.distinct().size != 20) return waiting
    val completed = current.filter { it.timestamp >= session.start && it.timestamp < session.end &&
        it.timestamp.plusSeconds(300) <= now }.sortedBy { it.timestamp }
    if (completed.map { it.timestamp } != expected || completed.any { !PaperStrategy.validCandle(it) }) return waiting
    val high = completed.take(3).maxOf { it.high }
    val low = completed.take(3).minOf { it.low }
    val historyByTime = history.groupBy { it.timestamp }
    var value = 0.0
    var volume = 0.0
    var status = "Waiting for breakout"
    completed.forEachIndexed { index, bar ->
        value += ((bar.high + bar.low + bar.close) / 3.0) * bar.volume
        volume += bar.volume
        if (index < 3 || volume <= 0.0) return@forEachIndexed
        val vwap = value / volume
        val breakout = when (side) {
            WatchSide.BUY -> bar.close > high && bar.close > vwap
            WatchSide.SELL -> bar.close < low && bar.close < vwap
        }
        if (!breakout) return@forEachIndexed
        val slot = bar.timestamp.atZone(MarketSession.ZONE).toLocalTime()
        val normal = prior.mapNotNull { day ->
            val start = day.date.atTime(slot).atZone(MarketSession.ZONE).toInstant()
            if (start < day.start || start.plusSeconds(300) > day.end) null
            else historyByTime[start]?.singleOrNull()?.takeIf(PaperStrategy::validCandle)?.volume
        }
        val average = normal.average()
        if (normal.size != 20 || !average.isFinite() || average <= 0.0) {
            status = waiting
            return@forEachIndexed
        }
        val ratio = bar.volume / average
        if (ratio >= 1.5) {
            val closeTime = bar.timestamp.plusSeconds(300).atZone(MarketSession.ZONE).toLocalTime()
            return String.format(Locale.US, "Passed %s IST · close ₹%.2f · range ₹%.2f–₹%.2f · est. VWAP ₹%.2f · %.2f× volume",
                closeTime, bar.close, low, high, vwap, ratio)
        }
        if (status != waiting) status = String.format(Locale.US, "Breakout volume %.2f× · needs 1.5×", ratio)
    }
    return status
}
