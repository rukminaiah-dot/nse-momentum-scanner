package com.nsemomentum.paper

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun IndexOverview(report: IndexMarketReport?, enabled: Boolean, onRefresh: () -> Unit) {
    Text("Market indices", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
    Text("Nifty 50 · Sensex · Bank Nifty", style = MaterialTheme.typography.titleMedium)
    Text("Web index rules: three rising 5-minute closes = Bullish; three falling closes = Bearish; otherwise Neutral. No RVOL filter. These do not use your 40 stock places.", style = MaterialTheme.typography.bodySmall)
    Button(enabled = enabled, onClick = onRefresh) { Text("Refresh index data") }
    val readings = report?.at(Instant.now())?.rows?.associateBy { it.symbol }.orEmpty()
    val names = mapOf("NIFTY50" to "Nifty 50 · NSE", "SENSEX" to "Sensex · BSE", "BANKNIFTY" to "Bank Nifty · NSE")
    StockCatalog.indices.forEach { index ->
        val row = readings[index.symbol] ?: IndexReading(index.symbol)
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(names.getValue(index.symbol), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
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
