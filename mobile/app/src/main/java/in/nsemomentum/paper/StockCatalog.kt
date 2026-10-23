package com.nsemomentum.paper

import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

data class Stock(val symbol: String, val instrumentKey: String, val isCustom: Boolean = false)

sealed interface StockInputResult {
    data class Accepted(val stock: Stock) : StockInputResult
    data class Rejected(val reason: String) : StockInputResult
}

object StockCatalog {
    const val MAX_ACTIVE = 20
    val indices = listOf(
        Stock("NIFTY50", "NSE_INDEX|Nifty 50"),
        Stock("SENSEX", "BSE_INDEX|SENSEX"),
        Stock("BANKNIFTY", "NSE_INDEX|Nifty Bank")
    )

    /** Existing favourites become the active list; never silently scan unselected instruments. */
    fun active(catalog: List<Stock>, selected: Set<String>): List<Stock> {
        require(selected.size <= MAX_ACTIVE) { "ACTIVE_LIST_OVER_LIMIT" }
        require(catalog.map { it.symbol }.distinct().size == catalog.size) { "DUPLICATE_SYMBOL" }
        require(selected.all { symbol -> catalog.any { it.symbol == symbol } }) { "UNKNOWN_ACTIVE_INSTRUMENT" }
        return catalog.filter { it.symbol in selected }
    }

    const val MAX_CUSTOM_STOCKS = 20
    private val symbolPattern = Regex("^[A-Z0-9][A-Z0-9&._-]{0,29}$")
    private val keyPattern = Regex("^(NSE_EQ|BSE_EQ)\\|[A-Z0-9]+$")

    fun validateNew(
        symbolInput: String,
        instrumentKeyInput: String,
        existing: List<Stock>,
        customCount: Int
    ): StockInputResult {
        val symbol = symbolInput.trim().uppercase(Locale.ROOT)
        val instrumentKey = instrumentKeyInput.trim().uppercase(Locale.ROOT)
        if (!symbolPattern.matches(symbol)) {
            return StockInputResult.Rejected("Enter a valid stock label (letters, numbers, . _ & or -).")
        }
        if (!keyPattern.matches(instrumentKey)) {
            return StockInputResult.Rejected("Enter the exact NSE_EQ or BSE_EQ Upstox equity key.")
        }
        if (existing.any { it.symbol.equals(symbol, ignoreCase = true) }) {
            return StockInputResult.Rejected("That symbol is already in the stock list.")
        }
        if (existing.any { it.instrumentKey.equals(instrumentKey, ignoreCase = true) }) {
            return StockInputResult.Rejected("That instrument key is already in the stock list.")
        }
        if (customCount >= MAX_CUSTOM_STOCKS) {
            return StockInputResult.Rejected("You can add up to $MAX_CUSTOM_STOCKS custom stocks.")
        }
        return StockInputResult.Accepted(Stock(symbol, instrumentKey, isCustom = true))
    }

    fun encodeCustom(stocks: List<Stock>): String = JSONArray().apply {
        stocks.filter { it.isCustom }.forEach { stock ->
            put(JSONObject().put("symbol", stock.symbol).put("instrumentKey", stock.instrumentKey))
        }
    }.toString()

    fun decodeCustom(encoded: String?, existing: List<Stock> = emptyList()): List<Stock> {
        if (encoded.isNullOrBlank()) return emptyList()
        return runCatching {
            val rows = JSONArray(encoded)
            val restored = mutableListOf<Stock>()
            for (index in 0 until rows.length()) {
                val row = rows.optJSONObject(index) ?: continue
                val symbol = row.optString("symbol")
                val key = row.optString("instrumentKey")
                when (val result = validateNew(symbol, key, existing + restored, restored.size)) {
                    is StockInputResult.Accepted -> restored += result.stock
                    is StockInputResult.Rejected -> Unit
                }
            }
            restored
        }.getOrDefault(emptyList())
    }
}
