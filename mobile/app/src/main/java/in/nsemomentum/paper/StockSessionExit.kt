package com.nsemomentum.paper

import android.content.Context
import kotlinx.coroutines.*
import java.time.Instant
import java.time.LocalTime
import org.json.JSONArray

object StockSessionExit {
    val cutoff: LocalTime = LocalTime.of(15,10)
    fun entriesClosed(now: Instant): Boolean = now.atZone(MarketSession.ZONE).toLocalTime() >= cutoff
    fun due(boughtAt: Instant, now: Instant): Boolean = now > boughtAt &&
        (boughtAt.atZone(MarketSession.ZONE).toLocalDate() < now.atZone(MarketSession.ZONE).toLocalDate() || entriesClosed(now))
    fun fresh(quote: LiveQuote, state: LivePriceState, now: Instant): Boolean = quote.price.isFinite() && quote.price>0 && state.connected &&
        state.markets[quote.instrumentKey.substringBefore('|')] == true &&
        quote.tradedAt.atZone(MarketSession.ZONE).toLocalDate() == now.atZone(MarketSession.ZONE).toLocalDate() &&
        java.time.Duration.between(quote.tradedAt,now).seconds in 0..30 &&
        java.time.Duration.between(quote.receivedAt,now).seconds in 0..30
}

/** Existing paper ledger only. An unavailable 15:10 quote leaves a pending exit, never a fabricated fill. */
object StockSessionCloser {
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO)
    private val owners=mutableSetOf<String>()
    private var job:Job?=null
    private var credential:String?=null
    @Synchronized fun acquire(owner:String,context:Context,token:String) {
        owners+=owner
        if(job?.isActive == true && credential == token) return
        val old=job;old?.cancel();credential=token
        job=scope.launch {
            old?.join()
            val db=CandleDatabase(context.applicationContext)
            try {
                val rows=JSONArray(context.assets.open("nse200.json").bufferedReader().use { it.readText() })
                val base=(0 until rows.length()).map { i -> val row=rows.getJSONObject(i);Stock(row.getString("symbol"),row.getString("instrumentKey")) }
                val prefs=context.getSharedPreferences("paper_preferences",0)
                while(true) {
                    val catalog=base+StockCatalog.decodeCustom(prefs.getString("custom_stocks",null),base)
                    val open=db.paperTradeHistory().filter { it.sell == null }
                    val instruments=catalog.filter { stock -> open.any { it.symbol == stock.symbol } }
                    if(instruments.isNotEmpty()) LiveMarketHub.acquire("stock-close",token,instruments.map { it.instrumentKey }.toSet())
                    else LiveMarketHub.release("stock-close")
                    val now=Instant.now();val live=LiveMarketHub.state.value
                    open.filter { StockSessionExit.due(it.boughtAt,now) }.forEach { trade ->
                        val stock=instruments.singleOrNull { it.symbol == trade.symbol }
                        val quote=stock?.let { live.quotes[it.instrumentKey] }
                        if(quote != null && StockSessionExit.fresh(quote,live,now)) db.closeTimedPaperBuy(trade.symbol,quote.price,now)
                    }
                    delay(1000)
                }
            } finally { db.close();LiveMarketHub.release("stock-close") }
        }
    }
    @Synchronized fun release(owner:String) { owners-=owner;if(owners.isEmpty()) { job?.cancel();job=null;credential=null } }
}
