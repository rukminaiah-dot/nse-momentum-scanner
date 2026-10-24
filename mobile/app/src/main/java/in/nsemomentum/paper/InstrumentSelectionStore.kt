package com.nsemomentum.paper

import android.content.Context

/** Commit the entire selected/custom preference change before updating the UI. Never deletes paper history. */
class InstrumentSelectionStore(context: Context, private val base: List<Stock>) {
    private val prefs = context.getSharedPreferences("paper_preferences", Context.MODE_PRIVATE)
    data class Snapshot(val catalog: List<Stock>, val active: Set<String>)
    fun read(): Snapshot {
        val catalog = base + StockCatalog.decodeCustom(prefs.getString("custom_stocks", null), base)
        val active = StockCatalog.stockSelections(prefs.getStringSet("favourites", emptySet()).orEmpty().toSet())
        StockCatalog.active(catalog, active)
        return Snapshot(catalog, active)
    }
    private fun save(catalog: List<Stock>, active: Set<String>): Snapshot {
        StockCatalog.active(catalog, active)
        check(prefs.edit().putString("custom_stocks", StockCatalog.encodeCustom(catalog))
            .putStringSet("favourites", active).commit()) { "Could not save the instrument list. Please retry." }
        return Snapshot(catalog, active)
    }
    fun add(instrument: SearchInstrument, ageSeconds: Long): Snapshot {
        val current = read()
        val result = InstrumentSearchRules.select(instrument, current.catalog, current.active, ageSeconds)
        return save(result.catalog, result.active)
    }
    fun setActive(symbol: String, enabled: Boolean): Snapshot {
        val current = read()
        require(StockCatalog.indices.none { it.symbol == symbol }) { "Indices are shown separately on Home." }
        require(current.catalog.any { it.symbol == symbol }) { "Unknown instrument." }
        return save(current.catalog, if (enabled) current.active + symbol else current.active - symbol)
    }
    fun deleteCustom(symbol: String): Snapshot {
        val current = read()
        require(current.catalog.any { it.symbol == symbol && it.isCustom }) { "Only custom entries can be deleted." }
        return save(current.catalog.filterNot { it.symbol == symbol }, current.active - symbol)
    }
}
