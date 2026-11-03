package com.nsemomentum.paper

import java.time.Instant
import org.junit.Assert.*
import org.junit.Test

class PaperRecordEditsTest {
    private val at=Instant.parse("2026-11-03T04:00:00Z")
    private fun command(op:PaperOperation,price:Double?=100.0,qty:Int=2,stamp:Instant?=at)=PaperRecordEdit("TEST",PaperSource.REVERSAL,op,stamp,price,qty)
    @Test fun manualReversalStopsRequestSellAndNeverCloseWithoutUserRecord() {
        val signal=ReversalState(buy=100.0,buyAt=at)
        val bought=PaperRecordEdits.reversal(signal,command(PaperOperation.BUY,101.0),at.plusSeconds(1),true,30.0,20.0)
        assertTrue(bought.manual);assertEquals(2,bought.quantity)
        val stopped=ReversalStrategy.tick(bought,98.0,null,null,at.plusSeconds(2))
        assertNotNull(stopped.buy);assertTrue(stopped.trades.isEmpty());assertTrue(stopped.action.startsWith("SELL_REQUIRED"))
        val waited=PaperRecordEdits.reversal(stopped,command(PaperOperation.WAIT,null),at.plusSeconds(3),true,null,null)
        assertNotNull(waited.buy)
        val closed=PaperRecordEdits.reversal(waited,command(PaperOperation.SELL,99.0),at.plusSeconds(4),false,null,null)
        assertNull(closed.buy);assertEquals(-4.0,closed.trades.single().gross,0.0)
        assertTrue(closed.trades.single().manual)
        assertEquals(1,PaperRecordEdits.reversal(closed,command(PaperOperation.SELL,99.0),at.plusSeconds(5),true,null,null).trades.size)
    }
    @Test fun staleBuyAndInvalidOrMismatchedEditsDoNotChangeState() {
        val s=ReversalState(buy=100.0,buyAt=at)
        assertFalse(PaperRecordEdits.reversal(s,command(PaperOperation.BUY),at,false,30.0,20.0).manual)
        for(price in listOf(0.0,-1.0,Double.NaN,Double.POSITIVE_INFINITY)) assertEquals(s,PaperRecordEdits.reversal(s,command(PaperOperation.EDIT_BUY,price),at,true,null,null))
        assertEquals(s,PaperRecordEdits.reversal(s,command(PaperOperation.EDIT_BUY,100.0,0),at,true,null,null))
        assertEquals(s,PaperRecordEdits.reversal(s,command(PaperOperation.SELL,99.0,stamp=at.minusSeconds(1)),at,true,null,null))
    }
    @Test fun closedPriceCorrectionsKeepTimesAndUpdateQtyPnl() {
        val t=ReversalTrade(at,100.0,at.plusSeconds(60),102.0,"TEST")
        var s=ReversalState(trades=listOf(t))
        s=PaperRecordEdits.reversal(s,command(PaperOperation.EDIT_BUY,101.0,3),at.plusSeconds(70),false,null,null)
        s=PaperRecordEdits.reversal(s,command(PaperOperation.EDIT_SELL,104.0),at.plusSeconds(71),false,null,null)
        assertEquals(at,s.trades.single().buyAt);assertEquals(t.sellAt,s.trades.single().sellAt)
        assertEquals(9.0,s.trades.single().gross,0.0)
        assertEquals((104.0/101-1)*100,s.trades.single().percent,1e-8)
    }
    @Test fun openingManualRecordNeedsCurrentSetupButSellsAndCorrectionsAreUserRecords() {
        val pending=OpeningState(alert="OPENING_BUY",alertAt=at,day="2026-11-03")
        assertNull(PaperRecordEdits.opening(pending,command(PaperOperation.BUY),at,false).buy)
        val bought=PaperRecordEdits.opening(pending,command(PaperOperation.BUY,100.0,3),at,true)
        assertEquals(3,bought.quantity)
        val closed=PaperRecordEdits.opening(bought,command(PaperOperation.SELL,101.0),at.plusSeconds(5),false)
        assertNull(closed.buy);assertEquals(3.0,closed.trades.single().gross,0.0)
        val corrected=PaperRecordEdits.opening(closed,command(PaperOperation.EDIT_SELL,102.0),at.plusSeconds(6),false)
        assertEquals(6.0,corrected.trades.single().gross,0.0)
    }
    @Test fun summariesCountOnlyClosedTradesUseQuantityAndIstDay() {
        val trades=listOf(UiTrade("T","TEST",PaperSource.OPENING,at,100.0,at.plusSeconds(20),102.0,3),UiTrade("X","OPEN",PaperSource.REVERSAL,at,100.0,null,null))
        val total=TradeResults.totals(trades)
        assertEquals(1,total.count);assertEquals(1,total.wins);assertEquals(6.0,total.pnl,0.0);assertEquals(2.0,total.average!!,1e-8)
        assertEquals(1,TradeResults.onDate(trades,java.time.LocalDate.parse("2026-11-03")).size)
        assertTrue(TradeResults.onDate(trades,java.time.LocalDate.parse("2026-11-02")).isEmpty())
    }
}
