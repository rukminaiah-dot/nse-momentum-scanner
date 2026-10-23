package com.nsemomentum.paper

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.time.Instant
import java.time.LocalDate
import java.time.ZonedDateTime

class CandleDatabase(context: Context) : SQLiteOpenHelper(context, "paper_candles.db", null, 3), CandleStore {
    override fun onCreate(db: SQLiteDatabase) {
        createCandles(db)
        createHistoryAttempts(db)
        createAnalytics(db)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) createHistoryAttempts(db)
        if (oldVersion < 3) createAnalytics(db)
    }

    private fun createCandles(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS candles(
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY(symbol, timestamp)
            )"""
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS candle_symbol_time ON candles(symbol, timestamp)")
    }

    private fun createHistoryAttempts(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS history_attempts(
                symbol TEXT NOT NULL PRIMARY KEY,
                attempted_on TEXT NOT NULL
            )"""
        )
    }

    private fun createAnalytics(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS daily_qualifications(
                session_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                peak_rvol REAL NOT NULL,
                last_price REAL,
                last_volume REAL,
                average_slot_volume REAL,
                PRIMARY KEY(session_date, symbol)
            )"""
        )
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS pending_paper_signals(
                symbol TEXT NOT NULL PRIMARY KEY,
                direction INTEGER NOT NULL,
                signal_time TEXT NOT NULL
            )"""
        )
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS paper_outcomes(
                symbol TEXT NOT NULL,
                signal_time TEXT NOT NULL,
                direction INTEGER NOT NULL,
                entry_time TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                return_percent REAL NOT NULL,
                PRIMARY KEY(symbol, signal_time)
            )"""
        )
        db.execSQL(
            """CREATE TABLE IF NOT EXISTS latest_scan_rows(
                symbol TEXT NOT NULL PRIMARY KEY,
                scanned_at TEXT NOT NULL,
                candle_time TEXT,
                signal TEXT NOT NULL,
                reason TEXT NOT NULL,
                relative_volume REAL,
                average_slot_volume REAL,
                daily_change_percent REAL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL
            )"""
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS paper_outcome_time ON paper_outcomes(signal_time)")
    }

    override fun save(symbol: String, bars: List<Candle>) {
        if (bars.isEmpty()) return
        val db = writableDatabase
        db.beginTransaction()
        try {
            bars.forEach { bar -> db.insertWithOnConflict("candles", null, candleValues(symbol, bar), SQLiteDatabase.CONFLICT_REPLACE) }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    override fun bars(symbol: String): List<Candle> {
        val output = mutableListOf<Candle>()
        readableDatabase.query(
            "candles", arrayOf("timestamp", "open", "high", "low", "close", "volume"),
            "symbol=?", arrayOf(symbol), null, null, "timestamp ASC"
        ).use { cursor ->
            while (cursor.moveToNext()) {
                runCatching {
                    output += Candle(
                        Instant.parse(cursor.getString(0)),
                        cursor.getDouble(1), cursor.getDouble(2), cursor.getDouble(3),
                        cursor.getDouble(4), cursor.getDouble(5)
                    )
                }
            }
        }
        return output
    }

    /** Persist latest UI rows and monotonic daily qualifications, then score only a verified next candle. */
    fun recordScanReport(report: ScanReport) {
        val scannedAt = runCatching { ZonedDateTime.parse(report.scanTime).toInstant() }.getOrNull() ?: return
        val sessionDate = scannedAt.atZone(MarketSession.ZONE).toLocalDate()
        val db = writableDatabase
        db.beginTransaction()
        try {
            db.delete("latest_scan_rows", null, null)
            report.rows.forEach { row ->
                db.insertWithOnConflict("latest_scan_rows", null, latestRowValues(row, scannedAt), SQLiteDatabase.CONFLICT_REPLACE)
                val candle = row.candle
                if (candle != null && row.relativeVolume != null && row.relativeVolume >= 1.5) {
                    upsertQualification(db, sessionDate, row, scannedAt)
                }
                if (candle != null) advancePaperOutcome(db, row)
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    private fun upsertQualification(db: SQLiteDatabase, date: LocalDate, row: ScanRow, at: Instant) {
        val key = arrayOf(date.toString(), row.symbol)
        var existing: QualifiedStock? = null
        db.query(
            "daily_qualifications",
            arrayOf("first_seen", "last_seen", "peak_rvol", "last_price", "last_volume", "average_slot_volume"),
            "session_date=? AND symbol=?", key, null, null, null
        ).use { cursor ->
            if (cursor.moveToFirst()) {
                existing = QualifiedStock(
                    row.symbol, Instant.parse(cursor.getString(0)), Instant.parse(cursor.getString(1)),
                    cursor.getDouble(2),
                    if (cursor.isNull(3)) null else cursor.getDouble(3),
                    if (cursor.isNull(4)) null else cursor.getDouble(4),
                    if (cursor.isNull(5)) null else cursor.getDouble(5)
                )
            }
        }
        val updated = PaperOutcomeLogic.updateQualification(existing, row, at) ?: return
        val values = ContentValues().apply {
            put("session_date", date.toString())
            put("symbol", updated.symbol)
            put("first_seen", updated.firstSeen.toString())
            put("last_seen", updated.lastSeen.toString())
            put("peak_rvol", updated.peakRelativeVolume)
            updated.lastPrice?.let { put("last_price", it) }
            updated.lastVolume?.let { put("last_volume", it) }
            updated.averageSlotVolume?.let { put("average_slot_volume", it) }
        }
        db.insertWithOnConflict("daily_qualifications", null, values, SQLiteDatabase.CONFLICT_REPLACE)
    }

    private fun advancePaperOutcome(db: SQLiteDatabase, row: ScanRow) {
        val candle = row.candle ?: return
        var pending: PendingPaperSignal? = null
        db.query(
            "pending_paper_signals", arrayOf("direction", "signal_time"),
            "symbol=?", arrayOf(row.symbol), null, null, null
        ).use { cursor ->
            if (cursor.moveToFirst()) {
                pending = runCatching {
                    PendingPaperSignal(row.symbol, cursor.getInt(0), Instant.parse(cursor.getString(1)))
                }.getOrNull()
            }
        }
        val previous = pending
        if (previous != null && candle.timestamp > previous.signalTime) {
            PaperOutcomeLogic.scoreNextCandle(previous, candle)?.let { outcome ->
                val values = ContentValues().apply {
                    put("symbol", outcome.symbol)
                    put("signal_time", outcome.signalTime.toString())
                    put("direction", outcome.direction)
                    put("entry_time", outcome.entryTime.toString())
                    put("entry_price", outcome.entryPrice)
                    put("exit_price", outcome.exitPrice)
                    put("return_percent", outcome.returnPercent)
                }
                db.insertWithOnConflict("paper_outcomes", null, values, SQLiteDatabase.CONFLICT_IGNORE)
            }
            db.delete("pending_paper_signals", "symbol=? AND signal_time=?", arrayOf(row.symbol, previous.signalTime.toString()))
        }
        val next = PaperOutcomeLogic.pendingFrom(row) ?: return
        val values = ContentValues().apply {
            put("symbol", next.symbol)
            put("direction", next.direction)
            put("signal_time", next.signalTime.toString())
        }
        db.insertWithOnConflict("pending_paper_signals", null, values, SQLiteDatabase.CONFLICT_IGNORE)
    }

    fun qualifiedStocks(date: LocalDate): List<QualifiedStock> {
        val output = mutableListOf<QualifiedStock>()
        readableDatabase.query(
            "daily_qualifications",
            arrayOf("symbol", "first_seen", "last_seen", "peak_rvol", "last_price", "last_volume", "average_slot_volume"),
            "session_date=?", arrayOf(date.toString()), null, null, "peak_rvol DESC, symbol ASC"
        ).use { cursor ->
            while (cursor.moveToNext()) {
                runCatching {
                    output += QualifiedStock(
                        cursor.getString(0), Instant.parse(cursor.getString(1)), Instant.parse(cursor.getString(2)),
                        cursor.getDouble(3),
                        if (cursor.isNull(4)) null else cursor.getDouble(4),
                        if (cursor.isNull(5)) null else cursor.getDouble(5),
                        if (cursor.isNull(6)) null else cursor.getDouble(6)
                    )
                }
            }
        }
        return output
    }

    fun latestScanReport(): ScanReport? {
        val db = readableDatabase
        val scanTime = db.rawQuery("SELECT MAX(scanned_at) FROM latest_scan_rows", null).use { cursor ->
            if (cursor.moveToFirst() && !cursor.isNull(0)) cursor.getString(0) else null
        } ?: return null
        val rows = mutableListOf<ScanRow>()
        db.query(
            "latest_scan_rows",
            arrayOf("symbol", "candle_time", "signal", "reason", "relative_volume", "average_slot_volume",
                "daily_change_percent", "open", "high", "low", "close", "volume"),
            null, null, null, null, "symbol ASC"
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val candle = if (cursor.isNull(7) || cursor.isNull(8) || cursor.isNull(9) ||
                    cursor.isNull(10) || cursor.isNull(11) || cursor.isNull(1)) null else runCatching {
                    Candle(Instant.parse(cursor.getString(1)), cursor.getDouble(7), cursor.getDouble(8),
                        cursor.getDouble(9), cursor.getDouble(10), cursor.getDouble(11))
                }.getOrNull()
                rows += ScanRow(
                    symbol = cursor.getString(0),
                    candleTime = cursor.getString(1),
                    signal = cursor.getString(2),
                    reason = cursor.getString(3),
                    relativeVolume = if (cursor.isNull(4)) null else cursor.getDouble(4),
                    candle = candle,
                    averageSlotVolume = if (cursor.isNull(5)) null else cursor.getDouble(5),
                    dailyChangePercent = if (cursor.isNull(6)) null else cursor.getDouble(6)
                )
            }
        }
        val failed = rows.count { it.reason in setOf("FETCH_FAILED", "RATE_LIMITED", "NETWORK_ERROR") || it.reason.startsWith("UPSTOX_") || it.reason.startsWith("INVALID_") }
        return ScanReport(rows, scanTime, failed, rows.size)
    }

    fun weeklyOutcomes(firstDate: LocalDate, lastDate: LocalDate): List<PaperOutcome> {
        val output = mutableListOf<PaperOutcome>()
        readableDatabase.query(
            "paper_outcomes",
            arrayOf("symbol", "direction", "signal_time", "entry_time", "entry_price", "exit_price", "return_percent"),
            null, null, null, null, "signal_time ASC"
        ).use { cursor ->
            while (cursor.moveToNext()) {
                runCatching {
                    val signalTime = Instant.parse(cursor.getString(2))
                    val date = signalTime.atZone(MarketSession.ZONE).toLocalDate()
                    if (date in firstDate..lastDate) {
                        output += PaperOutcome(cursor.getString(0), cursor.getInt(1), signalTime,
                            Instant.parse(cursor.getString(3)), cursor.getDouble(4), cursor.getDouble(5), cursor.getDouble(6))
                    }
                }
            }
        }
        return output
    }

    fun clearAll() {
        val db = writableDatabase
        listOf("candles", "history_attempts", "daily_qualifications", "pending_paper_signals", "paper_outcomes", "latest_scan_rows")
            .forEach { db.delete(it, null, null) }
    }

    private fun candleValues(symbol: String, bar: Candle) = ContentValues().apply {
        put("symbol", symbol); put("timestamp", bar.timestamp.toString())
        put("open", bar.open); put("high", bar.high); put("low", bar.low); put("close", bar.close); put("volume", bar.volume)
    }

    private fun latestRowValues(row: ScanRow, at: Instant) = ContentValues().apply {
        put("symbol", row.symbol); put("scanned_at", at.toString())
        put("candle_time", row.candle?.timestamp?.toString() ?: row.candleTime)
        put("signal", row.signal); put("reason", row.reason)
        row.relativeVolume?.let { put("relative_volume", it) }
        row.averageSlotVolume?.let { put("average_slot_volume", it) }
        row.dailyChangePercent?.let { put("daily_change_percent", it) }
        row.candle?.let { put("open", it.open); put("high", it.high); put("low", it.low); put("close", it.close); put("volume", it.volume) }
    }
}
