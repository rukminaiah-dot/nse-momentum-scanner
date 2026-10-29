package com.nsemomentum.paper

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class ReversalStrategyTest {
    private val now=Instant.parse("2026-10-30T05:00:00Z")
    private fun tick(s: ReversalState,k:Double,d:Double,price:Double=100.0,seconds:Long=1) = ReversalStrategy.tick(s,price,k,d,now.plusSeconds(seconds))
    @Test fun shortlistBelowTwentyThenBuyOnLiveCrossWithoutGapOrVolumeGate() {
        val watch=tick(ReversalState(),18.0,17.0)
        assertNotNull(watch.watchDate)
        val bought=tick(watch,20.01,20.0,101.0,2)
        assertEquals(101.0,bought.buy!!,0.0)
        assertEquals("BUY_LIVE_CROSS_20",bought.action)
        val repeated=tick(bought,25.0,24.0,102.0,3)
        assertEquals(bought.buyAt,repeated.buyAt)
        assertTrue(repeated.trades.isEmpty())
    }
    @Test fun highFirstReadingOrKBelowDOrEqualityCannotBuy() {
        assertNull(tick(ReversalState(),75.0,60.0).buy)
        val watch=tick(ReversalState(),20.0,19.0)
        assertNull(tick(watch,21.0,22.0,seconds=2).buy)
        assertNull(tick(watch,20.0,19.0,seconds=2).buy)
        assertNull(tick(watch,21.0,21.0,seconds=2).buy)
        assertNull(tick(ReversalState(),18.0,19.0).watchDate)
    }
    @Test fun reconnectAndRestartDoNotInventCrossings() {
        val watch=tick(ReversalState(),18.0,17.0)
        assertNull(tick(watch,25.0,20.0,seconds=40).buy)
        assertNull(tick(watch.copy(previousK=null,previousAt=null),25.0,20.0,seconds=2).buy)
        val nextDay=ReversalStrategy.tick(watch,100.0,25.0,20.0,now.plusSeconds(86400))
        assertNull(nextDay.buy)
        assertNull(nextDay.watchDate)
    }
    @Test fun stopLossUsesActualObservedPriceEvenWithoutKdAndCannotDuplicateExit() {
        val active=ReversalState(buy=100.0,buyAt=now)
        val closed=ReversalStrategy.tick(active,98.5,null,null,now.plusSeconds(1))
        assertNull(closed.buy)
        assertEquals("STOP_1_PERCENT",closed.trades.single().reason)
        assertEquals(-1.5,closed.trades.single().gross,0.0)
        assertEquals(1,ReversalStrategy.tick(closed,98.0,null,null,now.plusSeconds(2)).trades.size)
        assertNotNull(ReversalStrategy.tick(active,99.01,null,null,now.plusSeconds(1)).buy)
    }
    @Test fun eightyMustBeObservedBeforeExitAndStopHasPriority() {
        val active=ReversalState(buy=100.0,buyAt=now)
        assertNotNull(tick(active,70.0,75.0).buy)
        val reached=tick(active,80.0,70.0,103.0)
        assertTrue(reached.reached80)
        val closed=tick(reached,79.9,70.0,102.0,2)
        assertEquals("K_BACK_BELOW_80",closed.trades.single().reason)
        assertEquals(2.0,closed.trades.single().percent,0.0)
        assertEquals("STOP_1_PERCENT",tick(reached,79.0,70.0,98.0,2).trades.single().reason)
    }
}
