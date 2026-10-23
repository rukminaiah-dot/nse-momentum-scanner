package com.nsemomentum.paper

import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate

class IndexPaperStrategyTest {
    private val date = LocalDate.parse("2026-10-22")
    private val sessions = generateSequence(date.minusDays(1)) { it.minusDays(1) }
        .filter { it.dayOfWeek.value <= 5 }.take(21).map { regular(it) }.toList()
    private val history = sessions.flatMap { s -> s.slots().map { bar(it).copy(volume = 0.0) } }.sortedBy { it.timestamp }
    private val today = regular(date).slots().take(4).map { bar(it).copy(volume = 0.0) }
    private val now = today.last().timestamp.plusSeconds(901)
    @Test fun zeroVolumeIndexIsValidAndHasNoRvol() {
        val result = IndexPaperStrategy.evaluate(history + today, sessions, now)
        assertEquals("NO_QUALIFYING_15M_SHIFT", result.reason)
        assertNull(result.relativeVolume)
    }
    @Test fun missingOrDuplicateSessionBarsFailClosed() {
        assertFalse(IndexPaperStrategy.verifiedHistory(history.drop(1), sessions))
        assertFalse(IndexPaperStrategy.verifiedHistory(history + history.first(), sessions))
        assertFalse(IndexPaperStrategy.verifiedHistory(history, sessions.drop(1)))
    }
    @Test fun missingCurrentBarAndStaleDataCannotSignal() {
        assertEquals("NONCONTIGUOUS_15M_CANDLES", IndexPaperStrategy.evaluate(history + today +
            bar(today.last().timestamp.plusSeconds(1800)), sessions, now.plusSeconds(1800)).reason)
        assertEquals("STALE_OR_INCOMPLETE_15M_CANDLE", IndexPaperStrategy.evaluate(history + today, sessions, now.plusSeconds(1200)).reason)
    }
}
