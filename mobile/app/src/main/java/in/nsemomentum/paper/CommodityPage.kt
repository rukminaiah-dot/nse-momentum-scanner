package com.nsemomentum.paper

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import java.time.Instant

@Composable
fun CommodityPage(snapshot:CommoditySnapshot,prices:LivePriceState,modifier:Modifier=Modifier) {
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(Unit) {while(true) {now=Instant.now();delay(1000)}}
    LazyColumn(modifier.fillMaxSize(),contentPadding=PaddingValues(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        item {
            Text("COMMODITIES · MCX FUTURES",style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold)
            Text("Gold · Silver · Crude Oil · Natural Gas")
            Text("Same direction rule as indices: three rising completed 5m closes = bullish; three falling = bearish; otherwise neutral. No stock-volume rule or commodity paper trades.")
            Text("Automatically selects the nearest non-expired standard futures contract, fixed for this app session/day. Contract and expiry are shown below. These are futures prices, not spot prices.",style=MaterialTheme.typography.bodySmall)
            Text("Live prices share the existing stream. Direction checks every 10 seconds for new completed candles while the app is open or the existing full-day service is active. MCX uses its own verified session hours.",style=MaterialTheme.typography.bodySmall)
        }
        items(snapshot.rows,key={it.name}) { row ->
            Card(Modifier.fillMaxWidth()) {Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(6.dp)) {
                Text(row.name,fontWeight=FontWeight.Bold)
                row.contract?.let { contract ->
                    Text("${contract.symbol} · expiry ${contract.expiry}",style=MaterialTheme.typography.bodySmall)
                    LivePriceDisplay(Stock(row.name,contract.key),prices)
                } ?: Text("Resolving MCX contract…")
                val current=row.candle?.timestamp?.plusSeconds(300)?.let { java.time.Duration.between(it,now).seconds in 0..480 } == true
                Text(if(row.sessionOpen && current && row.error==null) row.direction else "WAIT · historical / delayed",fontWeight=FontWeight.Bold)
                row.candle?.let { Text("Last 5m close ₹%.2f · ${clockTime(it.timestamp.plusSeconds(300))}".format(it.close)) }
                row.technicals?.let { Text("Confirmed 5m Stoch RSI K %.2f / D %.2f".format(it.stochK,it.stochD)) }
                Text("Last successful refresh: ${row.checkedAt?.let(::clockTime) ?: "unavailable"}",style=MaterialTheme.typography.bodySmall)
                row.nextClose?.let { close ->
                    val remaining=java.time.Duration.between(now,close).seconds
                    Text(if(remaining>0) "Next 5m close ${clockTime(close)} · %02d:%02d".format(remaining/60,remaining%60) else "Waiting for completed candle data")
                } ?: Text("No active MCX candle countdown")
                if(row.changedAt!=null) Text("Last direction change: ${row.previousDirection} → ${row.direction} · ${clockTime(row.changedAt)}")
                row.error?.let { Text("Refresh issue: $it · last valid reading retained",color=MaterialTheme.colorScheme.error) }
            }}
        }
    }
}
