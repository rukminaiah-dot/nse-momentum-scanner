package com.nsemomentum.paper

import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test

class DisplayOnlyVolumeTest {
    private val today=regular(LocalDate.parse("2026-10-22"))
    private val prior=(1L..20L).map { regular(today.date.minusDays(it)) }
    private fun history()=prior.flatMapIndexed { i,s -> s.slots().mapIndexed { slot,at -> bar(at,if(slot==1) i+1.0 else 10000.0) } }

    @Test fun ratioUsesCompletedMatchingSlotAcrossExactlyTwentySessions() {
        val current=bar(today.start.plusSeconds(900),21.0)
        val bars=history()+bar(today.start,1000.0)+current+bar(today.start.plusSeconds(1800),999999.0)
        val reading=completedCandleVolume(bars,today.start.plusSeconds(1801))!!
        assertEquals(current.timestamp,reading.candleStart)
        assertEquals(21.0,reading.volume,0.0)
        assertEquals(10.5,reading.average!!,0.0)
        assertEquals(2.0,reading.ratio!!,0.0)
    }
    @Test fun missingAndZeroBaselinesShowUnavailableWithoutInventingVolumes() {
        val current=bar(today.start,50.0)
        val incomplete=completedCandleVolume(history().drop(1)+current,today.start.plusSeconds(901))!!
        assertNull(incomplete.average);assertNull(incomplete.ratio)
        val zeros=history().map { it.copy(volume=0.0) }
        assertTrue(PaperStrategy.verifiedSessions(zeros,prior))
        assertNull(completedCandleVolume(zeros+current,today.start.plusSeconds(901))!!.ratio)
        assertNull(completedCandleVolume(history()+current,today.start.plusSeconds(899)))
        assertNull(completedCandleVolume(history()+current,today.start.plusSeconds(1801)))
    }
    @Test fun volumeRatioNeverChangesAnEligibleKdDecision() {
        for(active in listOf(false,true)) for(baseline in listOf<Double?>(null,0.0,10.0,1000000.0)) {
            val closes=prior.sortedBy { it.date }.flatMap { s -> s.slots().map { at -> Candle(at,100.0,101.0,99.0,100.0,100.0) } }
            val bars=closes+Candle(today.start,100.0,101.0,99.0,100.8,0.0)
            val result=PaperStrategy.evaluate(bars,today.start.plusSeconds(901),baseline,qualifiedToday=false,hasActiveBuy=active)
            assertEquals(if(active) "PAPER_HOLD" else "PAPER_BUY",result.signal)
        }
    }
}
