package com.nsemomentum.paper

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun IndexOverview(report: IndexMarketReport?, enabled: Boolean, onRefresh: () -> Unit, livePrices: LivePriceState = LivePriceState()) {
    val context = LocalContext.current
    val latestPrices by rememberUpdatedState(livePrices)
    var now by remember { mutableStateOf(Instant.now()) }
    var previews by remember { mutableStateOf(emptyMap<String,LiveStochastic>()) }
    LaunchedEffect(Unit) {
        val db = CandleDatabase(context)
        try { while (true) {
            now = Instant.now()
            val state = latestPrices
            previews = withContext(Dispatchers.IO) { StockCatalog.indices.mapNotNull { stock ->
                LiveStochasticPreview.calculate(db.bars("index5:" + stock.instrumentKey),state.quotes[stock.instrumentKey],now,state.connected,
                    state.markets[stock.instrumentKey.substringBefore('|')] == true,5)?.let { stock.symbol to it }
            }.toMap() }
            delay(1000)
        } } finally { db.close() }
    }
    Text("Market indices", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
    Text("Nifty 50 · Sensex · Bank Nifty", style = MaterialTheme.typography.titleMedium)
    Text("Web index rules: three rising 5-minute closes = Bullish; three falling closes = Bearish; otherwise Neutral. No RVOL filter. These do not use your 40 stock places.", style = MaterialTheme.typography.bodySmall)
    Button(enabled = enabled, onClick = onRefresh) { Text("Refresh index data") }
    val readings = report?.at(now)?.rows?.associateBy { it.symbol }.orEmpty()
    val names = mapOf("NIFTY50" to "Nifty 50 · NSE", "SENSEX" to "Sensex · BSE", "BANKNIFTY" to "Bank Nifty · NSE")
    StockCatalog.indices.forEach { index ->
        val row = readings[index.symbol] ?: IndexReading(index.symbol)
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(names.getValue(index.symbol), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                LivePriceDisplay(index, livePrices)
                val local = now.atZone(MarketSession.ZONE)
                val minute = local.hour * 60 + local.minute
                if (minute in 555 until 930 && row.state in setOf(IndexDataState.LIVE, IndexDataState.STALE)) {
                    val close = local.toLocalDate().atTime(9,15).atZone(MarketSession.ZONE).toInstant().plusSeconds(((minute - 555) / 5 + 1) * 300L)
                    val seconds = java.time.Duration.between(now,close).seconds.coerceAtLeast(0)
                    Text("Next 5m close: ${clockTime(close)} · %02d:%02d remaining".format(seconds / 60,seconds % 60))
                    val expected = close.minusSeconds(300)
                    if ((row.candle?.timestamp?.plusSeconds(300) ?: Instant.EPOCH) < expected)
                        Text("Waiting for completed candle data · refresh checks every 10s")
                } else Text("Market closed / not confirmed open · no active candle countdown")
                Text("Last successful candle refresh: ${row.refreshedAt?.let(::clockTime) ?: "unavailable"}", style=MaterialTheme.typography.bodySmall)
                row.lastError?.let { Text("Refresh issue: $it · last valid reading retained", color=MaterialTheme.colorScheme.error) }
                row.technicals?.let { Text("Confirmed 5m Stoch RSI K ${indexNumber(it.stochK)} / D ${indexNumber(it.stochD)}") }
                previews[index.symbol]?.let { Text("Live 5m K ${indexNumber(it.context.stochK)} / D ${indexNumber(it.context.stochD)} · provisional · ${clockTime(it.sampledAt)}") }
                if (row.state == IndexDataState.LIVE && row.previousDirection != null && row.changedAt != null)
                    Text("Last change: ${row.previousDirection} → ${row.signal} · ${clockTime(row.changedAt)}")
                else if (row.signal != "WAIT") Text("Direction unchanged / first reading: ${row.signal}")
                Text(when (row.state) {
                    IndexDataState.LIVE -> "Fresh completed 5-minute candle"
                    IndexDataState.HISTORICAL -> "Historical context · no live signal"
                    IndexDataState.STALE -> "Saved snapshot · refresh needed"
                    IndexDataState.UNAVAILABLE -> "Data unavailable"
                }, style = MaterialTheme.typography.labelLarge)
                row.candle?.let { bar ->
                    val time = DateTimeFormatter.ofPattern("dd MMM yyyy HH:mm 'IST'", Locale.US).withZone(MarketSession.ZONE).format(bar.timestamp)
                    Text("Candle start: $time", style = MaterialTheme.typography.bodySmall)
                    Text("5m close: ${indexNumber(bar.close)} · Day change: ${indexNumber(row.dayChangePercent)}%")
                }
                Text(if (row.state == IndexDataState.LIVE) row.signal else "WAIT", fontWeight = FontWeight.SemiBold)
                Text(if (row.reason == "NO_INDEX_SCAN") "Save your token in Settings, then refresh index data." else row.reason.replace('_', ' ').lowercase(Locale.US), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
    HorizontalDivider(Modifier.padding(vertical = 8.dp))
    Text("My stock scanner", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
}

private fun indexNumber(value: Double?): String = value?.let { String.format(Locale.US, "%.2f", it) } ?: "—"
