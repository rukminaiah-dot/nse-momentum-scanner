package com.nsemomentum.paper

import android.content.Context
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.Duration
import java.net.URLEncoder

data class CommodityContract(val commodity:String,val key:String,val symbol:String,val expiry:LocalDate)
data class CommoditySession(val date:LocalDate,val start:Instant,val end:Instant) {
    fun valid()=start.atZone(MarketSession.ZONE).toLocalDate()==date && end>start && Duration.between(start,end).toHours() in 1..24
    fun target(now:Instant):Instant? {
        if(now<start.plusSeconds(300)) return null
        val count=Duration.between(start,minOf(now,end)).seconds/300
        return start.plusSeconds((count-1)*300)
    }
}
object CommodityContracts {
    val names=listOf("GOLD","SILVER","CRUDEOIL","NATURALGAS")
    fun parse(root:JSONObject,name:String,today:LocalDate):List<CommodityContract> {
        require(name in names && root.getString("status")=="success")
        val rows=root.getJSONArray("data")
        return (0 until rows.length()).mapNotNull { i ->
            val row=rows.getJSONObject(i)
            if(row.optString("exchange")!="MCX" || row.optString("segment")!="MCX_FO" || row.optString("instrument_type")!="FUT" || row.optString("underlying_symbol")!=name || row.optBoolean("is_suspended")) return@mapNotNull null
            val key=row.getString("instrument_key");require(key.matches(Regex("MCX_FO\\|[0-9]{1,12}")))
            val expiry=LocalDate.parse(row.getString("expiry"))
            if(expiry<today) null else CommodityContract(name,key,row.getString("trading_symbol"),expiry)
        }
    }
}

data class CommodityReading(val name:String,val contract:CommodityContract?=null,val candle:Candle?=null,
    val technicals:TechnicalContext?=null,val direction:String="WAIT",val checkedAt:Instant?=null,
    val nextClose:Instant?=null,val sessionOpen:Boolean=false,val error:String?=null,
    val previousDirection:String?=null,val changedAt:Instant?=null)
data class CommoditySnapshot(val rows:List<CommodityReading> = CommodityContracts.names.map { CommodityReading(it) })

