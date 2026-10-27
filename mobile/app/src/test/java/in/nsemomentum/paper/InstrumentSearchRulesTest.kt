package com.nsemomentum.paper

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException

class InstrumentSearchRulesTest {
    private val key = "NSE_EQ|INE002A01018"
    private fun row(exchange: String = "NSE", symbol: String = "RELIANCE", suffix: String = "") = """{
        "name":"RELIANCE INDUSTRIES LTD","segment":"${exchange}_EQ","exchange":"$exchange",
        "isin":"INE002A01018","instrument_key":"${exchange}_EQ|INE002A01018",
        "trading_symbol":"$symbol","instrument_type":"${if (exchange == "BSE") "A" else "EQ"}"$suffix} """
    private fun body(rows: String, page: Int = 1, total: Int = 1) = JSONObject("""{"status":"success","data":[$rows],
        "meta_data":{"page":{"page_number":$page,"total_pages":$total}}}""")
    private fun rejects(block: () -> Unit) {
        try { block(); fail("Expected rejection") } catch (_: IllegalArgumentException) { }
    }
    private fun invalid(root: JSONObject, exchange: String = "NSE", page: Int = 1) {
        try { InstrumentSearchRules.parse(root, exchange, page); fail("Expected invalid response") }
        catch (error: IOException) { assertEquals("INVALID_INSTRUMENT_SEARCH_RESPONSE", error.message) }
    }
    @Test fun parsesOfficialNseAndBseShapesWithoutUsingExchangeToken() {
        val nse = InstrumentSearchRules.parse(body(row(suffix = ",\"exchange_token\":\"2885\"")), "NSE", 1)
        val bse = InstrumentSearchRules.parse(body(row("BSE", suffix = ",\"exchange_token\":\"500325\"")), "BSE", 1)
        assertEquals(key, nse.instruments.single().instrumentKey)
        assertEquals("BSE_EQ|INE002A01018", bse.instruments.single().instrumentKey)
    }
    @Test fun validatesQueryAndResponseMetadata() {
        assertEquals("Reliance Industries", InstrumentSearchRules.query("  Reliance  Industries  "))
        rejects { InstrumentSearchRules.query("a") }; rejects { InstrumentSearchRules.query("a".repeat(51)) }
        invalid(body(row(), page = 2)); invalid(body(row(), total = 0))
        assertTrue(InstrumentSearchRules.parse(body("", total = 0), "NSE", 1).instruments.isEmpty())
    }
    @Test fun rejectsWrongExchangeMismatchedIsinAndConflictingDuplicateKeys() {
        invalid(body(row("BSE")))
        invalid(body(row().replace(key, "NSE_EQ|2885")))
        invalid(body(row() + "," + row(symbol = "OTHER")))
        assertEquals(1, InstrumentSearchRules.parse(body(row() + "," + row()), "NSE", 1).instruments.size)
    }
    @Test fun derivativesUnknownIndicesAndSuspendedRowsCannotBeSelected() {
        val derivative = """{"segment":"NSE_FO","instrument_key":"NSE_FO|123","instrument_type":"CE"}"""
        val unknown = """{"segment":"NSE_INDEX","exchange":"NSE","name":"Other Index","trading_symbol":"OTHER","instrument_key":"NSE_INDEX|Other"}"""
        assertTrue(InstrumentSearchRules.parse(body(derivative + "," + unknown + "," + row(suffix = ",\"is_suspended\":true")), "NSE", 1).instruments.isEmpty())
    }
    @Test fun reusesExistingKeyAndSeparatesNseBseWithSameSymbol() {
        val base = listOf(Stock("RELIANCE", key))
        val nse = InstrumentSearchRules.parse(body(row()), "NSE", 1).instruments.single()
        val first = InstrumentSearchRules.select(nse, base, emptySet(), 0)
        assertEquals(base, first.catalog); assertEquals(setOf("RELIANCE"), first.active)
        assertEquals(first, InstrumentSearchRules.select(nse, base, first.active, 0))
        val bse = InstrumentSearchRules.parse(body(row("BSE")), "BSE", 1).instruments.single()
        val second = InstrumentSearchRules.select(bse, base, first.active, 0)
        assertEquals(setOf("RELIANCE", "RELIANCE_BSE"), second.active)
        assertEquals("BSE_EQ|INE002A01018", second.selected.instrumentKey)
    }
    @Test fun rejectsExpiredResultsFullListAndSymbolCollisionWithoutMutation() {
        val candidate = InstrumentSearchRules.parse(body(row()), "NSE", 1).instruments.single()
        val base = (1..40).map { Stock("STOCK$it", "NSE_EQ|KEY$it") }
        val active = base.map { it.symbol }.toSet()
        rejects { InstrumentSearchRules.select(candidate, base, active, 0) }
        rejects { InstrumentSearchRules.select(candidate, emptyList(), emptySet(), 301) }
        rejects { InstrumentSearchRules.select(candidate, listOf(Stock("RELIANCE", "NSE_EQ|OTHER")), emptySet(), 0) }
        assertEquals(40, active.size); assertEquals(40, base.size)
    }
}
