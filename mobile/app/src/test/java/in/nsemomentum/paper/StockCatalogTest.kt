package com.nsemomentum.paper

import org.junit.Assert.*
import org.junit.Test

class StockCatalogTest {
    private val base = listOf(Stock("RELIANCE", "NSE_EQ|INE002A01018"))

    @Test fun trimsAndNormalizesNewNseStock() {
        val result = StockCatalog.validateNew("  abcd  ", " NSE_EQ|INE848E01016 ", base, 0)
        assertEquals(StockInputResult.Accepted(Stock("ABCD", "NSE_EQ|INE848E01016", true)), result)
    }

    @Test fun rejectsMalformedSymbolAndNonEquityInstrumentKey() {
        assertTrue(StockCatalog.validateNew("BAD SYMBOL", "NSE_EQ|INE123", base, 0) is StockInputResult.Rejected)
        assertTrue(StockCatalog.validateNew("ABC", "NSE_INDEX|Nifty 50", base, 0) is StockInputResult.Rejected)
    }

    @Test fun rejectsDuplicateSymbolOrInstrumentKey() {
        assertTrue(StockCatalog.validateNew("reliance", "NSE_EQ|INE999A01011", base, 0) is StockInputResult.Rejected)
        assertTrue(StockCatalog.validateNew("OTHER", "nse_eq|ine002a01018", base, 0) is StockInputResult.Rejected)
    }

    @Test fun enforcesCustomStockLimit() {
        val result = StockCatalog.validateNew("ABC", "NSE_EQ|INE123A01010", base, StockCatalog.MAX_CUSTOM_STOCKS)
        assertTrue(result is StockInputResult.Rejected)
    }

    @Test fun customStocksPersistAndRestoreWithoutDuplicates() {
        val custom = listOf(
            Stock("ABC", "NSE_EQ|INE123A01010", true),
            Stock("XYZ", "NSE_EQ|INE456A01010", true)
        )
        val encoded = StockCatalog.encodeCustom(base + custom)
        assertEquals(custom, StockCatalog.decodeCustom(encoded, base))
        assertEquals(emptyList<Stock>(), StockCatalog.decodeCustom("not-json", base))
    }

    @Test fun restoreDropsRowsDuplicatingConfiguredNse200Stocks() {
        val encoded = """[{"symbol":"RELIANCE","instrumentKey":"NSE_EQ|INE002A01018"},{"symbol":"ABC","instrumentKey":"NSE_EQ|INE123A01010"}]"""
        assertEquals(listOf(Stock("ABC", "NSE_EQ|INE123A01010", true)), StockCatalog.decodeCustom(encoded, base))
    }
}
