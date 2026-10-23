package com.nsemomentum.paper

import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Test

class StockListOrderingTest {
    private val stocks = listOf(Stock("BETA", "NSE_EQ|B"), Stock("ALPHA", "NSE_EQ|A"), Stock("GAMMA", "NSE_EQ|G"))
    private val rows = mapOf(
        "BETA" to ScanRow("BETA", relativeVolume = 1.5, reason = "ok",
            candle = Candle(Instant.EPOCH, 10.0, 11.0, 9.0, 10.5, 500.0),
            averageSlotVolume = 250.0, dailyChangePercent = 1.0),
        "ALPHA" to ScanRow("ALPHA", relativeVolume = 3.0, reason = "ok",
            candle = Candle(Instant.EPOCH, 10.0, 11.0, 9.0, 10.5, 200.0),
            averageSlotVolume = 66.7, dailyChangePercent = 3.0)
    )

    @Test fun currentVolumeSortsHighToLowAndUnverifiedRowsLast() {
        assertEquals(listOf("BETA", "ALPHA", "GAMMA"),
            StockListOrdering.sort(stocks, rows, StockSort.CURRENT_VOLUME).map { it.symbol })
    }

    @Test fun relativeVolumeSortsHighToLowAndUnverifiedRowsLast() {
        assertEquals(listOf("ALPHA", "BETA", "GAMMA"),
            StockListOrdering.sort(stocks, rows, StockSort.RELATIVE_VOLUME).map { it.symbol })
    }

    @Test fun dailyChangeSortsHighToLowAndUnverifiedRowsLast() {
        assertEquals(listOf("ALPHA", "BETA", "GAMMA"),
            StockListOrdering.sort(stocks, rows, StockSort.DAY_CHANGE).map { it.symbol })
    }

    @Test fun symbolSortIsAscending() {
        assertEquals(listOf("ALPHA", "BETA", "GAMMA"),
            StockListOrdering.sort(stocks, rows, StockSort.SYMBOL).map { it.symbol })
    }
}
