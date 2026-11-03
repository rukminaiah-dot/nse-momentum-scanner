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

data class ReversalRow(val stock: Stock, val state: ReversalState, val preview: LiveStochastic?, val status: String,val opening:OpeningState=OpeningState(),val openingSample:OpeningSample?=null,val previousPreview:LiveStochastic?=null,val signalAt:Instant?=null,val volumeSeconds:Long=0)
data class ReversalSnapshot(val rows: List<ReversalRow> = emptyList(), val updatedAt: Instant? = null,
                            val status: String = "Waiting for live connection",val recordStatus:String?=null)

/** One shared automatic runner, attached to the existing screen/service lifecycle. */
object ReversalRunner {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutable = MutableStateFlow(ReversalSnapshot())
    val state: StateFlow<ReversalSnapshot> = mutable
    private val owners = mutableSetOf<String>()
    private var job: Job? = null
    private var config = emptyList<Stock>()
    private var credential: String? = null
    private val verifiedHistory=ConcurrentHashMap<String,List<Candle>>()
    private val edits=kotlinx.coroutines.channels.Channel<PaperRecordEdit>(32)
    fun record(edit:PaperRecordEdit):Boolean=job?.isActive==true && PaperRecordEdits.valid(edit) && edits.trySend(edit).isSuccess
    private val approvals=kotlinx.coroutines.channels.Channel<OpeningApproval>(32)
    fun approveOpening(command:OpeningApproval):Boolean {
        val pending=state.value.rows.firstOrNull { it.stock.instrumentKey==command.key }?.opening ?: return false
        if(job?.isActive!=true || pending.alertAt!=command.alertAt || pending.alert==null ||
            java.time.Duration.between(command.alertAt,Instant.now()).toMillis() !in 0..59999) return false
        return approvals.trySend(command).isSuccess
    }
    @Synchronized fun acquire(owner: String, context: Context, token: String, stocks: List<Stock>) {
        owners += owner
        val selected = stocks.filter { "_EQ|" in it.instrumentKey }.distinctBy { it.instrumentKey }.sortedBy { it.instrumentKey }
        if (job?.isActive == true && selected == config && token == credential) return
        val previousJob=job
        previousJob?.cancel(); config=selected; credential=token
        job=scope.launch {
            previousJob?.join()
            while(isActive) {
                try { run(context.applicationContext,token,selected) }
                catch(cancelled:CancellationException) { throw cancelled }
                catch(error:Exception) {
                    DiagnosticLog.event("REVERSAL_RUNNER","RECOVERING")
                    mutable.value=mutable.value.copy(status="Monitor interrupted · retrying",updatedAt=null)
                    delay(5000)
                }
            }
        }
    }
    @Synchronized fun release(owner: String) {
        owners -= owner
        if (owners.isEmpty()) { job?.cancel();job=null;credential=null }
    }
    private suspend fun run(context: Context, token: String, selected: List<Stock>) = coroutineScope {
        val store=ReversalStore(context)
        var states=store.read()
        val openingStore=OpeningStore(context)
        var openingStates=openingStore.read()
        var recordMessage:String?=null
        var lastHealth=Instant.EPOCH
        DiagnosticLog.event("REVERSAL_RUNNER","STARTED")
        val activeOpening=openingStates.filter { it.value.buy!=null && selected.none { s -> s.instrumentKey==it.key } }.map { (key,_) -> Stock(states[key]?.symbol?.ifBlank { key } ?: key,key) }
        val activeMissing=states.filter { it.value.buy != null && selected.none { s -> s.instrumentKey == it.key } }.map { (key,value) -> Stock(value.symbol.ifBlank { key },key) }
        val work=(selected+activeMissing+activeOpening).distinctBy { it.instrumentKey }
        val previousPreviews=mutableMapOf<String,LiveStochastic>()
        val signalTimes=mutableMapOf<String,Instant>()
        val volumes=work.associate { it.instrumentKey to LiveVolumeWindow() }
        val priceWindows=work.associate { it.instrumentKey to OpeningPriceWindow() }
        val history=ConcurrentHashMap<String,List<Candle>>().apply { work.forEach { s -> verifiedHistory[s.instrumentKey]?.let { put(s.instrumentKey,it) } } }
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
                            verifiedHistory[stock.instrumentKey]=history.getValue(stock.instrumentKey)
                            done[stock.instrumentKey]=slot;errors.remove(stock.instrumentKey)
                            DiagnosticLog.event("REVERSAL_HISTORY","READY","bars=${history[stock.instrumentKey]?.size ?: 0}",stock.symbol)
                        } catch (cancelled: CancellationException) { throw cancelled }
                        catch (e: Exception) { errors[stock.instrumentKey]=DiagnosticLog.errorCode(e); DiagnosticLog.event("REVERSAL_HISTORY",DiagnosticLog.errorCode(e),symbol=stock.symbol) }
                    }
                } }.awaitAll()
                delay(10_000)
            }
        }
        try { while (true) {
            val live=LiveMarketHub.state.value; val now=Instant.now()
            val commands=mutableMapOf<String,OpeningApproval>()
            while(true) { val command=approvals.tryReceive().getOrNull() ?: break;commands.putIfAbsent(command.key,command) }
            val changes=mutableMapOf<String,PaperRecordEdit>()
            while(true) { val c=edits.tryReceive().getOrNull() ?: break;changes.putIfAbsent(c.key,c) }
            var nextOpening=openingStates
            var next=states
            val rows=work.map { stock ->
                val quote=live.quotes[stock.instrumentKey]
                val marketOpen=live.markets[stock.instrumentKey.substringBefore('|')] == true
                val local=now.atZone(MarketSession.ZONE).toLocalTime()
                val fresh=quote != null && live.connected && marketOpen &&
                    java.time.Duration.between(quote.tradedAt,now).toMillis() in -1000..50000 &&
                    java.time.Duration.between(quote.receivedAt,now).toMillis() in -1000..50000 &&
                    local >= java.time.LocalTime.of(9,15) && local < java.time.LocalTime.of(15,30)
                val preview=LiveStochasticPreview.calculate(history[stock.instrumentKey].orEmpty(),quote,now,live.connected,marketOpen)
                val old=states[stock.instrumentKey] ?: ReversalState()
                val volume=volumes.getValue(stock.instrumentKey)
                val volumeFresh=volume.ingest(quote,now,fresh,live.connectionId)
                val priceWindow=priceWindows.getValue(stock.instrumentKey)
                if(fresh) priceWindow.add(quote!!.receivedAt,quote.price,live.connectionId) else priceWindow.clear()
                val earlier=volume.amount(now.minusSeconds(120),now.minusSeconds(60))
                val latest=volume.amount(now.minusSeconds(60),now)
                val currentDate=now.atZone(MarketSession.ZONE).toLocalDate()
                val officialOpen=quote?.sessionOpen?.takeIf { quote.sessionOpenDate==currentDate }
                    ?: history[stock.instrumentKey]?.firstOrNull { it.timestamp==currentDate.atTime(9,15).atZone(MarketSession.ZONE).toInstant() }?.open
                val openingSample=OpeningSample(now,fresh,quote?.price,officialOpen,quote?.previousClose,preview?.context?.stochK,
                    preview?.context?.stochD,priceWindow.previous(now),earlier,latest,volumeFresh && earlier!=null && latest!=null)
                val previousOpening=openingStates[stock.instrumentKey] ?: OpeningState()
                var opening=commands[stock.instrumentKey]?.let { OpeningMomentum.approve(previousOpening,openingSample,it) }
                    ?: OpeningMomentum.tick(previousOpening,openingSample)
                changes[stock.instrumentKey]?.takeIf { it.source==PaperSource.OPENING }?.let { opening=PaperRecordEdits.opening(opening,it,now,fresh) }
                nextOpening=nextOpening+(stock.instrumentKey to opening)
                val start=old.confirmationAt ?: now
                val before=if (old.confirmationAt == null) volume.amount(now.minusSeconds(60),now) else old.beforeVolume
                val end=if (now >= start.plusSeconds(60)) start.plusSeconds(60) else now
                val after=if (old.confirmationAt != null && end > start) volume.amount(start,end) else null
                val continuous=volumeFresh && if(old.confirmationAt != null) volume.amount(start,end) != null else before != null
                var updated=if (fresh) ReversalStrategy.tick(old,quote!!.price,preview?.context?.stochK,preview?.context?.stochD,now,before,after,continuous)
                    else ReversalStrategy.interrupted(old,if (old.buy != null) "BUY_ACTIVE_WAITING_FRESH_QUOTE" else "QUOTE_GAP_LAST_VALID_K_RETAINED")
                changes[stock.instrumentKey]?.takeIf { it.source==PaperSource.REVERSAL }?.let { updated=PaperRecordEdits.reversal(updated,it,now,fresh,preview?.context?.stochK,preview?.context?.stochD) }
                val priorPreview=previousPreviews[stock.instrumentKey]
                val openingWatch=fresh && local>=java.time.LocalTime.of(9,15) && local<java.time.LocalTime.of(9,30) && preview?.context?.let { it.stochK>20 && it.stochK<50 && it.stochK>it.stochD }==true
                val wasOpeningWatch=priorPreview?.context?.let { it.stochK>20 && it.stochK<50 && it.stochK>it.stochD }==true
                val signalChanged=(openingWatch && !wasOpeningWatch) || (updated.watchDate!=null && updated.watchDate!=old.watchDate) || opening.alertAt!=previousOpening.alertAt || updated.confirmationAt!=old.confirmationAt || updated.buyAt!=old.buyAt || updated.trades.size!=old.trades.size || (updated.action.startsWith("SELL_REQUIRED") && updated.action!=old.action)
                if(signalChanged) signalTimes[stock.instrumentKey]=now
                val previousPreview=previousPreviews[stock.instrumentKey]
                if(preview!=null) previousPreviews[stock.instrumentKey]=preview
                next=next+(stock.instrumentKey to updated.copy(symbol=stock.symbol))
                ReversalRow(stock,updated.copy(symbol=stock.symbol),preview,errors[stock.instrumentKey] ?: if (fresh) updated.action else "Waiting for fresh live quote / market open",opening,openingSample,previousPreview,signalTimes[stock.instrumentKey]?.takeIf { it<=now },volume.observedSeconds(now))
            }
            changes.filterKeys { key -> work.none { it.instrumentKey==key } }.forEach { (key,edit) ->
                if(edit.source==PaperSource.OPENING) nextOpening=nextOpening+(key to PaperRecordEdits.opening(openingStates[key] ?: OpeningState(),edit,now,false))
                else next=next+(key to PaperRecordEdits.reversal(states[key] ?: ReversalState(),edit,now,false,null,null))
            }
            if(java.time.Duration.between(lastHealth,now).seconds>=60) {
                DiagnosticLog.event("REVERSAL_HEALTH","CHECKED","fresh=${rows.count { it.openingSample?.fresh==true }} kd=${rows.count { it.preview!=null }} volume=${rows.count { it.openingSample?.continuous==true }} total=${rows.size}")
                lastHealth=now
            }
            val changed=next.any { (key,value) -> val old=states[key] ?: ReversalState()
                value.identifiedAt!=old.identifiedAt || value.quantity!=old.quantity || value.manual!=old.manual || value.recordedAt!=old.recordedAt || value.peakPrice != old.peakPrice || value.symbol != old.symbol || value.watchDate != old.watchDate || value.buy != old.buy || value.buyAt != old.buyAt || value.reached80 != old.reached80 || value.trades != old.trades }
            var reversalSaved=false;var openingSaved=false
            try {
                rows.filter { row -> row.state.action != states[row.stock.instrumentKey]?.action }.forEach { row ->
                    DiagnosticLog.event("REVERSAL_DECISION",row.state.action.take(70),"k=${row.preview?.context?.stochK ?: -1.0} d=${row.preview?.context?.stochD ?: -1.0}",row.stock.symbol)
                }
                if (changed) { store.write(next);reversalSaved=true }
                if(nextOpening.any { (key,s) -> val previous=openingStates[key] ?: OpeningState()
                    s.recordedAt!=previous.recordedAt || s.quantity!=previous.quantity || s.day!=previous.day || s.boughtToday!=previous.boughtToday || s.skipped!=previous.skipped || s.buy!=previous.buy || s.peak!=previous.peak || s.trades!=previous.trades }) { openingStore.write(nextOpening);openingSaved=true }
                changes.forEach { (key,edit) ->
                    val accepted=if(edit.source==PaperSource.OPENING) nextOpening[key]?.recordedAt==now else next[key]?.recordedAt==now
                    val symbol=next[key]?.symbol?.ifBlank { key } ?: key
                    recordMessage=if(accepted) "$symbol · paper record saved" else "$symbol · not saved: signal or record changed"
                    DiagnosticLog.event("PAPER_RECORD",if(accepted) "SAVED" else "REJECTED_STALE_RECORD",symbol=symbol)
                }
                rows.forEach { row ->
                    val previous=openingStates[row.stock.instrumentKey]
                    if(row.opening.alertAt!=null && row.opening.alertAt!=previous?.alertAt)
                        DiagnosticLog.event("OPENING_ALERT",row.opening.alert ?: "WAIT",symbol=row.stock.symbol)
                    OpeningNotifications.update(context,row,live,now)
                    commands[row.stock.instrumentKey]?.let { command ->
                        OpeningNotifications.result(context,row.stock,previous ?: OpeningState(),row.opening,command)
                    }
                }
                openingStates=nextOpening
                rows.filter { it.state.action.startsWith("BUY_CONFIRMED") || it.state.action.startsWith("SELL_") }.forEach { DiagnosticLog.event("REVERSAL_SIGNAL",it.state.action,symbol=it.stock.symbol) }
                states=next
                val archiveKeys=(states.keys+openingStates.keys).filter { key -> work.none { it.instrumentKey==key } &&
                    (states[key]?.trades?.isNotEmpty()==true || openingStates[key]?.trades?.isNotEmpty()==true) }
                val archived=archiveKeys.map { key -> val saved=states[key] ?: ReversalState()
                    ReversalRow(Stock(saved.symbol.ifBlank { key },key),saved,null,"Not selected · saved history only",openingStates[key] ?: OpeningState()) }
                mutable.value=ReversalSnapshot(rows+archived,now,"Live · Opening + Reversal",recordMessage)
            } catch (_: Exception) {
                if(reversalSaved) states=next
                if(openingSaved) openingStates=nextOpening
                mutable.value=ReversalSnapshot(rows.map { row -> row.copy(state=states[row.stock.instrumentKey] ?: ReversalState(),opening=openingStates[row.stock.instrumentKey] ?: OpeningState()) },now,"Could not save records · signals paused until storage recovers","Save failed · check storage and retry")
            }
            delay(1000)
        } } finally { historyJob.cancel();LiveMarketHub.release("reversal") }
    }
}
