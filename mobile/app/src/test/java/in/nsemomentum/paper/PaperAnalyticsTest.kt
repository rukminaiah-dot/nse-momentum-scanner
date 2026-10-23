package com.nsemomentum.paper

import java.time.Instant
import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test

class PaperAnalyticsTest {
    private val start = LocalDate.parse("2026-10-23").atTime(10, 0).atZone(MarketSession.ZONE).toInstant()
    private fun candle(time: Instant, open: Double = 100.0, close: Double = 101.0) =
        Candle(time, open, maxOf(open, close) + 1, minOf(open, close) - 1, close, 1000.0)

    @Test fun signalUsesNextCandleOpenToCloseForLongAndShort() {
        val long = PaperOutcomeLogic.scoreNextCandle(PendingPaperSignal("ABC", 1, start), candle(start.plusSeconds(900), 100.0, 101.0))!!
        assertEquals(1.0, long.returnPercent, 1e-9)
        val short = PaperOutcomeLogic.scoreNextCandle(PendingPaperSignal("ABC", -1, start), candle(start.plusSeconds(900), 100.0, 99.0))!!
        assertEquals(1.0, short.returnPercent, 1e-9)
    }

    @Test fun noOutcomeWhenNextCandleWasMissedOrCrossesSession() {
        assertNull(PaperOutcomeLogic.scoreNextCandle(
            PendingPaperSignal("ABC", 1, start), candle(start.plusSeconds(1800))
        ))
        val lastBar = LocalDate.parse("2026-10-23").atTime(15, 15).atZone(MarketSession.ZONE).toInstant()
        assertNull(PaperOutcomeLogic.scoreNextCandle(
            PendingPaperSignal("ABC", 1, lastBar), candle(lastBar.plusSeconds(900))
        ))
    }

    @Test fun onlyBuySellSignalsBecomePendingAndFinalSlotCannotEnter() {
        val candidate = ScanRow("ABC", signal = "PAPER_BUY", reason = "test", candle = candle(start))
        assertEquals(PendingPaperSignal("ABC", 1, start), PaperOutcomeLogic.pendingFrom(candidate))
        assertEquals(-1, PaperOutcomeLogic.pendingFrom(candidate.copy(signal = "PAPER_SELL"))!!.direction)
        assertNull(PaperOutcomeLogic.pendingFrom(candidate.copy(signal = "WAIT")))
        val lastBar = LocalDate.parse("2026-10-23").atTime(15, 15).atZone(MarketSession.ZONE).toInstant()
        assertNull(PaperOutcomeLogic.pendingFrom(candidate.copy(candle = candle(lastBar))))
    }

    @Test fun weeklySummaryIncludesSevenCalendarDaysAndCountsOnlyClosedSignals() {
        val outcomes = listOf(
            PaperOutcome("A", 1, start, start.plusSeconds(900), 100.0, 101.0, 1.0),
            PaperOutcome("B", -1, start, start.plusSeconds(900), 100.0, 101.0, -1.0),
            PaperOutcome("C", 1, start.minusSeconds(86400), start.minusSeconds(85500), 100.0, 100.5, 0.5)
        )
        val summary = PaperOutcomeLogic.summarize(outcomes, LocalDate.parse("2026-10-17"), LocalDate.parse("2026-10-23"))
        assertEquals(7, summary.size)
        assertEquals(2, summary.last().closedSignals)
        assertEquals(0.0, summary.last().averageReturnPercent, 1e-9)
        assertEquals(50.0, summary.last().successPercent, 1e-9)
        assertEquals(0, summary.first().closedSignals)
    }
}