object CommodityMonitor {
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO)
    private val mutable=MutableStateFlow(CommoditySnapshot())
    val state:StateFlow<CommoditySnapshot> = mutable
    private var job:Job?=null
    private var credential:String?=null
    private val owners=mutableSetOf<String>()
    @Synchronized fun acquire(owner:String,context:Context,token:String) {
        owners+=owner
        if(job?.isActive==true && credential==token) return
        val old=job;old?.cancel();credential=token
        job=scope.launch { old?.join(); run(context.applicationContext,token) }
    }
    @Synchronized fun release(owner:String) { owners-=owner;if(owners.isEmpty()) {job?.cancel();job=null;credential=null} }
    private suspend fun run(context:Context,token:String) {
        val feed=UpstoxCandleFeed()
        val contracts=mutableMapOf<String,CommodityContract>()
        val sessions=mutableMapOf<LocalDate,CommoditySession?>()
        val priorMinutes=mutableMapOf<Pair<String,LocalDate>,List<Candle>>()
        val done=mutableMapOf<String,Instant?>()
        var selectedDate:LocalDate?=null
        suspend fun session(date:LocalDate):CommoditySession? {
            if(!sessions.containsKey(date)) sessions[date]=feed.commoditySession(token,date)
            return sessions[date]
        }
        suspend fun candles(contract:CommodityContract,s:CommoditySession,now:Instant):List<Candle> {
            val key=URLEncoder.encode(contract.key,"UTF-8")
            val today=now.atZone(MarketSession.ZONE).toLocalDate()
            val path=if(s.date==today) "/v3/historical-candle/intraday/$key/minutes/1" else "/v3/historical-candle/$key/minutes/1/${s.date}/${s.date}"
            val raw=feed.indexCandles(token,path)
            require(raw.map { it.timestamp }.distinct().size==raw.size && raw.all {
                PaperStrategy.validCandle(it) && it.timestamp>=s.start && it.timestamp<s.end && Duration.between(s.start,it.timestamp).seconds%60==0L
            }) { "INVALID_COMMODITY_CANDLE" }
            return raw.filter { it.timestamp.plusSeconds(60)<=now }.sortedBy { it.timestamp }
        }
        try { while(true) {
            val now=Instant.now();val date=now.atZone(MarketSession.ZONE).toLocalDate()
            if(selectedDate!=date) { contracts.clear();done.clear();selectedDate=date }
            val previous=mutable.value.rows.associateBy { it.name }
            val readings=CommodityContracts.names.map { name ->
                val old=previous[name] ?: CommodityReading(name)
                try {
                    val contract=contracts[name] ?: feed.commodityContracts(token,name,date).minWithOrNull(compareBy<CommodityContract> { it.expiry }.thenBy { it.key })?.also { contracts[name]=it }
                        ?: error("NO_COMMODITY_CONTRACT")
                    var current=session(date)
                    var cursor=date.minusDays(1)
                    repeat(14) { if(current==null || now<current!!.start.plusSeconds(300)) { current=session(cursor);cursor=cursor.minusDays(1) } }
                    val market=current ?: error("UNVERIFIED_COMMODITY_SESSION")
                    val target=market.target(now) ?: error("NO_COMPLETED_COMMODITY_CANDLE")
                    val open=market.date==date && now>=market.start && now<market.end
                    val next=if(open) target.plusSeconds(600).takeIf { it<=market.end } else null
                    if(done[name]==target && old.contract?.key==contract.key && old.error==null)
                        old.copy(sessionOpen=open,nextClose=next,direction=if(open) old.direction else "WAIT")
                    else {
                        val minutes=candles(contract,market,now)
                        val bars=minutes.filter { it.timestamp>=target && it.timestamp<target.plusSeconds(300) }
                        require(bars.map { it.timestamp }==(0 until 5).map { target.plusSeconds(it*60L) }) { "MISSING_COMMODITY_CANDLE" }
                        val candle=Candle(target,bars.first().open,bars.maxOf { it.high },bars.minOf { it.low },bars.last().close,0.0)
                        val direction=if(open) IndexDirectionStrategy.evaluate(minutes,target) else "WAIT"
                        var prior:CommoditySession?=null;cursor=market.date.minusDays(1)
                        repeat(14) { if(prior==null) {prior=session(cursor);cursor=cursor.minusDays(1)} }
                        val priorBars=prior?.let { s -> priorMinutes[contract.key to s.date] ?: candles(contract,s,now).also { priorMinutes[contract.key to s.date]=it } }.orEmpty()
                        val five=(priorBars+minutes).groupBy { it.timestamp.epochSecond/300 }.toSortedMap().mapNotNull { (_,group) ->
                            val sorted=group.sortedBy { it.timestamp };val start=Instant.ofEpochSecond(sorted.first().timestamp.epochSecond/300*300)
                            if(start>target || sorted.map { it.timestamp }!=(0 until 5).map { start.plusSeconds(it*60L) }) null
                            else Candle(start,sorted.first().open,sorted.maxOf { it.high },sorted.minOf { it.low },sorted.last().close,0.0)
                        }
                        val sameContract=old.contract?.key==contract.key
                        val changed=sameContract && open && direction!="WAIT" && old.direction in setOf("BULLISH","BEARISH","NEUTRAL") && old.direction!=direction
                        done[name]=target
                        CommodityReading(name,contract,candle,PaperStrategy.context(five),direction,Instant.now(),next,open,
                            previousDirection=if(changed) old.direction else if(sameContract) old.previousDirection else null,changedAt=if(changed) target.plusSeconds(300) else if(sameContract) old.changedAt else null)
                    }
                } catch(cancelled:CancellationException) {throw cancelled}
                catch(e:Exception) {
                    DiagnosticLog.record(context,"COMMODITY_REFRESH",DiagnosticLog.errorCode(e))
                    old.copy(error=DiagnosticLog.errorCode(e),sessionOpen=false)
                }
            }
            if(contracts.isNotEmpty()) LiveMarketHub.acquire("commodities",token,contracts.values.map { it.key }.toSet())
            mutable.value=CommoditySnapshot(readings)
            delay(10_000)
        } } finally {LiveMarketHub.release("commodities")}
    }
}
