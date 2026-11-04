package com.nsemomentum.paper

import java.time.LocalDate
import java.time.Instant
import kotlinx.coroutines.CancellationException

/** Metadata only: never URLs, instrument keys, credentials, response bodies or exception text. */
object HistoryDiagnostics {
    suspend fun fetch(feed: CandleFeed, token: String, path: String, symbol: String, start: LocalDate, end: LocalDate): List<Candle> {
        val began = System.nanoTime()
        DiagnosticLog.event("HISTORY_FETCH","STARTED","from=$start to=$end",symbol)
        try {
            val bars = feed.candles(token,path)
            DiagnosticLog.event("HISTORY_FETCH","RECEIVED","from=$start to=$end received=${bars.size} ms=${(System.nanoTime()-began)/1_000_000}",symbol)
            return bars
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) {
            DiagnosticLog.event("HISTORY_FETCH",DiagnosticLog.errorCode(error),"from=$start to=$end ms=${(System.nanoTime()-began)/1_000_000}",symbol)
            throw error
        }
    }

    fun day(stage: String, session: MarketSession, bars: List<Candle>, symbol: String?,
            log: (String, String, String, String?) -> Unit = { e, r, n, s -> DiagnosticLog.event(e,r,n,s) },
            expected: Set<Instant> = session.slots().toSet()) {
        val received = bars.map { it.timestamp }.toSet()
        val missing = (expected - received).sorted()
        val invalid = bars.count { !PaperStrategy.validCandle(it) }
        val duplicate = bars.size - received.size
        log("HISTORY_DAY", stage,
            "date=${session.date} expected=${expected.size} received=${bars.size} missing=${missing.size} extra=${(received-expected).size} invalid=$invalid duplicate=$duplicate", symbol)
        if (missing.isNotEmpty()) {
            val slots = missing.joinToString(",") {
                val time = it.atZone(MarketSession.ZONE)
                "%02d%02d".format(java.util.Locale.ROOT,time.hour,time.minute)
            }
            log("HISTORY_MISSING", stage, "date=${session.date} slots=$slots", symbol)
        }
    }
}
