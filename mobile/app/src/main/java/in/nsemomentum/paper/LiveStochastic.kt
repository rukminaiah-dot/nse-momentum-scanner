package com.nsemomentum.paper

import java.time.Duration
import java.time.Instant
import java.time.LocalTime

data class LiveStochastic(val context: TechnicalContext, val sampledAt: Instant, val tradedAt: Instant)

/** Quote-derived forming-candle preview only. Never saved as OHLCV or used for paper execution. */
object LiveStochasticPreview {
    fun calculate(history: List<Candle>, quote: LiveQuote?, now: Instant, connected: Boolean, marketOpen: Boolean): LiveStochastic? {
        if (quote == null || !connected || !marketOpen || !quote.price.isFinite() || quote.price <= 0) return null
        if (Duration.between(quote.receivedAt, now).seconds !in 0..30 ||
            Duration.between(quote.tradedAt, now).seconds !in 0..30) return null
        val local = now.atZone(MarketSession.ZONE)
        val minute = local.hour * 60 + local.minute
        if (minute !in 555 until 930) return null
        val slot = local.toLocalDate().atTime(9,15).atZone(MarketSession.ZONE).toInstant()
            .plusSeconds(((minute - 555) / 15) * 900L)
        if (quote.tradedAt < slot || quote.tradedAt > now) return null
        val complete = history.filter { it.timestamp < slot }.sortedBy { it.timestamp }
        if (complete.size < 52 || complete.any { !PaperStrategy.validCandle(it) } ||
            complete.map { it.timestamp }.distinct().size != complete.size) return null
        val last = complete.last().timestamp
        // Do not synthesize missing intermediate bars from a later quote.
        val firstSlot = local.toLocalTime() < LocalTime.of(9,30)
        if (last != slot.minusSeconds(900) && !(firstSlot &&
                last.atZone(MarketSession.ZONE).toLocalDate() < local.toLocalDate() &&
                last.atZone(MarketSession.ZONE).toLocalTime() == LocalTime.of(15,15))) return null
        if (complete.takeLast(52).zipWithNext().any { (a,b) ->
            a.timestamp.atZone(MarketSession.ZONE).toLocalDate() == b.timestamp.atZone(MarketSession.ZONE).toLocalDate() &&
                Duration.between(a.timestamp,b.timestamp).seconds != 900L }) return null
        val provisional = Candle(slot, quote.price, quote.price, quote.price, quote.price, 0.0)
        return PaperStrategy.context(complete + provisional)?.let { LiveStochastic(it,now,quote.tradedAt) }
    }
}

data class PaperTrade(val symbol: String, val boughtAt: Instant, val buy: Double,
                      val soldAt: Instant? = null, val sell: Double? = null) {
    fun gross(mark: Double?): Double? = (sell ?: mark)?.let { it - buy }
    fun percent(mark: Double?): Double? = gross(mark)?.let { it / buy * 100.0 }
}

data class PaperTradeEvent(val symbol: String, val time: Instant, val direction: Int, val price: Double)

fun paperTrades(events: List<PaperTradeEvent>): List<PaperTrade> {
    val active = mutableMapOf<String,PaperTrade>()
    val closed = mutableListOf<PaperTrade>()
    events.sortedBy { it.time }.forEach { event ->
        if (!event.price.isFinite() || event.price <= 0) return@forEach
        if (event.direction == 1 && event.symbol !in active)
            active[event.symbol] = PaperTrade(event.symbol,event.time,event.price)
        else if (event.direction == -1) active.remove(event.symbol)?.let {
            if (event.time > it.boughtAt) closed += it.copy(soldAt=event.time,sell=event.price)
        }
    }
    return (closed + active.values).sortedByDescending { it.boughtAt }
}
