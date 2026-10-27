package com.nsemomentum.paper

import java.time.Instant
import org.junit.Assert.*
import org.junit.Test

class PaperSignalDisplayTest {
    private val stamp = Instant.parse("2026-10-26T04:30:00Z")
    private fun row(signal: String) = ScanRow("TEST", signal = signal, reason = "15M_FILTERS_PASSED",
        candle = Candle(stamp, 100.0, 102.0, 99.0, 101.0, 200.0))
    @Test fun displaysFreshBuyAndSellWithReason() {
        assertTrue(paperSignalDisplay(row("PAPER_BUY"), stamp.plusSeconds(900)).startsWith("BUY · PAPER"))
        assertTrue(paperSignalDisplay(row("PAPER_SELL"), stamp.plusSeconds(900)).startsWith("SELL · PAPER"))
        assertTrue(paperSignalDisplay(row("WAIT"), stamp.plusSeconds(900)).contains("15M_FILTERS_PASSED"))
    }
    @Test fun missingStaleAndIncompleteCandlesCannotDisplayCurrentBuy() {
        assertTrue(paperSignalDisplay(null, stamp).startsWith("WAIT"))
        assertTrue(paperSignalDisplay(row("PAPER_BUY"), stamp.plusSeconds(899)).startsWith("WAIT"))
        assertTrue(paperSignalDisplay(row("PAPER_BUY"), stamp.plusSeconds(1981)).startsWith("WAIT"))
    }
}
