package com.nsemomentum.paper

import java.time.Instant
import org.junit.Assert.*
import org.junit.Test

class PaperRecordEditsTest {
    private val at=Instant.parse("2026-11-03T04:00:00Z")
    private fun command(op:PaperOperation,price:Double?=100.0,qty:Int=2,stamp:Instant?=at)=PaperRecordEdit("TEST",PaperSource.REVERSAL,op,stamp,price,qty)
    @Test fun manualReversalEntryAutomaticallyClosesOnceAtStop() {
        val signal=ReversalState(buy=100.0,buyAt=at)
        val bought=PaperRecordEdits.reversal(signal,command(PaperOperation.BUY,101.0),at.plusSeconds(1),true,30.0,20.0)
        assertTrue(bought.manual);assertEquals(2,bought.quantity)
        val closed=ReversalStrategy.tick(bought,98.0,null,null,at.plusSeconds(2))
        assertNull(closed.buy)
        assertEquals(-6.0,closed.trades.single().gross,0.0)
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
    @Test fun openingRecordsCanBeCorrectedAfterAnAutomaticEntry() {
        val opening=OpeningState(day="2026-11-03",buy=100.0,buyAt=at,quantity=3,automatic=true)
        val closed=PaperRecordEdits.opening(opening,command(PaperOperation.SELL,101.0),at.plusSeconds(5))
        assertNull(closed.buy);assertEquals(3.0,closed.trades.single().gross,0.0)
        val corrected=PaperRecordEdits.opening(closed,command(PaperOperation.EDIT_SELL,102.0),at.plusSeconds(6))
        assertEquals(6.0,corrected.trades.single().gross,0.0)
        assertFalse(corrected.trades.single().automatic)
    }
    @Test fun closedOtherStrategyCannotHideCurrentManualPositionOrBuySetup() {
        val closed=OpeningState(trades=listOf(OpeningTrade(at.minusSeconds(60),100.0,at,101.0,1,"TEST")))
        val held=ReversalState(buy=100.0,buyAt=at.minusSeconds(120),manual=true)
        val row=ReversalRow(Stock("TEST","NSE_EQ|TEST"),held,null,"",closed,signalAt=at)
        assertEquals(listOf(PaperSource.REVERSAL),unifiedSignals(ReversalSnapshot(listOf(row)),at).map { it.source })
        val setup=row.copy(state=held.copy(manual=false))
        assertEquals(PaperSource.REVERSAL,unifiedSignals(ReversalSnapshot(listOf(setup)),at).single().source)
    }
    @Test fun bothAutomaticPositionsAreVisibleWhenTheSameStockQualifies() {
        val opening=OpeningState(day="2026-11-03",buy=100.0,buyAt=at,quantity=2,automatic=true)
        val reversal=ReversalState(buy=101.0,buyAt=at.plusSeconds(1))
        val row=ReversalRow(Stock("TEST","NSE_EQ|TEST"),reversal,null,"",opening)
        val sources=unifiedSignals(ReversalSnapshot(listOf(row)),at.plusSeconds(2)).map { it.source }
        assertEquals(setOf(PaperSource.OPENING,PaperSource.REVERSAL),sources.toSet())
    }
    @Test fun summariesCountOnlyClosedTradesUseQuantityAndIstDay() {
        val trades=listOf(UiTrade("T","TEST",PaperSource.OPENING,at,100.0,at.plusSeconds(20),102.0,3),UiTrade("X","OPEN",PaperSource.REVERSAL,at,100.0,null,null))
        val total=TradeResults.totals(trades)
        assertEquals(1,total.count);assertEquals(1,total.wins);assertEquals(6.0,total.pnl,0.0);assertEquals(2.0,total.average!!,1e-8)
        assertEquals(1,TradeResults.onDate(trades,java.time.LocalDate.parse("2026-11-03")).size)
        assertTrue(TradeResults.onDate(trades,java.time.LocalDate.parse("2026-11-02")).isEmpty())
    }
}

