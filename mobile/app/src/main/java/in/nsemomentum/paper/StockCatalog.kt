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
    const val MAX_CUSTOM_STOCKS = 20
    private val symbolPattern = Regex("^[A-Z0-9][A-Z0-9&._-]{0,29}$")
    private val keyPattern = Regex("^NSE_EQ\\|[A-Z0-9]+$")

    fun validateNew(
        symbolInput: String,
        instrumentKeyInput: String,
        existing: List<Stock>,
        customCount: Int
    ): StockInputResult {
        val symbol = symbolInput.trim().uppercase(Locale.ROOT)
        val instrumentKey = instrumentKeyInput.trim().uppercase(Locale.ROOT)
        if (!symbolPattern.matches(symbol)) {
            return StockInputResult.Rejected("Enter a valid NSE symbol (letters, numbers, . _ & or -).")
        }
        if (!keyPattern.matches(instrumentKey)) {
            return StockInputResult.Rejected("Enter the exact Upstox key, for example NSE_EQ|INE848E01016.")
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
