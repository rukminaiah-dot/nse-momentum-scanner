package in.nsemomentum.paper

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.json.JSONArray

private data class Stock(val symbol: String, val instrumentKey: String)
private enum class Page(val title: String) {
    DASHBOARD("Home"), UNIVERSE("NSE 200"), FAVOURITES("Favourites"), HEALTH("Data health")
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(color = MaterialTheme.colorScheme.background) {
                    PaperScannerApp()
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PaperScannerApp() {
    val context = LocalContext.current
    val stocks = remember {
        runCatching {
            val json = context.assets.open("nse200.json").bufferedReader().use { it.readText() }
            val rows = JSONArray(json)
            (0 until rows.length()).map { i ->
                val row = rows.getJSONObject(i)
                Stock(row.getString("symbol"), row.getString("instrumentKey"))
            }
        }.getOrElse { emptyList() }
    }
    val preferences = remember { context.getSharedPreferences("paper_preferences", 0) }
    val favourites = remember {
        mutableStateListOf<String>().apply {
            addAll(preferences.getStringSet("favourites", emptySet()).orEmpty().take(20))
        }
    }
    var page by remember { mutableStateOf(Page.DASHBOARD) }
    var search by remember { mutableStateOf("") }

    Scaffold(
        topBar = {
            TopAppBar(title = {
                Column {
                    Text("NSE Momentum", fontWeight = FontWeight.Bold)
                    Text("PAPER ONLY · NO ORDERS", style = MaterialTheme.typography.labelSmall)
                }
            })
        },
        bottomBar = {
            NavigationBar {
                Page.entries.forEach { item ->
                    NavigationBarItem(
                        selected = page == item,
                        onClick = { page = item },
                        icon = { Text("•") },
                        label = { Text(item.title) }
                    )
                }
            }
        }
    ) { inset ->
        when (page) {
            Page.DASHBOARD -> Dashboard(stocks.size, favourites.size, Modifier.padding(inset))
            Page.UNIVERSE -> Column(Modifier.fillMaxSize().padding(inset)) {
                OutlinedTextField(
                    value = search,
                    onValueChange = { search = it },
                    label = { Text("Search symbol") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)
                )
                val shown = stocks.filter { it.symbol.contains(search.trim(), ignoreCase = true) }
                Text("${shown.size} of ${stocks.size} configured stocks", Modifier.padding(horizontal = 16.dp))
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(shown, key = { it.symbol }) { stock ->
                        val selected = stock.symbol in favourites
                        Card(
                            onClick = {
                                if (selected) favourites.remove(stock.symbol)
                                else if (favourites.size < 20) favourites.add(stock.symbol)
                                preferences.edit().putStringSet("favourites", favourites.toSet()).apply()
                            },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(14.dp)
                        ) {
                            Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                                Column(Modifier.weight(1f)) {
                                    Text(stock.symbol, fontWeight = FontWeight.SemiBold)
                                    Text(stock.instrumentKey, style = MaterialTheme.typography.labelSmall)
                                }
                                Text(if (selected) "★ Saved" else "☆ Add")
                            }
                        }
                    }
                }
            }
            Page.FAVOURITES -> {
                val selectedStocks = stocks.filter { it.symbol in favourites }
                if (selectedStocks.isEmpty()) {
                    MessagePage(
                        "Your favourites",
                        "Add stocks from NSE 200. Each favourite will get its own 15-minute trend and Stochastic RSI check after verified candle data is connected.",
                        Modifier.padding(inset)
                    )
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize().padding(inset),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        item { Text("FAVOURITES · PAPER SIGNALS", fontWeight = FontWeight.Bold) }
                        items(selectedStocks, key = { it.symbol }) { stock ->
                            Card(Modifier.fillMaxWidth()) {
                                Column(Modifier.padding(16.dp)) {
                                    Text(stock.symbol, fontWeight = FontWeight.Bold)
                                    Spacer(Modifier.height(6.dp))
                                    Text("WAIT · NO VERIFIED CANDLE DATA")
                                    Text("15-minute candle, RVOL, EMA 20/50 and Stochastic RSI will appear after read-only feed setup.",
                                        style = MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                    }
                }
            }
            Page.HEALTH -> MessagePage(
                "Data health",
                "No market data has been fetched by this prototype. It will never label stored or sample values as live. A paper signal requires a completed, fresh 15-minute candle and a verified 20-session same-slot volume baseline.",
                Modifier.padding(inset)
            )
        }
    }
}

@Composable
private fun Dashboard(stockCount: Int, favouriteCount: Int, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
            Column(Modifier.padding(18.dp)) {
                Text("PAPER TRADING · NO ORDERS", fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text("WAIT · READ-ONLY FEED NOT CONNECTED", style = MaterialTheme.typography.titleMedium)
                Text("No live or simulated performance is shown until genuine candles are available.")
            }
        }
        InfoCard("NSE 200", "$stockCount stocks configured", "Volume-first screening is planned for all 200 stocks.")
        InfoCard("Favourites", "$favouriteCount / 20 selected", "15-minute technical checks apply only to saved favourites.")
        InfoCard("Next step", "Connect read-only Upstox feed", "Secure sign-in and data validation come before any signal calculation.")
    }
}

@Composable
private fun InfoCard(title: String, headline: String, detail: String) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.labelLarge)
            Text(headline, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text(detail, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun MessagePage(title: String, detail: String, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(detail)
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Signal state", fontWeight = FontWeight.SemiBold)
                Text("WAIT · DATA NOT VERIFIED")
                Text("Paper only. No orders can be placed from this app.", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
