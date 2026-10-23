package com.nsemomentum.paper

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import java.util.Locale

private enum class Page(val title: String) {
    DASHBOARD("Home"), UNIVERSE("NSE 200"), FAVOURITES("Favourites"), SETTINGS("Settings")
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(color = MaterialTheme.colorScheme.background) { PaperScannerApp() }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PaperScannerApp() {
    val context = LocalContext.current
    val preferences = remember { context.getSharedPreferences("paper_preferences", 0) }
    val baseStocks = remember {
        runCatching {
            val json = context.assets.open("nse200.json").bufferedReader().use { it.readText() }
            val rows = JSONArray(json)
            (0 until rows.length()).map { i ->
                val row = rows.getJSONObject(i)
                Stock(row.getString("symbol"), row.getString("instrumentKey"))
            }
        }.getOrElse { emptyList() }
    }
    val stocks = remember {
        mutableStateListOf<Stock>().apply {
            addAll(baseStocks)
            addAll(StockCatalog.decodeCustom(preferences.getString("custom_stocks", null), baseStocks))
        }
    }
    val tokenStore = remember { SecureTokenStore(context) }
    val scanner = remember { UpstoxPaperScanner(CandleDatabase(context)) }
    val favourites = remember {
        mutableStateListOf<String>().apply {
            addAll(preferences.getStringSet("favourites", emptySet()).orEmpty().take(20))
        }
    }
    var page by remember { mutableStateOf(Page.DASHBOARD) }
    var search by remember { mutableStateOf("") }
    var stockSort by remember { mutableStateOf(StockSort.DAY_CHANGE) }
    var customSymbolInput by remember { mutableStateOf("") }
    var customKeyInput by remember { mutableStateOf("") }
    var customStockMessage by remember { mutableStateOf("") }
    var scanning by remember { mutableStateOf(false) }
    var scanProgress by remember { mutableStateOf("") }
    var scanStatus by remember { mutableStateOf("No scan run yet. Add your Upstox token in Settings.") }
    var report by remember { mutableStateOf<ScanReport?>(null) }
    var tokenConfigured by remember { mutableStateOf(tokenStore.read() != null) }
    val scope = rememberCoroutineScope()
    var scanJob by remember { mutableStateOf<Job?>(null) }
    LaunchedEffect(report) {
        while (report != null) {
            val snapshot = java.time.ZonedDateTime.parse(report!!.scanTime).toInstant()
            val candleExpiry = report!!.rows.mapNotNull { it.candle?.timestamp?.plusSeconds(1800) }.minOrNull()
            val expiresAt = minOf(snapshot.plusSeconds(900), candleExpiry ?: snapshot.plusSeconds(900))
            if (java.time.Instant.now() >= expiresAt) {
                report = null
                scanStatus = "Previous snapshot expired. Run a new paper scan."
                scanProgress = ""
            }
            delay(15_000)
        }
    }

    val runScan = {
        val token = tokenStore.read()
        if (token == null) {
            scanStatus = "Set your Upstox access token in Settings before scanning."
            page = Page.SETTINGS
        } else if (!scanning && baseStocks.size == 200 && stocks.size >= 200) {
            scanning = true
            scanProgress = "Verifying NSE session calendar, then stock history…"
            scanStatus = "Fetching read-only 15-minute candles for ${stocks.size} stocks…"
            report = null
            val selectedFavourites = favourites.toSet()
            scanJob = scope.launch {
                try {
                    val result = withContext(Dispatchers.IO) {
                        scanner.scan(
                            token,
                            stocks.map { it.symbol to it.instrumentKey },
                            selectedFavourites,
                            onProgress = { completed, total, symbol ->
                                withContext(Dispatchers.Main.immediate) {
                                    scanProgress = "Checked $completed / $total stocks · last: $symbol"
                                }
                            }
                        )
                    }
                    report = result
                    scanStatus = "Snapshot as of ${result.scanTime} · ${result.failedRequests} stock feed errors\n" +
                        result.rows.groupingBy { it.reason }.eachCount().entries.joinToString(" · ") { "${it.key}: ${it.value}" }
                    scanProgress = "Finished ${result.requestCount} of ${stocks.size} stocks."
                } catch (error: TimeoutCancellationException) {
                    scanProgress = ""
                    scanStatus = "Scan timed out after 10 minutes. No signals retained."
                } catch (error: CancellationException) {
                    scanProgress = ""
                    scanStatus = "Scan cancelled. No signals retained."
                    throw error
                } catch (error: Exception) {
                    scanProgress = ""
                    scanStatus = when (error.message) {
                        "UPSTOX_AUTH_REQUIRED" -> "Upstox rejected the token. Generate a fresh token and save it in Settings."
                        "RATE_LIMITED" -> "Upstox rate limit reached. Wait before scanning again."
                        "LOCAL_RATE_BUDGET_EXHAUSTED" -> "Local 30-minute API budget reached. Wait before scanning again."
                        "MARKET_CLOSED" -> "NSE is closed according to the exchange calendar."
                        "NO_COMPLETED_MARKET_CANDLE" -> "No fresh completed market candle. Scan after 09:30 IST during a regular session."
                        "UNSUPPORTED_SPECIAL_SESSION" -> "Special NSE session detected. Regular-session baseline unavailable; scan stopped."
                        "UNVERIFIED_MARKET_CALENDAR" -> "Exchange calendar could not verify 20 prior sessions. Scan stopped."
                        else -> "Scan failed. Check internet and Data health; no signal is assigned."
                    }
                } finally {
                    scanning = false
                }
            }
        }
    }

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
            Page.DASHBOARD -> Dashboard(
                stockCount = stocks.size,
                favouriteCount = favourites.size,
                customStockCount = stocks.count { it.isCustom },
                scanStatus = scanStatus,
                report = report,
                scanning = scanning,
                scanProgress = scanProgress,
                onRunScan = runScan,
                onCancelScan = { scanJob?.cancel() },
                modifier = Modifier.padding(inset)
            )
            Page.UNIVERSE -> {
                val bySymbol = report?.rows?.associateBy { it.symbol }.orEmpty()
                Column(Modifier.fillMaxSize().padding(inset)) {
                    Card(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("Add custom NSE stock", fontWeight = FontWeight.SemiBold)
                            OutlinedTextField(
                                value = customSymbolInput,
                                onValueChange = { customSymbolInput = it },
                                label = { Text("Stock symbol") },
                                singleLine = true,
                                modifier = Modifier.fillMaxWidth()
                            )
                            OutlinedTextField(
                                value = customKeyInput,
                                onValueChange = { customKeyInput = it },
                                label = { Text("Upstox instrument key, e.g. NSE_EQ|INE…") },
                                singleLine = true,
                                modifier = Modifier.fillMaxWidth()
                            )
                            Button(onClick = {
                                when (val result = StockCatalog.validateNew(
                                    customSymbolInput, customKeyInput, stocks, stocks.count { it.isCustom }
                                )) {
                                    is StockInputResult.Accepted -> {
                                        stocks.add(result.stock)
                                        preferences.edit().putString("custom_stocks", StockCatalog.encodeCustom(stocks)).apply()
                                        customSymbolInput = ""
                                        customKeyInput = ""
                                        customStockMessage = "${result.stock.symbol} added on this phone. It will be checked on the next scan."
                                    }
                                    is StockInputResult.Rejected -> customStockMessage = result.reason
                                }
                            }, enabled = stocks.count { it.isCustom } < StockCatalog.MAX_CUSTOM_STOCKS) {
                                Text("Add stock")
                            }
                            Text("Custom rows are saved on this phone. Enter the exact NSE equity key from Upstox; symbol-only lookup is not available.",
                                style = MaterialTheme.typography.bodySmall)
                            if (customStockMessage.isNotBlank()) Text(customStockMessage, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    OutlinedTextField(
                        value = search,
                        onValueChange = { search = it },
                        label = { Text("Search symbol") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                    val filteredStocks = stocks.filter { it.symbol.contains(search.trim(), ignoreCase = true) }
                    Text("Sort stocks", Modifier.padding(start = 16.dp, top = 4.dp))
                    Row(
                        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        StockSort.entries.forEach { option ->
                            FilterChip(
                                selected = stockSort == option,
                                onClick = { stockSort = option },
                                label = { Text(option.label) }
                            )
                        }
                    }
                    val shown = StockListOrdering.sort(filteredStocks, bySymbol, stockSort)
                    Text("${shown.size} of ${stocks.size} stocks · ${stocks.count { it.isCustom }} custom", Modifier.padding(horizontal = 16.dp))
                    LazyColumn(
                        modifier = Modifier.weight(1f),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(shown, key = { it.symbol }) { stock ->
                            val selected = stock.symbol in favourites
                            val row = bySymbol[stock.symbol]
                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(14.dp)
                            ) {
                                Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                                    Column(Modifier.weight(1f)) {
                                        Text(stock.symbol + if (stock.isCustom) " · CUSTOM" else "", fontWeight = FontWeight.SemiBold)
                                        Text(
                                            row?.candle?.close?.let { "Last 15m close ₹${formatPrice(it)}" } ?: "Last 15m close unavailable",
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                        Text(
                                            row?.dailyChangePercent?.let {
                                                "Day change ${if (it >= 0) "+" else ""}${formatPercent(it)}% vs prior close"
                                            } ?: "Day change unavailable",
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                        Text(
                                            row?.let {
                                                val currentVolume = it.candle?.volume?.let(::formatVolume) ?: "unavailable"
                                                val averageVolume = it.averageSlotVolume?.let(::formatVolume) ?: "unavailable"
                                                val rvol = it.relativeVolume?.let { value -> "${formatPrice(value)}×" } ?: "unavailable"
                                                "15m volume $currentVolume · 20-session same-slot avg $averageVolume · RVOL $rvol"
                                            } ?: "15m volume unavailable · 20-session avg unavailable",
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                        Text(
                                            row?.let { "${it.signal} · ${it.reason}" } ?: "WAIT · No verified scan data",
                                            style = MaterialTheme.typography.labelSmall
                                        )
                                        Text(stock.instrumentKey, style = MaterialTheme.typography.labelSmall)
                                    }
                                    Column {
                                        TextButton(
                                            onClick = {
                                                if (selected) favourites.remove(stock.symbol)
                                                else if (favourites.size < 20) favourites.add(stock.symbol)
                                                preferences.edit().putStringSet("favourites", favourites.toSet()).apply()
                                            },
                                            enabled = selected || favourites.size < 20
                                        ) { Text(if (selected) "★ Saved" else "☆ Add") }
                                        if (stock.isCustom) TextButton(onClick = {
                                            stocks.remove(stock)
                                            favourites.remove(stock.symbol)
                                            preferences.edit()
                                                .putStringSet("favourites", favourites.toSet())
                                                .putString("custom_stocks", StockCatalog.encodeCustom(stocks))
                                                .apply()
                                            report = report?.copy(rows = report!!.rows.filterNot { it.symbol == stock.symbol })
                                            customStockMessage = "${stock.symbol} removed from this phone."
                                        }) { Text("Remove") }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Page.FAVOURITES -> {
                val selectedStocks = stocks.filter { it.symbol in favourites }
                val bySymbol = report?.rows?.associateBy { it.symbol }.orEmpty()
                if (selectedStocks.isEmpty()) {
                    MessagePage(
                        "Your favourites",
                        "Search the NSE 200 list and tap a star to add up to 20 stocks. Technical checks run only for favourites.",
                        Modifier.padding(inset)
                    )
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize().padding(inset),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        item { Text("FAVOURITES · 15-MINUTE PAPER SIGNALS", fontWeight = FontWeight.Bold)
                            Text("BUY/SELL require RVOL ≥ 1.5×, EMA direction, a strong candle breaking the prior 3 bars, and a Stoch RSI cross at ≤20 / ≥80. Otherwise WAIT; no position or order tracking.", style = MaterialTheme.typography.bodySmall) }
                        items(selectedStocks, key = { it.symbol }) { stock ->
                            val row = bySymbol[stock.symbol]
                            Card(Modifier.fillMaxWidth()) {
                                Column(Modifier.padding(16.dp)) {
                                    Text(stock.symbol, fontWeight = FontWeight.Bold)
                                    Spacer(Modifier.height(6.dp))
                                    Text(row?.signal ?: "WAIT · NO VERIFIED SCAN")
                                    Text(
                                        row?.let { rowDetail(it) } ?: "Candle time, RVOL, EMA trend and Stochastic RSI appear after a successful read-only scan.",
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                            }
                        }
                    }
                }
            }
            Page.SETTINGS -> SettingsPage(
                tokenConfigured = tokenConfigured,
                scanStatus = scanStatus,
                onSaveToken = { token ->
                    scanJob?.cancel()
                    report = null
                    runCatching { tokenStore.save(token) }
                    tokenConfigured = tokenStore.read() != null
                },
                onClearToken = {
                    scanJob?.cancel()
                    report = null
                    tokenStore.clear()
                    tokenConfigured = false
                    scanStatus = "Token cleared from this device."
                },
                modifier = Modifier.padding(inset)
            )
        }
    }
}

private fun formatPrice(value: Double): String = String.format(Locale.US, "%.2f", value)
private fun formatPercent(value: Double): String = String.format(Locale.US, "%.2f", value)
private fun formatVolume(value: Double): String =
    java.text.NumberFormat.getNumberInstance(Locale("en", "IN")).apply { maximumFractionDigits = 2 }.format(value)

private fun rowSummary(row: ScanRow): String {
    val rvol = row.relativeVolume?.let { " · RVOL ${"%.2f".format(it)}×" }.orEmpty()
    return "${row.signal}$rvol · ${row.reason}"
}

private fun rowDetail(row: ScanRow): String {
    val time = row.candleTime ?: "Candle time unavailable"
    val rvol = row.relativeVolume?.let { "RVOL ${"%.2f".format(it)}×" } ?: "RVOL unavailable"
    val candle = row.candle?.let { "\n15m O ${it.open} · H ${it.high} · L ${it.low} · C ${it.close} · V ${it.volume.toLong()}" }.orEmpty()
    val technical = row.technicals?.let {
        "\nEMA 20 ${"%.2f".format(it.ema20)} · EMA 50 ${"%.2f".format(it.ema50)}" +
            "\nStoch RSI (14,14,3,3) K ${"%.2f".format(it.stochK)} · D ${"%.2f".format(it.stochD)}"
    }.orEmpty()
    return "$time · $rvol · ${row.reason}$candle$technical"
}

@Composable
private fun Dashboard(
    stockCount: Int,
    favouriteCount: Int,
    customStockCount: Int,
    scanStatus: String,
    report: ScanReport?,
    scanning: Boolean,
    scanProgress: String,
    onRunScan: () -> Unit,
    onCancelScan: () -> Unit,
    modifier: Modifier = Modifier
) {
    val qualified = report?.rows?.count { (it.relativeVolume ?: 0.0) >= 1.5 } ?: 0
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
            Column(Modifier.padding(18.dp)) {
                Text("PAPER TRADING · NO ORDERS", fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text(if (scanning) "SCANNING · READ ONLY" else "15-MINUTE VOLUME-FIRST SCAN", style = MaterialTheme.typography.titleMedium)
                Text(scanStatus)
                if (scanProgress.isNotBlank()) Text(scanProgress, style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(8.dp))
                Button(onClick = onRunScan, enabled = !scanning && stockCount >= 200) {
                    Text(if (scanning) "Scanning…" else "Run paper scan")
                }
                if (scanning) Button(onClick = onCancelScan) { Text("Cancel scan") }
            }
        }
        InfoCard("NSE 200 + custom volume screen", "$stockCount stocks configured", "$customStockCount custom additions · $qualified stocks at or above 1.5× verified volume, if a scan has completed.")
        InfoCard("Favourites", "$favouriteCount / 20 selected", "EMA 20/50 and Stochastic RSI checks run only for saved favourites.")
        if (report != null) {
            report.rows.filter { (it.relativeVolume ?: 0.0) >= 1.5 }.forEach { row ->
                InfoCard(row.symbol, row.signal, rowDetail(row))
            }
        }
    }
}

@Composable
private fun SettingsPage(
    tokenConfigured: Boolean,
    scanStatus: String,
    onSaveToken: (String) -> Unit,
    onClearToken: () -> Unit,
    modifier: Modifier = Modifier
) {
    var tokenInput by remember { mutableStateOf("") }
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Settings & data health", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text("PAPER MODE · no order placement capability")
        Text("Generate a personal access token in Upstox Developer Apps, then enter it here. The app encrypts it on this phone and does not log or upload it.")
        OutlinedTextField(
            value = tokenInput,
            onValueChange = { tokenInput = it },
            label = { Text("Upstox access token") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = {
                if (tokenInput.isNotBlank()) {
                    onSaveToken(tokenInput)
                    tokenInput = ""
                }
            }, enabled = tokenInput.isNotBlank()) { Text("Save encrypted token") }
            Button(onClick = onClearToken) { Text("Clear token") }
        }
        Text(if (tokenConfigured) "Token saved on this device" else "No token saved")
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Latest scan status", fontWeight = FontWeight.SemiBold)
                Text(scanStatus)
                Text("Missing, stale, invalid, or incomplete candles produce WAIT / unavailable states.",
                    style = MaterialTheme.typography.bodySmall)
            }
        }
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
