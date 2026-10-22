package com.nsemomentum.paper

import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import kotlin.math.abs

data class Candle(
    val timestamp: Instant,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double,
    val volume: Double
)

data class PaperSignal(
    val signal: String = "WAIT",
    val reason: String,
    val relativeVolume: Double? = null,
    val stochK: Double? = null,
    val stochD: Double? = null
)

object PaperStrategy {
    private val marketZone = ZoneId.of("Asia/Kolkata")

    /** Strict average for the 20 latest prior weekday observations of this 15m slot. */
    fun sameSlotAverage(current: Candle, priorCandles: List<Candle>, sessions: Int = 20): Double? {
        if (sessions < 1 || current.volume < 0 || !current.volume.isFinite()) return null
        val local = current.timestamp.atZone(marketZone)
        val slot = local.toLocalTime()
        val minutes = slot.hour * 60 + slot.minute
        if (minutes < 9 * 60 + 15 || minutes >= 15 * 60 + 30 || (minutes - 9 * 60 - 15) % 15 != 0) return null
        val dayVolumes = mutableMapOf<LocalDate, Double>()
        for (bar in priorCandles) {
            val stamp = bar.timestamp.atZone(marketZone)
            if (stamp.toLocalDate() >= local.toLocalDate() || stamp.dayOfWeek.value > 5 || stamp.toLocalTime() != slot) continue
            if (!bar.volume.isFinite() || bar.volume < 0) continue
            if (dayVolumes.put(stamp.toLocalDate(), bar.volume) != null) return null
        }
        val values = dayVolumes.toSortedMap().values.toList().takeLast(sessions)
        if (values.size != sessions) return null
        val average = values.average()
        return average.takeIf { it > 0 && it.isFinite() }
    }

    fun relativeVolume(currentVolume: Double, baseline: Double): Double? =
        if (currentVolume >= 0 && baseline > 0 && currentVolume.isFinite() && baseline.isFinite())
            currentVolume / baseline else null

