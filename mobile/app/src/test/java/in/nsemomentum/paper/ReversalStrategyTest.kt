package com.nsemomentum.paper

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class ReversalStrategyTest {
    private val now=Instant.parse("2026-10-30T05:00:00Z")
    private fun tick(s:ReversalState,k:Double?,d:Double?,seconds:Long,price:Double=100.0,before:Long?=100,after:Long?=null,continuous:Boolean=true)=
        ReversalStrategy.tick(s,price,k,d,now.plusSeconds(seconds),before,after,continuous)
    private fun pending():ReversalState {
        val watch=tick(ReversalState(),18.0,17.0,0)
        return tick(watch,20.01,20.0,1)
    }
    private fun confirmed():ReversalState {
        var s=pending()
        for (i in 2L..61L) s=tick(s,25.0,20.0,i,after=150)
        return s
    }
    @Test fun crossStartsOneMinuteWaitAndOnlyGreaterVolumeCanBuy() {
        var s=pending()
        assertNull(s.buy);assertNotNull(s.confirmationAt)
        for(i in 2L..60L) s=tick(s,22.0,21.9,i,after=150)
        assertNull(s.buy)
        s=tick(s,22.0,21.9,61,price=101.0,after=150)
        assertEquals(101.0,s.buy!!,0.0);assertEquals(100L,s.beforeVolume!!);assertEquals(150L,s.afterVolume!!)
        assertEquals(s.buyAt,tick(s,40.0,35.0,62).buyAt)
        assertTrue(s.trades.isEmpty())
    }
    @Test fun equalLowerMissingAndZeroVolumeDoNotBuy() {
        for(after in listOf<Long?>(100,99,null)) {
            var s=pending();for(i in 2L..61L) s=tick(s,25.0,20.0,i,after=after)
            assertNull(s.buy)
        }
        val watch=tick(ReversalState(),18.0,17.0,0)
        for (before in listOf<Long?>(null,0)) assertNull(tick(watch,21.0,20.0,1,before=before).confirmationAt)
    }
    @Test fun reversalOrGapCancelsConfirmationAndRetainsLastValidK() {
        assertNull(tick(pending(),20.0,18.0,2).confirmationAt)
        assertNull(tick(pending(),25.0,26.0,2).confirmationAt)
        assertNull(tick(pending(),25.0,20.0,2,continuous=false).confirmationAt)
        val before=tick(ReversalState(),18.0,17.0,0)
        val gap=tick(before,null,null,1)
        assertEquals(18.0,gap.previousK!!,0.0)
        val recovered=tick(gap,27.12,16.89,2)
        assertNull(recovered.buy);assertNull(recovered.confirmationAt)
        assertTrue(recovered.action.contains("GAP"))
        assertNull(tick(before,25.0,20.0,40).confirmationAt)
        assertNull(tick(ReversalState(),75.0,60.0,0).buy)
    }
    @Test fun profitStopStepsNeverMoveDownAndIgnoreKdEighty() {
        var s=confirmed()
        assertEquals(-1.0,ReversalStrategy.stopPercent(100.0,100.49),0.0)
        for ((price,percent) in listOf(100.5 to .25,100.75 to .5,101.0 to .75,101.25 to 1.0)) {
            s=tick(s,79.0,85.0,62,price=price)
            assertNotNull(s.buy)
            assertEquals(percent,ReversalStrategy.stopPercent(s.buy!!,s.peakPrice!!),1e-8)
        }
        val lowered=tick(s,null,null,63,price=101.1)
        assertEquals(101.25,lowered.peakPrice!!,0.0)
        val closed=tick(lowered,null,null,64,price=100.9)
        assertNull(closed.buy);assertEquals("STEPPED_PROFIT_STOP",closed.trades.single().reason)
        assertEquals(100.9,closed.trades.single().sell,0.0)
        assertEquals(1,tick(closed,null,null,65,price=100.0).trades.size)
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
