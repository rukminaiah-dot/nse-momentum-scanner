package com.nsemomentum.paper

import java.time.LocalDate
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test

class CommoditiesTest {
    private val date=LocalDate.parse("2026-10-30")
    private fun row(name:String,key:String,expiry:String,type:String="FUT")=JSONObject().put("exchange","MCX").put("segment","MCX_FO")
        .put("instrument_type",type).put("underlying_symbol",name).put("instrument_key",key).put("expiry",expiry).put("trading_symbol","$name FUT $expiry")
    @Test fun resolvesExactStandardFutureNotMiniOptionOrExpiredContract() {
        val root=JSONObject().put("status","success").put("data",JSONArray(listOf(
            row("GOLD","MCX_FO|1","2026-10-01"),row("GOLDM","MCX_FO|2","2026-11-01"),
            row("GOLD","MCX_FO|3","2026-11-01","CE"),row("GOLD","MCX_FO|4","2026-12-05"),row("GOLD","MCX_FO|5","2027-02-05"))))
        val contracts=CommodityContracts.parse(root,"GOLD",date)
        assertEquals(2,contracts.size)
        assertEquals("MCX_FO|4",contracts.minBy { it.expiry }.key)
        val keys=StockCatalog.indices.map { it.instrumentKey }.toSet()+setOf("MCX_FO|4","MCX_FO|5")
        assertEquals("full",JSONObject(LivePriceDecoder.subscription(keys).utf8()).getJSONObject("data").getString("mode"))
        try {LivePriceDecoder.subscription((1..5).map { "MCX_FO|$it" }.toSet());fail()} catch(_:IllegalArgumentException) {}
    }
    @Test fun commoditySessionUsesExchangeHoursNotStockCutoff() {
        val start=date.atTime(9,0).atZone(MarketSession.ZONE).toInstant()
        val end=date.atTime(23,30).atZone(MarketSession.ZONE).toInstant()
        val session=CommoditySession(date,start,end)
        assertTrue(session.valid())
        assertNull(session.target(start.plusSeconds(299)))
        assertEquals(start,session.target(start.plusSeconds(300)))
        assertEquals(start.plusSeconds(6*3600+10*60),session.target(start.plusSeconds(6*3600+15*60)))
        val minutes=(0 until 15).map { i -> val p=100.0+i;Candle(start.plusSeconds(i*60L),p,p+1,p-1,p,0.0) }
        assertEquals("BULLISH",IndexDirectionStrategy.evaluate(minutes,start.plusSeconds(600)))
    }
}
