package com.nsemomentum.paper

import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.time.Instant
import java.time.LocalDate

class IndexMarketScannerTest {
    private val date = LocalDate.parse("2026-10-23")
    private val today = regular(date)
    private val now = today.start.plusSeconds(3601)
    private class Store : CandleStore {
        override fun bars(symbol: String) = emptyList<Candle>()
        override fun save(symbol: String, bars: List<Candle>) { assertTrue("5m history must be isolated from stock 15m cache", symbol.startsWith("index5:")) }
    }
    private fun minutes(s: MarketSession, count: Int = 375) = (0 until count).map {
        val price = 100.0 + it
        Candle(s.start.plusSeconds(it * 60L), price, price + 1, price - 1, price, 0.0)
    }
    private inner class Feed : CandleFeed {
        var transform: (List<Candle>) -> List<Candle> = { it }
        var error: String? = null
        var hang = false
        var bseClosed = false
        var count = 61
        val paths = mutableListOf<String>()
        override suspend fun session(token: String, date: LocalDate) = session(token, date, "NSE")
        override suspend fun session(token: String, date: LocalDate, exchange: String): MarketSession? =
            if (date.dayOfWeek.value <= 5 && !(bseClosed && exchange == "BSE" && date == this@IndexMarketScannerTest.date)) regular(date) else null
        override suspend fun candles(token: String, path: String): List<Candle> = error("Stock volume parser must not be used")
        override suspend fun indexCandles(token: String, path: String): List<Candle> {
            paths += path
            if (hang) awaitCancellation()
            error?.let { throw IOException(it) }
            return if (path.contains("intraday")) transform(minutes(today, count))
                else minutes(regular(LocalDate.parse(path.substringAfterLast('/'))))
        }
    }
    @Test fun matchesWebThreeCloseDirectionAndDoesNotApplyStockFilters() {
        val bars = minutes(today, 15)
        val target = today.start.plusSeconds(600)
        assertEquals("BULLISH", IndexDirectionStrategy.evaluate(bars, target))
        val falling = bars.map { it.copy(open = 300 - it.open, high = 301 - it.open, low = 299 - it.open, close = 300 - it.close) }
        assertEquals("BEARISH", IndexDirectionStrategy.evaluate(falling, target))
        assertEquals("NEUTRAL", IndexDirectionStrategy.evaluate(bars.map { it.copy(open = 100.0, high = 101.0, low = 99.0, close = 100.0) }, target))
        val mixed = bars.mapIndexed { i, b -> if (i == 9) b.copy(close = 99.5, low = 99.0) else b }
        assertEquals("NEUTRAL", IndexDirectionStrategy.evaluate(mixed, target))
        assertEquals("WAIT", IndexDirectionStrategy.evaluate(bars.drop(1), target))
        assertEquals("WAIT", IndexDirectionStrategy.evaluate(bars + bars.first(), target))
        assertEquals("BULLISH", IndexDirectionStrategy.evaluate(bars + bar(target.plusSeconds(300)), target))
    }
    @Test fun fixedIndicesUseOneMinuteOhlcAndIndependentExchangeCalendars() = runBlocking {
        val feed = Feed(); val progress = mutableListOf<Int>()
        val report = IndexMarketScanner(Store(), feed).scan("test", now) { done, total, _ -> assertEquals(3, total); progress += done }
        assertEquals(listOf(1, 2, 3), progress)
        assertEquals(StockCatalog.indices.map { it.symbol }, report.rows.map { it.symbol })
        assertTrue(report.rows.all { it.state == IndexDataState.LIVE && it.signal == "BULLISH" && it.dayChangePercent != null })
        assertTrue(feed.paths.all { it.contains("/minutes/1") })
        assertTrue(report.rows.all { it.technicals == null && it.sma21 == null })
        feed.bseClosed = true
        val closed = IndexMarketScanner(Store(), feed).scan("test", now).rows
        assertEquals(IndexDataState.HISTORICAL, closed.single { it.symbol == "SENSEX" }.state)
        assertEquals("WAIT", closed.single { it.symbol == "SENSEX" }.signal)
        assertEquals("BULLISH", closed.single { it.symbol == "NIFTY50" }.signal)
    }
    @Test fun gapsDuplicatesAndFutureCandlesCannotProduceDirection() = runBlocking {
        val feed = Feed()
        feed.transform = { it.filterIndexed { i, _ -> i != 46 } }
        assertTrue(IndexMarketScanner(Store(), feed).scan("test", now).rows.all { it.signal == "WAIT" })
        feed.transform = { it.filterIndexed { i, _ -> i != 59 } }
        assertTrue(IndexMarketScanner(Store(), feed).scan("test", now).rows.all { it.state == IndexDataState.UNAVAILABLE })
        feed.transform = { it + it.first() }
        assertTrue(IndexMarketScanner(Store(), feed).scan("test", now).rows.all { it.reason == "INVALID_INDEX_CANDLE" })
        feed.transform = { it + bar(now.plusSeconds(60)) }
        assertTrue(IndexMarketScanner(Store(), feed).scan("test", now).rows.all { it.reason == "INVALID_INDEX_CANDLE" })
    }
    @Test fun closedSessionsAreHistoricalAndSavedReadingsExpire() = runBlocking {
        val report = IndexMarketScanner(Store(), Feed().apply { count = 375 }).scan("test", today.end.plusSeconds(1))
        assertTrue(report.rows.all { it.state == IndexDataState.HISTORICAL && it.signal == "WAIT" })
        val live = IndexReading("NIFTY50", IndexDataState.LIVE, bar(now.minusSeconds(301)), signal = "BULLISH")
        assertEquals(IndexDataState.LIVE, live.at(now).state)
        assertEquals(IndexDataState.STALE, live.at(now.plusSeconds(481)).state)
        assertEquals("WAIT", live.at(now.plusSeconds(481)).signal)
        assertEquals(IndexDataState.HISTORICAL, live.at(today.end).state)
        assertEquals(IndexDataState.UNAVAILABLE, live.copy(candle = bar(now)).at(now).state)
        val weekend = IndexMarketScanner(Store(), Feed()).scan("test", regular(date.plusDays(1)).start)
        assertTrue(weekend.rows.all { it.state == IndexDataState.HISTORICAL })
    }
    @Test fun authenticationTimeoutAndCancellationFailClosedWithoutLeakingErrors() = runBlocking {
        val feed = Feed().apply { error = "UPSTOX_AUTH_REQUIRED" }
        try { IndexMarketScanner(Store(), feed).scan("test", now); fail() }
        catch (error: IOException) { assertEquals("UPSTOX_AUTH_REQUIRED", error.message) }
        feed.error = "PRIVATE_SENTINEL"
        assertTrue(IndexMarketScanner(Store(), feed).scan("test", now).rows.all { it.reason == "INDEX_FETCH_FAILED" })
        feed.error = null; feed.hang = true
        try { IndexMarketScanner(Store(), feed, 30).scan("test", now); fail() }
        catch (_: TimeoutCancellationException) { }
        val job = async { IndexMarketScanner(Store(), feed).scan("test", now) }
        yield(); job.cancelAndJoin(); assertTrue(job.isCancelled)
    }
}
