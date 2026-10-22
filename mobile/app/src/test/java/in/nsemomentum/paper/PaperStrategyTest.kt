package in.nsemomentum.paper

import java.time.Instant
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PaperStrategyTest {
    private fun priorWeekdays(current: Candle, count: Int): List<Candle> {
        val zone = ZoneId.of("Asia/Kolkata")
        var day = current.timestamp.atZone(zone).toLocalDate()
        val rows = mutableListOf<Candle>()
        while (rows.size < count) {
            day = day.minusDays(1)
            if (day.dayOfWeek.value <= 5) {
                rows += current.copy(
                    timestamp = day.atTime(9, 15).atZone(zone).toInstant(),
                    volume = (rows.size + 1).toDouble()
                )
            }
        }
        return rows
    }

    private fun current() = Candle(
        Instant.parse("2026-10-22T03:45:00Z"), 10.0, 11.0, 9.0, 10.5, 100.0
    )

    @Test fun incompleteSameSlotBaselineIsRejected() {
        assertNull(PaperStrategy.sameSlotAverage(current(), priorWeekdays(current(), 19)))
    }

    @Test fun exactTwentyPriorSlotReadingsAreAveraged() {
        val average = PaperStrategy.sameSlotAverage(current(), priorWeekdays(current(), 20))
        assertEquals(10.5, average!!, 0.0001)
        assertEquals(2.0, PaperStrategy.relativeVolume(21.0, average)!!, 0.0001)
    }

    @Test fun duplicateHistoricalDayInvalidatesBaseline() {
        val prior = priorWeekdays(current(), 20).toMutableList()
        prior += prior.first()
        assertNull(PaperStrategy.sameSlotAverage(current(), prior))
    }

    @Test fun insufficientBarsNeverProducePaperEntry() {
        val now = Instant.parse("2026-10-22T04:15:00Z")
        val bars = (0..20).map { i ->
            val stamp = Instant.parse("2026-10-22T03:00:00Z").plusSeconds(i * 900L)
            Candle(stamp, 100.0, 101.0, 99.0, 100.5, 1000.0)
        }
        val result = PaperStrategy.evaluate(bars, now, 100.0)
        assertEquals("WAIT", result.signal)
        assertEquals("INSUFFICIENT_15M_HISTORY", result.reason)
    }
}
