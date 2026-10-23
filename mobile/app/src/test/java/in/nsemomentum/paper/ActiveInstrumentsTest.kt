package com.nsemomentum.paper

import org.junit.Assert.*
import org.junit.Test

class ActiveInstrumentsTest {
    private val catalog = (1..200).map { Stock("STOCK$it", "NSE_EQ|KEY$it") } + StockCatalog.indices
    @Test fun scansOnlyExplicitSelectionsIncludingIndices() {
        val selected = setOf("STOCK150", "BANKNIFTY", "SENSEX")
        assertEquals(selected, StockCatalog.active(catalog, selected).map { it.symbol }.toSet())
        assertTrue(StockCatalog.active(catalog, emptySet()).isEmpty())
    }
    @Test fun twentyAllowedButTwentyOneRejected() {
        assertEquals(20, StockCatalog.active(catalog, catalog.take(20).map { it.symbol }.toSet()).size)
        try { StockCatalog.active(catalog, catalog.take(21).map { it.symbol }.toSet()); fail() }
        catch (_: IllegalArgumentException) { }
    }
    @Test fun unknownSelectionNeverSilentlyDropped() {
        try { StockCatalog.active(catalog, setOf("MISSING")); fail() }
        catch (_: IllegalArgumentException) { }
    }
    @Test fun bseEquityCanBeAddedButArbitraryIndexCannot() {
        assertTrue(StockCatalog.validateNew("BSE_RELIANCE", "BSE_EQ|500325", catalog, 0) is StockInputResult.Accepted)
        assertTrue(StockCatalog.validateNew("FAKE", "BSE_INDEX|FAKE", catalog, 0) is StockInputResult.Rejected)
    }
}
