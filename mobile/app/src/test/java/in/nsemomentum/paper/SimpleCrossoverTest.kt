package com.nsemomentum.paper

import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test

class SimpleCrossoverTest {
    private val prices = listOf(100.565,99.1921,99.6522,100.3123,99.5102,100.1067,100.2875,99.7113,99.4546,100.3863,100.8959,99.9418,100.1598,101.3774,100.0847,100.1415,101.9225,99.5914,101.0179,99.3678,100.2418,101.5322,101.3929,100.1493,100.4478,100.7981,100.0251,101.1413,102.1765,100.0569,99.7111,101.1029,100.8885,102.0726,100.9238,101.0196,100.9655,100.5156,101.5438,100.3756,101.8999,101.235,101.5622,100.9583,100.7679,102.4302,101.6611,102.1342,101.5523,103.037,101.7145,100.9121,102.0211,101.8452,100.2273,101.5805,102.2681,102.1907,101.5363,101.0424,102.0948,101.1425,102.6548,101.7062,101.3651,101.6094,101.4935,101.6736,101.5982,101.8426,102.2434,102.4881,101.4939,101.6191,101.9625,102.2882)
    private val days = listOf("2026-10-22","2026-10-23","2026-10-26","2026-10-27").map(LocalDate::parse)
    private fun candles(volume: Double) = prices.mapIndexed { index, close ->
        val time = days[index / 25].atTime(9,15).atZone(MarketSession.ZONE).toInstant().plusSeconds(index % 25 * 900L)
        Candle(time, close, close + 1, close - 1, close, volume)
    }
    @Test fun firstTodaysCandleCanBuyAboveTwentyWithoutBreakoutOrStrongBody() {
        val bars = candles(200.0)
        val now = bars.last().timestamp.plusSeconds(901)
        val result = PaperStrategy.evaluate(bars, now, 100.0)
        assertEquals("PAPER_BUY", result.signal)
        assertTrue(result.stochK!! > 20 && result.stochK!! < 80)
        assertEquals(48.571, result.stochK!!, .001)
    }
    @Test fun qualifiedStockIsStillAnalyzedWhenLatestVolumeFalls() {
        val bars = candles(50.0); val now = bars.last().timestamp.plusSeconds(901)
        assertEquals("NOT_SHORTLISTED_TODAY", PaperStrategy.evaluate(bars, now, 100.0).reason)
        assertEquals("PAPER_BUY", PaperStrategy.evaluate(bars, now, 100.0, qualifiedToday = true).signal)
    }
    @Test fun sellRequiresExistingBuyAndDoesNotRequireOverboughtOrDownwardEmaTrend() {
        assertEquals("PAPER_SELL", PaperStrategy.crossoverSignal(110.0,100.0,70.0,65.0,60.0,65.0,true).signal)
        assertEquals("WAIT", PaperStrategy.crossoverSignal(110.0,100.0,70.0,65.0,60.0,65.0,false).signal)
        assertEquals("PAPER_HOLD", PaperStrategy.crossoverSignal(110.0,100.0,30.0,35.0,40.0,35.0,true).signal)
        assertEquals("WAIT", PaperStrategy.crossoverSignal(90.0,100.0,30.0,35.0,40.0,35.0,false).signal)
    }
    @Test fun incompleteOrStaleCandlesStillCannotBuy() {
        val bars = candles(200.0)
        assertEquals("WAIT", PaperStrategy.evaluate(bars,bars.last().timestamp.plusSeconds(899),100.0).signal)
        assertEquals("WAIT", PaperStrategy.evaluate(bars,bars.last().timestamp.plusSeconds(1981),100.0).signal)
    }
    @Test fun gapDescribesDirectionAndStrengthWithoutFilteringSignals() {
        assertEquals("Upward momentum strengthening", TechnicalContext(110.0,100.0,60.0,50.0,5.0).momentum)
        assertEquals("Upward momentum weakening", TechnicalContext(110.0,100.0,60.0,50.0,15.0).momentum)
        assertEquals("Downward momentum strengthening", TechnicalContext(110.0,100.0,40.0,50.0,-5.0).momentum)
        assertEquals("New upward crossover", TechnicalContext(110.0,100.0,51.0,50.0,-1.0).momentum)
        assertEquals("PAPER_BUY", PaperStrategy.crossoverSignal(110.0,100.0,49.0,50.0,50.01,50.0,false).signal)
    }
}
