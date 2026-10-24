package com.nsemomentum.paper

import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId

/** A session is verified from the exchange timings response, never inferred from stock coverage. */
data class MarketSession(val date: LocalDate, val start: Instant, val end: Instant) {
    fun isRegular(): Boolean = start.atZone(ZONE).toLocalDate() == date &&
        end.atZone(ZONE).toLocalDate() == date &&
        start.atZone(ZONE).toLocalTime() == LocalTime.of(9, 15) &&
        end.atZone(ZONE).toLocalTime() == LocalTime.of(15, 30)

    fun slots(): List<Instant> = (0 until 25).map { start.plusSeconds(it * 900L) }

    fun completedSlot(now: Instant): Instant? {
        if (!isRegular() || now < start.plusSeconds(900) || now > end.plusSeconds(180)) return null
        return slots().lastOrNull { it.plusSeconds(900) <= now }
    }

    companion object { val ZONE: ZoneId = ZoneId.of("Asia/Kolkata") }
}

interface CandleStore {
    fun save(symbol: String, bars: List<Candle>)
    fun bars(symbol: String): List<Candle>
}

interface CandleFeed {
    suspend fun session(token: String, date: LocalDate): MarketSession?
    suspend fun session(token: String, date: LocalDate, exchange: String): MarketSession? {
        require(exchange == "NSE") { "UNVERIFIED_EXCHANGE_CALENDAR" }
        return session(token, date)
    }
    suspend fun candles(token: String, path: String): List<Candle>
    suspend fun indexCandles(token: String, path: String): List<Candle> = candles(token, path)
}
