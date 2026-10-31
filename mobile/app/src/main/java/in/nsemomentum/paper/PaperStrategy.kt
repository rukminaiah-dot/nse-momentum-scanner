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

data class TechnicalContext(val ema20: Double, val ema50: Double, val stochK: Double, val stochD: Double,
                            val previousGap: Double? = null) {
    val gap: Double get() = stochK - stochD
    val momentum: String get() {
        val previous = previousGap ?: return if (gap > 0) "Upward momentum" else if (gap < 0) "Downward momentum" else "K and D together"
        if (gap > 0 && previous <= 0) return "New upward crossover"
        if (gap < 0 && previous >= 0) return "New downward crossover"
        if (gap == 0.0) return "K and D together"
        val change = abs(gap) - abs(previous)
        val strength = if (change > 0.01) "strengthening" else if (change < -0.01) "weakening" else "steady"
        return (if (gap > 0) "Upward" else "Downward") + " momentum " + strength
    }
}

data class PaperSignal(
    val signal: String = "WAIT",
    val reason: String,
    val relativeVolume: Double? = null,
    val stochK: Double? = null,
    val stochD: Double? = null
)

object PaperStrategy {
    private val marketZone = ZoneId.of("Asia/Kolkata")

    /** Exactly the preceding 20 exchange-verified sessions; missing sessions are never substituted. */
    fun sameSlotAverage(current: Candle, priorCandles: List<Candle>, sessions: List<MarketSession>): Double? {
        if (!validCandle(current) || sessions.size != 20 || sessions.any { !it.isRegular() } ||
            sessions.map { it.date }.distinct().size != 20) return null
        val local = current.timestamp.atZone(marketZone)
        if (sessions.any { it.date >= local.toLocalDate() }) return null
        val slot = local.toLocalTime()
        if (slot.second != 0 || slot.nano != 0 || slot < LocalTime.of(9, 15) ||
            slot >= LocalTime.of(15, 30) || (slot.hour * 60 + slot.minute - 555) % 15 != 0) return null
        val volumes = sessions.map { session ->
            val bars = priorCandles.filter { it.timestamp.atZone(marketZone).toLocalDate() == session.date }
            if (bars.size != 25 || bars.any { !validCandle(it) } ||
                bars.map { it.timestamp }.toSet() != session.slots().toSet()) return null
            bars.single { it.timestamp.atZone(marketZone).toLocalTime() == slot }.volume
        }
        return volumes.average().takeIf { it > 0 && it.isFinite() }
    }

    fun validCandle(bar: Candle): Boolean =
        listOf(bar.open, bar.high, bar.low, bar.close, bar.volume).all { it.isFinite() } &&
            minOf(bar.open, bar.high, bar.low, bar.close) > 0 && bar.volume >= 0 &&
            bar.high >= maxOf(bar.open, bar.close) && bar.low <= minOf(bar.open, bar.close) &&
            bar.high >= bar.low

    fun context(bars: List<Candle>): TechnicalContext? {
        if (bars.size < 52 || bars.any { !validCandle(it) }) return null
        val closes = bars.map { it.close }
        val (k, d) = stochRsi(closes)
        return TechnicalContext(ema(closes, 20).last(), ema(closes, 50).last(), k.last(), d.last(), k[k.lastIndex - 1] - d[d.lastIndex - 1])
    }

    fun relativeVolume(currentVolume: Double, baseline: Double): Double? =
        if (currentVolume >= 0 && baseline > 0 && currentVolume.isFinite() && baseline.isFinite())
            currentVolume / baseline else null

    /** Simple paper-only crossover strategy after volume qualification, using full verified history. */
    fun evaluate(bars: List<Candle>, now: Instant, sameSlotAverageVolume: Double?,
                 qualifiedToday: Boolean = false, hasActiveBuy: Boolean = false): PaperSignal {
        fun wait(reason: String) = PaperSignal(reason = reason)
        if (bars.size < 52) return wait("INSUFFICIENT_15M_HISTORY")
        val recent = bars.takeLast(52)
        if (recent.map { it.timestamp }.toSet().size != recent.size) return wait("DUPLICATE_15M_CANDLE")
        for ((a, b) in recent.zipWithNext()) {
            val gap = ChronoUnit.MINUTES.between(a.timestamp, b.timestamp)
            val sameDate = a.timestamp.atZone(marketZone).toLocalDate() == b.timestamp.atZone(marketZone).toLocalDate()
            if (gap <= 0) return wait("UNSORTED_15M_HISTORY")
            if (sameDate && gap != 15L) return wait("NONCONTIGUOUS_15M_CANDLES")
        }
        val latest = recent.last()
        val candleAge = ChronoUnit.SECONDS.between(latest.timestamp.plus(15, ChronoUnit.MINUTES), now) / 60.0
        if (candleAge < 0 || candleAge > 18 || latest.timestamp.atZone(marketZone).toLocalDate() != now.atZone(marketZone).toLocalDate())
            return wait("STALE_OR_INCOMPLETE_15M_CANDLE")
        if (bars.any { !validCandle(it) }) return wait("INVALID_CANDLE")
        val rvol = sameSlotAverageVolume?.let { relativeVolume(latest.volume, it) }
        if (!qualifiedToday && !hasActiveBuy && (rvol == null || rvol < 1.5)) return wait("NOT_SHORTLISTED_TODAY")
        if (StockSessionExit.entriesClosed(now)) return wait("SESSION_1510_WAITING_FRESH_PRICE_EXIT")
        val closes = bars.map { it.close }
        val (k, d) = stochRsi(closes)
        if (k.size < 2 || d.size < 2) return wait("INSUFFICIENT_STOCH_RSI_HISTORY")
        val decision = crossoverSignal( k[k.lastIndex - 1], d[d.lastIndex - 1], k.last(), d.last(), hasActiveBuy)
        return decision.copy(relativeVolume = rvol, stochK = k.last(), stochD = d.last())
    }

    internal fun crossoverSignal(previousK: Double, previousD: Double,
                                 k: Double, d: Double, hasActiveBuy: Boolean): PaperSignal {
        val bullishCross = k > d
        return when {
            hasActiveBuy && k < d -> PaperSignal("PAPER_SELL", "BEARISH_CROSS_EXIT")
            hasActiveBuy -> PaperSignal("PAPER_HOLD", "BUY_ACTIVE_WAITING_BEARISH_CROSS")
            bullishCross -> PaperSignal("PAPER_BUY", "BULLISH_ALIGNMENT")
            else -> PaperSignal(reason = "NO_BULLISH_CROSS")
        }
    }

    internal fun ema(values: List<Double>, period: Int): List<Double> {
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

    internal fun stochRsi(values: List<Double>): Pair<List<Double>, List<Double>> {
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
