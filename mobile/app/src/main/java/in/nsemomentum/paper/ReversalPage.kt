package com.nsemomentum.paper

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
fun ReversalPage(snapshot: ReversalSnapshot, prices: LivePriceState, modifier: Modifier = Modifier) {
    var onlyShortlisted by remember { mutableStateOf(true) }
    val allTrades = snapshot.rows.flatMap { row -> row.state.trades.map { t -> PaperTrade(row.stock.symbol,t.buyAt,t.buy,t.sellAt,t.sell) } }
    val visible = snapshot.rows.filter { !onlyShortlisted || it.state.watchDate == java.time.LocalDate.now(MarketSession.ZONE).toString() || it.state.buy != null || it.state.trades.lastOrNull()?.sellAt?.atZone(MarketSession.ZONE)?.toLocalDate() == java.time.LocalDate.now(MarketSession.ZONE) }
    LazyColumn(modifier.fillMaxSize(),contentPadding=PaddingValues(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        item {
            Text("LIVE K/D REVERSAL · PAPER ONLY",style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold)
            Text("Same selected stocks and live connection · no indices · 60s volume confirmation for BUY")
            Text("Shortlist: K>D with K<20. A live cross above 20 starts 60s confirmation. K must stay above 20 and D; post-cross 60s volume must exceed pre-cross 60s volume. No minimum K−D gap.")
            Text("All stock paper trades close at 15:10 IST using a fresh price. No new stock BUYs after 15:10. App must be open or the existing full-day service running.",style=MaterialTheme.typography.bodySmall)
            Text("Exit: initial 1% stop. At +0.50% peak gain, protect +0.25%; at +0.75%, protect +0.50%; continue in 0.25-point steps. No 80-based exit. Quotes are paper marks, not execution fills.")
            Text("${snapshot.rows.size} stocks with current / saved state · ${snapshot.rows.count { it.state.watchDate == java.time.LocalDate.now(MarketSession.ZONE).toString() }} shortlisted · ${snapshot.rows.count { it.state.buy != null }} active BUY")
            Text("${snapshot.status} · ${snapshot.updatedAt?.let(::clockTime) ?: "waiting"}",style=MaterialTheme.typography.bodySmall)
            Text("First collect at least 60 seconds of uninterrupted volume. Gaps cancel pending entries. K/D is sampled about once per second.",style=MaterialTheme.typography.bodySmall)
            Text("Automatic while this app is open; continues in the background with the existing full-day service. No separate scan controls.",style=MaterialTheme.typography.bodySmall)
            TextButton(onClick={onlyShortlisted=!onlyShortlisted}) { Text(if (onlyShortlisted) "Show all selected stocks" else "Show shortlisted / active / completed today") }
            if (snapshot.rows.isEmpty()) Text("Waiting for selected stocks, saved token and live data. Candle history loads automatically.")
        }
        items(visible,key={it.stock.instrumentKey}) { row ->
            Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(6.dp)) {
                Text(row.stock.symbol,fontWeight=FontWeight.Bold)
                LivePriceDisplay(row.stock,prices)
                row.state.confirmationAt?.let { start ->
                    val remaining=(60-java.time.Duration.between(start,snapshot.updatedAt ?: java.time.Instant.now()).seconds).coerceAtLeast(0)
                    Text("Volume confirmation: $remaining seconds remaining",fontWeight=FontWeight.Bold)
                }
                row.state.beforeVolume?.let { before ->
                    Text("60s before: $before · after: ${row.state.afterVolume?.toString() ?: "collecting"} shares")
                    if (before > 0 && row.state.afterVolume != null) Text("Volume ratio: %.2f×".format(row.state.afterVolume.toDouble()/before))
                }
                Text(reversalActionLabel(row.state.action),fontWeight=FontWeight.SemiBold)
                if (row.status != row.state.action) Text(row.status.replace('_',' ').lowercase(),style=MaterialTheme.typography.bodySmall)
                row.preview?.let { p ->
                    Text("Live 15m Stoch RSI K %.2f / D %.2f · gap %+.2f".format(p.context.stochK,p.context.stochD,p.context.gap))
                    Text("${clockTime(p.sampledAt)} · forming candle · live signals may reverse",style=MaterialTheme.typography.bodySmall)
                } ?: Text("Live K/D unavailable · stop-loss still monitored when a fresh price is available")
                row.state.buy?.let { buy ->
                    Text("BUY ₹%.2f · ${row.state.buyAt?.let(::clockTime)}".format(buy))
                    val peak=row.state.peakPrice ?: buy
                    Text("Highest observed price ₹%.2f · peak gain %+.2f%%".format(peak,(peak/buy-1)*100))
                    Text("Current exit threshold ₹%.2f · %+.2f%% from BUY".format(ReversalStrategy.stopPrice(row.state),ReversalStrategy.stopPercent(buy,peak)))
                }
                val trades = row.state.trades.map { t -> PaperTrade(row.stock.symbol,t.buyAt,t.buy,t.sellAt,t.sell) }.toMutableList()
                if (row.state.buy != null && row.state.buyAt != null) trades += PaperTrade(row.stock.symbol,row.state.buyAt,row.state.buy)
                val quote=prices.quotes[row.stock.instrumentKey]
                PaperTradesTable(trades.sortedByDescending { it.boughtAt },quote?.price,quote?.label(java.time.Instant.now(),prices.connected,
                    prices.markets[row.stock.instrumentKey.substringBefore('|')] == true))
                row.state.trades.lastOrNull()?.let { Text("${if(it.policy == "VOLUME_STEP_V2") "Volume-confirmed entry" else "Earlier entry"} · Last exit: ${it.reason.replace('_',' ')} · ${clockTime(it.sellAt)}",style=MaterialTheme.typography.bodySmall) }
            } }
        }
        item {
            Text("Historical results include earlier 80-exit trades. The second summary includes only new volume-confirmed entries. Existing open positions adopt profit protection from prices observed after this update; past peak gains cannot be reconstructed.",style=MaterialTheme.typography.bodySmall)
            Text("Reversal strategy results only",fontWeight=FontWeight.Bold)
            CompletedTradeSummary(allTrades)
            val newTrades=snapshot.rows.flatMap { row -> row.state.trades.filter { it.policy == "VOLUME_STEP_V2" }.map { t -> PaperTrade(row.stock.symbol,t.buyAt,t.buy,t.sellAt,t.sell) } }
            Text("New volume + stepped-exit results only",fontWeight=FontWeight.Bold)
            CompletedTradeSummary(newTrades)
            Text("Open trades are excluded from win rate. P&L is gross per share. Reversal records are saved separately on this device and are not part of the existing backup file.",style=MaterialTheme.typography.bodySmall)
        }
    }
}

