package com.nsemomentum.paper

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import kotlinx.coroutines.delay
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun LivePriceDisplay(stock: Stock, state: LivePriceState) {
    val quote = state.quotes[stock.instrumentKey]
    if (quote == null) {
        Text("Price unavailable · waiting for Upstox quote", style = MaterialTheme.typography.bodySmall)
        return
    }
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(quote) { while (true) { now = Instant.now(); delay(1000) } }
    val label = quote.label(now, state.connected, state.markets[stock.instrumentKey.substringBefore('|')] == true)
    val color = when {
        (quote.change ?: 0.0) > 0 -> Color(0xFF146B32)
        (quote.change ?: 0.0) < 0 -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.onSurface
    }
    Text("₹${String.format(Locale.US, "%.2f", quote.price)}", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
    val change = quote.change?.let { String.format(Locale.US, "%+.2f", it) }
    val percent = quote.changePercent?.let { String.format(Locale.US, "%+.2f", it) }
    Text(if (change != null && percent != null) "₹$change ($percent%) today" else "Day change unavailable", color = color)
    val time = DateTimeFormatter.ofPattern("dd MMM HH:mm:ss 'IST'", Locale.US).withZone(MarketSession.ZONE).format(quote.tradedAt)
    Text("$label · $time", style = MaterialTheme.typography.bodySmall)
}
