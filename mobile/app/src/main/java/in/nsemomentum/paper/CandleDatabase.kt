package com.nsemomentum.paper

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.time.Instant
import java.time.LocalDate
import java.time.ZonedDateTime

class CandleDatabase(context: Context) : SQLiteOpenHelper(context, "paper_candles.db", null, 4), CandleStore {
    override fun onCreate(db: SQLiteDatabase) {
        createCandles(db)
        createHistoryAttempts(db)
        createAnalytics(db)
        createSignalEvents(db)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) createHistoryAttempts(db)
        if (oldVersion < 3) createAnalytics(db)
        if (oldVersion < 4) {
            createSignalEvents(db)
            val existing = mutableSetOf<String>()
            db.rawQuery("PRAGMA table_info(latest_scan_rows)", null).use { cursor ->
                while (cursor.moveToNext()) existing += cursor.getString(1)
            }
            for (column in listOf("ema20", "ema50", "stoch_k", "stoch_d", "previous_gap")) {
                if (column !in existing) db.execSQL("ALTER TABLE latest_scan_rows ADD COLUMN $column REAL")
            }
        }
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
                volume REAL,
                ema20 REAL, ema50 REAL, stoch_k REAL, stoch_d REAL, previous_gap REAL
            )"""
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS paper_outcome_time ON paper_outcomes(signal_time)")
    }

    private fun createSignalEvents(db: SQLiteDatabase) {
        db.execSQL("""CREATE TABLE IF NOT EXISTS paper_signal_events(
            symbol TEXT NOT NULL, signal_time TEXT NOT NULL, direction INTEGER NOT NULL,
            price REAL NOT NULL, PRIMARY KEY(symbol, signal_time))""")
    }

    override fun qualifiedOn(symbol: String, date: LocalDate): Boolean = readableDatabase.rawQuery(
        "SELECT 1 FROM daily_qualifications WHERE symbol=? AND session_date=? LIMIT 1",
        arrayOf(symbol, date.toString())
    ).use { it.moveToFirst() }

    fun paperTradeHistory(): List<PaperTrade> {
        val events = mutableListOf<PaperTradeEvent>()
        readableDatabase.rawQuery("SELECT symbol,signal_time,direction,price FROM paper_signal_events ORDER BY signal_time", null).use { cursor ->
            while (cursor.moveToNext()) events += PaperTradeEvent(cursor.getString(0), Instant.parse(cursor.getString(1)), cursor.getInt(2), cursor.getDouble(3))
        }
        return paperTrades(events)
    }

    fun closeTimedPaperBuy(symbol:String,price:Double,now:Instant):Boolean {
        if(!price.isFinite() || price <= 0) return false
        val db=writableDatabase
        db.beginTransaction()
        try {
            val last=lastSignal(db,symbol)
            if(last == null || last.second != 1 || !StockSessionExit.due(last.first,now)) return false
            val row=ContentValues().apply { put("symbol",symbol);put("signal_time",now.toString());put("direction",-1);put("price",price) }
            val added=db.insertWithOnConflict("paper_signal_events",null,row,SQLiteDatabase.CONFLICT_IGNORE) != -1L
            db.setTransactionSuccessful()
            if(added) DiagnosticLog.event("STOCK_TIMED_EXIT","SESSION_1510",symbol=symbol)
            return added
        } finally { db.endTransaction() }
    }

    override fun hasActivePaperBuy(symbol: String): Boolean = lastSignal(readableDatabase, symbol)?.second == 1

    override fun recordedPaperSignal(symbol: String, candleStart: Instant): String? = readableDatabase.rawQuery(
        "SELECT direction FROM paper_signal_events WHERE symbol=? AND signal_time=?", arrayOf(symbol, candleStart.plusSeconds(900).toString())
    ).use { if (it.moveToFirst()) (if (it.getInt(0) == 1) "PAPER_BUY" else "PAPER_SELL") else null }

    private fun lastSignal(db: SQLiteDatabase, symbol: String): Pair<Instant, Int>? = db.rawQuery(
        "SELECT signal_time,direction FROM paper_signal_events WHERE symbol=? ORDER BY signal_time DESC LIMIT 1", arrayOf(symbol)
    ).use { if (it.moveToFirst()) Instant.parse(it.getString(0)) to it.getInt(1) else null }

    private fun recordSignalEvent(db: SQLiteDatabase, row: ScanRow) {
        val candle = row.candle ?: return
        val committedAt=Instant.now()
        if(row.signal == "PAPER_BUY" && candle.timestamp.atZone(MarketSession.ZONE).toLocalDate() == committedAt.atZone(MarketSession.ZONE).toLocalDate() && StockSessionExit.entriesClosed(committedAt)) return
        if (StockCatalog.indices.any { it.symbol == row.symbol }) return
        val direction = when (row.signal) { "PAPER_BUY" -> 1; "PAPER_SELL" -> -1; else -> return }
        val time = candle.timestamp.plusSeconds(900)
        val last = lastSignal(db, row.symbol)
        if (last != null && time <= last.first) return
        if (direction == -1 && last?.second != 1 || direction == 1 && last?.second == 1) return
        val values = ContentValues().apply {
            put("symbol", row.symbol); put("signal_time", time.toString())
            put("direction", direction); put("price", candle.close)
        }
        db.insertWithOnConflict("paper_signal_events", null, values, SQLiteDatabase.CONFLICT_IGNORE)
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
                DiagnosticLog.event("SIGNAL_CHECK",row.signal, "rvol=${row.relativeVolume ?: -1.0} k=${row.technicals?.stochK ?: -1.0} d=${row.technicals?.stochD ?: -1.0}", row.symbol)
                db.insertWithOnConflict("latest_scan_rows", null, latestRowValues(row, scannedAt), SQLiteDatabase.CONFLICT_REPLACE)
                val candle = row.candle
                if (candle != null && row.relativeVolume != null && row.relativeVolume >= 1.5) {
                    upsertQualification(db, sessionDate, row, scannedAt)
                }
                if (candle != null) {
                    recordSignalEvent(db, row)
                    advancePaperOutcome(db, row)
                }
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
                "daily_change_percent", "open", "high", "low", "close", "volume", "ema20", "ema50", "stoch_k", "stoch_d", "previous_gap"),
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
                    dailyChangePercent = if (cursor.isNull(6)) null else cursor.getDouble(6),
                    technicals = if ((12..15).any { cursor.isNull(it) }) null else TechnicalContext(
                        cursor.getDouble(12), cursor.getDouble(13), cursor.getDouble(14), cursor.getDouble(15),
                        if (cursor.isNull(16)) null else cursor.getDouble(16))
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

    fun exportPaperHistory(): org.json.JSONObject {
        val result = org.json.JSONObject()
        val db = readableDatabase
        db.beginTransaction()
        try {
            PaperBackup.tables.forEach { (table, columns) ->
                val rows = org.json.JSONArray()
                db.query(table, columns.toTypedArray(), null, null, null, null, null).use { cursor ->
                    while (cursor.moveToNext()) {
                        val row = org.json.JSONObject()
                        columns.forEachIndexed { index, name ->
                            row.put(name, when (cursor.getType(index)) {
                                android.database.Cursor.FIELD_TYPE_NULL -> org.json.JSONObject.NULL
                                android.database.Cursor.FIELD_TYPE_INTEGER -> cursor.getLong(index)
                                android.database.Cursor.FIELD_TYPE_FLOAT -> cursor.getDouble(index)
                                else -> cursor.getString(index)
                            })
                        }
                        rows.put(row)
                    }
                }
                result.put(table, rows)
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        return result
    }

    /** Caller validates the complete backup before entry. Existing history wins; retry is idempotent. */
    fun importPaperHistory(history: org.json.JSONObject) {
        val db = writableDatabase
        db.beginTransaction()
        try {
            PaperBackup.tables.forEach { (table, columns) ->
                val rows = history.getJSONArray(table)
                for (i in 0 until rows.length()) {
                    val row = rows.getJSONObject(i)
                    val values = ContentValues()
                    columns.forEach { column ->
                        when (val value = row.get(column)) {
                            org.json.JSONObject.NULL -> values.putNull(column)
                            is Number -> values.put(column, value.toDouble())
                            else -> values.put(column, value as String)
                        }
                    }
                    db.insertWithOnConflict(table, null, values, SQLiteDatabase.CONFLICT_IGNORE)
                }
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
    }

    fun clearAll() {
        val db = writableDatabase
        listOf("candles", "history_attempts", "daily_qualifications", "pending_paper_signals", "paper_outcomes", "latest_scan_rows", "paper_signal_events")
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
        row.technicals?.let {
            put("ema20", it.ema20); put("ema50", it.ema50); put("stoch_k", it.stochK); put("stoch_d", it.stochD)
            it.previousGap?.let { gap -> put("previous_gap", gap) }
        }
        row.candle?.let { put("open", it.open); put("high", it.high); put("low", it.low); put("close", it.close); put("volume", it.volume) }
    }
}