fun reversalActionLabel(action: String): String = when(action) {
    "CONFIRMING_60S_VOLUME_AND_KD" -> "Checking K/D and volume for 60 seconds"
    "BUY_CONFIRMED_60S_VOLUME_INCREASE" -> "BUY · 60-second volume increased"
    "BUY_ACTIVE_INITIAL_STOP" -> "BUY active · initial 1% stop"
    "BUY_ACTIVE_PROFIT_PROTECTED" -> "BUY active · profit threshold raised"
    "SELL_STEPPED_PROFIT_STOP" -> "SELL · profit-protection threshold reached"
    "SELL_SESSION_1510" -> "SELL · 15:10 session exit"
    "NO_NEW_BUYS_AFTER_1510" -> "Session entry cutoff reached · no new BUYs"
    "SELL_STOP_1_PERCENT" -> "SELL · initial stop reached"
    "ALREADY_ABOVE_20_WAITING_FOR_NEW_CROSS" -> "K already above 20 · waiting for a new crossing"
    "CROSS_UNOBSERVED_AFTER_DATA_GAP_NEW_CROSS_REQUIRED" -> "Crossing interrupted by a data gap · new crossing required"
    "K_NOT_ABOVE_D_AT_CROSS_NEW_CROSS_REQUIRED" -> "K was not above D at crossing · new crossing required"
    "PRE_CROSS_VOLUME_UNAVAILABLE_NEW_CROSS_REQUIRED" -> "Need a complete nonzero 60-second volume baseline · new crossing required"
    "VOLUME_DID_NOT_INCREASE_NEW_CROSS_REQUIRED" -> "Volume did not increase · waiting for a new crossing"
    "CONFIRMATION_CANCELLED_KD_REVERSED" -> "Entry cancelled · K/D conditions reversed"
    "CONFIRMATION_CANCELLED_DATA_GAP" -> "Entry cancelled · data interrupted"
    "SHORTLISTED_BELOW_20_WAITING_FOR_CROSS" -> "Shortlisted below 20 · watching for upward crossing"
    "WAITING_FOR_K_ABOVE_D_BELOW_20" -> "Watching for K above D below 20"
    else -> action.replace('_',' ').lowercase()
}
