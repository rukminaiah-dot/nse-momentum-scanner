package com.nsemomentum.paper

import java.time.Instant
import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test

class PaperStrategyTest {
    private val today = regular(LocalDate.parse("2026-10-22"))
    private val sessions = (1L..20L).map { regular(today.date.minusDays(it)) } // Dates supplied by exchange, not weekday inference.
    private val current = bar(today.start)
    private fun history(): List<Candle> = sessions.flatMapIndexed { i, session -> session.slots().map { bar(it, i + 1.0) } }

    @Test fun exactTwentyVerifiedSessionsAreAveraged() {
        assertEquals(10.5, PaperStrategy.sameSlotAverage(current, history(), sessions)!!, 0.0001)
    }
    @Test fun nineteenSessionsAreRejected() {
        assertNull(PaperStrategy.sameSlotAverage(current, history(), sessions.dropLast(1)))
    }
    @Test fun missingSlotCannotBeReplacedByOlderSession() {
        val old = regular(today.date.minusDays(21))
        val bars = history().filterNot { it.timestamp == sessions.first().start } + old.slots().map { bar(it) }
        assertNull(PaperStrategy.sameSlotAverage(current, bars, sessions))
    }
    @Test fun missingOtherSlotInvalidatesFullSession() {
        assertNull(PaperStrategy.sameSlotAverage(current, history().drop(1), sessions))
    }
    @Test fun duplicatesAreRejectedBeforeAveraging() {
        assertNull(PaperStrategy.sameSlotAverage(current, history() + history().first(), sessions))
    }
    @Test fun holidaySkippedByCalendarDoesNotRequireStockData() {
        val holiday = sessions.first().date
        val verified = sessions.drop(1) + regular(today.date.minusDays(21))
        val bars = history().filterNot { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() == holiday } +
            verified.last().slots().map { bar(it) }
        assertNotNull(PaperStrategy.sameSlotAverage(current, bars, verified))
    }
    @Test fun invalidAndOffGridBarsAreRejected() {
        assertFalse(PaperStrategy.validCandle(current.copy(low = -1.0)))
        assertFalse(PaperStrategy.validCandle(current.copy(high = Double.NaN)))
        assertTrue(PaperStrategy.validCandle(current.copy(open = 10.0, high = 10.0, low = 10.0, close = 10.0)))
        assertNull(PaperStrategy.sameSlotAverage(current.copy(timestamp = current.timestamp.plusSeconds(1)), history(), sessions))
    }
    @Test fun exactCandleBoundaryAndCloseGrace() {
        assertNull(today.completedSlot(today.start.plusSeconds(899)))
        assertEquals(today.start, today.completedSlot(today.start.plusSeconds(900)))
        assertEquals(today.start.plusSeconds(900), today.completedSlot(today.start.plusSeconds(1800)))
        assertEquals(today.slots().last(), today.completedSlot(today.end.plusSeconds(180)))
        assertNull(today.completedSlot(today.end.plusSeconds(181)))
    }
    @Test fun specialAndDuplicateSessionsCannotBeBaselines() {
        assertNull(PaperStrategy.sameSlotAverage(current, history(), sessions.dropLast(1) + sessions.first()))
        val special = sessions.first().copy(end = sessions.first().end.minusSeconds(900))
        assertNull(PaperStrategy.sameSlotAverage(current, history(), sessions.drop(1) + special))
    }
    @Test fun contextUsesHistoryAndReturnsIndicators() {
        val context = PaperStrategy.context(history().sortedBy { it.timestamp })!!
        assertEquals(10.5, context.ema20, 0.0001)
        assertEquals(50.0, context.stochK, 0.0001)
    }
    @Test fun insufficientBarsNeverProduceEntry() {
        assertEquals("INSUFFICIENT_15M_HISTORY", PaperStrategy.evaluate(listOf(current), today.end, 10.0).reason)
    }
    @Test fun zeroAndInvalidBaselinesDoNotProduceRvol() {
        assertNull(PaperStrategy.relativeVolume(10.0, 0.0))
        assertNull(PaperStrategy.relativeVolume(Double.NaN, 10.0))
        assertEquals(1.5, PaperStrategy.relativeVolume(15.0, 10.0)!!, 0.0)
    }
}

internal fun regular(date: LocalDate): MarketSession = MarketSession(date,
    date.atTime(9, 15).atZone(MarketSession.ZONE).toInstant(), date.atTime(15, 30).atZone(MarketSession.ZONE).toInstant())
internal fun bar(time: Instant, volume: Double = 100.0) = Candle(time, 10.0, 11.0, 9.0, 10.5, volume)
