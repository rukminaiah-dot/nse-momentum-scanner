package com.nsemomentum.paper

import java.time.Duration
import java.time.Instant

/** Presentation only: never changes strategy, qualification or outcome records. */
fun paperSignalDisplay(row: ScanRow?, now: Instant = Instant.now()): String {
    val stamp = row?.candle?.timestamp ?: return "WAIT · NO VERIFIED SCAN"
    val age = Duration.between(stamp.plusSeconds(900), now).seconds
    if (age !in 0..1080) return "WAIT · scan is stale; run a scan for a current signal"
    if (StockSessionExit.entriesClosed(now)) return "15:10 session cutoff · see recorded exit details; open trades await a fresh quote"
    val signal = when (row.signal) {
        "PAPER_BUY" -> "BUY · PAPER"
        "PAPER_SELL" -> "SELL · PAPER"
        "PAPER_HOLD" -> "BUY ACTIVE · PAPER"
        else -> "WAIT"
    }
    val reason = when (row.reason) {
        "BULLISH_ALIGNMENT" -> "Qualified today and K above D"
        "BEARISH_CROSS_EXIT" -> "K below D after BUY · exit"
        "BUY_ACTIVE_WAITING_BEARISH_CROSS" -> "Waiting for K to cross below D"
        "NOT_SHORTLISTED_TODAY" -> "Waiting for volume qualification"
        "EMA_TREND_NOT_UP" -> "EMA20 is not above EMA50"
        "SESSION_1510_WAITING_FRESH_PRICE_EXIT" -> "No new BUYs after 15:10; open trades exit on a fresh quote"
        "NO_BULLISH_CROSS" -> "Waiting for confirmed K above D"
        else -> row.reason
    }
    return "$signal · $reason"
}

fun stochasticGapDisplay(context: TechnicalContext): String {
    val gap = String.format(java.util.Locale.US, "%+.2f", context.gap)
    return "K−D gap $gap · ${context.momentum}"
}

/** Report completeness is distinct from qualification and from the live-price socket. */
fun scanHealthSummary(report:ScanReport?):String {
    if(report==null) return "No verified scan result loaded"
    val ready=report.rows.count { it.candle!=null }
    val buy=report.rows.count { it.signal=="PAPER_BUY" };val sell=report.rows.count { it.signal=="PAPER_SELL" }
    val hold=report.rows.count { it.signal=="PAPER_HOLD" }
    val failures=report.rows.filter { it.candle==null }.groupingBy { it.reason }.eachCount().entries.sortedByDescending { it.value }.take(3)
    return "Scan ${report.scanTime} · verified $ready/${report.rows.size} · BUY $buy · SELL $sell · HOLD $hold"+
        if(failures.isEmpty()) "" else "\nBlocked: "+failures.joinToString(" · ") { "${it.key}: ${it.value}" }
}
