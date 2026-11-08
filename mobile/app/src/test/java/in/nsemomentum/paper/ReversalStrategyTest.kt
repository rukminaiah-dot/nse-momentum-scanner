package com.nsemomentum.paper

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class ReversalStrategyTest {
    private val now=Instant.parse("2026-10-30T05:00:00Z")
    private fun tick(s:ReversalState,k:Double?,d:Double?,seconds:Long,price:Double=100.0,before:Long?=100,after:Long?=null,continuous:Boolean=true,volumeRatio:Double?=null)=
        ReversalStrategy.tick(s,price,k,d,now.plusSeconds(seconds),before,after,continuous,volumeRatio)
    private fun confirmed():ReversalState {
        val watch=tick(ReversalState(),18.0,17.0,0)
        return tick(watch,20.01,20.0,1)
    }
    @Test fun observedBullishCrossBuysImmediatelyWithoutVolumeOrWait() {
        for(volume in listOf<Long?>(null,0,100)) {
            val watch=tick(ReversalState(),18.0,17.0,0)
            val buy=tick(watch,20.01,19.0,1,before=volume,after=0,continuous=false)
            assertEquals(100.0,buy.buy!!,0.0);assertEquals(now.plusSeconds(1),buy.buyAt)
            assertNull(buy.confirmationAt);assertEquals("BUY_CONFIRMED_K_CROSS_20",buy.action)
            assertEquals("KD_CROSS_V3",buy.entryPolicy)
            assertEquals(buy.buyAt,tick(buy,30.0,20.0,2).buyAt)
        }
    }
    @Test fun missingBearishOrUnobservedCrossStillCannotBuy() {
        val watch=tick(ReversalState(),18.0,17.0,0)
        assertNull(tick(watch,20.0,18.0,1).buy)
        assertNull(tick(watch,21.0,22.0,1).buy)
        val gap=tick(watch,null,null,1)
        assertEquals(18.0,gap.previousK!!,0.0)
        assertNull(tick(gap,27.12,16.89,2).buy)
        assertNull(tick(watch,25.0,20.0,40).buy)
        assertNull(tick(ReversalState(),75.0,60.0,0).buy)
        val bearish=tick(ReversalState(),18.0,19.0,0)
        assertNull(tick(bearish,21.0,20.0,1).buy)
    }
    @Test fun profitReviewHoldsAtTwoPercentAndExitsOnVerifiedWeakVolume() {
        val bought = confirmed()
        assertNotNull(tick(bought, 25.0, 24.0, 2, price = 101.99, volumeRatio = 1.0).buy)
        val atTwoPercent = tick(bought, 25.0, 24.0, 2, price = 102.0, volumeRatio = 1.5)
        assertEquals("BUY_ACTIVE_PROFIT_REVIEW", atTwoPercent.action)
        val higher = tick(atTwoPercent, 25.0, 24.0, 3, price = 104.0)
        assertNotNull(higher.buy)
        val closed = tick(higher, 25.0, 24.0, 4, price = 103.0, volumeRatio = 1.49)
        assertNull(closed.buy)
        assertEquals("VOLUME_BELOW_1_5X_AFTER_2_PERCENT", closed.trades.single().reason)
        assertEquals(103.0, closed.trades.single().sell, 0.0)
        assertEquals(1, tick(closed, null, null, 5).trades.size)
        assertNotNull(tick(bought, null, null, 2, price = 99.01).buy)
        assertEquals("STOP_1_PERCENT", tick(bought, null, null, 2, price = 99.0).trades.single().reason)
    }
    @Test fun bearishReadingAutomaticallySellsManualAndAutomaticPositions() {
        val bought = confirmed()
        assertNotNull(tick(bought, 25.0, 25.0, 2).buy)
        assertNotNull(tick(bought, -1.0, 25.0, 2).buy)
        assertEquals("KD_BEARISH", tick(bought, 25.0, 26.0, 2).trades.single().reason)
        val manual = bought.copy(manual = true, quantity = 4, manualWaitUntil = now.plusSeconds(30))
        val closed = tick(manual, 25.0, 26.0, 2)
        assertNull(closed.buy)
        assertEquals("KD_BEARISH", closed.trades.single().reason)
        assertEquals(4, closed.trades.single().quantity)
    }
    @Test fun initialStopUsesActualQuoteWithoutKdAndDayChangeCannotInventBuy() {
        val active=ReversalState(buy=100.0,buyAt=now)
        val closed=tick(active,null,null,1,price=98.5)
        assertEquals("STOP_1_PERCENT",closed.trades.single().reason)
        assertEquals(-1.5,closed.trades.single().gross,0.0)
        val watch=tick(ReversalState(),18.0,17.0,0)
        val tomorrow=ReversalStrategy.tick(watch,100.0,25.0,20.0,now.plusSeconds(86400),100,150,true)
        assertNull(tomorrow.buy);assertNull(tomorrow.confirmationAt)
    }
}

