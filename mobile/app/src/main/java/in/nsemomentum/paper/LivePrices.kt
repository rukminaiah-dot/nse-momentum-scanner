package com.nsemomentum.paper

import com.google.protobuf.CodedInputStream
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import okhttp3.*
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.URI
import java.time.Instant
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Display only. Never fed into candle strategies, qualification or paper outcomes. */
data class LiveQuote(val instrumentKey: String, val price: Double, val previousClose: Double?, val tradedAt: Instant, val receivedAt: Instant) {
    val change: Double? get() = previousClose?.let { (price - it).takeIf(Double::isFinite) }
    val changePercent: Double? get() = previousClose?.let { ((price / it - 1) * 100).takeIf(Double::isFinite) }
    fun label(now: Instant, connected: Boolean, marketOpen: Boolean): String = when {
        !marketOpen -> "Last trade · market not confirmed open"
        !connected -> "Disconnected · last received price"
        java.time.Duration.between(receivedAt, now).seconds !in -5..30 -> "Stale · waiting for an update"
        java.time.Duration.between(tradedAt, now).seconds !in -5..30 -> "Last trade · no recent trade"
        else -> "LIVE"
    }
}
data class LivePriceState(val status: String = "Connecting to Upstox…", val connected: Boolean = false,
                          val quotes: Map<String, LiveQuote> = emptyMap(), val markets: Map<String, Boolean> = emptyMap())
data class LivePriceFrame(val quotes: Map<String, LiveQuote>, val markets: Map<String, Boolean>)

/** LTPC subset of Upstox's official V3 MarketDataFeed.proto (field numbers unchanged).
 * Unknown fields, including auction extensions, are skipped by the protobuf runtime. */
object LivePriceDecoder {
    private fun fields(bytes: ByteArray, block: (Int, CodedInputStream) -> Boolean) {
        val input = CodedInputStream.newInstance(bytes)
        while (!input.isAtEnd) {
            val tag = input.readTag()
            require(tag != 0)
            if (!block(tag, input)) require(input.skipField(tag))
        }
    }
    fun decode(bytes: ByteArray, subscribed: Set<String>, now: Instant): LivePriceFrame {
        require(bytes.size <= 2 * 1024 * 1024)
        var timestamp = 0L
        val rawFeeds = mutableListOf<ByteArray>()
        val markets = mutableMapOf<String, Boolean>()
        fields(bytes) { tag, input -> when (tag) {
            18 -> { rawFeeds += input.readByteArray(); true }
            24 -> { timestamp = input.readInt64(); true }
            34 -> { fields(input.readByteArray()) { t, nested ->
                if (t != 10) false else {
                    var key = ""; var status = 0
                    fields(nested.readByteArray()) { mt, value -> when (mt) {
                        10 -> { key = value.readStringRequireUtf8(); true }
                        16 -> { status = value.readEnum(); true }
                        else -> false
                    } }
                    if (key.isNotEmpty()) markets[key] = status == 2 // NORMAL_OPEN, never inferred from weekday.
                    true
                }
            }; true }
            else -> false
        } }
        require(timestamp > 0 && timestamp <= now.plusSeconds(10).toEpochMilli())
        val quotes = mutableMapOf<String, LiveQuote>()
        val seen = mutableSetOf<String>()
        for (entry in rawFeeds) {
            var key = ""; var feed: ByteArray? = null
            fields(entry) { tag, input -> when (tag) {
                10 -> { key = input.readStringRequireUtf8(); true }
                18 -> { feed = input.readByteArray(); true }
                else -> false
            } }
            if (key !in subscribed) continue
            require(seen.add(key))
            var ltpc: ByteArray? = null
            feed?.let { fields(it) { tag, input -> if (tag == 10) { ltpc = input.readByteArray(); true } else false } }
            var price = Double.NaN; var close = Double.NaN; var time = 0L
            ltpc?.let { fields(it) { tag, input -> when (tag) {
                9 -> { price = input.readDouble(); true }
                16 -> { time = input.readInt64(); true }
                33 -> { close = input.readDouble(); true }
                else -> false
            } } }
            if (!price.isFinite() || price <= 0 || time <= 0 || time > timestamp + 1000) continue
            quotes[key] = LiveQuote(key, price, close.takeIf { it.isFinite() && it > 0 }, Instant.ofEpochMilli(time), now)
        }
        return LivePriceFrame(quotes, markets)
    }
    fun authorizedSocket(value: String): Boolean = runCatching {
        val uri = URI(value)
        uri.scheme == "wss" && uri.host?.endsWith(".upstox.com") == true && uri.userInfo == null &&
            uri.port in setOf(-1, 443) && uri.fragment == null
    }.getOrDefault(false)
    fun subscription(keys: Set<String>): ByteString {
        require(keys.isNotEmpty() && keys.size <= 20 && keys.all { it.matches(Regex("(?:NSE|BSE)_EQ\\|[^\\s,]{1,100}")) })
        return JSONObject().put("guid", java.util.UUID.randomUUID().toString()).put("method", "sub")
            .put("data", JSONObject().put("mode", "ltpc").put("instrumentKeys", JSONArray(keys.sorted())))
            .toString().toByteArray(Charsets.UTF_8).toByteString()
    }
    fun merge(previous: Map<String, LiveQuote>, incoming: Map<String, LiveQuote>): Map<String, LiveQuote> = previous + incoming.filter { (key, quote) ->
        previous[key]?.let { quote.tradedAt >= it.tradedAt } ?: true
    }
}

