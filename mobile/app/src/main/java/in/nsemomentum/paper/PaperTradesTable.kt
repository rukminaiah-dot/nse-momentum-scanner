package com.nsemomentum.paper

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.util.Locale

fun clockTime(time: Instant): String = DateTimeFormatter.ofPattern("dd MMM HH:mm:ss 'IST'", Locale.US)
    .withZone(MarketSession.ZONE).format(time)

private fun money(value: Double?): String = value?.let { String.format(Locale.US,"%+.2f",it) } ?: "—"

@Composable
fun PaperTradesTable(trades: List<PaperTrade>, mark: Double?, markLabel: String?, allTrades: Boolean = false) {
    var expanded by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (!allTrades) {
            val latest = trades.firstOrNull()
            Text(if (latest == null) "Paper return: — · P&L: — · no recorded BUY" else
                "${if (latest.sell == null) "Open" else "Completed"} paper return ${money(latest.percent(mark))}% · gross P&L ₹${money(latest.gross(mark))} / share",
                fontWeight = FontWeight.SemiBold)
            if (latest?.sell == null && latest != null) Text("Mark: ${markLabel ?: "unavailable"}", style = MaterialTheme.typography.bodySmall)
        }
        TextButton(onClick = { expanded = !expanded }) {
            Text("${if (expanded) "Hide" else "Show"} ${if (allTrades) "all paper trades" else "BUY / SELL details"} (${trades.size})")
        }
        if (expanded) {
            Text("Paper only · 1 share per trade · gross before charges / slippage. Signal prices are completed-candle closes, not execution fills.", style = MaterialTheme.typography.bodySmall)
            if (trades.isEmpty()) Text("No recorded paper trades yet.")
            Column(Modifier.horizontalScroll(rememberScrollState())) {
                Row { listOf("Stock", "BUY ₹", "BUY time", "SELL ₹", "SELL time", "Return %", "P&L ₹ / share").forEach { TradeCell(it) } }
                trades.forEach { trade ->
                    val currentMark = if (allTrades) null else mark
                    Row {
                        listOf(trade.symbol, String.format(Locale.US,"%.2f",trade.buy), clockTime(trade.boughtAt),
                            trade.sell?.let { String.format(Locale.US,"%.2f",it) } ?: "OPEN",
                            trade.soldAt?.let(::clockTime) ?: "—", money(trade.percent(currentMark)), money(trade.gross(currentMark)))
                            .forEach { TradeCell(it) }
                    }
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun TradeCell(value: String) { Text(value, Modifier.width(150.dp).padding(6.dp), style = MaterialTheme.typography.bodySmall) }
