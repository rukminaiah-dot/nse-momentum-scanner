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
        else -> "WAIT"
    }
    return "$signal · ${row.reason}"
}
