package com.nsemomentum.paper

import android.content.Context
import java.time.Instant
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
class BuyPathVerificationTest {
    private val date=LocalDate.parse("2026-11-04")
    private fun session(day:LocalDate)=MarketSession(day,day.atTime(9,15).atZone(MarketSession.ZONE).toInstant(),day.atTime(15,30).atZone(MarketSession.ZONE).toInstant())

    @Test fun dashboardWaitExplainsVolumeGateThenEligibleBuyReachesDatabaseAndDisplayWithoutSocket()=runBlocking {
        val context=RuntimeEnvironment.getApplication() as Context
        context.deleteDatabase("paper_candles.db")
        java.io.File(context.filesDir,"diagnostics").deleteRecursively()
        DiagnosticLog.initialize(context)
        val prior=generateSequence(date.minusDays(1)) { it.minusDays(1) }.filter { it.dayOfWeek.value<=5 }.take(20).toList()
        fun bar(at:Instant,close:Double=100.0,volume:Double=100.0)=Candle(at,100.0,101.0,99.0,close,volume)
        val history=prior.flatMap { session(it).slots().map { at -> bar(at) } }
        val today=session(date)
        var intraday=listOf(bar(today.start,100.8,100.0))
        val feed=object:CandleFeed {
            override suspend fun session(token:String,date:LocalDate)=if(date.dayOfWeek.value<=5) this@BuyPathVerificationTest.session(date) else null
            override suspend fun candles(token:String,path:String):List<Candle> {
                if(path.contains("intraday")) return intraday
                val parts=path.split('/');val start=LocalDate.parse(parts.last());val end=LocalDate.parse(parts[parts.lastIndex-1])
                return history.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() in start..end }
            }
        }
        val db=CandleDatabase(context)
        try {
            val scanner=UpstoxPaperScanner(db,feed)
            val wait=scanner.scan("test",listOf("TEST" to "NSE_EQ|TEST"),setOf("TEST"),today.start.plusSeconds(901))
            db.recordScanReport(wait)
            assertEquals("NOT_SHORTLISTED_TODAY",wait.rows.single().reason)
            assertFalse(db.hasActivePaperBuy("TEST"))
            assertTrue(scanHealthSummary(wait).contains("Waiting: NOT_SHORTLISTED_TODAY: 1"))
            assertTrue(DiagnosticLog.export(context).contains("SIGNAL_REASON NOT_SHORTLISTED_TODAY"))
            intraday=intraday+bar(today.start.plusSeconds(900),100.9,200.0)
            val at=today.start.plusSeconds(1801)
            val buy=scanner.scan("test",listOf("TEST" to "NSE_EQ|TEST"),setOf("TEST"),at)
            db.recordScanReport(buy)
            assertEquals("PAPER_BUY",buy.rows.single().signal)
            assertTrue(db.hasActivePaperBuy("TEST"))
            assertEquals(1,db.paperTradeHistory().size)
            assertTrue(paperSignalDisplay(db.latestScanReport()!!.rows.single(),at).startsWith("BUY"))
            assertTrue(scanHealthSummary(db.latestScanReport()).contains("BUY 1"))
            assertTrue(DiagnosticLog.export(context).contains("SIGNAL_REASON BULLISH_ALIGNMENT"))
        } finally { db.close() }
    }

    @Test fun sameCustomStockAndServiceSelectionHaveIdenticalMonitorConfiguration() {
        val screen=listOf(Stock("TCS","NSE_EQ|TCS",true),Stock("BSE","BSE_EQ|BSE",true))
        val service=screen.reversed().map { Stock(it.symbol,it.instrumentKey) }
        assertEquals(reversalMonitorSelection(screen),reversalMonitorSelection(service))
        assertNotEquals(reversalMonitorSelection(screen),reversalMonitorSelection(screen.drop(1)))
        assertNotEquals(reversalMonitorSelection(screen),reversalMonitorSelection(listOf(Stock("TCS","NSE_EQ|OTHER"))))
    }

    @Test fun loggedReversalSnapshotsWaitButNextObservedCrossCanStillBuy() {
        val at=Instant.parse("2026-11-04T04:36:58Z")
        var s=ReversalStrategy.tick(ReversalState(),100.0,11.48202057586063,7.194404356186851,at)
        assertEquals("SHORTLISTED_BELOW_20_WAITING_FOR_CROSS",s.action)
        assertNull(s.buy)
        s=ReversalStrategy.tick(s,100.1,20.01,15.0,at.plusSeconds(1))
        assertEquals("BUY_CONFIRMED_K_CROSS_20",s.action)
        assertNotNull(s.buy)
        val interrupted=ReversalStrategy.interrupted(ReversalState(watchDate=date.toString(),previousK=18.0,previousAt=at),"QUOTE_GAP_LAST_VALID_K_RETAINED")
        val above=ReversalStrategy.tick(interrupted,100.0,100.0,82.97270381172122,at.plusSeconds(1))
        assertNull(above.buy)
        assertEquals("CROSS_UNOBSERVED_AFTER_DATA_GAP_NEW_CROSS_REQUIRED",above.action)
    }
}
