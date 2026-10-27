package com.nsemomentum.paper

import java.time.Duration
import java.time.Instant

/** Presentation only: never changes strategy, qualification or outcome records. */
fun paperSignalDisplay(row: ScanRow?, now: Instant = Instant.now()): String {
    val stamp = row?.candle?.timestamp ?: return "WAIT · NO VERIFIED SCAN"
    val age = Duration.between(stamp.plusSeconds(900), now).seconds
    if (age !in 0..1080) return "WAIT · scan is stale; run a scan for a current signal"
    val signal = when (row.signal) {
        "PAPER_BUY" -> "BUY · PAPER"
        "PAPER_SELL" -> "SELL · PAPER"
        "PAPER_HOLD" -> "BUY ACTIVE · PAPER"
        else -> "WAIT"
    }
    val reason = when (row.reason) {
        "UPTREND_BULLISH_CROSS" -> "Uptrend + K crossed above D"
        "BEARISH_CROSS_EXIT" -> "K crossed below D after BUY"
        "BUY_ACTIVE_WAITING_BEARISH_CROSS" -> "Waiting for K to cross below D"
        "NOT_SHORTLISTED_TODAY" -> "Waiting for volume qualification"
        "EMA_TREND_NOT_UP" -> "EMA20 is not above EMA50"
        "NO_BULLISH_CROSS" -> "Waiting for K to cross above D"
        else -> row.reason
    }
    return "$signal · $reason"
}

fun stochasticGapDisplay(context: TechnicalContext): String {
    val gap = String.format(java.util.Locale.US, "%+.2f", context.gap)
    return "K−D gap $gap · ${context.momentum}"
}
