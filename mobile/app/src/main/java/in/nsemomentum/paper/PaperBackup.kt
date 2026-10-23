package com.nsemomentum.paper

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate

/** Explicit allowlist: never serializes preferences wholesale, tokens, keys, or cached candles. */
object PaperBackup {
    const val MAX_BYTES = 8 * 1024 * 1024
    val tables = linkedMapOf(
        "daily_qualifications" to listOf("session_date", "symbol", "first_seen", "last_seen", "peak_rvol", "last_price", "last_volume", "average_slot_volume"),
        "pending_paper_signals" to listOf("symbol", "direction", "signal_time"),
        "paper_outcomes" to listOf("symbol", "signal_time", "direction", "entry_time", "entry_price", "exit_price", "return_percent")
    )
    data class Snapshot(val favourites: Set<String>, val custom: List<Stock>, val history: JSONObject)
    fun encode(snapshot: Snapshot): String = JSONObject()
        .put("format", "nse-paper-backup").put("version", 1)
        .put("favourites", JSONArray(snapshot.favourites.sorted()))
        .put("custom", JSONArray(StockCatalog.encodeCustom(snapshot.custom)))
        .put("history", snapshot.history).toString().also {
            require(it.toByteArray(Charsets.UTF_8).size <= MAX_BYTES) { "Backup too large" }
        }

    fun decode(text: String, base: List<Stock>): Snapshot {
        require(text.toByteArray(Charsets.UTF_8).size <= MAX_BYTES)
        val root = JSONObject(text)
        require(root.keys().asSequence().toSet() == setOf("format", "version", "favourites", "custom", "history"))
        require(root.getString("format") == "nse-paper-backup" && root.get("version") == 1)
        val customRows = root.getJSONArray("custom")
        require(customRows.length() <= 20)
        val custom = mutableListOf<Stock>()
        for (i in 0 until customRows.length()) {
            val row = customRows.getJSONObject(i)
            require(row.keys().asSequence().toSet() == setOf("symbol", "instrumentKey"))
            val result = StockCatalog.validateNew(row.getString("symbol"), row.getString("instrumentKey"), base + custom, custom.size)
            require(result is StockInputResult.Accepted)
            custom += result.stock
        }
        val favRows = root.getJSONArray("favourites")
        val favourites = (0 until favRows.length()).map { favRows.getString(it) }
        require(favourites.size <= 20 && favourites.distinct().size == favourites.size)
        require(favourites.all { symbol -> (base + custom).any { it.symbol == symbol } })
        val history = root.getJSONObject("history")
        require(history.keys().asSequence().toSet() == tables.keys)
        var count = 0
        tables.forEach { (table, columns) ->
            val rows = history.getJSONArray(table)
            count += rows.length(); require(count <= 50000)
            val identities = mutableSetOf<String>()
            for (i in 0 until rows.length()) {
                val row = rows.getJSONObject(i)
                require(row.keys().asSequence().toSet() == columns.toSet())
                require(Regex("^[A-Z0-9][A-Z0-9&._-]{0,29}$").matches(row.getString("symbol")))
                columns.forEach { column ->
                    val value = row.get(column)
                    when (column) {
                        "symbol" -> Unit
                        "session_date" -> LocalDate.parse(row.getString(column))
                        "first_seen", "last_seen", "signal_time", "entry_time" -> Instant.parse(row.getString(column))
                        "direction" -> require(value is Number && value.toDouble() in listOf(-1.0, 1.0))
                        else -> {
                            val nullable = column in setOf("last_price", "last_volume", "average_slot_volume")
                            if (value == JSONObject.NULL) require(nullable)
                            else {
                                require(value is Number && value.toDouble().isFinite())
                                if (column != "return_percent") require(value.toDouble() >= 0)
                                if (column in setOf("entry_price", "exit_price", "last_price")) require(value.toDouble() > 0)
                            }
                        }
                    }
                }
                val identity = row.getString("symbol") + when (table) {
                    "daily_qualifications" -> row.getString("session_date")
                    "paper_outcomes" -> row.getString("signal_time")
                    else -> ""
                }
                require(identities.add(identity))
            }
        }
        return Snapshot(favourites.toSet(), custom, history)
    }

    /** Non-destructive merge: conflicts and capacity overflow reject the entire import. */
    fun merge(incoming: Snapshot, favourites: Set<String>, custom: List<Stock>, base: List<Stock>): Snapshot {
        val combined = custom.toMutableList()
        incoming.custom.forEach { stock ->
            if (combined.none { it == stock }) {
                val result = StockCatalog.validateNew(stock.symbol, stock.instrumentKey, base + combined, combined.size)
                require(result is StockInputResult.Accepted)
                combined += result.stock
            }
        }
        val favs = favourites + incoming.favourites
        require(favs.size <= 20)
        return incoming.copy(favourites = favs, custom = combined)
    }
}