    /** Mirrors the experimental Python rules; emits paper labels only. */
    fun evaluate(bars: List<Candle>, now: Instant, sameSlotAverageVolume: Double?): PaperSignal {
        fun wait(reason: String) = PaperSignal(reason = reason)
        val required = maxOf(52, 14 + 14 + 3 + 3 + 2, 4)
        if (bars.size < required) return wait("INSUFFICIENT_15M_HISTORY")
        val recent = bars.takeLast(required)
        if (recent.map { it.timestamp }.toSet().size != recent.size) return wait("DUPLICATE_15M_CANDLE")
        for ((a, b) in recent.zipWithNext()) {
            val gap = ChronoUnit.MINUTES.between(a.timestamp, b.timestamp)
            val sameDate = a.timestamp.atZone(marketZone).toLocalDate() == b.timestamp.atZone(marketZone).toLocalDate()
            if (gap <= 0) return wait("UNSORTED_15M_HISTORY")
            if (sameDate && gap != 15L) return wait("NONCONTIGUOUS_15M_CANDLES")
        }
        val latest = recent.last()
        val currentDay = latest.timestamp.atZone(marketZone).toLocalDate()
        if (recent.takeLast(4).any { it.timestamp.atZone(marketZone).toLocalDate() != currentDay })
            return wait("INSUFFICIENT_SAME_SESSION_BREAKOUT_BARS")
        val candleAge = ChronoUnit.SECONDS.between(latest.timestamp.plus(15, ChronoUnit.MINUTES), now) / 60.0
        if (candleAge < 0 || candleAge > 18) return wait("STALE_OR_INCOMPLETE_15M_CANDLE")
        if (sameSlotAverageVolume == null || !sameSlotAverageVolume.isFinite() || sameSlotAverageVolume <= 0)
            return wait("MISSING_VERIFIED_20_SESSION_VOLUME_BASELINE")
        if (recent.any { !it.close.isFinite() || it.close <= 0 }) return wait("INVALID_PRICE")
        if (listOf(latest.open, latest.high, latest.low, latest.close, latest.volume).any { !it.isFinite() } ||
            latest.high <= latest.low || latest.volume < 0) return wait("INVALID_CANDLE")
        val rvol = relativeVolume(latest.volume, sameSlotAverageVolume) ?: return wait("INVALID_VOLUME_BASELINE")
        if (rvol < 1.5) return wait("VOLUME_BELOW_THRESHOLD")
        val body = abs(latest.close - latest.open) / (latest.high - latest.low)
        if (body < 0.5) return wait("WEAK_CANDLE_BODY")

        val closes = recent.map { it.close }
        val fast = ema(closes, 20).lastOrNull() ?: return wait("INSUFFICIENT_EMA_HISTORY")
        val slow = ema(closes, 50).lastOrNull() ?: return wait("INSUFFICIENT_EMA_HISTORY")
        val (k, d) = stochRsi(closes)
        if (k.size < 2 || d.size < 2) return wait("INSUFFICIENT_STOCH_RSI_HISTORY")
        val bullishCross = k[k.lastIndex - 1] <= d[d.lastIndex - 1] && k.last() > d.last() && k.last() <= 20.0
        val bearishCross = k[k.lastIndex - 1] >= d[d.lastIndex - 1] && k.last() < d.last() && k.last() >= 80.0
        val prior = recent.takeLast(4).dropLast(1)
        val range = latest.high - latest.low
        val buy = fast > slow && latest.close > latest.open &&
            latest.close >= latest.high - 0.25 * range &&
            latest.close > prior.maxOf { it.high } && bullishCross
        val sell = fast < slow && latest.close < latest.open &&
            latest.close <= latest.low + 0.25 * range &&
            latest.close < prior.minOf { it.low } && bearishCross
        return PaperSignal(
            signal = if (buy) "PAPER_BUY" else if (sell) "PAPER_SELL" else "WAIT",
            reason = if (buy || sell) "15M_FILTERS_PASSED" else "NO_QUALIFYING_SETUP",
            relativeVolume = (rvol * 1000).toInt() / 1000.0,
            stochK = (k.last() * 100).toInt() / 100.0,
            stochD = (d.last() * 100).toInt() / 100.0
        )
    }

    private fun ema(values: List<Double>, period: Int): List<Double> {
        if (values.size < period) return emptyList()
        val out = mutableListOf(values.take(period).average())
        val alpha = 2.0 / (period + 1)
        values.drop(period).forEach { out.add(alpha * it + (1 - alpha) * out.last()) }
        return out
    }

    private fun rsi(values: List<Double>, period: Int = 14): List<Double> {
        if (values.size <= period) return emptyList()
        val changes = values.zipWithNext { a, b -> b - a }
        val gains = changes.map { maxOf(0.0, it) }
        val losses = changes.map { maxOf(0.0, -it) }
        var gain = gains.take(period).average()
        var loss = losses.take(period).average()
        val out = mutableListOf<Double>()
        for (i in period - 1 until changes.size) {
            if (i >= period) {
                gain = (gain * (period - 1) + gains[i]) / period
                loss = (loss * (period - 1) + losses[i]) / period
            }
            out.add(if (gain == 0.0 && loss == 0.0) 50.0 else if (loss == 0.0) 100.0 else 100.0 - 100.0 / (1 + gain / loss))
        }
        return out
    }

    private fun stochRsi(values: List<Double>): Pair<List<Double>, List<Double>> {
        val rsi = rsi(values)
        val raw = (13 until rsi.size).map { i ->
            val window = rsi.subList(i - 13, i + 1)
            val high = window.max()
            val low = window.min()
            if (high == low) 50.0 else 100.0 * (rsi[i] - low) / (high - low)
        }
        val k = raw.windowed(3).map { it.average() }
        val d = k.windowed(3).map { it.average() }
        return k to d
    }
}
