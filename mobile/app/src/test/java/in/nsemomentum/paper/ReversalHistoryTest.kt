package com.nsemomentum.paper

import java.time.LocalDate
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class ReversalHistoryTest {
    private val date=LocalDate.parse("2026-10-30")
    private fun regular(date:LocalDate)=MarketSession(date,date.atTime(9,15).atZone(MarketSession.ZONE).toInstant(),date.atTime(15,30).atZone(MarketSession.ZONE).toInstant())
    private val prior=(1L..20L).flatMap { day -> regular(date.minusDays(day)).slots().map { Candle(it,100.0,101.0,99.0,100.0,0.0) } }
    private class Feed(val days:List<Candle>,val today:List<Candle>,val session:(LocalDate)->MarketSession):CandleFeed {
        override suspend fun session(token:String,date:LocalDate)=session(date)
        override suspend fun candles(token:String,path:String)=if (path.contains("intraday")) today else days
    }
    @Test fun specialSessionHistoryDoesNotBlockOpeningOrReversal() = runBlocking {
        val specialDate=date.minusDays(1)
        val special=MarketSession(specialDate,specialDate.atTime(18,15).atZone(MarketSession.ZONE).toInstant(),
            specialDate.atTime(19,15).atZone(MarketSession.ZONE).toInstant())
        val history=prior.filterNot { it.timestamp.atZone(MarketSession.ZONE).toLocalDate()==specialDate } +
            special.slots().map { Candle(it,100.0,101.0,99.0,100.0,0.0) }
        val now=regular(date).start.plusSeconds(120)
        val feed=Feed(history,emptyList()) { day -> if(day==specialDate) special else regular(day) }
        val verified=reversalHistory(feed,"test",Stock("TEST","NSE_EQ|TEST"),now)
        assertEquals(479,verified.size)
        val quote=LiveQuote("NSE_EQ|TEST",101.0,null,now,now)
        assertNotNull(LiveStochasticPreview.calculate(verified,quote,now,true,true,
            verifiedPreviousClose=special.slots().last()))
        assertNull(LiveStochasticPreview.calculate(verified,quote,now,true,true))
        val completed=regular(date).slots().take(1).map { Candle(it,100.0,101.0,99.0,100.0,200.0) }
        assertNull(completedCandleVolume(verified+completed,regular(date).start.plusSeconds(901))!!.ratio)
    }

    @Test fun historyIsIndependentOfVolumeAndIncludesOnlyCompletedBars() = runBlocking {
        val morning=regular(date).slots().take(2).map { Candle(it,100.0,101.0,99.0,100.0,0.0) }
        val now=regular(date).start.plusSeconds(901)
        val bars=reversalHistory(Feed(prior,morning,::regular),"test",Stock("TEST","NSE_EQ|TEST"),now)
        assertEquals(501,bars.size)
        assertTrue(bars.all { it.volume == 0.0 })
        assertEquals(morning.first().timestamp,bars.last().timestamp)
        try { reversalHistory(Feed(prior.drop(1),morning,::regular),"test",Stock("TEST","NSE_EQ|TEST"),now); fail("Missing history must not be fabricated") }
        catch (_:IllegalArgumentException) {}
    }
}
