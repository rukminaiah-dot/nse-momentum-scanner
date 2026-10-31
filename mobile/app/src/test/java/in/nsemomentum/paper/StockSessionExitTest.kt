package com.nsemomentum.paper

import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test

class StockSessionExitTest {
    private val date=LocalDate.parse("2026-10-30")
    private fun time(hour:Int,minute:Int,second:Int=0)=date.atTime(hour,minute,second).atZone(MarketSession.ZONE).toInstant()
    @Test fun exactCutoffBlocksEntriesAndRequestsAllActiveExits() {
        val bought=time(11,28)
        assertFalse(StockSessionExit.entriesClosed(time(15,9,59)))
        assertTrue(StockSessionExit.entriesClosed(time(15,10)))
        assertFalse(StockSessionExit.due(bought,time(15,9,59)))
        assertTrue(StockSessionExit.due(bought,time(15,10)))
        assertTrue(StockSessionExit.due(bought,time(15,10).plusSeconds(86400)))
        val old=bought.minusSeconds(86400)
        assertTrue(StockSessionExit.due(old,time(9,16)))
        val active=ReversalState(buy=100.0,buyAt=bought)
        val closed=ReversalStrategy.tick(active,101.0,null,null,time(15,10))
        assertEquals("SESSION_1510",closed.trades.single().reason)
        assertEquals(101.0,closed.trades.single().sell,0.0)
        val setup=ReversalState(watchDate=date.toString(),previousK=18.0,previousAt=time(15,9,59),observationGap=false)
        assertNull(ReversalStrategy.tick(setup,100.0,25.0,20.0,time(15,10),100,150,true).confirmationAt)
    }
    @Test fun closedMarketOrStaleQuotesCannotBeBackdatedAsExits() {
        val now=time(15,10)
        val q=LiveQuote("NSE_EQ|TEST",100.0,101.0,now,now)
        val live=LivePriceState(connected=true,markets=mapOf("NSE_EQ" to true))
        assertTrue(StockSessionExit.fresh(q,live,now))
        assertFalse(StockSessionExit.fresh(q,live.copy(connected=false),now))
        assertFalse(StockSessionExit.fresh(q,live,now.plusSeconds(31)))
        assertFalse(StockSessionExit.fresh(q,live.copy(markets=mapOf("NSE_EQ" to false)),now))
    }
}
