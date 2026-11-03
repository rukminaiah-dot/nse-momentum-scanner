package com.nsemomentum.paper

import java.time.Duration
import java.time.Instant
import java.time.LocalTime

/** Separate, approval-only paper experiment. No broker order endpoint is called. */
data class OpeningTrade(val buyAt:Instant,val buy:Double,val sellAt:Instant,val sell:Double,val quantity:Int,val reason:String) {
    val gross:Double get()=(sell-buy)*quantity
    val percent:Double get()=(sell/buy-1)*100
}
data class OpeningState(
    val day:String="",val previousK:Double?=null,val previousD:Double?=null,val previousAt:Instant?=null,
    val boughtToday:Boolean=false,val skipped:Boolean=false,val buy:Double?=null,val buyAt:Instant?=null,
    val quantity:Int=0,val peak:Double?=null,val alert:String?=null,val alertAt:Instant?=null,
    val waitUntil:Instant?=null,val status:String="Waiting for opening data",val trades:List<OpeningTrade> = emptyList()
)
data class OpeningSample(val at:Instant,val fresh:Boolean,val price:Double?,val open:Double?,val previousClose:Double?,
    val k:Double?,val d:Double?,val price60:Double?,val beforeVolume:Long?,val latestVolume:Long?,val continuous:Boolean)
