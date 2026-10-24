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
    private val holiday = date.minusDays(3)
    private val allSessions = generateSequence(date) { it.minusDays(1) }
        .filter { it.dayOfWeek.value <= 5 && it != holiday }.take(50).map { regular(it) }.toList()
    private val historical = allSessions.flatMap { s -> s.slots().map { bar(it, 0.0) } }
    private class Store : CandleStore {
        val data = mutableMapOf<String, List<Candle>>()
        override fun bars(symbol: String) = data[symbol].orEmpty()
        override fun save(symbol: String, bars: List<Candle>) {
            data[symbol] = (data[symbol].orEmpty() + bars).associateBy { it.timestamp }.values.sortedBy { it.timestamp }
        }
    }
    private inner class Feed(var clock: Instant = now) : CandleFeed {
        val paths = mutableListOf<String>()
        val calendarCalls = mutableListOf<Pair<String, LocalDate>>()
        var missingDate: LocalDate? = null
        var duplicate = false
        var error: String? = null
        var hang = false
        var missingCurrent = false
        var includeFuture = false
        var bseClosedToday = false
        var failNseOnly = false
        var flatFormingCandle = false
        override suspend fun session(token: String, date: LocalDate): MarketSession? = session(token, date, "NSE")
        override suspend fun session(token: String, date: LocalDate, exchange: String): MarketSession? {
            calendarCalls += exchange to date
            return if (date.dayOfWeek.value <= 5 && date != holiday && !(bseClosedToday && exchange == "BSE" && date == this@IndexMarketScannerTest.date)) regular(date) else null
        }
        override suspend fun candles(token: String, path: String): List<Candle> {
            paths += path
            if (hang) awaitCancellation()
            error?.let { throw IOException(it) }
            if (failNseOnly && !path.contains("BSE_INDEX")) throw IOException("NETWORK_ERROR")
            if (path.contains("intraday")) {
                val complete = today.slots().filter { it <= clock }.map { timestamp ->
                    if (flatFormingCandle && timestamp.plusSeconds(900) > clock) Candle(timestamp, 10.5, 10.5, 10.5, 10.5, 0.0) else bar(timestamp, 0.0)
                }
                val latestComplete = today.slots().lastOrNull { it.plusSeconds(900) <= clock }
                return (if (missingCurrent) complete.filterNot { it.timestamp == latestComplete } else complete) +
                    (if (includeFuture) listOf(bar(today.start.plusSeconds(10 * 900), 0.0)) else emptyList())
            }
            val from = LocalDate.parse(path.substringAfterLast('/'))
            val to = LocalDate.parse(path.substringBeforeLast('/').substringAfterLast('/'))
            assertTrue(java.time.temporal.ChronoUnit.DAYS.between(from, to) <= 27)
            val selected = historical.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() in from..to }
                .filterNot { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() == missingDate }
            return if (duplicate && selected.isNotEmpty()) selected + selected.first() else selected
        }
    }
    @Test fun threeFixedIndicesHaveIndependentPriceRulesWithoutAnyStockSelectionsOrVolume() = runBlocking {
        val store = Store(); val feed = Feed()
        val progress = mutableListOf<Int>()
        val report = IndexMarketScanner(store, feed).scan("test", now) { completed, total, _ ->
            assertEquals(3, total); progress += completed
        }
        assertEquals(listOf(1, 2, 3), progress)
        assertEquals(StockCatalog.indices.map { it.symbol }, report.rows.map { it.symbol })
        assertTrue(report.rows.all { it.state == IndexDataState.LIVE && it.candle?.volume == 0.0 })
        report.rows.forEach { assertEquals(10.5, it.sma21!!, 1e-9); assertEquals(10.5, it.technicals!!.ema20, 1e-9) }
        assertTrue(report.rows.all { it.signal == "WAIT" && it.reason == "NO_QUALIFYING_15M_SHIFT" })
        assertEquals(setOf("NSE", "BSE"), feed.calendarCalls.map { it.first }.toSet())
        assertEquals(feed.calendarCalls.size, feed.calendarCalls.toSet().size)
        assertEquals(3, store.data.size)
    }
    @Test fun exchangeClosuresAndErrorsDoNotMasqueradeAsOtherIndexData() = runBlocking {
        val holidayFeed = Feed().apply { bseClosedToday = true }
        val holidayReport = IndexMarketScanner(Store(), holidayFeed).scan("test", now)
        assertEquals(IndexDataState.HISTORICAL, holidayReport.rows.single { it.symbol == "SENSEX" }.state)
        assertTrue(holidayReport.rows.filter { it.symbol != "SENSEX" }.all { it.state == IndexDataState.LIVE })
        val failed = IndexMarketScanner(Store(), Feed().apply { failNseOnly = true }).scan("test", now)
        assertEquals(IndexDataState.LIVE, failed.rows.single { it.symbol == "SENSEX" }.state)
        assertTrue(failed.rows.filter { it.symbol != "SENSEX" }.all { it.state == IndexDataState.UNAVAILABLE && it.signal == "WAIT" })
    }
    @Test fun weekendUsesLastVerifiedSessionAndNeverCreatesALiveSignal() = runBlocking {
        val saturday = date.plusDays(1).atTime(10, 0).atZone(MarketSession.ZONE).toInstant()
        val feed = Feed(saturday)
        val report = IndexMarketScanner(Store(), feed).scan("test", saturday)
        assertTrue(report.rows.all { it.state == IndexDataState.HISTORICAL && it.signal == "WAIT" })
        assertTrue(report.rows.all { it.candle?.timestamp == today.slots().last() })
        assertFalse(feed.paths.any { it.contains("intraday") })
        assertTrue(report.rows.all { it.reason == "HISTORICAL_CONTEXT_ONLY" })
    }
    @Test fun premarketAndAfterCloseReadingsAreHistoricalOnly() = runBlocking {
        for (clock in listOf(today.start.minusSeconds(600), today.end.plusSeconds(3600))) {
            val report = IndexMarketScanner(Store(), Feed(clock)).scan("test", clock)
            assertTrue(report.rows.all { it.state == IndexDataState.HISTORICAL && it.signal == "WAIT" })
            assertTrue(report.rows.all { it.candle != null })
        }
    }
    @Test fun missingVerifiedSessionCannotBeReplacedByOlderBarsAndDuplicatesFailClosed() = runBlocking {
        for (feed in listOf(Feed().apply { missingDate = date.minusDays(1) }, Feed().apply { duplicate = true })) {
            val report = IndexMarketScanner(Store(), feed).scan("test", now)
            assertTrue(report.rows.all { it.state == IndexDataState.UNAVAILABLE && it.signal == "WAIT" })
            assertTrue(report.rows.all { it.reason == "NO_VERIFIED_21_SESSION_HISTORY" })
        }
    }
    @Test fun cachedHistoryCannotHideCurrentFeedGapsOrFutureCandles() = runBlocking {
        val store = Store(); val feed = Feed(); val scanner = IndexMarketScanner(store, feed)
        scanner.scan("test", now)
        feed.missingCurrent = true
        assertTrue(scanner.scan("test", now).rows.all { it.state == IndexDataState.UNAVAILABLE })
        feed.missingCurrent = false; feed.includeFuture = true
        assertTrue(scanner.scan("test", now).rows.all { it.reason == "INVALID_INDEX_CANDLE" })
    }
    @Test fun formingCandleIsIgnoredAndClosingTimeSuppressesAnyLiveSignal() = runBlocking {
        val report = IndexMarketScanner(Store(), Feed().apply { flatFormingCandle = true }).scan("test", now)
        assertTrue(report.rows.all { it.state == IndexDataState.LIVE && it.candle?.timestamp == today.start.plusSeconds(2700) })
        val saved = report.rows.first().copy(signal = "PAPER_BUY")
        val afterClose = saved.at(today.end.plusSeconds(1))
        assertEquals(IndexDataState.HISTORICAL, afterClose.state); assertEquals("WAIT", afterClose.signal)
    }
    @Test fun authenticationAbortsAndUnknownErrorTextIsNeverDisplayed() = runBlocking {
        val feed = Feed().apply { error = "UPSTOX_AUTH_REQUIRED" }
        try { IndexMarketScanner(Store(), feed).scan("test", now); fail() }
        catch (error: IOException) { assertEquals("UPSTOX_AUTH_REQUIRED", error.message) }
        feed.error = "PRIVATE_PROVIDER_SENTINEL"
        assertTrue(IndexMarketScanner(Store(), feed).scan("test", now).rows.all { it.reason == "INDEX_FETCH_FAILED" })
    }
    @Test fun freshSnapshotExpiresToWaitAndHistoricalSignalCannotBecomeLive() {
        val live = IndexReading("NIFTY50", IndexDataState.LIVE, bar(now.minusSeconds(901), 0.0), signal = "PAPER_BUY")
        val expired = live.at(now.plusSeconds(1100))
        assertEquals(IndexDataState.STALE, expired.state); assertEquals("WAIT", expired.signal)
        assertEquals("WAIT", live.copy(state = IndexDataState.HISTORICAL).at(now).signal)
        assertEquals(IndexDataState.UNAVAILABLE, live.copy(candle = bar(now.plusSeconds(900), 0.0)).at(now).state)
    }
    @Test fun cancellationAndTimeoutCannotReturnAPartialReport() = runBlocking {
        val feed = Feed().apply { hang = true }
        try { IndexMarketScanner(Store(), feed, 30).scan("test", now); fail() }
        catch (_: TimeoutCancellationException) { }
        val job = async { IndexMarketScanner(Store(), feed).scan("test", now) }
        yield(); job.cancelAndJoin(); assertTrue(job.isCancelled)
    }
}
