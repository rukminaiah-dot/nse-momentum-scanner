package com.nsemomentum.paper

import java.time.DayOfWeek
import java.time.LocalDate
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class TomorrowWatchTest {
    private val friday = LocalDate.parse("2026-11-20")

    @Test fun closeAndUpstoxDailyVolumeDetermineTheNextTradingSessionWatchlist() = runBlocking {
        val stocks = listOf("UP", "DOWN", "INSIDE", "LOWVOL", "MISSING").map { Stock(it, it) }
        val feed = object : CandleFeed {
            override suspend fun session(token: String, date: LocalDate) =
                if (date.dayOfWeek in setOf(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY)) null else regular(date)

            override suspend fun candles(token: String, path: String): List<Candle> {
                val close = when {
                    "/UP/" in path -> 505.0
                    "/DOWN/" in path -> 475.0
                    "/INSIDE/" in path -> 490.0
                    else -> 505.0
                }
                val baseline = (1L..32L).map { friday.minusDays(it) }
                    .filter { it.dayOfWeek.value <= 5 }.take(if ("/MISSING/" in path) 19 else 20)
                    .map { Candle(regular(it).start, 490.0, 500.0, 480.0, 490.0, 100.0) }
                val volume = if ("/LOWVOL/" in path) 149.0 else 150.0
                return baseline + Candle(regular(friday).start, close, close, close, close, volume)
            }
        }
        val result = TomorrowWatch(feed).prepare("token", stocks, friday, regular(friday).end)
        assertEquals(friday.plusDays(3), result.target)
        assertEquals(listOf(WatchSide.BUY, WatchSide.SELL), result.rows.map { it.side })
        assertEquals(2, result.skipped)
        assertEquals(1, result.missing)
        assertTrue(result.rows.all { it.dailyRelativeVolume == 1.5 })
        assertEquals(result, SavedWatch.decode(result.encode()))
    }

    @Test fun breakoutRequiresCompletedOpeningRangeAndTwentyMatchingVolumes() {
        val session = regular(friday)
        val prior = (1L..20L).map { regular(friday.minusDays(it)) }
        val history = prior.map { bar(it.start.plusSeconds(900), 100.0) }
        val opening = (0L..2L).map { bar(session.start.plusSeconds(it * 300)) }
        val breakout = Candle(session.start.plusSeconds(900), 11.0, 13.0, 11.0, 12.0, 150.0)
        val candles = opening + breakout
        val closeTime = session.start.plusSeconds(1200)
        assertTrue(validateWatch(WatchSide.BUY, session, prior, candles, history, closeTime).startsWith("Passed"))
        assertFalse(validateWatch(WatchSide.SELL, session, prior, candles, history, closeTime).startsWith("Passed"))
        assertEquals("Waiting for verified data", validateWatch(WatchSide.BUY, session, prior, candles, history.dropLast(1), closeTime))
        assertEquals("Waiting for verified data", validateWatch(WatchSide.BUY, session, prior, candles, history, closeTime.minusSeconds(1)))
    }
}
