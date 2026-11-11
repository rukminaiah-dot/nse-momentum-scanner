package com.nsemomentum.paper

import kotlinx.coroutines.CancellationException

/** Recover whole, verified days only. Never synthesize candles or hide invalid/duplicate payloads. */
suspend fun recoverSessionHistory(feed:CandleFeed,token:String,encodedKey:String,sessions:List<MarketSession>,fetched:List<Candle>,cached:List<Candle>,
    symbol:String?=null, log:(String,String,String,String?)->Unit={ e,r,n,s -> DiagnosticLog.event(e,r,n,s) }):List<Candle> {
    if (!fetched.all(PaperStrategy::validCandle) || fetched.map { it.timestamp }.distinct().size!=fetched.size) {
        sessions.forEach { session -> HistoryDiagnostics.day("REJECTED",session,fetched.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate()==session.date },symbol,log) }
        log("HISTORY_RECOVERY","INVALID_HISTORY_CANDLES","received=${fetched.size}",symbol)
        throw IllegalArgumentException("INVALID_HISTORY_CANDLES")
    }
    fun day(bars:List<Candle>,session:MarketSession)=bars.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate()==session.date }
    fun complete(bars:List<Candle>,session:MarketSession)=session.hasVerifiedSlots() && bars.size==session.slots().size && bars.all(PaperStrategy::validCandle) && bars.map { it.timestamp }.toSet()==session.slots().toSet()
    var cacheDays=0
    val recovered=sessions.associateWith { session ->
        val raw=day(fetched,session);val saved=day(cached,session)
        if(!session.needsMinuteHistory() && complete(raw,session)) raw else {
            HistoryDiagnostics.day("FETCHED",session,raw,symbol,log)
            HistoryDiagnostics.day("CACHE",session,saved,symbol,log)
            if(complete(saved,session)) { cacheDays++;saved } else if (session.needsMinuteHistory()) emptyList() else raw
        }
    }.toMutableMap()
    val missing=sessions.filter { !complete(recovered.getValue(it),it) }
    // Bounded repair prevents a burst of per-day requests for a wholly unavailable baseline.
    if(missing.size<=2) for(session in missing) {
        log("HISTORY_RETRY","STARTED","date=${session.date}",symbol)
        val retry=try {
            val interval = if (session.needsMinuteHistory()) 1 else 15
            val bars = feed.candles(token,"/v3/historical-candle/$encodedKey/minutes/$interval/${session.date}/${session.date}")
            if (interval == 1) aggregateFullSessionSlots(session, bars) else bars
        }
        catch(cancelled:CancellationException) { throw cancelled }
        catch(error:Exception) {
            log("HISTORY_RETRY",DiagnosticLog.errorCode(error),"date=${session.date}",symbol)
            throw error
        }
        HistoryDiagnostics.day("RETRY",session,retry,symbol,log)
        log("HISTORY_RETRY",if(complete(retry,session)) "COMPLETE" else "INCOMPLETE","date=${session.date}",symbol)
        if(complete(retry,session)) recovered[session]=retry
    } else log("HISTORY_RETRY","SKIPPED_DAY_LIMIT","missing=${missing.size} limit=2",symbol)
    val remaining=sessions.filter { !complete(recovered.getValue(it),it) }
    remaining.forEach { HistoryDiagnostics.day("BLOCKED",it,recovered.getValue(it),symbol,log) }
    log("HISTORY_RECOVERY",if(remaining.isEmpty()) "COMPLETE" else "INCOMPLETE","sessions=${sessions.size} cache=$cacheDays missing=${remaining.size}",symbol)
    return sessions.flatMap { recovered.getValue(it) }.sortedBy { it.timestamp }
}



internal fun aggregateFullSessionSlots(session: MarketSession, minutes: List<Candle>): List<Candle> {
    val byTime = minutes.associateBy { it.timestamp }
    if (byTime.size != minutes.size || minutes.any {
        !PaperStrategy.validCandle(it) || it.timestamp < session.start || it.timestamp >= session.end ||
            it.timestamp.nano != 0 || it.timestamp.epochSecond % 60 != 0L
    }) return emptyList()
    return session.slots().mapNotNull { start ->
        val bars = (0 until 15).mapNotNull { byTime[start.plusSeconds(it * 60L)] }
        if (bars.size != 15) null else Candle(start, bars.first().open, bars.maxOf { it.high },
            bars.minOf { it.low }, bars.last().close, bars.sumOf { it.volume })
    }
}
