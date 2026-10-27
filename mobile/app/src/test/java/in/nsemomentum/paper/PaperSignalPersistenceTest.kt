package com.nsemomentum.paper

import android.content.Context
import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class PaperSignalPersistenceTest {
    private val start = LocalDate.parse("2026-10-27").atTime(9,15).atZone(MarketSession.ZONE).toInstant()
    private fun row(signal: String, offset: Long = 0) = ScanRow("TEST", signal = signal, reason = "TEST", relativeVolume = 2.0,
        candle = Candle(start.plusSeconds(offset),100.0,102.0,99.0,101.0,200.0),
        technicals = TechnicalContext(110.0,100.0,60.0,50.0,5.0))
    private fun save(db: CandleDatabase, row: ScanRow) = db.recordScanReport(ScanReport(listOf(row),
        row.candle!!.timestamp.plusSeconds(901).atZone(MarketSession.ZONE).toString(),0,1))
    @Test fun restartDuplicateScansAndSellPreserveExactlyOneBuyAndOneSell() {
        val context = RuntimeEnvironment.getApplication() as Context
        context.deleteDatabase("paper_candles.db")
        CandleDatabase(context).use { db ->
            save(db,row("PAPER_BUY"));save(db,row("PAPER_BUY"))
            assertTrue(db.hasActivePaperBuy("TEST"))
            assertEquals(1,db.exportPaperHistory().getJSONArray("paper_signal_events").length())
            assertEquals(10.0,db.latestScanReport()!!.rows.single().technicals!!.gap,0.0)
            assertEquals(5.0,db.latestScanReport()!!.rows.single().technicals!!.previousGap!!,0.0)
        }
        CandleDatabase(context).use { db ->
            assertTrue(db.hasActivePaperBuy("TEST"))
            save(db,row("PAPER_SELL",900));save(db,row("PAPER_SELL",900))
            assertFalse(db.hasActivePaperBuy("TEST"))
            assertEquals(2,db.exportPaperHistory().getJSONArray("paper_signal_events").length())
            assertEquals("PAPER_SELL",db.recordedPaperSignal("TEST",start.plusSeconds(900)))
            save(db,row("PAPER_BUY"))
            assertFalse(db.hasActivePaperBuy("TEST"))
        }
    }
    @Test fun aSellWithoutBuyDoesNotCreateAnExitRecord() {
        val context = RuntimeEnvironment.getApplication() as Context
        context.deleteDatabase("paper_candles.db")
        CandleDatabase(context).use { db ->
            save(db,row("PAPER_SELL"))
            assertEquals(0,db.exportPaperHistory().getJSONArray("paper_signal_events").length())
        }
    }
    @Test fun oldDatabaseUpgradePreservesExistingQualificationRows() {
        val context = RuntimeEnvironment.getApplication() as Context
        context.deleteDatabase("paper_candles.db")
        context.openOrCreateDatabase("paper_candles.db",0,null).use { old ->
            old.execSQL("CREATE TABLE daily_qualifications(session_date TEXT,symbol TEXT,first_seen TEXT,last_seen TEXT,peak_rvol REAL,last_price REAL,last_volume REAL,average_slot_volume REAL,PRIMARY KEY(session_date,symbol))")
            old.execSQL("INSERT INTO daily_qualifications VALUES('2026-10-27','TEST','2026-10-27T04:00:00Z','2026-10-27T04:00:00Z',2,101,200,100)")
            old.execSQL("CREATE TABLE latest_scan_rows(symbol TEXT PRIMARY KEY,scanned_at TEXT,candle_time TEXT,signal TEXT,reason TEXT,relative_volume REAL,average_slot_volume REAL,daily_change_percent REAL,open REAL,high REAL,low REAL,close REAL,volume REAL)")
            old.version=3
        }
        CandleDatabase(context).use { db ->
            assertTrue(db.qualifiedOn("TEST",LocalDate.parse("2026-10-27")))
            assertFalse(db.hasActivePaperBuy("TEST"))
            assertNotNull(db.writableDatabase)
        }
    }
}
