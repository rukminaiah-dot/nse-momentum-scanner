package com.nsemomentum.paper

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.time.LocalDate
import java.time.ZoneId

class CandleDatabase(context: Context) : SQLiteOpenHelper(context, "paper_candles.db", null, 1) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE candles(
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
        db.execSQL("CREATE INDEX candle_symbol_time ON candles(symbol, timestamp)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    fun save(symbol: String, bars: List<Candle>) {
        if (bars.isEmpty()) return
        val db = writableDatabase
        db.beginTransaction()
        try {
            bars.forEach { bar ->
                val values = ContentValues().apply {
                    put("symbol", symbol)
                    put("timestamp", bar.timestamp.toString())
                    put("open", bar.open)
                    put("high", bar.high)
                    put("low", bar.low)
                    put("close", bar.close)
                    put("volume", bar.volume)
                }
                db.insertWithOnConflict("candles", null, values, SQLiteDatabase.CONFLICT_REPLACE)
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    fun bars(symbol: String): List<Candle> {
        val output = mutableListOf<Candle>()
        readableDatabase.query(
            "candles", arrayOf("timestamp", "open", "high", "low", "close", "volume"),
            "symbol=?", arrayOf(symbol), null, null, "timestamp ASC"
        ).use { cursor ->
            while (cursor.moveToNext()) {
                runCatching {
                    output += Candle(
                        java.time.Instant.parse(cursor.getString(0)),
                        cursor.getDouble(1), cursor.getDouble(2), cursor.getDouble(3),
                        cursor.getDouble(4), cursor.getDouble(5)
                    )
                }
            }
        }
        return output
    }

    fun hasTwentyPriorSessions(symbol: String, sessionDate: LocalDate): Boolean {
        val zone = ZoneId.of("Asia/Kolkata")
        val dates = bars(symbol).map { it.timestamp.atZone(zone).toLocalDate() }
            .filter { it < sessionDate && it.dayOfWeek.value <= 5 }
            .toSet()
        return dates.size >= 20
    }

    fun clearAll() {
        writableDatabase.delete("candles", null, null)
    }
}
