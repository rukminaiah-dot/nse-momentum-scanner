package com.nsemomentum.paper

import java.time.Instant
import java.time.LocalDate

data class CandleVolumeComparison(val candleStart:Instant,val volume:Double,val average:Double?,val ratio:Double?)

/** Input is history already verified by reversalHistory; never builds candles from live quote volume. */
fun completedCandleVolume(verifiedHistory:List<Candle>,now:Instant):CandleVolumeComparison? {
    val date=now.atZone(MarketSession.ZONE).toLocalDate()
    fun shape(day:LocalDate)=MarketSession(day,day.atTime(9,15).atZone(MarketSession.ZONE).toInstant(),day.atTime(15,30).atZone(MarketSession.ZONE).toInstant())
    val today=shape(date)
    val target=today.slots().lastOrNull { it.plusSeconds(900)<=now } ?: return null
    val current=verifiedHistory.singleOrNull { it.timestamp==target }?.takeIf(PaperStrategy::validCandle) ?: return null
    val days=verifiedHistory.map { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() }.filter { it<date }.distinct().sortedDescending().take(20)
    val sessions=days.map(::shape)
    val average=if(PaperStrategy.verifiedSessions(verifiedHistory,sessions)) PaperStrategy.sameSlotAverage(current,verifiedHistory,sessions) else null
    return CandleVolumeComparison(target,current.volume,average,average?.let { PaperStrategy.relativeVolume(current.volume,it) })
}
