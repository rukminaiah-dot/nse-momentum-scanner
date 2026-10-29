package com.nsemomentum.paper

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class MarketRefreshTest {
    private val start = Instant.parse("2026-10-30T05:00:00Z")
    private fun reading(signal: String, time: Instant = start) = IndexReading("NIFTY50",IndexDataState.LIVE,
        Candle(time,100.0,102.0,99.0,101.0,0.0), signal=signal, refreshedAt=time.plusSeconds(301))
    @Test fun temporaryFailureRetainsLastGoodCandleAndRefreshTime() {
        val old = reading("BULLISH")
        val merged = mergeIndexReading(old,IndexReading("NIFTY50",reason="NETWORK_ERROR"))
        assertEquals(old.candle,merged.candle)
        assertEquals(old.refreshedAt,merged.refreshedAt)
        assertEquals("NETWORK_ERROR",merged.lastError)
    }
    @Test fun confirmedReversalHasItsOwnTimestampAndOldReportsCannotReplaceIt() {
        val old = reading("BULLISH")
        val fresh = reading("BEARISH",start.plusSeconds(300))
        val changed = mergeIndexReading(old,fresh)
        assertEquals("BULLISH",changed.previousDirection)
        assertEquals(start.plusSeconds(600),changed.changedAt)
        assertEquals(changed,mergeIndexReading(changed,old))
        val repeated = mergeIndexReading(changed,reading("BEARISH",start.plusSeconds(600)))
        assertEquals(changed.changedAt,repeated.changedAt)
    }
    @Test fun logRejectsFreeFormExceptions() {
        assertEquals("REQUEST_FAILED",DiagnosticLog.errorCode(Exception("Bearer secret-token-value")))
        assertEquals("RATE_LIMITED",DiagnosticLog.errorCode(Exception("RATE_LIMITED")))
    }
}