class UpstoxLivePrices(
    private val authClient: OkHttpClient = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).callTimeout(20, TimeUnit.SECONDS)
        .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false).build(),
    private val apiBase: String = "https://api.upstox.com",
    private val socketClient: OkHttpClient = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).readTimeout(0, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false).build()
) {
    internal suspend fun authorize(token: String): String = suspendCancellableCoroutine { continuation ->
        val request = Request.Builder().url("$apiBase/v3/feed/market-data-feed/authorize").get()
            .header("Authorization", "Bearer $token").header("Accept", "application/json").build()
        val call = authClient.newCall(request)
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { if (continuation.isActive) continuation.resumeWithException(IOException("QUOTE_NETWORK_ERROR")) }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    try {
                        if (response.code == 401 || response.code == 403) throw IOException("UPSTOX_AUTH_REQUIRED")
                        if (response.code == 429) throw IOException("QUOTE_RATE_LIMITED")
                        if (!response.isSuccessful) throw IOException("QUOTE_CONNECTION_FAILED")
                        val root = JSONObject(response.body?.string() ?: "")
                        val url = root.getJSONObject("data").getString("authorized_redirect_uri")
                        if (root.optString("status") != "success" || !LivePriceDecoder.authorizedSocket(url)) throw IOException("INVALID_QUOTE_AUTHORIZATION")
                        if (continuation.isActive) continuation.resume(url)
                    } catch (e: Exception) {
                        val safe = e.message?.takeIf { it in setOf("UPSTOX_AUTH_REQUIRED", "QUOTE_RATE_LIMITED", "QUOTE_CONNECTION_FAILED", "INVALID_QUOTE_AUTHORIZATION") }
                            ?: "INVALID_QUOTE_AUTHORIZATION"
                        if (continuation.isActive) continuation.resumeWithException(IOException(safe))
                    }
                }
            }
        })
    }
    private sealed class Event {
        data object Open : Event()
        data class Data(val bytes: ByteArray) : Event()
        data class End(val auth: Boolean = false) : Event()
    }
    fun stream(token: String, keys: Set<String>): Flow<LivePriceState> = flow {
        val subscription = LivePriceDecoder.subscription(keys)
        require(token.isNotBlank())
        var state = LivePriceState()
        var failures = 0
        while (currentCoroutineContext().isActive) {
            emit(state.copy(status = if (failures == 0) "Connecting to Upstox…" else "Reconnecting to Upstox…", connected = false))
            val events = Channel<Event>(64)
            var socket: WebSocket? = null
            var authenticationFailed = false
            try {
                val url = authorize(token)
                socket = socketClient.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
                    override fun onOpen(webSocket: WebSocket, response: Response) {
                        if (!webSocket.send(subscription) || events.trySend(Event.Open).isFailure) webSocket.cancel()
                    }
                    override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                        if (bytes.size > 2 * 1024 * 1024 || events.trySend(Event.Data(bytes.toByteArray())).isFailure) webSocket.cancel()
                    }
                    override fun onMessage(webSocket: WebSocket, text: String) { webSocket.cancel() }
                    override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(code, null) }
                    override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { events.trySend(Event.End()) }
                    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { events.trySend(Event.End(response?.code in setOf(401, 403))) }
                })
                while (currentCoroutineContext().isActive) {
                    when (val event = withTimeout(90_000) { events.receive() }) {
                        Event.Open -> { state = state.copy(status = "Connected · waiting for market data", connected = true, markets = emptyMap()); emit(state) }
                        is Event.Data -> {
                            val frame = LivePriceDecoder.decode(event.bytes, keys, Instant.now())
                            state = state.copy(status = "Upstox price stream connected", connected = true,
                                quotes = LivePriceDecoder.merge(state.quotes, frame.quotes), markets = state.markets + frame.markets)
                            failures = 0
                            emit(state)
                        }
                        is Event.End -> { authenticationFailed = event.auth; break }
                    }
                }
            } catch (_: TimeoutCancellationException) {
                // Missing market frames reconnect safely; prices lose LIVE labeling while disconnected.
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) { authenticationFailed = error.message == "UPSTOX_AUTH_REQUIRED" }
            finally { socket?.cancel(); events.close() }
            if (authenticationFailed) {
                emit(LivePriceState(status = "Upstox rejected the token. Update it in Settings."))
                awaitCancellation()
            }
            state = state.copy(status = "Price connection interrupted · retrying", connected = false, markets = emptyMap())
            emit(state)
            delay((1000L shl failures.coerceAtMost(5)).coerceAtMost(30_000))
            failures++
        }
    }
}
