package com.nsemomentum.paper

import java.time.Instant
import kotlin.math.abs

/** Port of experimental_15m_index_trend: 21 session-close SMA, EMA20/50,
 * Stoch RSI 14/14/3/3 cross, candle body/edge and three-bar breakout. No index RVOL. */
object IndexPaperStrategy {
    fun verifiedHistory(bars: List<Candle>, sessions: List<MarketSession>): Boolean {
        if (sessions.size != 21 || sessions.map { it.date }.distinct().size != 21 ||
            sessions.any { !it.isRegular() }) return false
        return sessions.all { session ->
            val day = bars.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() == session.date }
            day.size == 25 && day.all { PaperStrategy.validCandle(it) && it.high > it.low } &&
                day.map { it.timestamp }.toSet() == session.slots().toSet()
        }
    }

    fun evaluate(bars: List<Candle>, sessions: List<MarketSession>, now: Instant): PaperSignal {
        fun wait(reason: String) = PaperSignal(reason = reason)
        if (!verifiedHistory(bars, sessions)) return wait("NO_VERIFIED_21_SESSION_HISTORY")
        if (bars.map { it.timestamp }.distinct().size != bars.size ||
            bars.zipWithNext().any { (a, b) -> a.timestamp >= b.timestamp }) return wait("INVALID_INDEX_HISTORY")
        if (bars.any { !PaperStrategy.validCandle(it) || it.high <= it.low }) return wait("INVALID_CANDLE")
        val date = now.atZone(MarketSession.ZONE).toLocalDate()
        if (sessions.any { it.date >= date }) return wait("INVALID_INDEX_HISTORY")
        val today = bars.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() == date }
        if (today.size < 4) return wait("INSUFFICIENT_SAME_SESSION_BREAKOUT_BARS")
        val latest = today.last()
        val age = java.time.Duration.between(latest.timestamp.plusSeconds(900), now).seconds
        if (age !in 0..1080) return wait("STALE_OR_INCOMPLETE_15M_CANDLE")
        val start = date.atTime(9, 15).atZone(MarketSession.ZONE).toInstant()
        if (today.map { it.timestamp } != (today.indices).map { start.plusSeconds(it * 900L) } || today.size > 25)
            return wait("NONCONTIGUOUS_15M_CANDLES")
        val closes = bars.map { it.close }
        val technicals = PaperStrategy.context(bars) ?: return wait("INSUFFICIENT_INDICATOR_HISTORY")
        val sma21 = sessions.map { session -> bars.single { it.timestamp == session.slots().last() }.close }.average()
        val (k, d) = PaperStrategy.stochRsi(closes)
        val bullishCross = k[k.lastIndex - 1] <= d[d.lastIndex - 1] && k.last() > d.last() && k.last() <= 20
        val bearishCross = k[k.lastIndex - 1] >= d[d.lastIndex - 1] && k.last() < d.last() && k.last() >= 80
        val range = latest.high - latest.low
        if (abs(latest.close - latest.open) / range < 0.5) return wait("NO_QUALIFYING_15M_SHIFT")
        val prior = today.takeLast(4).dropLast(1)
        val buy = technicals.ema20 > technicals.ema50 && latest.close > sma21 && bullishCross &&
            latest.close > latest.open && latest.close >= latest.high - 0.25 * range && latest.close > prior.maxOf { it.high }
        val sell = technicals.ema20 < technicals.ema50 && latest.close < sma21 && bearishCross &&
            latest.close < latest.open && latest.close <= latest.low + 0.25 * range && latest.close < prior.minOf { it.low }
        return PaperSignal(if (buy) "PAPER_BUY" else if (sell) "PAPER_SELL" else "WAIT",
            if (buy || sell) "STOCH_RSI_CROSS_AND_TREND_FILTERS_PASSED" else "NO_QUALIFYING_15M_SHIFT")
    }
}
