package com.nsemomentum.paper

import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test

class LiveStochasticTest {
    private val days = listOf("2026-10-23","2026-10-26","2026-10-27").map(LocalDate::parse)
    private val history = days.flatMapIndexed { dayIndex, date -> (0 until 25).map { i ->
        val price = 100.0 + kotlin.math.sin((dayIndex * 25 + i).toDouble()) * 3
        Candle(date.atTime(9,15).atZone(MarketSession.ZONE).toInstant().plusSeconds(i * 900L),price,price+1,price-1,price,100.0)
    } }
    private val now = LocalDate.parse("2026-10-28").atTime(9,20).atZone(MarketSession.ZONE).toInstant()
    private val quote = LiveQuote("NSE_EQ|TEST",105.0,100.0,now,now)
    @Test fun previewUsesExactlyOneFormingCloseAndDoesNotMutateHistory() {
        val actual = LiveStochasticPreview.calculate(history,quote,now,true,true)!!
        val (k,d) = PaperStrategy.stochRsi(history.map { it.close } + quote.price)
        assertEquals(k.last(),actual.context.stochK,0.000001)
        assertEquals(d.last(),actual.context.stochD,0.000001)
        assertEquals(75,history.size)
        assertEquals(105.0,quote.price,0.0)
    }
    @Test fun staleDisconnectedClosedAndMissingSlotAreUnavailable() {
        assertNull(LiveStochasticPreview.calculate(history,quote,now.plusSeconds(31),true,true))
        assertNull(LiveStochasticPreview.calculate(history,quote,now,false,true))
        assertNull(LiveStochasticPreview.calculate(history,quote,now,true,false))
        assertNull(LiveStochasticPreview.calculate(history.dropLast(1),quote,now,true,true))
        val later = now.plusSeconds(900)
        assertNull(LiveStochasticPreview.calculate(history,quote.copy(tradedAt=later,receivedAt=later),later,true,true))
    }
    @Test fun completedBarAtCurrentSlotIsReplacedRatherThanDuplicated() {
        val current = Candle(now.minusSeconds(300),104.0,106.0,103.0,104.0,50.0)
        assertEquals(LiveStochasticPreview.calculate(history,quote,now,true,true),
            LiveStochasticPreview.calculate(history+current,quote,now,true,true))
    }
    @Test fun tradesPairEntriesExitsAndCalculateGrossPerShare() {
        val events = listOf(PaperTradeEvent("A",now,-1,90.0), PaperTradeEvent("A",now.plusSeconds(1),1,100.0),
            PaperTradeEvent("A",now.plusSeconds(2),1,110.0), PaperTradeEvent("A",now.plusSeconds(3),-1,98.0),
            PaperTradeEvent("A",now.plusSeconds(4),1,200.0))
        val trades = paperTrades(events)
        assertEquals(2,trades.size)
        assertEquals(-2.0,trades[1].gross(null)!!,0.0)
        assertEquals(-2.0,trades[1].percent(null)!!,0.0)
        assertEquals(10.0,trades[0].gross(210.0)!!,0.0)
        assertEquals(5.0,trades[0].percent(210.0)!!,0.0)
        assertNull(trades[0].gross(null))
    }
}
