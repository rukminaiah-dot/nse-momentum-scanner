package in.nsemomentum.paper

import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PaperStrategyTest {
    @Test fun incompleteSameSlotBaselineIsRejected() {
        val current = Candle(Instant.parse("2026-10-22T03:45:00Z"), 10.0, 11.0, 9.0, 10.5, 100.0)
        val prior = (1..19).map {
            current.copy(timestamp = current.timestamp.minusSeconds(it * 86400L), volume = 100.0)
        }
        assertNull(PaperStrategy.sameSlotAverage(current, prior))
    }

    @Test fun exactTwentyPriorSlotReadingsAreAveraged() {
        val current = Candle(Instant.parse("2026-10-22T03:45:00Z"), 10.0, 11.0, 9.0, 10.5, 100.0)
        val prior = (1..20).map {
            current.copy(timestamp = current.timestamp.minusSeconds(it * 86400L), volume = it.toDouble())
        }
        assertEquals(10.5, PaperStrategy.sameSlotAverage(current, prior)!!, 0.0001)
        assertEquals(2.0, PaperStrategy.relativeVolume(21.0, 10.5)!!, 0.0001)
    }

    @Test fun duplicateHistoricalDayInvalidatesBaseline() {
        val current = Candle(Instant.parse("2026-10-22T03:45:00Z"), 10.0, 11.0, 9.0, 10.5, 100.0)
        val prior = (1..20).map {
            current.copy(timestamp = current.timestamp.minusSeconds(it * 86400L), volume = 100.0)
        }.toMutableList()
        prior += prior.first()
        assertNull(PaperStrategy.sameSlotAverage(current, prior))
    }

    @Test fun insufficientBarsNeverProducePaperEntry() {
        val now = Instant.parse("2026-10-22T04:15:00Z")
        val bars = (0..20).map { i ->
            val stamp = Instant.parse("2026-10-22T03:00:00Z").plusSeconds(i * 900L)
            Candle(stamp, 100.0, 101.0, 99.0, 100.5, 1000.0)
        }
        assertEquals("WAIT", PaperStrategy.evaluate(bars, now, 100.0).signal)
        assertEquals("INSUFFICIENT_15M_HISTORY", PaperStrategy.evaluate(bars, now, 100.0).reason)
    }
}
