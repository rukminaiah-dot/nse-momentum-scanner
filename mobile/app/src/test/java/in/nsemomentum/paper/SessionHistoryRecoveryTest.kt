package com.nsemomentum.paper

import java.time.LocalDate
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class SessionHistoryRecoveryTest {
    private fun session(date:LocalDate)=MarketSession(date,date.atTime(9,15).atZone(MarketSession.ZONE).toInstant(),date.atTime(15,30).atZone(MarketSession.ZONE).toInstant())
    private val sessions=(1L..20L).map { session(LocalDate.parse("2026-11-04").minusDays(it)) }
    private val bars=sessions.flatMap { it.slots().map { at->Candle(at,100.0,101.0,99.0,100.0,100.0) } }
    @Test fun missingDayUsesOnlyCompleteVerifiedCacheOrBoundedDayRetry()=runBlocking {
        var calls=0
        val feed=object:CandleFeed {
            override suspend fun session(token:String,date:LocalDate)=null
            override suspend fun candles(token:String,path:String):List<Candle> { calls++;return bars.filter { it.timestamp in sessions.first().slots() } }
        }
        val incomplete=bars.filterNot { it.timestamp in sessions.first().slots() }
        assertEquals(500,recoverSessionHistory(feed,"test","KEY",sessions,incomplete,bars).size);assertEquals(0,calls)
        assertEquals(500,recoverSessionHistory(feed,"test","KEY",sessions,incomplete,emptyList()).size);assertEquals(1,calls)
        val bad=bars+bars.first()
        try { recoverSessionHistory(feed,"test","KEY",sessions,bad,bars);fail("Duplicate raw candle must not be hidden") } catch(_:IllegalArgumentException) {}
    }
    @Test fun incompleteProviderDataIsNotFilledWithInventedBarsAndBulkOutageDoesNotBurstRequests()=runBlocking {
        var calls=0
        val feed=object:CandleFeed {
            override suspend fun session(token:String,date:LocalDate)=null
            override suspend fun candles(token:String,path:String):List<Candle> { calls++;return emptyList() }
        }
        assertEquals(499,recoverSessionHistory(feed,"test","KEY",sessions,bars.drop(1),emptyList()).size)
        assertEquals(1,calls)
        assertTrue(recoverSessionHistory(feed,"test","KEY",sessions,emptyList(),emptyList()).isEmpty())
        assertEquals(1,calls)
    }
}
