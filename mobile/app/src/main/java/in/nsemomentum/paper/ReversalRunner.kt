package com.nsemomentum.paper

import android.content.Context
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.net.URLEncoder
import java.time.Instant
import java.time.LocalDate
import java.util.concurrent.ConcurrentHashMap

suspend fun reversalHistory(feed: CandleFeed, token: String, stock: Stock, now: Instant, cached: List<Candle> = emptyList()): List<Candle> {
    val date = now.atZone(MarketSession.ZONE).toLocalDate()
    val exchange = stock.instrumentKey.substringBefore('_')
    val sessions = mutableListOf<MarketSession>()
    var prior = date.minusDays(1)
    repeat(60) {
        if (sessions.size < 20) { feed.session(token,prior,exchange)?.let { s -> require(s.isRegular()); sessions += s }; prior=prior.minusDays(1) }
    }
    require(sessions.size == 20) { "UNVERIFIED_MARKET_CALENDAR" }
    val encoded = URLEncoder.encode(stock.instrumentKey,"UTF-8").replace("+","%20")
    fun completeHistory(bars: List<Candle>): Boolean = sessions.all { session ->
        val day = bars.filter { it.timestamp.atZone(MarketSession.ZONE).toLocalDate() == session.date }
        day.size == 25 && day.map { it.timestamp }.toSet() == session.slots().toSet() && day.all(PaperStrategy::validCandle)
    }
    val past = if (completeHistory(cached)) cached else {
        val fetched=mutableListOf<Candle>()
        var end=sessions.maxOf { it.date }
        val oldest=sessions.minOf { it.date }
        while (end >= oldest) {
            val start=maxOf(oldest,end.minusDays(27))
            fetched += feed.candles(token,"/v3/historical-candle/$encoded/minutes/15/$end/$start")
            end=start.minusDays(1)
        }
        fetched
    }
    require(completeHistory(past)) { "MISSING_REVERSAL_HISTORY" }
    val today = feed.session(token,date,exchange)
    require(today == null || today.isRegular()) { "UNVERIFIED_MARKET_CALENDAR" }
    val current = if (today != null && now >= today.start) {
        val expected = today.slots().filter { it.plusSeconds(900) <= now }.toSet()
        val saved = cached.filter { it.timestamp in expected }
        val bars = if (saved.size == expected.size && saved.map { it.timestamp }.toSet() == expected && saved.all(PaperStrategy::validCandle)) saved
            else feed.candles(token,"/v3/historical-candle/intraday/$encoded/minutes/15")
        require(bars.map { it.timestamp }.distinct().size == bars.size && bars.all { PaperStrategy.validCandle(it) && it.timestamp in today.slots() }) { "INVALID_INTRADAY_CANDLES" }
        val complete = bars.filter { it.timestamp.plusSeconds(900) <= now }
        require(complete.map { it.timestamp }.toSet() == today.slots().filter { it.plusSeconds(900) <= now }.toSet()) { "MISSING_COMPLETED_15M_CANDLE" }
        complete
    } else emptyList()
    return (past.filter { b -> sessions.any { it.date == b.timestamp.atZone(MarketSession.ZONE).toLocalDate() } } + current).sortedBy { it.timestamp }
}

data class ReversalRow(val stock: Stock, val state: ReversalState, val preview: LiveStochastic?, val status: String)
data class ReversalSnapshot(val rows: List<ReversalRow> = emptyList(), val updatedAt: Instant? = null,
                            val status: String = "Waiting for live connection")

