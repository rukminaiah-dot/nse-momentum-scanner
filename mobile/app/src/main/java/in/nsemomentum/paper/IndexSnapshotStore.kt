package com.nsemomentum.paper

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/** A separate display snapshot: never mixed into stock qualification or paper performance tables. */
class IndexSnapshotStore(context: Context) {
    private val prefs = context.getSharedPreferences("index_snapshot", Context.MODE_PRIVATE)
    fun write(report: IndexMarketReport) {
        val rows = JSONArray()
        report.rows.forEach { row ->
            val json = JSONObject().put("symbol", row.symbol).put("state", row.state.name)
                .put("signal", row.signal).put("reason", row.reason)
            row.refreshedAt?.let { json.put("refreshedAt", it.toString()) }
            row.lastError?.let { json.put("lastError", it) }
            row.previousDirection?.let { json.put("previousDirection", it) }
            row.changedAt?.let { json.put("changedAt", it.toString()) }
            row.candle?.let { bar ->
                json.put("candle", JSONArray(listOf(bar.timestamp.toString(), bar.open, bar.high, bar.low, bar.close, bar.volume)))
            }
            row.technicals?.let { t -> json.put("technicals", JSONArray(listOf(t.ema20, t.ema50, t.stochK, t.stochD))) }
            row.sma21?.let { json.put("sma21", it) }
            row.dayChangePercent?.let { json.put("change", it) }
            rows.put(json)
        }
        val encoded = JSONObject().put("version", 2).put("checkedAt", report.checkedAt.toString()).put("rows", rows).toString()
        check(prefs.edit().putString("report", encoded).commit()) { "INDEX_SNAPSHOT_SAVE_FAILED" }
    }
    fun clear() { prefs.edit().remove("report").apply() }
    fun read(now: Instant = Instant.now(), applyAge: Boolean = true): IndexMarketReport? = runCatching {
        val text = prefs.getString("report", null) ?: return null
        require(text.length <= 32_000)
        val root = JSONObject(text)
        require(root.getInt("version") == 2)
        val rows = root.getJSONArray("rows")
        require(rows.length() == 3)
        val decoded = (0 until rows.length()).map { i ->
            val item = rows.getJSONObject(i)
            val symbol = item.getString("symbol")
            require(StockCatalog.indices.any { it.symbol == symbol })
            val state = IndexDataState.valueOf(item.getString("state"))
            val c = item.optJSONArray("candle")
            val candle = c?.let { Candle(Instant.parse(it.getString(0)), it.getDouble(1), it.getDouble(2), it.getDouble(3), it.getDouble(4), it.getDouble(5)) }
            require(candle == null || PaperStrategy.validCandle(candle))
            val t = item.optJSONArray("technicals")
            val technicals = t?.let { TechnicalContext(it.getDouble(0), it.getDouble(1), it.getDouble(2), it.getDouble(3)) }
            require(technicals == null || listOf(technicals.ema20, technicals.ema50, technicals.stochK, technicals.stochD).all { it.isFinite() })
            val sma = if (item.has("sma21")) item.getDouble("sma21") else null
            val change = if (item.has("change")) item.getDouble("change") else null
            require(sma == null || sma.isFinite() && sma > 0)
            require(change == null || change.isFinite())
            if (state in setOf(IndexDataState.LIVE, IndexDataState.HISTORICAL, IndexDataState.STALE)) {
                require(candle != null)
            }
            val signal = item.getString("signal")
            require(signal in setOf("WAIT", "BULLISH", "BEARISH", "NEUTRAL"))
            IndexReading(symbol, state, candle, technicals, sma, change, signal, item.getString("reason"),
                item.optString("refreshedAt").takeIf { it.isNotEmpty() }?.let(Instant::parse),
                item.optString("lastError").takeIf { it.isNotEmpty() },
                item.optString("previousDirection").takeIf { it.isNotEmpty() },
                item.optString("changedAt").takeIf { it.isNotEmpty() }?.let(Instant::parse)).let { if (applyAge) it.at(now) else it }
        }
        require(decoded.map { it.symbol }.toSet().size == 3)
        IndexMarketReport(decoded, Instant.parse(root.getString("checkedAt")))
    }.getOrNull()
}
