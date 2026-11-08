package com.nsemomentum.paper

import java.time.Duration
import java.time.Instant
import java.time.LocalTime

/** Automatic Opening paper entries and exits. */
data class OpeningTrade(val buyAt:Instant,val buy:Double,val sellAt:Instant,val sell:Double,val quantity:Int,val reason:String,val automatic:Boolean=false) {
    val gross:Double get()=(sell-buy)*quantity
    val percent:Double get()=(sell/buy-1)*100
}
data class OpeningState(
    val day:String="",val previousK:Double?=null,val previousD:Double?=null,val previousAt:Instant?=null,
    val boughtToday:Boolean=false,val skipped:Boolean=false,val buy:Double?=null,val buyAt:Instant?=null,
    val quantity:Int=0,val peak:Double?=null,val automatic:Boolean=false,val status:String="Waiting for opening data",val trades:List<OpeningTrade> = emptyList(),val recordedAt:Instant?=null,val identifiedAt:Instant?=null
)
data class OpeningSample(val at:Instant,val fresh:Boolean,val price:Double?,val open:Double?,val previousClose:Double?,
    val k:Double?,val d:Double?,val price60:Double?,val beforeVolume:Long?,val latestVolume:Long?,val continuous:Boolean,val volumeRatio:Double?=null)
object OpeningMomentum {
    fun tick(saved:OpeningState,s:OpeningSample,quantity:Int=1):OpeningState {
        val date=s.at.atZone(MarketSession.ZONE).toLocalDate().toString()
        var old=if(saved.day==date) saved else saved.copy(day=date,previousK=null,previousD=null,previousAt=null,
            boughtToday=false,skipped=false,identifiedAt=null)
        val price=s.price
        if(!s.fresh || price==null || !price.isFinite() || price<=0) return old.copy(previousAt=null,status="Waiting for fresh quote")
        val kd=s.k!=null && s.d!=null && s.k.isFinite() && s.d.isFinite() && s.k in 0.0..100.0 && s.d in 0.0..100.0
        val recent=old.previousAt?.let { Duration.between(it,s.at).toMillis() in 1..5000 }==true
        val rising=kd && recent && old.previousK!=null && s.k!!>old.previousK
        val time=s.at.atZone(MarketSession.ZONE).toLocalTime()
        if(kd && time>=LocalTime.of(9,15) && time<LocalTime.of(9,30) && s.k!!>20 && s.k<50 && s.k>s.d!! && old.identifiedAt==null) old=old.copy(identifiedAt=s.at)
        old=old.copy(previousK=if(kd) s.k else old.previousK,previousD=if(kd) s.d else old.previousD,previousAt=if(kd) s.at else null)
        val openBuy=old.buy
        val boughtAt=old.buyAt
        if (openBuy != null && boughtAt != null) {
            val peak = maxOf(openBuy, old.peak ?: openBuy, price)
            val profitReview = StockSessionExit.reachedProfitReview(openBuy, peak)
            val reason = StockSessionExit.exitReason(boughtAt, s.at, openBuy, price, profitReview, s.volumeRatio, kd && s.k!! < s.d!!)
            if (reason != null) {
                val trade = OpeningTrade(boughtAt, openBuy, s.at, price, old.quantity, reason, old.automatic)
                return old.copy(buy=null,buyAt=null,quantity=0,peak=null,automatic=false,
                    trades=old.trades+trade,status="Paper SELL · ${reason.replace('_', ' ')}")
            }
            return old.copy(peak=peak,
                status=if (profitReview) "Paper position open · monitoring 15m volume" else "Paper position open")
        }
        val window = time >= LocalTime.of(9,17) && time < LocalTime.of(9,30)
        val positiveOpen = s.open != null && s.previousClose != null && s.open > 0 && s.previousClose > 0 && s.open > s.previousClose
        if (!old.boughtToday && !old.skipped && window && rising && s.k!! > 20 && s.k < 50 && s.k > s.d!! && positiveOpen) {
            return old.copy(buy=price,buyAt=s.at,quantity=quantity.takeIf { it in 1..1000000 } ?: 1,
                peak=price,boughtToday=true,automatic=true,status="Automatic paper BUY")
        }
        return old.copy(status="Watching opening 20<K<50, K>D, K rising and positive open")
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

