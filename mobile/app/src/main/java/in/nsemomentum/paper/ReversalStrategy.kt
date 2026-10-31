package com.nsemomentum.paper

import java.time.Duration
import java.time.Instant
import kotlin.math.floor

data class ReversalTrade(val buyAt: Instant, val buy: Double, val sellAt: Instant, val sell: Double, val reason: String,
                         val policy: String = "LEGACY_80", val beforeVolume: Long? = null, val afterVolume: Long? = null) {
    val gross: Double get() = sell - buy
    val percent: Double get() = gross / buy * 100.0
}
data class ReversalState(
    val watchDate: String? = null,
    val previousK: Double? = null,
    val previousAt: Instant? = null,
    val buy: Double? = null,
    val buyAt: Instant? = null,
    val reached80: Boolean = false, // Legacy storage compatibility only; no longer an exit rule.
    val trades: List<ReversalTrade> = emptyList(),
    val action: String = "WAITING_FOR_K_ABOVE_D_BELOW_20",
    val symbol: String = "",
    val peakPrice: Double? = null,
    val confirmationAt: Instant? = null,
    val beforeVolume: Long? = null,
    val afterVolume: Long? = null,
    val observationGap: Boolean = true
)
object ReversalStrategy {
    fun stopPercent(buy: Double, peak: Double): Double {
        val steps=floor((((peak / buy)-1)*100 + 1e-9)/0.25).toLong()
        return if (steps >= 2) (steps-1)*0.25 else -1.0
    }
    fun stopPrice(state: ReversalState): Double? = state.buy?.let { it*(1+stopPercent(it,maxOf(it,state.peakPrice ?: it))/100) }
    fun interrupted(state: ReversalState, reason: String): ReversalState = state.copy(
        confirmationAt=null,beforeVolume=null,afterVolume=null,observationGap=true,action=reason)

    fun tick(state: ReversalState, price: Double, k: Double?, d: Double?, now: Instant,
             before: Long? = null, after: Long? = null, volumeContinuous: Boolean = false): ReversalState {
        if (!price.isFinite() || price <= 0) return interrupted(state,"INVALID_QUOTE")
        val day=now.atZone(MarketSession.ZONE).toLocalDate().toString()
        if (state.buy != null && state.buyAt != null) {
            val active=state.copy(peakPrice=maxOf(state.buy,state.peakPrice ?: state.buy,price),
                confirmationAt=null)
            val stop=stopPrice(active)!!
            if (StockSessionExit.due(state.buyAt,now) || price <= stop + state.buy*1e-12) {
                val reason=if (StockSessionExit.due(state.buyAt,now)) "SESSION_1510" else if (stopPercent(state.buy,active.peakPrice!!) < 0) "STOP_1_PERCENT" else "STEPPED_PROFIT_STOP"
                val trade=ReversalTrade(state.buyAt,state.buy,now,price,reason,if (state.beforeVolume == null) "LEGACY_ENTRY_STEP_EXIT" else "VOLUME_STEP_V2",state.beforeVolume,state.afterVolume)
                return ReversalState(trades=state.trades+trade,symbol=state.symbol,action="SELL_$reason",previousK=k,previousAt=now)
            }
            return active.copy(action=if (stopPercent(state.buy,active.peakPrice!!) < 0) "BUY_ACTIVE_INITIAL_STOP" else "BUY_ACTIVE_PROFIT_PROTECTED")
        }
        if (StockSessionExit.entriesClosed(now)) return interrupted(state,"NO_NEW_BUYS_AFTER_1510")
        if (k == null || d == null || !k.isFinite() || !d.isFinite() || k !in 0.0..100.0 || d !in 0.0..100.0)
            return interrupted(state,"KD_GAP_LAST_VALID_READING_RETAINED")
        val recent=state.previousAt?.let { Duration.between(it,now).toMillis() in 0..5000 } == true
        val watching=state.watchDate == day
        val observed=state.copy(previousK=k,previousAt=now,observationGap=false)
        if (state.confirmationAt != null) {
            if (!recent || state.observationGap || !volumeContinuous)
                return interrupted(observed,"CONFIRMATION_CANCELLED_DATA_GAP")
            if (k <= 20 || k <= d) return observed.copy(confirmationAt=null,beforeVolume=null,afterVolume=null,
                watchDate=if (k < 20 && k > d) day else null,action="CONFIRMATION_CANCELLED_KD_REVERSED")
            val elapsed=Duration.between(state.confirmationAt,now).seconds
            if (elapsed >= 60) {
                if (state.beforeVolume == null || state.beforeVolume <= 0 || after == null)
                    return observed.copy(confirmationAt=null,action="VOLUME_COMPARISON_UNAVAILABLE_NEW_CROSS_REQUIRED")
                if (after > state.beforeVolume) return observed.copy(buy=price,buyAt=now,peakPrice=price,watchDate=null,
                    confirmationAt=null,afterVolume=after,action="BUY_CONFIRMED_60S_VOLUME_INCREASE")
                return observed.copy(confirmationAt=null,afterVolume=after,action="VOLUME_DID_NOT_INCREASE_NEW_CROSS_REQUIRED")
            }
            return observed.copy(afterVolume=after,action="CONFIRMING_60S_VOLUME_AND_KD")
        }
        val crossing=recent && !state.observationGap && state.previousK != null && state.previousK <= 20 && k > 20
        if (watching && crossing && k > d) {
            if (before == null || before <= 0 || !volumeContinuous) return observed.copy(
                beforeVolume=before,afterVolume=null,action="PRE_CROSS_VOLUME_UNAVAILABLE_NEW_CROSS_REQUIRED")
            return observed.copy(confirmationAt=now,beforeVolume=before,afterVolume=0,action="CONFIRMING_60S_VOLUME_AND_KD")
        }
        val watch=when { k < 20 && k > d -> day; k < 20 && k <= d -> null; watching -> day; else -> null }
        val reason=when {
            watching && k > 20 && (!recent || state.observationGap) -> "CROSS_UNOBSERVED_AFTER_DATA_GAP_NEW_CROSS_REQUIRED"
            crossing && k <= d -> "K_NOT_ABOVE_D_AT_CROSS_NEW_CROSS_REQUIRED"
            watch != null && k > 20 -> if (state.action.endsWith("NEW_CROSS_REQUIRED") || state.action.startsWith("CONFIRMATION_CANCELLED")) state.action else "ALREADY_ABOVE_20_WAITING_FOR_NEW_CROSS"
            watch != null -> "SHORTLISTED_BELOW_20_WAITING_FOR_CROSS"
            else -> "WAITING_FOR_K_ABOVE_D_BELOW_20"
        }
        return observed.copy(watchDate=watch,action=reason)
    }
}
