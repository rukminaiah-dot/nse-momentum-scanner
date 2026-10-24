package com.nsemomentum.paper

import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.util.concurrent.TimeUnit

class UpstoxInstrumentSearchTest {
    private val response = """{"status":"success","data":[{"name":"RELIANCE INDUSTRIES LTD.","segment":"BSE_EQ","exchange":"BSE",
        "isin":"INE002A01018","instrument_key":"BSE_EQ|INE002A01018","exchange_token":"500325",
        "trading_symbol":"RELIANCE","instrument_type":"A"}],"meta_data":{"page":{"page_number":1,"total_pages":2}}}"""
    private fun feed(server: MockWebServer) = UpstoxCandleFeed(
        OkHttpClient.Builder().callTimeout(2, TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false)
            .retryOnConnectionFailure(false).build(), server.url("/").toString().trimEnd('/'), 0)
    @Test fun searchUsesReadOnlyGetEncodedQueryExchangeAndPagination() = runBlocking {
        val server = MockWebServer()
        try {
            server.enqueue(MockResponse().setBody(response))
            val result = feed(server).searchInstruments("TEST_TOKEN", "M&M & Industries", "BSE")
            val request = server.takeRequest()
            assertEquals("GET", request.method); assertEquals(0L, request.bodySize)
            assertEquals("Bearer TEST_TOKEN", request.getHeader("Authorization"))
            val url = request.requestUrl!!
            assertEquals("/v2/instruments/search", url.encodedPath)
            assertEquals("M&M & Industries", url.queryParameter("query"))
            assertEquals("BSE", url.queryParameter("exchanges")); assertEquals("EQ", url.queryParameter("segments"))
            assertEquals("1", url.queryParameter("page_number")); assertEquals("30", url.queryParameter("records"))
            assertEquals("BSE_EQ|INE002A01018", result.instruments.single().instrumentKey)
            assertEquals(2, result.totalPages)
        } finally { server.shutdown() }
    }
    @Test fun authFailureDoesNotRetryOrExposeProviderBody() = runBlocking {
        val server = MockWebServer()
        try {
            server.enqueue(MockResponse().setResponseCode(401).setBody("PRIVATE_PROVIDER_SENTINEL"))
            try { feed(server).searchInstruments("TEST_TOKEN", "Reliance", "NSE"); fail() }
            catch (error: IOException) { assertEquals("UPSTOX_AUTH_REQUIRED", error.message) }
            assertEquals(1, server.requestCount)
        } finally { server.shutdown() }
    }
    @Test fun invalidMappingAndMissingPaginationFailBeforeSelection() = runBlocking {
        val server = MockWebServer()
        try {
            server.enqueue(MockResponse().setBody(response.replace("BSE_EQ|INE002A01018", "BSE_EQ|500325")))
            try { feed(server).searchInstruments("TEST_TOKEN", "Reliance", "BSE"); fail() }
            catch (error: IOException) { assertEquals("INVALID_INSTRUMENT_SEARCH_RESPONSE", error.message) }
            server.enqueue(MockResponse().setBody("""{"status":"success","data":[]}"""))
            try { feed(server).searchInstruments("TEST_TOKEN", "Reliance", "BSE"); fail() }
            catch (error: IOException) { assertEquals("INVALID_INSTRUMENT_SEARCH_RESPONSE", error.message) }
        } finally { server.shutdown() }
    }
    @Test fun cancellationClosesSearchWithoutReturningOldResults() = runBlocking {
        val server = MockWebServer()
        try {
            server.enqueue(MockResponse().setBody(response).setBodyDelay(2, TimeUnit.SECONDS))
            val job = async(Dispatchers.IO) { feed(server).searchInstruments("TEST_TOKEN", "Reliance", "BSE") }
            withContext(Dispatchers.IO) { assertNotNull(server.takeRequest(1, TimeUnit.SECONDS)) }
            withTimeout(1000) { job.cancelAndJoin() }
            assertTrue(job.isCancelled)
        } finally { server.shutdown() }
    }
    @Test fun badInputNeverContactsUpstox() = runBlocking {
        val server = MockWebServer()
        try {
            for (token in listOf("", "TEST_TOKEN")) {
                try { feed(server).searchInstruments(token, "a", "NSE"); fail() }
                catch (_: IllegalArgumentException) { }
            }
            assertEquals(0, server.requestCount)
        } finally { server.shutdown() }
    }
    @Test fun redirectsCannotForwardTokenToAnotherHost() = runBlocking {
        val server = MockWebServer()
        try {
            server.enqueue(MockResponse().setResponseCode(302).addHeader("Location", "https://other.example/"))
            try { feed(server).searchInstruments("TEST_TOKEN", "Reliance", "NSE"); fail() }
            catch (error: IOException) { assertEquals("UPSTOX_HTTP_302", error.message) }
            assertEquals(1, server.requestCount)
        } finally { server.shutdown() }
    }
}
