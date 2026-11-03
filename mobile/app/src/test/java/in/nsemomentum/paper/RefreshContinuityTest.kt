package com.nsemomentum.paper

import java.time.Instant
import org.junit.Assert.*
import org.junit.Test

class RefreshContinuityTest {
    private val at=Instant.parse("2026-11-03T04:00:00Z")
    private val key="NSE_EQ|TEST"
    @Test fun partialPriceFramesPreserveVolumeTimestampWithoutInventingFreshVolume() {
        val original=LiveQuote(key,100.0,99.0,at,at,1000,at)
        val partial=LiveQuote(key,101.0,99.0,at.plusSeconds(1),at.plusSeconds(1))
        val merged=LivePriceDecoder.merge(mapOf(key to original),mapOf(key to partial)).getValue(key)
        assertEquals(1000L,merged.volumeToday!!);assertEquals(at,merged.volumeAt)
        assertEquals(101.0,merged.price,0.0)
        val nextDay=LivePriceDecoder.merge(mapOf(key to original),mapOf(key to partial.copy(tradedAt=at.plusSeconds(86400)))).getValue(key)
        assertNull(nextDay.volumeToday)
    }
    @Test fun partialUpdatesKeepSixtySecondWindowButRealGapOrReconnectCannotConfirm() {
        val window=LiveVolumeWindow();var last:LiveQuote?=null
        for(i in 0L..120L) {
            val full=LiveQuote(key,100.0,99.0,at.plusSeconds(i),at.plusSeconds(i),1000+i*10,at.plusSeconds(i))
            last=LivePriceDecoder.merge(last?.let { mapOf(key to it) }.orEmpty(),mapOf(key to if(i%2==0L) full else full.copy(volumeToday=null,volumeAt=null))).getValue(key)
            assertTrue(window.ingest(last,at.plusSeconds(i),true,1))
        }
        assertEquals(600L,window.amount(at.plusSeconds(60),at.plusSeconds(120))!!)
        assertFalse(window.ingest(last,at.plusSeconds(126),true,1))
        assertNull(window.amount(at.plusSeconds(60),at.plusSeconds(120)))
        window.ingest(last,at.plusSeconds(120),true,2)
        assertNull(window.amount(at.plusSeconds(60),at.plusSeconds(120)))
    }
    @Test fun identifiedStockRemainsListedWhenKdReversesWithoutCreatingBuy() {
        val watch=ReversalStrategy.tick(ReversalState(),100.0,18.0,16.0,at)
        val reversed=ReversalStrategy.tick(watch,100.0,17.0,19.0,at.plusSeconds(1))
        assertNull(reversed.watchDate);assertEquals(at,reversed.identifiedAt);assertNull(reversed.buy)
        val row=ReversalRow(Stock("TEST",key),reversed,null,"")
        assertEquals(1,unifiedSignals(ReversalSnapshot(listOf(row)),at.plusSeconds(1)).size)
        assertTrue(unifiedSignals(ReversalSnapshot(listOf(row)),at.plusSeconds(86400)).isEmpty())
    }
    @Test fun openingIdentificationRemainsVisibleAfterOpeningWindowWithoutCreatingBuy() {
        val morning=Instant.parse("2026-11-03T03:50:00Z")
        val sample=OpeningSample(morning,true,100.0,99.0,98.0,30.0,20.0,null,null,null,false)
        val watch=OpeningMomentum.tick(OpeningState(),sample)
        assertEquals(morning,watch.identifiedAt);assertNull(watch.buy)
        val later=OpeningMomentum.tick(watch,sample.copy(at=morning.plusSeconds(1800),k=70.0,d=80.0))
        val row=ReversalRow(Stock("TEST",key),ReversalState(),null,"",later)
        assertEquals(PaperSource.OPENING,unifiedSignals(ReversalSnapshot(listOf(row)),morning.plusSeconds(1800)).single().source)
    }
    @Test fun staleMonitorAndFutureClockAreNotLabelledLive() {
        assertTrue(monitorStatus(at,true,at.plusSeconds(60)).contains("stale"))
        assertTrue(monitorStatus(at,true,at.minusSeconds(60)).contains("Clock changed"))
        val bytes=LivePriceDecoder.subscription(setOf(key),"unsub").utf8()
        assertTrue(bytes.contains("unsub"));assertFalse(bytes.contains("\"method\":\"sub\""))
    }
}
