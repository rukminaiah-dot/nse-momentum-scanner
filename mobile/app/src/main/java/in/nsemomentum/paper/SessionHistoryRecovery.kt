package com.nsemomentum.paper

/** Recover whole, verified days only. Never synthesize candles or hide invalid/duplicate payloads. */
suspend fun recoverSessionHistory(feed:CandleFeed,token:String,encodedKey:String,sessions:List<MarketSession>,fetched:List<Candle>,cached:List<Candle>):List<Candle> {
    require(fetched.all(PaperStrategy::validCandle) && fetched.map { it.timestamp }.distinct().size==fetched.size) { "INVALID_HISTORY_CANDLES" }
    fun day(bars:List<Candle>,session:MarketSession)=bars.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate()==session.date }
    fun complete(bars:List<Candle>,session:MarketSession)=session.isRegular() && bars.size==25 && bars.all(PaperStrategy::validCandle) && bars.map { it.timestamp }.toSet()==session.slots().toSet()
    val recovered=sessions.associateWith { session ->
        val raw=day(fetched,session);val saved=day(cached,session)
        if(complete(raw,session)) raw else if(complete(saved,session)) saved else raw
    }.toMutableMap()
    val missing=sessions.filter { !complete(recovered.getValue(it),it) }
    // Bounded repair prevents a burst of per-day requests for a wholly unavailable baseline.
    if(missing.size<=2) for(session in missing) {
        val retry=feed.candles(token,"/v3/historical-candle/$encodedKey/minutes/15/${session.date}/${session.date}")
        if(complete(retry,session)) recovered[session]=retry
    }
    DiagnosticLog.event("HISTORY_RECOVERY",if(recovered.all { (session,bars)->complete(bars,session) }) "COMPLETE" else "INCOMPLETE","missing=${recovered.count { (session,bars)->!complete(bars,session) }} date=${sessions.firstOrNull { !complete(recovered.getValue(it),it) }?.date ?: "none"}")
    return sessions.flatMap { recovered.getValue(it) }.sortedBy { it.timestamp }
}
