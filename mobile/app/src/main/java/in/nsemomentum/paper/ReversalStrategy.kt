package com.nsemomentum.paper

import java.time.Duration
import java.time.Instant

/** Separate live strategy; never reads volume qualification or writes the existing signal ledger. */
data class ReversalTrade(val buyAt: Instant, val buy: Double, val sellAt: Instant, val sell: Double, val reason: String) {
    val gross: Double get() = sell - buy
    val percent: Double get() = gross / buy * 100.0
}
data class ReversalState(
    val watchDate: String? = null,
    val previousK: Double? = null,
    val previousAt: Instant? = null,
    val buy: Double? = null,
    val buyAt: Instant? = null,
    val reached80: Boolean = false,
    val trades: List<ReversalTrade> = emptyList(),
    val action: String = "WAITING_FOR_K_ABOVE_D_BELOW_20",
    val symbol: String = ""
)
object ReversalStrategy {
    fun tick(state: ReversalState, price: Double, k: Double?, d: Double?, now: Instant): ReversalState {
        if (!price.isFinite() || price <= 0) return state
        val day = now.atZone(MarketSession.ZONE).toLocalDate().toString()
        fun exit(reason: String): ReversalState {
            val trade = ReversalTrade(state.buyAt!!,state.buy!!,now,price,reason)
            return ReversalState(trades=state.trades + trade, action="SELL_$reason",previousK=k,previousAt=now,symbol=state.symbol)
        }
        // Stop price remains actionable even if forming-candle history is unavailable.
        if (state.buy != null && state.buyAt != null && price <= state.buy * 0.99) return exit("STOP_1_PERCENT")
        if (k == null || d == null || !k.isFinite() || !d.isFinite() || k !in 0.0..100.0 || d !in 0.0..100.0)
            return state.copy(previousK=null,previousAt=null,action=if (state.buy != null) "BUY_ACTIVE_KD_UNAVAILABLE" else "KD_UNAVAILABLE")
        if (state.buy != null) {
            if (state.reached80 && k < 80.0) return exit("K_BACK_BELOW_80")
            return state.copy(reached80=state.reached80 || k >= 80.0,previousK=k,previousAt=now,
                action=if (state.reached80 || k >= 80.0) "BUY_ACTIVE_80_REACHED" else "BUY_ACTIVE_WAITING_FOR_80")
        }
        val recentlyObserved = state.previousAt?.let { Duration.between(it,now).seconds in 0..30 } == true
        val watching = state.watchDate == day
        if (watching && recentlyObserved && state.previousK != null && state.previousK <= 20.0 && k > 20.0 && k > d)
            return state.copy(buy=price,buyAt=now,reached80=false,watchDate=null,previousK=k,previousAt=now,action="BUY_LIVE_CROSS_20")
        val watch = when {
            k <= 20.0 && k > d -> day
            k <= 20.0 && k <= d -> null
            watching -> day
            else -> null
        }
        return state.copy(watchDate=watch,previousK=k,previousAt=now,
            action=if (watch != null) "SHORTLISTED_WAITING_FOR_CROSS_20" else "WAITING_FOR_K_ABOVE_D_BELOW_20")
    }
}
