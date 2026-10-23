package com.nsemomentum.paper

import org.json.JSONObject
import java.io.IOException

/** Search contracts follow Upstox /v2/instruments/search. No network or order capability. */
data class SearchInstrument(val symbol: String, val name: String, val exchange: String, val instrumentKey: String) {
    val isIndex: Boolean get() = instrumentKey.contains("_INDEX|")
}
data class InstrumentSearchPage(val instruments: List<SearchInstrument>, val number: Int, val totalPages: Int)
data class InstrumentSelection(val catalog: List<Stock>, val active: Set<String>, val selected: Stock)

object InstrumentSearchRules {
    fun query(input: String): String = input.trim().replace(Regex("\\s+"), " ").also {
        require(it.length in 2..50 && it.none { c -> c.isISOControl() }) { "Enter 2–50 characters of a company name or symbol." }
    }

    fun parse(root: JSONObject, exchange: String, requestedPage: Int): InstrumentSearchPage {
        require(exchange in setOf("NSE", "BSE") && requestedPage >= 1)
        try {
            require(root.getString("status") == "success")
            val data = root.getJSONArray("data")
            require(data.length() <= 30)
            val page = root.getJSONObject("meta_data").getJSONObject("page")
            val number = page.getInt("page_number")
            val total = page.getInt("total_pages")
            require(number == requestedPage && total in 0..100000 && (total >= number || total == 0 && data.length() == 0))
            val found = linkedMapOf<String, SearchInstrument>()
            for (i in 0 until data.length()) {
                val row = data.getJSONObject(i)
                val segment = row.optString("segment")
                if (segment !in setOf("NSE_EQ", "BSE_EQ", "NSE_INDEX", "BSE_INDEX")) continue
                require(row.getString("exchange") == exchange && segment.startsWith("${exchange}_"))
                val key = row.getString("instrument_key")
                val symbol = row.getString("trading_symbol")
                val name = row.getString("name")
                require(name.isNotBlank() && name.length <= 160 && name.none { it.isISOControl() })
                if (segment.endsWith("INDEX")) {
                    if (StockCatalog.indices.none { it.instrumentKey == key }) continue
                    require(row.getString("instrument_type") == "INDEX")
                } else {
                    val isin = row.getString("isin")
                    require(Regex("^[A-Z]{2}[A-Z0-9]{9}[0-9]$").matches(isin) && key == "$segment|$isin")
                    require(Regex("^[A-Z0-9][A-Z0-9&._-]{0,29}$").matches(symbol))
                    require(row.optString("instrument_type") !in setOf("", "FUT", "CE", "PE", "INDEX"))
                }
                if (row.optBoolean("is_suspended", false)) continue
                val instrument = SearchInstrument(symbol, name, exchange, key)
                require(found[key] == null || found[key] == instrument)
                found[key] = instrument
            }
            return InstrumentSearchPage(found.values.toList(), number, total)
        } catch (_: Exception) { throw IOException("INVALID_INSTRUMENT_SEARCH_RESPONSE") }
    }

    /** No silent remapping: an existing instrument is found by key, never by company name. */
    fun select(instrument: SearchInstrument, catalog: List<Stock>, active: Set<String>, ageSeconds: Long): InstrumentSelection {
        require(ageSeconds in 0..300) { "Search results expired. Search again before adding." }
        StockCatalog.active(catalog, active)
        val existing = catalog.singleOrNull { it.instrumentKey == instrument.instrumentKey }
        if (existing != null) {
            require(existing.symbol in active || active.size < StockCatalog.MAX_ACTIVE) { "Remove one instrument before adding another; maximum 20." }
            return InstrumentSelection(catalog, active + existing.symbol, existing)
        }
        require(active.size < StockCatalog.MAX_ACTIVE) { "Remove one instrument before adding another; maximum 20." }
        require(!instrument.isIndex) { "Unsupported index." }
        // Distinct persistent labels allow both exchange listings of the same company.
        val label = if (instrument.exchange == "BSE") instrument.symbol.take(26) + "_BSE" else instrument.symbol
        val result = StockCatalog.validateNew(label, instrument.instrumentKey, catalog, catalog.count { it.isCustom })
        require(result is StockInputResult.Accepted) {
            (result as StockInputResult.Rejected).reason
        }
        return InstrumentSelection(catalog + result.stock, active + result.stock.symbol, result.stock)
    }
}
