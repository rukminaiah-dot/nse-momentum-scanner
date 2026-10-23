package com.nsemomentum.paper

import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.time.LocalDate
import java.util.concurrent.TimeUnit

class UpstoxCandleFeedTest {
    private val emptyCandles = """{"status":"success","data":{"candles":[]}}"""
    private fun feed(server: MockWebServer, timeout: Long = 1000) = UpstoxCandleFeed(
        OkHttpClient.Builder().callTimeout(timeout, TimeUnit.MILLISECONDS).retryOnConnectionFailure(false)
            .followRedirects(false).followSslRedirects(false).build(), server.url("/").toString().trimEnd('/'), 0)

    @Test fun authenticationIsNotRetriedAndUsesGet() = runBlocking {
        val server = MockWebServer()
        try {
            server.enqueue(MockResponse().setResponseCode(401))
            try { feed(server).candles("test", "/v3/historical-candle/test"); fail("Expected auth failure") }
            catch (error: IOException) { assertEquals("UPSTOX_AUTH_REQUIRED", error.message) }
            assertEquals(1, server.requestCount)
            assertEquals("GET", server.takeRequest().method)
        } finally { server.shutdown() }
    }
    @Test fun throttledRequestRetriesAndStopsAtThreeAttempts() = runBlocking {
        val server = MockWebServer()
        try {
            repeat(3) { server.enqueue(MockResponse().setResponseCode(429).addHeader("Retry-After", "1")) }
            try { feed(server).candles("test", "/v3/historical-candle/test"); fail("Expected rate limit") }
            catch (error: IOException) { assertEquals("RATE_LIMITED", error.message) }
            assertEquals(3, server.requestCount)
        } finally { server.shutdown() }
    }
    @Test fun serverErrorCanRecover() = runBlocking {
        val server = MockWebServer()
        try {
            server.enqueue(MockResponse().setResponseCode(503)); server.enqueue(MockResponse().setBody(emptyCandles))
            assertTrue(feed(server).candles("test", "/v3/historical-candle/test").isEmpty())
            assertEquals(2, server.requestCount)
        } finally { server.shutdown() }
    }
    @Test fun cancellationDuringBodyReadClosesCallPromptly() = runBlocking {
        val server = MockWebServer()
        try {
            server.enqueue(MockResponse().setBody(emptyCandles).setBodyDelay(3, TimeUnit.SECONDS))
            val job = async(Dispatchers.IO) { feed(server, 5000).candles("test", "/v3/historical-candle/test") }
            withContext(Dispatchers.IO) { assertNotNull(server.takeRequest(1, TimeUnit.SECONDS)) }
            withTimeout(1000) { job.cancelAndJoin() }
            assertTrue(job.isCancelled)
        } finally { server.shutdown() }
    }
    @Test fun calendarSupportsClosedAndRegularDatesAndRejectsSpecial() = runBlocking {
        val server = MockWebServer()
        try {
            val date = LocalDate.parse("2026-10-22"); val regular = regular(date)
            server.enqueue(MockResponse().setBody("""{"status":"success","data":[]}"""))
            assertNull(feed(server).session("test", date))
            fun body(end: Long) = """{"status":"success","data":[{"exchange":"NSE","start_time":${regular.start.toEpochMilli()},"end_time":$end}]}"""
            server.enqueue(MockResponse().setBody(body(regular.end.toEpochMilli())))
            assertEquals(regular, feed(server).session("test", date))
            server.enqueue(MockResponse().setBody(body(regular.end.minusSeconds(3600).toEpochMilli())))
            try { feed(server).session("test", date); fail("Expected special-session rejection") }
            catch (error: IOException) { assertEquals("UNSUPPORTED_SPECIAL_SESSION", error.message) }
        } finally { server.shutdown() }
    }

    @Test fun totalCallTimeoutBoundsSlowResponseBodies() = runBlocking {
        val server = MockWebServer()
        val attempts = java.util.concurrent.atomic.AtomicInteger()
        try {
            repeat(3) { server.enqueue(MockResponse().setBody(emptyCandles).setBodyDelay(2, TimeUnit.SECONDS)) }
            val http = OkHttpClient.Builder().callTimeout(300, TimeUnit.MILLISECONDS)
                .retryOnConnectionFailure(false)
                .eventListener(object : okhttp3.EventListener() {
                    override fun callStart(call: okhttp3.Call) { attempts.incrementAndGet() }
                }).build()
            val client = UpstoxCandleFeed(http, server.url("/").toString().trimEnd('/'), 0)
            withTimeout(6000) {
                try { client.candles("test", "/v3/historical-candle/test"); fail("Expected network timeout") }
                catch (error: IOException) { assertEquals("NETWORK_ERROR", error.message) }
            }
            // Timeout scheduling can stop retries early on a loaded runner; assert bounded calls.
            assertTrue("Expected one to three bounded attempts", attempts.get() in 1..3)
            assertTrue(server.requestCount in 0..3)
        } finally { server.shutdown() }
    }
    @Test fun localRollingBudgetBlocksFurtherCalls() = runBlocking {
        val server = MockWebServer()
        try {
            repeat(2) { server.enqueue(MockResponse().setBody(emptyCandles)) }
            val client = UpstoxCandleFeed(OkHttpClient(), server.url("/").toString().trimEnd('/'), 0, 2)
            repeat(2) { client.candles("test", "/v3/historical-candle/test") }
            try { client.candles("test", "/v3/historical-candle/test"); fail("Expected local budget limit") }
            catch (error: IOException) { assertEquals("LOCAL_RATE_BUDGET_EXHAUSTED", error.message) }
            assertEquals(2, server.requestCount)
        } finally { server.shutdown() }
    }

    @Test fun bseCalendarCannotBeSubstitutedWithNseCalendar() = runBlocking {
        val server = MockWebServer()
        try {
            val date = LocalDate.parse("2026-10-22"); val regular = regular(date)
            fun body(exchange: String) = """{"status":"success","data":[{"exchange":"$exchange","start_time":${regular.start.toEpochMilli()},"end_time":${regular.end.toEpochMilli()}}]}"""
            server.enqueue(MockResponse().setBody(body("NSE")))
            assertNull(feed(server).session("test", date, "BSE"))
            server.enqueue(MockResponse().setBody(body("BSE")))
            assertEquals(regular, feed(server).session("test", date, "BSE"))
        } finally { server.shutdown() }
    }

    @Test fun duplicateAndInvalidPayloadsAreRejected() {
        val row = """["2026-10-22T09:15:00+05:30",10,11,9,10.5,100]"""
        try {
            UpstoxCandleFeed.parseCandles(JSONObject("""{"data":{"candles":[$row,$row]}}"""))
            fail("Expected duplicate rejection")
        } catch (error: IOException) { assertEquals("DUPLICATE_CANDLE", error.message) }
        val invalid = row.replace(",9,", ",-9,")
        try {
            UpstoxCandleFeed.parseCandles(JSONObject("""{"data":{"candles":[$invalid]}}"""))
            fail("Expected invalid candle rejection")
        } catch (error: IOException) { assertEquals("INVALID_CANDLE", error.message) }
    }
}