/** One shared automatic runner, attached to the existing screen/service lifecycle. */
object ReversalRunner {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutable = MutableStateFlow(ReversalSnapshot())
    val state: StateFlow<ReversalSnapshot> = mutable
    private val owners = mutableSetOf<String>()
    private var job: Job? = null
    private var config = emptyList<Stock>()
    private var credential: String? = null
    @Synchronized fun acquire(owner: String, context: Context, token: String, stocks: List<Stock>) {
        owners += owner
        val selected = stocks.filter { "_EQ|" in it.instrumentKey }.distinctBy { it.instrumentKey }.sortedBy { it.instrumentKey }
        if (job?.isActive == true && selected == config && token == credential) return
        val previousJob=job
        previousJob?.cancel(); config=selected; credential=token
        job=scope.launch { previousJob?.join(); run(context.applicationContext,token,selected) }
    }
    @Synchronized fun release(owner: String) {
        owners -= owner
        if (owners.isEmpty()) { job?.cancel();job=null;credential=null }
    }
    private suspend fun run(context: Context, token: String, selected: List<Stock>) = coroutineScope {
        val store=ReversalStore(context)
        var states=store.read()
        val activeMissing=states.filter { it.value.buy != null && selected.none { s -> s.instrumentKey == it.key } }.map { (key,value) -> Stock(value.symbol.ifBlank { key },key) }
        val work=selected+activeMissing
        val volumes=work.associate { it.instrumentKey to LiveVolumeWindow() }
        val history=ConcurrentHashMap<String,List<Candle>>()
        val errors=ConcurrentHashMap<String,String>()
        val done=ConcurrentHashMap<String,Long>()
        val underlying=UpstoxCandleFeed()
        val calendarLock=Mutex()
        val calendars=mutableMapOf<Pair<LocalDate,String>,MarketSession?>()
        val feed=object : CandleFeed {
            override suspend fun candles(token:String,path:String)=underlying.candles(token,path)
            override suspend fun session(token:String,date:LocalDate)=session(token,date,"NSE")
            override suspend fun session(token:String,date:LocalDate,exchange:String):MarketSession? = calendarLock.withLock {
                val key=date to exchange
                if (!calendars.containsKey(key)) calendars[key]=underlying.session(token,date,exchange)
                calendars[key]
            }
        }
        val permits=Semaphore(4)
        // Shares the existing socket; also keeps open positions subscribed after selection changes.
        LiveMarketHub.acquire("reversal",token, (work.map { it.instrumentKey } + StockCatalog.indices.map { it.instrumentKey }).toSet())
        val historyJob=launch {
            while (true) {
                val now=Instant.now(); val slot=now.epochSecond/900
                work.map { stock -> async {
                    if (done[stock.instrumentKey] != slot) permits.withPermit {
                        try {
                            val database=CandleDatabase(context)
                            val cached=try { database.bars(stock.instrumentKey) } finally { database.close() }
                            history[stock.instrumentKey]=reversalHistory(feed,token,stock,now,(cached+history[stock.instrumentKey].orEmpty()).distinctBy { it.timestamp })
                            done[stock.instrumentKey]=slot;errors.remove(stock.instrumentKey)
                        } catch (cancelled: CancellationException) { throw cancelled }
                        catch (e: Exception) { errors[stock.instrumentKey]=DiagnosticLog.errorCode(e); DiagnosticLog.event("REVERSAL_HISTORY",DiagnosticLog.errorCode(e),symbol=stock.symbol) }
                    }
                } }.awaitAll()
                delay(10_000)
            }
        }
        try { while (true) {
            val now=Instant.now(); val live=LiveMarketHub.state.value
            var next=states
            val rows=work.map { stock ->
                val quote=live.quotes[stock.instrumentKey]
                val marketOpen=live.markets[stock.instrumentKey.substringBefore('|')] == true
                val local=now.atZone(MarketSession.ZONE).toLocalTime()
                val fresh=quote != null && live.connected && marketOpen &&
                    java.time.Duration.between(quote.tradedAt,now).seconds in 0..30 &&
                    java.time.Duration.between(quote.receivedAt,now).seconds in 0..30 &&
                    local >= java.time.LocalTime.of(9,15) && local < java.time.LocalTime.of(15,30)
                val preview=LiveStochasticPreview.calculate(history[stock.instrumentKey].orEmpty(),quote,now,live.connected,marketOpen)
                val old=states[stock.instrumentKey] ?: ReversalState()
                val volume=volumes.getValue(stock.instrumentKey)
                val volumeFresh=fresh && quote?.volumeToday != null && quote.volumeAt != null &&
                    java.time.Duration.between(quote.volumeAt,now).toMillis() in 0..3000
                if (volumeFresh) volume.add(quote!!.volumeAt!!,quote.volumeToday!!,live.connectionId) else volume.clear()
                val start=old.confirmationAt ?: now
                val before=if (old.confirmationAt == null) volume.amount(now.minusSeconds(60),now) else old.beforeVolume
                val end=if (now >= start.plusSeconds(60)) start.plusSeconds(60) else now
                val after=if (old.confirmationAt != null && end > start) volume.amount(start,end) else null
                val continuous=volumeFresh && if(old.confirmationAt != null) volume.amount(start,end) != null else before != null
                val updated=if (fresh) ReversalStrategy.tick(old,quote!!.price,preview?.context?.stochK,preview?.context?.stochD,now,before,after,continuous)
                    else ReversalStrategy.interrupted(old,if (old.buy != null) "BUY_ACTIVE_WAITING_FRESH_QUOTE" else "QUOTE_GAP_LAST_VALID_K_RETAINED")
                next=next+(stock.instrumentKey to updated.copy(symbol=stock.symbol))
                ReversalRow(stock,updated.copy(symbol=stock.symbol),preview,errors[stock.instrumentKey] ?: if (fresh) updated.action else "Waiting for fresh live quote / market open")
            }
            val changed=next.any { (key,value) -> val old=states[key] ?: ReversalState()
                value.peakPrice != old.peakPrice || value.symbol != old.symbol || value.watchDate != old.watchDate || value.buy != old.buy || value.buyAt != old.buyAt || value.reached80 != old.reached80 || value.trades != old.trades }
            try {
                rows.filter { row -> row.state.action != states[row.stock.instrumentKey]?.action }.forEach { row ->
                    DiagnosticLog.event("REVERSAL_DECISION",row.state.action.take(70),"k=${row.preview?.context?.stochK ?: -1.0} d=${row.preview?.context?.stochD ?: -1.0}",row.stock.symbol)
                }
                if (changed) store.write(next)
                rows.filter { it.state.action.startsWith("BUY_CONFIRMED") || it.state.action.startsWith("SELL_") }.forEach { DiagnosticLog.event("REVERSAL_SIGNAL",it.state.action,symbol=it.stock.symbol) }
                states=next
                val archived=states.filter { entry -> work.none { it.instrumentKey == entry.key } && entry.value.trades.isNotEmpty() }.map { (key,value) -> ReversalRow(Stock(value.symbol.ifBlank { key },key),value,null,"Not selected · saved history only") }
                mutable.value=ReversalSnapshot(rows+archived,now,"Automatic · live 60s volume confirmation · stepped profit protection")
            } catch (_: Exception) {
                mutable.value=ReversalSnapshot(rows.map { row -> row.copy(state=states[row.stock.instrumentKey] ?: ReversalState()) },now,"Could not save reversal history · signals paused until storage recovers")
            }
            delay(1000)
        } } finally { historyJob.cancel();LiveMarketHub.release("reversal") }
    }
}
