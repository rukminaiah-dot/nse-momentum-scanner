package com.nsemomentum.paper

import android.content.Context
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Instant
import java.time.LocalTime

/** One socket shared by the visible app and full-day service. No credentials are persisted here. */
object LiveMarketHub {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutable = MutableStateFlow(LivePriceState())
    val state: StateFlow<LivePriceState> = mutable
    private val owners = mutableMapOf<String, Set<String>>()
    private var keys = emptySet<String>()
    private var credential: String? = null
    private var job: Job? = null
    @Synchronized fun acquire(owner: String, token: String, requested: Set<String>) {
        owners[owner] = requested
        val union = owners.values.flatten().toSet()
        if (union == keys && token == credential && job?.isActive == true) return
        val sameCredential = token == credential
        job?.cancel(); keys = union; credential = token
        val initial = if (mutable.value.quotes.isNotEmpty() && sameCredential) mutable.value.quotes.filterKeys { it in union } else emptyMap()
        job = scope.launch {
            try { UpstoxLivePrices().stream(token, union, initial).collect { mutable.value = it } }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { mutable.value = LivePriceState(status = "Live connection unavailable · reopen to retry") }
        }
    }
    @Synchronized fun release(owner: String) {
        owners.remove(owner)
        if (owners.isEmpty()) { job?.cancel(); job = null; credential = null; keys = emptySet(); mutable.value = LivePriceState(status="Live connection stopped") }
    }
    @Synchronized fun reconnect() { job?.cancel(); job = null }
}

/** Single-flight index requests; retries failures, avoids re-downloading an already confirmed candle. */
object IndexRefresh {
    private val feed = UpstoxCandleFeed()
    private val lock = Mutex()
    private var lastAttempt = Instant.EPOCH
    private var lastSlot: Long? = null
    private var succeeded = false
    suspend fun refresh(context: Context, token: String, force: Boolean = false): IndexMarketReport? = lock.withLock {
        val store = IndexSnapshotStore(context)
        val now = Instant.now()
        val slot = now.epochSecond / 300
        val elapsed = java.time.Duration.between(lastAttempt, now).seconds
        val time = now.atZone(MarketSession.ZONE).toLocalTime()
        val regular = time >= LocalTime.of(9,20) && time < LocalTime.of(15,33)
        if (elapsed < 10 || (!force && succeeded && lastSlot == slot) || (!regular && !force && elapsed < 60)) return@withLock store.read()
        lastAttempt = now
        val database = CandleDatabase(context)
        try {
            val fresh = IndexMarketScanner(database,feed).scan(token)
            val old = store.read()?.rows?.associateBy { it.symbol }.orEmpty()
            val merged = fresh.copy(rows = fresh.rows.map { row -> mergeIndexReading(old[row.symbol], row) })
            store.write(merged)
            succeeded = fresh.rows.all { it.candle != null && it.lastError == null }
            lastSlot = slot
            DiagnosticLog.record(context,"INDEX_REFRESH", if (succeeded) "SUCCESS" else "PARTIAL", "rows=${fresh.rows.count { it.candle != null }}")
            merged
        } catch (error: TimeoutCancellationException) {
            succeeded = false
            DiagnosticLog.record(context,"INDEX_REFRESH","TIMEOUT")
            store.read()?.let { old -> old.copy(rows=old.rows.map { it.copy(lastError="INDEX_TIMEOUT") }).also(store::write) }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) {
            succeeded = false
            val code = DiagnosticLog.errorCode(error)
            DiagnosticLog.record(context,"INDEX_REFRESH",code)
            store.read()?.let { old ->
                val retained = old.copy(rows=old.rows.map { it.copy(lastError=code) })
                store.write(retained); retained
            }
        } finally { database.close() }
    }
}

fun mergeIndexReading(old: IndexReading?, fresh: IndexReading): IndexReading {
    if (fresh.candle == null && old?.candle != null) return old.copy(lastError=fresh.reason)
    if (old == null || fresh.candle == null) return fresh
    if (fresh.candle.timestamp < (old.candle?.timestamp ?: Instant.EPOCH)) return old
    val changed = old.signal in setOf("BULLISH","BEARISH","NEUTRAL") && old.signal != fresh.signal && fresh.state == IndexDataState.LIVE
    return fresh.copy(previousDirection=if (changed) old.signal else old.previousDirection,
        changedAt=if (changed) fresh.candle.timestamp.plusSeconds(300) else old.changedAt)
}
