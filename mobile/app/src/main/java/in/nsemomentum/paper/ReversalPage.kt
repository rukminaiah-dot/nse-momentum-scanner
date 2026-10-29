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
    val visible = snapshot.rows.filter { !onlyShortlisted || it.state.watchDate == java.time.LocalDate.now(MarketSession.ZONE).toString() || it.state.buy != null }
    LazyColumn(modifier.fillMaxSize(),contentPadding=PaddingValues(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        item {
            Text("LIVE K/D REVERSAL · PAPER ONLY",style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold)
            Text("Same selected stocks and live connection · no indices · no volume requirement")
            Text("Shortlist: K>D with K≤20. BUY: observed live K crosses above 20 with K>D. No minimum K−D gap.")
            Text("SELL: live price ≤99% of BUY, or K falls below 80 after reaching 80. First trigger wins. Quotes are paper marks, not execution fills.")
            Text("${snapshot.rows.size} stocks with current / saved state · ${snapshot.rows.count { it.state.watchDate == java.time.LocalDate.now(MarketSession.ZONE).toString() }} shortlisted · ${snapshot.rows.count { it.state.buy != null }} active BUY")
            Text("${snapshot.status} · ${snapshot.updatedAt?.let(::clockTime) ?: "waiting"}",style=MaterialTheme.typography.bodySmall)
            Text("Automatic while this app is open; continues in the background with the existing full-day service. No separate scan controls.",style=MaterialTheme.typography.bodySmall)
            TextButton(onClick={onlyShortlisted=!onlyShortlisted}) { Text(if (onlyShortlisted) "Show all selected stocks" else "Show shortlisted / active only") }
            if (snapshot.rows.isEmpty()) Text("Waiting for selected stocks, saved token and live data. Candle history loads automatically.")
        }
        items(visible,key={it.stock.instrumentKey}) { row ->
            Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(6.dp)) {
                Text(row.stock.symbol,fontWeight=FontWeight.Bold)
                LivePriceDisplay(row.stock,prices)
                Text(row.state.action.replace('_',' '),fontWeight=FontWeight.SemiBold)
                Text(row.status.replace('_',' '),style=MaterialTheme.typography.bodySmall)
                row.preview?.let { p ->
                    Text("Live 15m Stoch RSI K %.2f / D %.2f · gap %+.2f".format(p.context.stochK,p.context.stochD,p.context.gap))
                    Text("${clockTime(p.sampledAt)} · forming candle · live signals may reverse",style=MaterialTheme.typography.bodySmall)
                } ?: Text("Live K/D unavailable · stop-loss still monitored when a fresh price is available")
                row.state.buy?.let { buy ->
                    Text("BUY ₹%.2f · ${row.state.buyAt?.let(::clockTime)}".format(buy))
                    Text("Stop ₹%.2f · ${if (row.state.reached80) "K reached 80; watching for drop below 80" else "waiting for K to reach 80"}".format(buy*0.99))
                }
                val trades = row.state.trades.map { t -> PaperTrade(row.stock.symbol,t.buyAt,t.buy,t.sellAt,t.sell) }.toMutableList()
                if (row.state.buy != null && row.state.buyAt != null) trades += PaperTrade(row.stock.symbol,row.state.buyAt,row.state.buy)
                val quote=prices.quotes[row.stock.instrumentKey]
                PaperTradesTable(trades.sortedByDescending { it.boughtAt },quote?.price,quote?.label(java.time.Instant.now(),prices.connected,
                    prices.markets[row.stock.instrumentKey.substringBefore('|')] == true))
                row.state.trades.lastOrNull()?.let { Text("Last exit: ${it.reason.replace('_',' ')} · ${clockTime(it.sellAt)}",style=MaterialTheme.typography.bodySmall) }
            } }
        }
        item {
            Text("Reversal strategy results only",fontWeight=FontWeight.Bold)
            CompletedTradeSummary(allTrades)
            Text("Open trades are excluded from win rate. P&L is gross per share. Reversal records are saved separately on this device and are not part of the existing backup file.",style=MaterialTheme.typography.bodySmall)
        }
    }
}
