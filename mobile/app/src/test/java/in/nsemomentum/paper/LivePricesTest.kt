package com.nsemomentum.paper

import com.google.protobuf.CodedOutputStream
import kotlinx.coroutines.*
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.time.Instant

class LivePricesTest {
    private val now = Instant.parse("2026-10-23T05:00:00Z")
    private val key = "NSE_EQ|INE090A01021"
    private fun message(block: (CodedOutputStream) -> Unit): ByteArray {
        val bytes = ByteArrayOutputStream(); val out = CodedOutputStream.newInstance(bytes)
        block(out); out.flush(); return bytes.toByteArray()
    }
    private fun tick(price: Double = 110.0, close: Double = 100.0, time: Instant = now, instrument: String = key): ByteArray {
        val ltpc = message { it.writeDouble(1, price); it.writeInt64(2, time.toEpochMilli()); it.writeDouble(4, close); it.writeDouble(77, 99.0) }
        val feed = message { it.writeByteArray(1, ltpc) }
        return message { it.writeString(1, instrument); it.writeByteArray(2, feed) }
    }
    private fun frame(vararg entries: ByteArray, time: Instant = now): ByteArray = message { out ->
        out.writeEnum(1, 1); entries.forEach { out.writeByteArray(2, it) }; out.writeInt64(3, time.toEpochMilli())
    }
    @Test fun decodesOfficialV3LtpcWireNumbersAndComputesSignedDayChange() {
        val q = LivePriceDecoder.decode(frame(tick()), setOf(key), now).quotes.getValue(key)
        assertEquals(110.0, q.price, 0.0); assertEquals(10.0, q.change!!, 0.0); assertEquals(10.0, q.changePercent!!, 0.00001)
        assertEquals(now, q.tradedAt); assertEquals("LIVE", q.label(now, true, true))
        val down = LivePriceDecoder.decode(frame(tick(price = 90.0)), setOf(key), now).quotes.getValue(key)
        assertEquals(-10.0, down.change!!, 0.0); assertEquals(-10.0, down.changePercent!!, 0.00001)
        val noClose = LivePriceDecoder.decode(frame(tick(close = 0.0)), setOf(key), now).quotes.getValue(key)
        assertNull(noClose.change); assertNull(noClose.changePercent)
    }
    @Test fun neverLabelsOldDisconnectedOrUnconfirmedMarketDataLive() {
        val q = LivePriceDecoder.decode(frame(tick()), setOf(key), now).quotes.getValue(key)
        assertNotEquals("LIVE", q.label(now.plusSeconds(31), true, true))
        assertNotEquals("LIVE", q.label(now, false, true))
        assertNotEquals("LIVE", q.label(now, true, false))
        assertNotEquals("LIVE", q.copy(tradedAt = now.minusSeconds(60)).label(now, true, true))
        assertNotEquals("LIVE", q.label(now.minusSeconds(10), true, true))
    }
    @Test fun parsesMarketStatusAndDoesNotTreatAbsentOrClosedSegmentsAsOpen() {
        val entry = message { it.writeString(1, "NSE_EQ"); it.writeEnum(2, 2) }
        val market = message { it.writeByteArray(1, entry) }
        val bytes = message { it.writeEnum(1, 2); it.writeInt64(3, now.toEpochMilli()); it.writeByteArray(4, market) }
        val result = LivePriceDecoder.decode(bytes, setOf(key), now)
        assertEquals(true, result.markets["NSE_EQ"]); assertNull(result.markets["BSE_EQ"]); assertTrue(result.quotes.isEmpty())
        val closedEntry = message { it.writeString(1, "NSE_EQ"); it.writeEnum(2, 3) }
        val closed = message { it.writeInt64(3, now.toEpochMilli()); it.writeByteArray(4, message { m -> m.writeByteArray(1, closedEntry) }) }
        assertEquals(false, LivePriceDecoder.decode(closed, setOf(key), now).markets["NSE_EQ"])
    }
    @Test fun rejectsBadFramesAndIgnoresUnsubscribedAndInvalidPrices() {
        for (price in listOf(0.0, -1.0, Double.NaN, Double.POSITIVE_INFINITY))
            assertTrue(LivePriceDecoder.decode(frame(tick(price = price)), setOf(key), now).quotes.isEmpty())
        assertTrue(LivePriceDecoder.decode(frame(tick(instrument = "BSE_EQ|OTHER")), setOf(key), now).quotes.isEmpty())
        assertTrue(LivePriceDecoder.decode(frame(tick(time = now.plusSeconds(2))), setOf(key), now).quotes.isEmpty())
        for (bytes in listOf(byteArrayOf(18, 100, 1), frame(tick(), tick()), frame(tick(), time = now.plusSeconds(11)))) {
            try { LivePriceDecoder.decode(bytes, setOf(key), now); fail("Bad frame accepted") } catch (_: Exception) {}
        }
    }
    @Test fun outOfOrderTicksCannotReplaceANewerPriceAndSubscriptionIsLimitedToSelectedEquities() {
        val q = LiveQuote(key, 110.0, 100.0, now, now)
        val merged = LivePriceDecoder.merge(mapOf(key to q), mapOf(key to q.copy(price = 90.0, tradedAt = now.minusSeconds(1))))
        assertEquals(q, merged[key])
        val root = JSONObject(LivePriceDecoder.subscription(setOf(key)).utf8())
        assertEquals("sub", root.getString("method")); assertEquals("ltpc", root.getJSONObject("data").getString("mode"))
        assertEquals(1, root.getJSONObject("data").getJSONArray("instrumentKeys").length())
        for (keys in listOf(emptySet(), setOf("NSE_INDEX|Nifty 50"), (1..41).map { "NSE_EQ|TEST$it" }.toSet())) {
            try { LivePriceDecoder.subscription(keys); fail("Invalid subscription accepted") } catch (_: IllegalArgumentException) {}
        }
    }
    @Test fun fortySelectedEquitiesCanSubscribeTogether() {
        val keys = (1..40).map { "NSE_EQ|TEST$it" }.toSet()
        val root = JSONObject(LivePriceDecoder.subscription(keys).utf8())
        assertEquals(40, root.getJSONObject("data").getJSONArray("instrumentKeys").length())
    }
    @Test fun partialTickKeepsSameSessionCloseButNeverCarriesItIntoAnotherDay() {
        val previous = LiveQuote(key, 110.0, 100.0, now, now)
        val update = previous.copy(price = 112.0, previousClose = null, tradedAt = now.plusSeconds(1))
        val merged = LivePriceDecoder.merge(mapOf(key to previous), mapOf(key to update)).getValue(key)
        assertEquals(112.0, merged.price, 0.0)
        assertEquals(12.0, merged.changePercent!!, 0.000001)
        val nextDay = update.copy(tradedAt = now.plusSeconds(86400))
        assertNull(LivePriceDecoder.merge(mapOf(key to previous), mapOf(key to nextDay)).getValue(key).previousClose)
    }
    @Test fun onlyAcceptsSecureAuthorizedUpstoxSockets() {
        assertTrue(LivePriceDecoder.authorizedSocket("wss://feed.upstox.com/market-data-feeder/v3/test?code=private"))
        for (url in listOf("ws://feed.upstox.com/a", "wss://upstox.com.evil.test/a", "wss://evil.test/a", "wss://name@feed.upstox.com/a", "wss://feed.upstox.com:80/a"))
            assertFalse(LivePriceDecoder.authorizedSocket(url))
    }
    @Test fun authorizationIsReadOnlyDoesNotFollowRedirectsAndSanitizesFailures() = runBlocking {
        val server = MockWebServer(); server.start()
        try {
            val client = UpstoxLivePrices(apiBase = server.url("").toString().trimEnd('/'))
            server.enqueue(MockResponse().setResponseCode(401).setBody("PRIVATE_PROVIDER_SENTINEL"))
            try { client.authorize("TOKEN_SENTINEL"); fail() } catch (e: IOException) { assertEquals("UPSTOX_AUTH_REQUIRED", e.message) }
            val request = server.takeRequest()
            assertEquals("GET", request.method); assertEquals("/v3/feed/market-data-feed/authorize", request.path)
            assertEquals("Bearer TOKEN_SENTINEL", request.getHeader("Authorization"))
            server.enqueue(MockResponse().setResponseCode(302).addHeader("Location", "https://evil.test/"))
            try { client.authorize("test"); fail() } catch (e: IOException) { assertEquals("QUOTE_CONNECTION_FAILED", e.message) }
            server.enqueue(MockResponse().setBody("{\"status\":\"success\",\"data\":{\"authorized_redirect_uri\":\"wss://feed.upstox.com/test\"}}"))
            assertEquals("wss://feed.upstox.com/test", client.authorize("test"))
            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            try { withTimeout(100) { client.authorize("test") }; fail() } catch (_: TimeoutCancellationException) {}
        } finally { server.shutdown() }
    }
}