enum class OpeningChoice { BUY, SELL, WAIT, SKIP }
data class OpeningApproval(val key:String,val alertAt:Instant,val choice:OpeningChoice,val quantity:Int=1)
object OpeningMomentum {
    fun tick(saved:OpeningState,s:OpeningSample):OpeningState {
        val date=s.at.atZone(MarketSession.ZONE).toLocalDate().toString()
        var old=if(saved.day==date) saved else saved.copy(day=date,previousK=null,previousD=null,previousAt=null,
            boughtToday=false,skipped=false,alert=null,alertAt=null,waitUntil=null)
        val price=s.price
        if(!s.fresh || price==null || !price.isFinite() || price<=0) return old.copy(previousAt=null,alert=null,alertAt=null,status="Waiting for fresh quote")
        val kd=s.k!=null && s.d!=null && s.k.isFinite() && s.d.isFinite() && s.k in 0.0..100.0 && s.d in 0.0..100.0
        val recent=old.previousAt?.let { Duration.between(it,s.at).toMillis() in 1..5000 }==true
        val rising=kd && recent && old.previousK!=null && s.k!!>old.previousK
        val upward=rising || (old.alert=="OPENING_BUY" && kd && recent && old.previousK!=null && s.k!!>=old.previousK)
        val bearish=kd && recent && old.previousK!=null && old.previousD!=null &&
            s.k!!<s.d!! && s.k<old.previousK && (old.previousK>=old.previousD || old.alert=="KD_BEARISH")
        old=old.copy(previousK=if(kd) s.k else old.previousK,previousD=if(kd) s.d else old.previousD,previousAt=if(kd) s.at else null)
        val openBuy=old.buy
        val reason=if(openBuy!=null && old.buyAt!=null) {
            old=old.copy(peak=maxOf(openBuy,old.peak ?: openBuy,price))
            val stop=openBuy*(1+ReversalStrategy.stopPercent(openBuy,old.peak!!)/100)
            when {
                StockSessionExit.due(old.buyAt!!,s.at) -> "SESSION_1510"
                price<=stop -> "PRICE_STOP"
                s.continuous && (s.beforeVolume ?: 0)>0 && s.latestVolume!=null && s.latestVolume.toDouble()<=s.beforeVolume!!*.70 -> "VOLUME_DROP_30_PERCENT"
                bearish -> "KD_BEARISH"
                else -> null
            }
        } else {
            val time=s.at.atZone(MarketSession.ZONE).toLocalTime()
            val window=time>=LocalTime.of(9,17) && time<LocalTime.of(9,30)
            val positive=s.open!=null && s.previousClose!=null && s.open>0 && s.previousClose>0 && s.open>s.previousClose && price>s.open
            val volume=s.continuous && (s.beforeVolume ?: 0)>0 && s.latestVolume!=null && s.latestVolume>s.beforeVolume!!
            if(!old.boughtToday && !old.skipped && window && kd && s.k!!>20 && s.k<50 && s.k>s.d!! && upward && positive &&
                s.price60!=null && price>s.price60 && volume) "OPENING_BUY" else null
        }
        if(reason==null) return old.copy(alert=null,alertAt=null,status=if(openBuy!=null) "Paper position open" else "Watching opening 20<K<50, K>D, rising price and 60s volume")
        if(old.waitUntil?.let { s.at<it }==true) return old.copy(alert=null,alertAt=null,status="Waiting · paper position unchanged")
        if(old.alertAt?.let { Duration.between(it,s.at).seconds>=30 }==true) return old.copy(alert=null,alertAt=null,waitUntil=s.at.plusSeconds(30),status="Approval expired · rechecking")
        return old.copy(alert=reason,alertAt=if(old.alert==reason) old.alertAt ?: s.at else s.at,status="Approval required · PAPER ONLY")
    }
    /** Must be called with a freshly re-evaluated sample, never the displayed price. */
    fun approve(state:OpeningState,s:OpeningSample,command:OpeningApproval):OpeningState {
        val checked=tick(state,s)
        if(state.alertAt!=command.alertAt || checked.alertAt!=command.alertAt || checked.alert==null ||
            Duration.between(command.alertAt,s.at).toMillis() !in 0..29999) return checked
        return when(command.choice) {
            OpeningChoice.WAIT -> checked.copy(alert=null,alertAt=null,waitUntil=s.at.plusSeconds(30),status="Wait selected · no paper order")
            OpeningChoice.SKIP -> if(checked.buy==null) checked.copy(skipped=true,alert=null,alertAt=null,status="Opening BUY skipped today") else checked
            OpeningChoice.BUY -> if(checked.alert=="OPENING_BUY" && checked.buy==null && command.quantity in 1..1000000)
                checked.copy(buy=s.price,buyAt=s.at,quantity=command.quantity,peak=s.price,boughtToday=true,alert=null,alertAt=null,status="Paper BUY approved") else checked
            OpeningChoice.SELL -> if(checked.buy!=null && checked.buyAt!=null && checked.alert!="OPENING_BUY") {
                val trade=OpeningTrade(checked.buyAt,checked.buy,s.at,s.price!!,checked.quantity,checked.alert)
                checked.copy(buy=null,buyAt=null,quantity=0,peak=null,alert=null,alertAt=null,trades=checked.trades+trade,status="Paper SELL approved")
            } else checked
        }
    }
}
/** Same-session price comparison; resets with feed connection and gaps. */
class OpeningPriceWindow {
    private val points=java.util.ArrayDeque<Pair<Instant,Double>>()
    private var connection:Long?=null
    fun clear() { points.clear();connection=null }
    fun add(at:Instant,price:Double,epoch:Long) {
        if(!price.isFinite() || price<=0) return
        if(connection!=epoch || points.lastOrNull()?.let { at.atZone(MarketSession.ZONE).toLocalDate()!=it.first.atZone(MarketSession.ZONE).toLocalDate() || Duration.between(it.first,at).seconds>5 }==true) clear()
        connection=epoch
        if(points.lastOrNull()?.let { at<=it.first }==true) return
        points.addLast(at to price)
        while(points.isNotEmpty() && points.first.first<at.minusSeconds(125)) points.removeFirst()
    }
    fun previous(now:Instant):Double?=points.lastOrNull { it.first<=now.minusSeconds(60) }?.takeIf { Duration.between(it.first,now.minusSeconds(60)).toMillis() in 0..2000 }?.second
}
