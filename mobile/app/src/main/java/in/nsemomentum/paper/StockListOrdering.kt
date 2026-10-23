package com.nsemomentum.paper

enum class StockSort(val label: String) {
    CURRENT_VOLUME("Volume ↓"),
    RELATIVE_VOLUME("RVOL ↓"),
    DAY_CHANGE("Day % ↓"),
    SYMBOL("Name A–Z")
}

object StockListOrdering {
    fun sort(stocks: List<Stock>, rows: Map<String, ScanRow>, sort: StockSort): List<Stock> = when (sort) {
        StockSort.CURRENT_VOLUME -> stocks.sortedWith(
            compareBy<Stock> { rows[it.symbol]?.candle?.volume == null }
                .thenByDescending { rows[it.symbol]?.candle?.volume ?: Double.NEGATIVE_INFINITY }
                .thenBy { it.symbol }
        )
        StockSort.RELATIVE_VOLUME -> stocks.sortedWith(
            compareBy<Stock> { rows[it.symbol]?.relativeVolume == null }
                .thenByDescending { rows[it.symbol]?.relativeVolume ?: Double.NEGATIVE_INFINITY }
                .thenBy { it.symbol }
        )
        StockSort.DAY_CHANGE -> stocks.sortedWith(
            compareBy<Stock> { rows[it.symbol]?.dailyChangePercent == null }
                .thenByDescending { rows[it.symbol]?.dailyChangePercent ?: Double.NEGATIVE_INFINITY }
                .thenBy { it.symbol }
        )
        StockSort.SYMBOL -> stocks.sortedBy { it.symbol }
    }
}
