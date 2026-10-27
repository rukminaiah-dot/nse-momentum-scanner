package com.nsemomentum.paper

import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.time.LocalDate

class UpstoxPaperScannerTest {
    private val date = LocalDate.parse("2026-10-22")
    private val today = regular(date)
    private val now = today.start.plusSeconds(3601)
    private val holiday = date.minusDays(2)
    private val sessions = generateSequence(date.minusDays(1)) { it.minusDays(1) }
        .filter { it.dayOfWeek.value <= 5 && it != holiday }.take(20).map { regular(it) }.toList()
    private val history = sessions.flatMap { it.slots().map { t -> bar(t) } }
    private val intraday = today.slots().take(4).mapIndexed { index, time ->
        bar(time, 200.0).let { if (index == 3) it.copy(close = 10.8) else it }
    }
    private val universe = listOf("ONE" to "NSE_EQ|ONE", "TWO" to "NSE_EQ|TWO")

    private class MemoryStore : CandleStore {
        val data = mutableMapOf<String, List<Candle>>()
        var qualified = false
        var activeBuy = false
        override fun qualifiedOn(symbol: String, date: LocalDate) = qualified
        override fun hasActivePaperBuy(symbol: String) = activeBuy
        override fun bars(symbol: String) = data[symbol].orEmpty()
        override fun save(symbol: String, bars: List<Candle>) {
            data[symbol] = (data[symbol].orEmpty() + bars).associateBy { it.timestamp }.values.sortedBy { it.timestamp }
        }
    }
    @Test fun qualifiedStockCanBuyOnFirstCandleDespiteLowLatestVolume() = runBlocking {
        val store = MemoryStore().apply { qualified = true }
        val feed = Feed().apply { intradayBars = listOf(bar(today.start,50.0).copy(close=10.8)) }
        val report = UpstoxPaperScanner(store,feed).scan("test",listOf(universe.first()),setOf("ONE"),today.start.plusSeconds(901))
        assertEquals("PAPER_BUY",report.rows.single().signal)
        assertEquals(.5,report.rows.single().relativeVolume!!,0.0)
    }
    @Test fun activeBuyCanExitOnBearishCrossWithoutAnotherVolumeQualification() = runBlocking {
        val store = MemoryStore().apply { activeBuy = true }
        val feed = Feed().apply { intradayBars = listOf(bar(today.start,50.0).copy(close=10.2)) }
        val report = UpstoxPaperScanner(store,feed).scan("test",listOf(universe.first()),setOf("ONE"),today.start.plusSeconds(901))
        assertEquals("PAPER_SELL",report.rows.single().signal)
    }
    private inner class Feed : CandleFeed {
        val paths = mutableListOf<String>()
        var missingDate: LocalDate? = null
        var fail: String? = null
        var waitForever = false
        var intradayBars = intraday
        val calendarDates = mutableListOf<LocalDate>()
        override suspend fun session(token: String, date: LocalDate): MarketSession? {
            calendarDates += date
            return if (date.dayOfWeek.value > 5 || date == holiday) null else regular(date)
        }
        override suspend fun candles(token: String, path: String): List<Candle> {
            paths += path
            if (waitForever) awaitCancellation()
            fail?.let { throw IOException(it) }
            if (path.contains("intraday")) return intradayBars
            val pieces = path.split('/')
            val from = LocalDate.parse(pieces.last())
            val to = LocalDate.parse(pieces[pieces.lastIndex - 1])
            assertTrue(java.time.temporal.ChronoUnit.DAYS.between(from, to) <= 27)
            return history.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() in from..to }
                .filterNot { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() == missingDate }
        }
    }

    @Test fun scansSameSnapshotWithExactSessionsAndOrderedProgress() = runBlocking {
        val store = MemoryStore(); val feed = Feed(); val progress = mutableListOf<Int>()
        val result = UpstoxPaperScanner(store, feed).scan("test", universe, setOf("ONE"), now) { n, total, _ ->
            assertEquals(2, total); progress += n
        }
        assertEquals(listOf(1, 2), progress)
        assertEquals(2, result.requestCount); assertEquals(0, result.failedRequests)
        assertTrue(result.rows.all { it.relativeVolume == 2.0 })
        assertTrue(result.rows.all { it.candle?.close == 10.8 })
        assertTrue(result.rows.all { it.averageSlotVolume == 100.0 })
        assertEquals((10.8 / 10.5 - 1.0) * 100.0, result.rows.first().dailyChangePercent!!, 1e-9)
        assertNotNull(result.rows.first { it.symbol == "ONE" }.technicals)
        assertNull(result.rows.first { it.symbol == "TWO" }.technicals)
        assertTrue(feed.calendarDates.contains(holiday))
        val historicalCalls = feed.paths.count { !it.contains("intraday") }
        UpstoxPaperScanner(store, feed).scan("test", universe, emptySet(), now)
        assertEquals(historicalCalls, feed.paths.count { !it.contains("intraday") })
    }
    @Test fun missingSessionFailsClosedAndCanRetrySameDay() = runBlocking {
        val store = MemoryStore(); val feed = Feed().apply { missingDate = sessions.first().date }
        val scanner = UpstoxPaperScanner(store, feed)
        val failed = scanner.scan("test", universe, emptySet(), now)
        assertTrue(failed.rows.all { it.reason == "NO_VERIFIED_20_SESSION_BASELINE" && it.relativeVolume == null })
        feed.missingDate = null
        assertTrue(scanner.scan("test", universe, emptySet(), now).rows.all { it.relativeVolume == 2.0 })
    }
    @Test fun cachedTodayCannotConcealMissingOrStaleFeedCandle() = runBlocking {
        val store = MemoryStore(); val feed = Feed(); val scanner = UpstoxPaperScanner(store, feed)
        scanner.scan("test", universe, emptySet(), now)
        feed.intradayBars = intraday.dropLast(1)
        val report = scanner.scan("test", universe, emptySet(), now)
        assertTrue(report.rows.all { it.reason == "MISSING_COMPLETED_15M_CANDLE" && it.signal == "WAIT" })
        assertEquals(2, report.failedRequests)
    }
    @Test fun safeHttpErrorsAreCounted() = runBlocking {
        val feed = Feed().apply { fail = "UPSTOX_HTTP_400" }
        val report = UpstoxPaperScanner(MemoryStore(), feed).scan("test", universe, emptySet(), now)
        assertEquals(2, report.failedRequests)
        assertTrue(report.rows.all { it.reason == "UPSTOX_HTTP_400" })
    }
    @Test fun cancellationAndDeadlineDoNotProducePartialReport() = runBlocking {
        val feed = Feed().apply { waitForever = true }
        val job = async { UpstoxPaperScanner(MemoryStore(), feed).scan("test", universe, emptySet(), now) }
        yield(); job.cancelAndJoin(); assertTrue(job.isCancelled)
        try {
            UpstoxPaperScanner(MemoryStore(), feed, 30).scan("test", universe, emptySet(), now)
            fail("Expected timeout")
        } catch (_: TimeoutCancellationException) { }
    }
    @Test fun indexScanUses21SessionsZeroVolumeAndCorrectExchange() = runBlocking {
        val dates = generateSequence(date.minusDays(1)) { it.minusDays(1) }
            .filter { it.dayOfWeek.value <= 5 }.take(21).map { regular(it) }.toList()
        val calls = mutableListOf<String>()
        val feed = object : CandleFeed {
            override suspend fun session(token: String, date: LocalDate): MarketSession? = error("Exchange required")
            override suspend fun session(token: String, date: LocalDate, exchange: String): MarketSession? {
                calls += exchange
                return if (date.dayOfWeek.value <= 5) regular(date) else null
            }
            override suspend fun candles(token: String, path: String): List<Candle> {
                if (path.contains("intraday")) return intraday.map { it.copy(volume = 0.0) }
                val from = LocalDate.parse(path.substringAfterLast('/'))
                val to = LocalDate.parse(path.substringBeforeLast('/').substringAfterLast('/'))
                return dates.filter { it.date in from..to }.flatMap { s -> s.slots().map { bar(it, 0.0) } }
            }
        }
        val report = UpstoxPaperScanner(MemoryStore(), feed).scan("test", listOf("SENSEX" to "BSE_INDEX|SENSEX"), setOf("SENSEX"), now)
        assertEquals(setOf("BSE"), calls.toSet())
        assertEquals(0, report.failedRequests)
        assertNull(report.rows.single().relativeVolume)
        assertNotNull(report.rows.single().technicals)
        assertEquals("NO_QUALIFYING_15M_SHIFT", report.rows.single().reason)
    }
    @Test fun closedDayNeverRequestsCandles() = runBlocking {
        val feed = Feed()
        try {
            UpstoxPaperScanner(MemoryStore(), feed).scan("test", universe, emptySet(), regular(holiday).start.plusSeconds(1800))
            fail("Expected market closed")
        } catch (error: IOException) { assertEquals("MARKET_CLOSED", error.message) }
        assertTrue(feed.paths.isEmpty())
    }
}
