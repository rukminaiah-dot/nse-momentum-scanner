package com.nsemomentum.paper

import android.content.Context
import java.time.LocalDate
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
class DashboardPipelineTest {
    private val date=LocalDate.parse("2026-10-22")
    private fun session(date:LocalDate)=MarketSession(date,date.atTime(9,15).atZone(MarketSession.ZONE).toInstant(),date.atTime(15,30).atZone(MarketSession.ZONE).toInstant())
    @Test fun qualifiedBuyThenLowVolumeSellPersistAndSurviveRepeatScanAndRestart()=runBlocking {
        val context=RuntimeEnvironment.getApplication() as Context;context.deleteDatabase("paper_candles.db")
        val prior=generateSequence(date.minusDays(1)) { it.minusDays(1) }.filter { it.dayOfWeek.value<=5 }.take(20).toList()
        fun bar(at:java.time.Instant,volume:Double=100.0,close:Double=10.5)=Candle(at,10.0,11.0,9.0,close,volume)
        val history=prior.flatMap { session(it).slots().map { at->bar(at) } }
        val today=session(date);var intraday=listOf(bar(today.start,200.0,10.8));var historyCalls=0
        val feed=object:CandleFeed {
            override suspend fun session(token:String,date:LocalDate)=if(date.dayOfWeek.value<=5) this@DashboardPipelineTest.session(date) else null
            override suspend fun candles(token:String,path:String):List<Candle> {
                if(path.contains("intraday")) return intraday
                historyCalls++;val parts=path.split('/');val first=LocalDate.parse(parts.last());val last=LocalDate.parse(parts[parts.lastIndex-1])
                return history.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() in first..last }
            }
        }
        var db=CandleDatabase(context)
        try {
            var scanner=UpstoxPaperScanner(db,feed)
            val first=scanner.scan("test",listOf("TEST" to "NSE_EQ|TEST"),setOf("TEST"),today.start.plusSeconds(901))
            assertEquals("PAPER_BUY",first.rows.single().signal);db.recordScanReport(first)
            assertEquals(1,db.qualifiedStocks(date).size);assertTrue(db.hasActivePaperBuy("TEST"))
            assertTrue(scanHealthSummary(db.latestScanReport()).contains("BUY 1"))
            assertTrue(paperSignalDisplay(db.latestScanReport()!!.rows.single(),today.start.plusSeconds(901)).startsWith("BUY"))
            intraday=intraday+bar(today.start.plusSeconds(900),50.0,10.2)
            val sell=scanner.scan("test",listOf("TEST" to "NSE_EQ|TEST"),setOf("TEST"),today.start.plusSeconds(1801))
            assertEquals("PAPER_SELL",sell.rows.single().signal);assertEquals(.5,sell.rows.single().relativeVolume!!,0.0)
            db.recordScanReport(sell);val calls=historyCalls
            db.recordScanReport(scanner.scan("test",listOf("TEST" to "NSE_EQ|TEST"),setOf("TEST"),today.start.plusSeconds(1802)))
            assertEquals(calls,historyCalls);assertEquals(1,db.paperTradeHistory().size)
            assertFalse(db.hasActivePaperBuy("TEST"));assertEquals(10.2,db.paperTradeHistory().single().sell!!,0.0)
            db.close();db=CandleDatabase(context);scanner=UpstoxPaperScanner(db,feed)
            assertEquals("PAPER_SELL",db.latestScanReport()!!.rows.single().signal)
            assertEquals(1,db.paperTradeHistory().size);assertEquals(1,db.qualifiedStocks(date).size)
        } finally { db.close() }
    }

    @Test fun volumeSelectsOnceThenLowVolumeKdBuyDoesNotNeedAnotherVolumeSpike()=runBlocking {
        val context=RuntimeEnvironment.getApplication() as Context;context.deleteDatabase("paper_candles.db")
        val prior=generateSequence(date.minusDays(1)) { it.minusDays(1) }.filter { it.dayOfWeek.value<=5 }.take(20).toList()
        fun bar(at:java.time.Instant,volume:Double=100.0,close:Double=10.5)=Candle(at,10.0,11.0,9.0,close,volume)
        val history=prior.flatMap { session(it).slots().map { at->bar(at) } }
        val today=session(date);var intraday=listOf(bar(today.start,150.0,10.2))
        val feed=object:CandleFeed {
            override suspend fun session(token:String,date:LocalDate)=if(date.dayOfWeek.value<=5) this@DashboardPipelineTest.session(date) else null
            override suspend fun candles(token:String,path:String):List<Candle> {
                if(path.contains("intraday")) return intraday
                val parts=path.split('/');val first=LocalDate.parse(parts.last());val last=LocalDate.parse(parts[parts.lastIndex-1])
                return history.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() in first..last }
            }
        }
        val db=CandleDatabase(context)
        try {
            val scanner=UpstoxPaperScanner(db,feed)
            val selected=scanner.scan("test",listOf("TEST" to "NSE_EQ|TEST"),setOf("TEST"),today.start.plusSeconds(901))
            db.recordScanReport(selected)
            assertEquals(1.5,selected.rows.single().relativeVolume!!,0.0)
            assertEquals("WAIT",selected.rows.single().signal)
            assertTrue(db.qualifiedOn("TEST",date));assertFalse(db.hasActivePaperBuy("TEST"))
            intraday=intraday+bar(today.start.plusSeconds(900),50.0,10.8)
            val buy=scanner.scan("test",listOf("TEST" to "NSE_EQ|TEST"),setOf("TEST"),today.start.plusSeconds(1801))
            db.recordScanReport(buy)
            assertEquals(.5,buy.rows.single().relativeVolume!!,0.0)
            assertEquals("PAPER_BUY",buy.rows.single().signal)
            assertTrue(db.hasActivePaperBuy("TEST"));assertEquals(1,db.qualifiedStocks(date).size)
        } finally { db.close() }
    }
}
