package com.nsemomentum.paper

import java.time.LocalDate
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class SessionHistoryRecoveryTest {
    private fun session(date:LocalDate)=MarketSession(date,date.atTime(9,15).atZone(MarketSession.ZONE).toInstant(),date.atTime(15,30).atZone(MarketSession.ZONE).toInstant())
    private val sessions=(1L..20L).map { session(LocalDate.parse("2026-11-04").minusDays(it)) }
    private val bars=sessions.flatMap { it.slots().map { at->Candle(at,100.0,101.0,99.0,100.0,100.0) } }
    @Test fun offGridMuhuratSessionUsesOnlyFullClockAlignedCandles() = runBlocking {
        val date = LocalDate.parse("2026-11-08")
        val special = MarketSession(date, date.atTime(14,20).atZone(MarketSession.ZONE).toInstant(),
            date.atTime(15,30).atZone(MarketSession.ZONE).toInstant())
        val minutes = (0 until 70).map { bar(special.start.plusSeconds(it * 60L), 1.0) }
        val feed = object : CandleFeed {
            override suspend fun session(token: String, date: LocalDate) = special
            override suspend fun candles(token: String, path: String): List<Candle> {
                assertTrue(path.endsWith("/minutes/1/2026-11-08/2026-11-08"))
                return minutes
            }
        }
        assertTrue(special.hasVerifiedSlots())
        val recovered = recoverSessionHistory(feed, "test", "KEY", listOf(special), emptyList(), emptyList())
        assertEquals((0 until 4).map { special.start.plusSeconds(600L + it * 900L) }, recovered.map { it.timestamp })
        assertTrue(recovered.all { it.volume == 15.0 })
        assertEquals(3, aggregateFullSessionSlots(special, minutes.dropLast(1)).size)
        assertTrue(aggregateFullSessionSlots(special, minutes + minutes.first()).isEmpty())
    }

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

    @Test fun diagnosticsIdentifyEveryMissingSlotAndCacheRecovery()=runBlocking {
        val events=mutableListOf<String>()
        val logger:(String,String,String,String?)->Unit={ e,r,n,s -> events+="$e $r $n symbol=$s" }
        val feed=object:CandleFeed {
            override suspend fun session(token:String,date:LocalDate)=null
            override suspend fun candles(token:String,path:String):List<Candle> = error("No retry expected")
        }
        val result=recoverSessionHistory(feed,"secret-token","secret-key",sessions,bars.drop(1),bars,"TCS",logger)
        assertEquals(500,result.size)
        assertTrue(events.any { it.contains("HISTORY_MISSING FETCHED date=2026-11-03 slots=0915 symbol=TCS") })
        assertTrue(events.any { it.contains("HISTORY_DAY CACHE date=2026-11-03 expected=25 received=25 missing=0") })
        assertTrue(events.any { it.contains("HISTORY_RECOVERY COMPLETE sessions=20 cache=1 missing=0") })
        assertFalse(events.joinToString().contains("secret"))
    }
    @Test fun failedRetryAndBulkLimitAreVisibleWithoutInventingData()=runBlocking {
        val events=mutableListOf<String>()
        val logger:(String,String,String,String?)->Unit={ e,r,n,s -> events+="$e $r $n symbol=$s" }
        var calls=0
        val feed=object:CandleFeed {
            override suspend fun session(token:String,date:LocalDate)=null
            override suspend fun candles(token:String,path:String):List<Candle> { calls++;return emptyList() }
        }
        assertEquals(499,recoverSessionHistory(feed,"token","key",sessions,bars.drop(1),emptyList(),"TCS",logger).size)
        assertTrue(events.any { it.contains("HISTORY_RETRY INCOMPLETE date=2026-11-03") })
        assertTrue(events.any { it.contains("HISTORY_MISSING BLOCKED date=2026-11-03 slots=0915") })
        events.clear()
        recoverSessionHistory(feed,"token","key",sessions,emptyList(),emptyList(),"TCS",logger)
        assertEquals(1,calls)
        assertTrue(events.any { it.contains("HISTORY_RETRY SKIPPED_DAY_LIMIT missing=20 limit=2") })
        assertEquals(20,events.count { it.startsWith("HISTORY_MISSING BLOCKED") })
    }
    @Test fun retryFailureKeepsSafeErrorAndDateAndPropagates()=runBlocking {
        val events=mutableListOf<String>()
        val logger:(String,String,String,String?)->Unit={ e,r,n,s -> events+="$e $r $n symbol=$s" }
        val feed=object:CandleFeed {
            override suspend fun session(token:String,date:LocalDate)=null
            override suspend fun candles(token:String,path:String):List<Candle> = throw java.io.IOException("RATE_LIMITED")
        }
        try { recoverSessionHistory(feed,"token","key",sessions,bars.drop(1),emptyList(),"TCS",logger);fail("Must propagate") }
        catch(e:java.io.IOException) { assertEquals("RATE_LIMITED",e.message) }
        assertTrue(events.any { it.contains("HISTORY_RETRY RATE_LIMITED date=2026-11-03 symbol=TCS") })
    }
}
