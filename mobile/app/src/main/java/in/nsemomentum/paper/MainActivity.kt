package com.nsemomentum.paper

import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import android.os.Bundle
import android.Manifest
import android.content.pm.PackageManager
import android.content.Intent
import android.os.Build
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.Alignment
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
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import java.util.Locale
import kotlin.math.abs

private enum class Page(val title: String) {
    DASHBOARD("Home"), UNIVERSE("Stocks"), FAVOURITES("My 40"), REVERSAL("Reversal"), COMMODITIES("MCX"), SETTINGS("Settings")
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        DiagnosticLog.initialize(this)
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
            } + StockCatalog.indices
        }.getOrElse { emptyList() }
    }
    val stocks = remember {
        mutableStateListOf<Stock>().apply {
            addAll(baseStocks)
            addAll(StockCatalog.decodeCustom(preferences.getString("custom_stocks", null), baseStocks))
        }
    }
    val tokenStore = remember { SecureTokenStore(context) }
    val database = remember { CandleDatabase(context) }
    val sharedFeed = remember { UpstoxCandleFeed() }
    val scanner = remember { UpstoxPaperScanner(database, sharedFeed) }
    val selectionStore = remember { InstrumentSelectionStore(context, baseStocks) }
    val indexScanner = remember { IndexMarketScanner(database, sharedFeed) }
    val indexStore = remember { IndexSnapshotStore(context) }
    var indexReport by remember { mutableStateOf(indexStore.read()) }
    val favourites = remember {
        mutableStateListOf<String>().apply {
            addAll(StockCatalog.stockSelections(preferences.getStringSet("favourites", emptySet()).orEmpty()).take(StockCatalog.MAX_ACTIVE))
        }
    }
    var page by remember { mutableStateOf(Page.DASHBOARD) }
    var search by remember { mutableStateOf("") }
    var stockSort by remember { mutableStateOf(StockSort.DAY_CHANGE) }
    var showInstrumentSearch by remember { mutableStateOf(false) }
    var customStockMessage by remember { mutableStateOf("") }
    var scanning by remember { mutableStateOf(false) }
    var scanProgress by remember { mutableStateOf("") }
    var scanStatus by remember { mutableStateOf("No scan run yet. Add your Upstox token in Settings.") }
    var report by remember { mutableStateOf<ScanReport?>(null) }
    var autoScanActive by remember { mutableStateOf(preferences.getBoolean(PaperScanService.PREF_ACTIVE, false)) }
    var autoScanStatus by remember { mutableStateOf(preferences.getString(PaperScanService.PREF_STATUS, "Full-day scan is off.") ?: "Full-day scan is off.") }
    var qualifiedToday by remember { mutableStateOf(emptyList<QualifiedStock>()) }
    var liveStochastic by remember { mutableStateOf(emptyMap<String, LiveStochastic>()) }
    var paperTrades by remember { mutableStateOf(emptyList<PaperTrade>()) }
    var previewSampledAt by remember { mutableStateOf(java.time.Instant.now()) }
    var weeklySummary by remember { mutableStateOf(emptyList<DailyPaperSummary>()) }
    var weeklyOutcomes by remember { mutableStateOf(emptyList<PaperOutcome>()) }
    var tokenConfigured by remember { mutableStateOf(tokenStore.read() != null) }
    val livePriceClient = remember { UpstoxLivePrices() }
    var livePrices by remember { mutableStateOf(LivePriceState(status = "Save your Upstox token in Settings for live prices.")) }
    var liveTokenRevision by remember { mutableStateOf(0) }
    val priceLifecycle = LocalLifecycleOwner.current.lifecycle
    val priceKeys = (stocks.filter { it.symbol in favourites && "_EQ|" in it.instrumentKey } + StockCatalog.indices).map { it.instrumentKey }.toSet()
    LaunchedEffect(priceKeys, tokenConfigured, liveTokenRevision, priceLifecycle) {
        priceLifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            val savedToken = tokenStore.read()
            if (!savedToken.isNullOrBlank()) {
                LiveMarketHub.acquire("screen", savedToken, priceKeys)
                try { LiveMarketHub.state.collect { livePrices = it; delay(1000) } }
                finally { LiveMarketHub.release("screen") }
            } else livePrices = LivePriceState(status="Save your Upstox token in Settings")
        }
    }
    LaunchedEffect(tokenConfigured, liveTokenRevision) {
        priceLifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                tokenStore.read()?.let { token -> withContext(Dispatchers.IO) { IndexRefresh.refresh(context,token) } }
                delay(10_000)
            }
        }
    }
    var reversalSnapshot by remember { mutableStateOf(ReversalRunner.state.value) }
    val reversalStocks = stocks.filter { it.symbol in favourites && "_EQ|" in it.instrumentKey }.toList()
    LaunchedEffect(reversalStocks, tokenConfigured, liveTokenRevision) {
        priceLifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            val saved = tokenStore.read()
            if (!saved.isNullOrBlank()) {
                StockSessionCloser.acquire("screen",context,saved)
                ReversalRunner.acquire("screen",context,saved,reversalStocks)
                try { ReversalRunner.state.collect { reversalSnapshot=it } }
                finally { ReversalRunner.release("screen");StockSessionCloser.release("screen") }
            }
        }
    }
    var commoditySnapshot by remember { mutableStateOf(CommodityMonitor.state.value) }
    LaunchedEffect(tokenConfigured,liveTokenRevision) {
        priceLifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            val saved=tokenStore.read()
            if(!saved.isNullOrBlank()) {
                CommodityMonitor.acquire("screen",context,saved)
                try { CommodityMonitor.state.collect { commoditySnapshot=it } }
                finally { CommodityMonitor.release("screen") }
            }
        }
    }
    val scope = rememberCoroutineScope()
    var scanJob by remember { mutableStateOf<Job?>(null) }
    var backupStatus by remember { mutableStateOf("") }
    var backupBusy by remember { mutableStateOf(false) }
    var pendingBackup by remember { mutableStateOf<PaperBackup.Snapshot?>(null) }
    fun backupAllowed() = !scanning && !preferences.getBoolean(PaperScanService.PREF_ACTIVE, false)
    val exportBackup = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null && backupAllowed()) {
            backupBusy = true
            scope.launch {
                try {
                    val saved = withContext(Dispatchers.IO) {
                        val encoded = PaperBackupStore(context, database, baseStocks).export()
                        val snapshot = PaperBackup.decode(encoded, baseStocks)
                        val bytes = encoded.toByteArray(Charsets.UTF_8)
                        requireNotNull(context.contentResolver.openOutputStream(uri, "wt")).use { it.write(bytes) }
                        val readBack = requireNotNull(context.contentResolver.openInputStream(uri)).use { it.readBytes() }
                        require(bytes.contentEquals(readBack))
                        snapshot
                    }
                    backupStatus = "Backup saved and read back: ${saved.favourites.size} favourites, ${saved.custom.size} custom stocks, and paper history. Token excluded. Keep this file private."
                } catch (_: Exception) {
                    backupStatus = "Backup failed. Do not uninstall or clear app data. Try another file location."
                } finally { backupBusy = false }
            }
        }
    }
    val importBackup = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null && backupAllowed()) {
            backupBusy = true
            scope.launch {
                try {
                    pendingBackup = withContext(Dispatchers.IO) {
                        val bytes = requireNotNull(context.contentResolver.openInputStream(uri)).use { input ->
                            val out = java.io.ByteArrayOutputStream()
                            val buffer = ByteArray(8192)
                            while (true) {
                                val n = input.read(buffer)
                                if (n < 0) break
                                require(out.size() + n <= PaperBackup.MAX_BYTES)
                                out.write(buffer, 0, n)
                            }
                            out.toByteArray()
                        }
                        PaperBackup.decode(bytes.toString(Charsets.UTF_8), baseStocks)
                    }
                } catch (_: Exception) {
                    backupStatus = "Backup rejected: invalid, unsupported, or too large. No data changed."
                } finally { backupBusy = false }
            }
        }
    }
    if (backupBusy && pendingBackup == null) {
        androidx.compose.material3.AlertDialog(
            onDismissRequest = {}, confirmButton = {},
            title = { Text("Processing backup") },
            text = { Text("Keep the app open until this completes.") }
        )
    }
    pendingBackup?.let { incoming ->
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { if (!backupBusy) pendingBackup = null },
            title = { Text("Restore paper backup?") },
            text = { Text("Merge ${incoming.favourites.size} favourites, ${incoming.custom.size} custom stocks, and paper history. Existing history is kept on duplicate keys. Token and live scan state are unchanged. Imported history is user-supplied, not verified performance.") },
            confirmButton = {
                Button(enabled = !backupBusy, onClick = {
                    if (backupAllowed()) {
                        backupBusy = true
                        scope.launch {
                            try {
                                val merged = withContext(Dispatchers.IO) {
                                    PaperBackupStore(context, database, baseStocks).restore(PaperBackup.encode(incoming))
                                }
                                stocks.clear(); stocks.addAll(baseStocks + merged.custom)
                                favourites.clear(); favourites.addAll(StockCatalog.stockSelections(merged.favourites).sorted())
                                backupStatus = "Restore complete. Imported history is user-supplied paper data, not verified performance."
                                pendingBackup = null
                            } catch (_: Exception) {
                                backupStatus = "Restore not completed. Check stock conflicts, 40-stock limits, and free storage. Existing data is kept; retry is safe."
                            } finally { backupBusy = false }
                        }
                    } else backupStatus = "Stop all scans before restoring."
                }) { Text("Merge backup") }
            },
            dismissButton = { Button(enabled = !backupBusy, onClick = { pendingBackup = null }) { Text("Cancel") } }
        )
    }
    val startFullDayScan: () -> Unit = {
        if (tokenStore.read().isNullOrBlank()) {
            page = Page.SETTINGS
            autoScanStatus = "Add an Upstox token in Settings before starting the full-day scan."
        } else {
            val intent = Intent(context, PaperScanService::class.java).setAction(PaperScanService.ACTION_START)
            runCatching {
                if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent) else context.startService(intent)
                autoScanActive = true
                autoScanStatus = "Starting full-day scan…"
            }.onFailure { autoScanStatus = "Could not start full-day scan. Open the app and try again." }
        }
    }
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startFullDayScan()
        else autoScanStatus = "Allow notifications to keep the full-day scan visible and easy to stop."
    }
    val requestFullDayScan: () -> Unit = {
        if (Build.VERSION.SDK_INT >= 33 &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else startFullDayScan()
    }
    val stopFullDayScan: () -> Unit = {
        context.stopService(Intent(context, PaperScanService::class.java))
        autoScanActive = false
        autoScanStatus = "Full-day paper scan stopped."
    }
    LaunchedEffect(Unit) {
        while (true) {
            autoScanActive = preferences.getBoolean(PaperScanService.PREF_ACTIVE, false)
            autoScanStatus = preferences.getString(PaperScanService.PREF_STATUS, autoScanStatus) ?: autoScanStatus
            val today = java.time.LocalDate.now(MarketSession.ZONE)
            val snapshot = withContext(Dispatchers.IO) {
                Triple(
                    database.latestScanReport(),
                    database.qualifiedStocks(today),
                    database.weeklyOutcomes(today.minusDays(6), today)
                )
            }
            val persistedReport = snapshot.first
            val persistedScanTime = persistedReport?.let {
                runCatching { java.time.ZonedDateTime.parse(it.scanTime).toInstant() }.getOrNull()
            }
            val snapshotAge = persistedScanTime?.let { java.time.Duration.between(it, java.time.Instant.now()).seconds }
            if (persistedReport != null && snapshotAge != null && snapshotAge in 0..900 &&
                persistedReport.rows.map { it.symbol }.toSet() == favourites.toSet()) report = persistedReport
            indexReport = withContext(Dispatchers.IO) { indexStore.read() }
            qualifiedToday = snapshot.second
            weeklyOutcomes = snapshot.third
            weeklySummary = PaperOutcomeLogic.summarize(snapshot.third, today.minusDays(6), today)
            delay(10_000)
        }
    }
    LaunchedEffect(Unit) {
        priceLifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                val now = java.time.Instant.now()
                val state = livePrices
                val instruments = stocks.filter { stock -> qualifiedToday.any { it.symbol == stock.symbol } && stock.symbol in favourites }
                val snapshot = withContext(Dispatchers.IO) {
                    instruments.mapNotNull { stock ->
                        LiveStochasticPreview.calculate(database.bars(stock.instrumentKey), state.quotes[stock.instrumentKey], now,
                            state.connected, state.markets[stock.instrumentKey.substringBefore('|')] == true)
                            ?.let { stock.symbol to it }
                    }.toMap() to database.paperTradeHistory()
                }
                liveStochastic = snapshot.first
                paperTrades = snapshot.second
                previewSampledAt = now
                delay(1000)
            }
        }
    }
    LaunchedEffect(report) {
        while (report != null) {
            val snapshot = java.time.ZonedDateTime.parse(report!!.scanTime).toInstant()
            val candleExpiry = report!!.rows.mapNotNull { it.candle?.timestamp?.plusSeconds(1800) }.minOrNull()
            val expiresAt = minOf(snapshot.plusSeconds(900), candleExpiry ?: snapshot.plusSeconds(900))
            if (java.time.Instant.now() >= expiresAt && !autoScanActive) {
                report = null
                scanStatus = "Previous snapshot expired. Run a new paper scan."
                scanProgress = ""
            }
            delay(10_000)
        }
    }

    if (showInstrumentSearch) {
        InstrumentSearchDialog(
            enabled = !scanning && !autoScanActive && !backupBusy && pendingBackup == null,
            activeCount = favourites.size,
            onSearch = { query, exchange, number ->
                val token = tokenStore.read()?.takeIf { it.isNotBlank() } ?: error("TOKEN_NOT_CONFIGURED")
                sharedFeed.searchInstruments(token, query, exchange, number)
            },
            onAdd = { instrument, age ->
                if (scanning || autoScanActive || backupBusy || pendingBackup != null) "Stop scans and backup operations before changing the list."
                else runCatching {
                    val saved = selectionStore.add(instrument, age)
                    stocks.clear(); stocks.addAll(saved.catalog)
                    favourites.clear(); favourites.addAll(saved.active.sorted())
                    report = null
                    customStockMessage = "${instrument.symbol} · ${instrument.exchange} added. ${saved.active.size} / 40 active."
                    customStockMessage
                }.getOrElse { it.message ?: "Could not save selection. Nothing was added." }
            },
            onDismiss = { showInstrumentSearch = false }
        )
    }

    var refreshingIndices by remember { mutableStateOf(false) }
    val refreshIndices: () -> Unit = {
        if (!refreshingIndices) {
            val saved = tokenStore.read()
            if (saved == null) { page = Page.SETTINGS }
            else {
                refreshingIndices = true
                scope.launch {
                    try { indexReport = withContext(Dispatchers.IO) { IndexRefresh.refresh(context,saved,true) } }
                    finally { refreshingIndices = false }
                }
            }
        }
    }
    val runScan = {
        val token = tokenStore.read()
        if (token == null) {
            scanStatus = "Set your Upstox access token in Settings before scanning."
            page = Page.SETTINGS
        } else if (!backupBusy && pendingBackup == null && !scanning && !autoScanActive && favourites.isNotEmpty() && favourites.size <= StockCatalog.MAX_ACTIVE) {
            scanning = true
            scanProgress = "Verifying exchange session calendars, then stock history…"
            scanStatus = "Fetching read-only 15-minute candles for ${favourites.size} selected instruments…"
            report = null
            val selectedFavourites = favourites.toSet()
            val activeStocks = stocks.toList()
            scanJob = scope.launch {
                try {
                    val result = withContext(Dispatchers.IO) {
                        scanner.scan(
                            token,
                            StockCatalog.active(activeStocks, selectedFavourites).map { it.symbol to it.instrumentKey },
                            selectedFavourites,
                            onProgress = { completed, total, symbol ->
                                withContext(Dispatchers.Main.immediate) {
                                    scanProgress = "Checked $completed / $total stocks · last: $symbol"
                                }
                            }
                        )
                    }
                    withContext(Dispatchers.IO) { database.recordScanReport(result) }
                    report = result
                    scanStatus = "Snapshot as of ${result.scanTime} · ${result.failedRequests} stock feed errors\n" +
                        result.rows.groupingBy { it.reason }.eachCount().entries.joinToString(" · ") { "${it.key}: ${it.value}" }
                    scanProgress = "Finished ${result.requestCount} of ${selectedFavourites.size} instruments."
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
                indexReport = indexReport,
                onRefreshIndices = refreshIndices,
                indexRefreshEnabled = tokenConfigured && !refreshingIndices,
                stockCount = favourites.size,
                favouriteCount = favourites.size,
                customStockCount = stocks.count { it.isCustom },
                scanStatus = scanStatus,
                report = report,
                scanning = scanning,
                scanProgress = scanProgress,
                autoScanActive = autoScanActive,
                autoScanStatus = autoScanStatus,
                qualifiedToday = qualifiedToday,
                catalog = stocks.toList(),
                livePrices = livePrices,
                liveStochastic = liveStochastic,
                paperTrades = paperTrades,
                previewSampledAt = previewSampledAt,
                onRefreshPrices = { LiveMarketHub.reconnect(); liveTokenRevision++ },
                pricesRefreshEnabled = tokenConfigured && priceKeys.isNotEmpty(),
                weeklySummary = weeklySummary,
                weeklyOutcomes = weeklyOutcomes,
                onStartFullDayScan = requestFullDayScan,
                onStopFullDayScan = stopFullDayScan,
                onRunScan = runScan,
                onCancelScan = { scanJob?.cancel() },
                modifier = Modifier.padding(inset)
            )
            Page.UNIVERSE -> {
                val bySymbol = report?.rows?.associateBy { it.symbol }.orEmpty()
                val qualifiedBySymbol = qualifiedToday.associateBy { it.symbol }
                Column(Modifier.fillMaxSize().padding(inset)) {
                    Card(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("My scan · ${favourites.size} / 40 active", fontWeight = FontWeight.SemiBold)
                            Button(onClick = { showInstrumentSearch = true },
                                enabled = !scanning && !autoScanActive && !backupBusy && pendingBackup == null) {
                                Text("Search company · NSE / BSE")
                            }
                            Text("Choose a company and exchange. Upstox supplies its instrument key automatically. Remove a selection to free a place when your list reaches 40.",
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
                    val filteredStocks = stocks.filter { !it.instrumentKey.contains("_INDEX|") && it.symbol.contains(search.trim(), ignoreCase = true) }
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
                    Text("${shown.size} stocks in catalogue · ${stocks.count { it.isCustom }} custom", Modifier.padding(horizontal = 16.dp))
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
                                        qualifiedBySymbol[stock.symbol]?.let { qualified ->
                                            Text("QUALIFIED TODAY · peak RVOL ${formatPrice(qualified.peakRelativeVolume)}×", style = MaterialTheme.typography.labelSmall)
                                        }
                                        Text(stock.instrumentKey, style = MaterialTheme.typography.labelSmall)
                                    }
                                    Column {
                                        TextButton(
                                            onClick = {
                                                runCatching { selectionStore.setActive(stock.symbol, !selected) }
                                                    .onSuccess { saved ->
                                                        stocks.clear(); stocks.addAll(saved.catalog)
                                                        favourites.clear(); favourites.addAll(saved.active.sorted())
                                                        report = null
                                                        customStockMessage = if (selected) "${stock.symbol} removed from scan. History kept." else "${stock.symbol} added to scan."
                                                    }.onFailure { customStockMessage = it.message ?: "Could not save selection." }
                                            },
                                            enabled = !scanning && !autoScanActive && !backupBusy && (selected || favourites.size < StockCatalog.MAX_ACTIVE)
                                        ) { Text(if (selected) "Remove from scan" else "Add to scan") }
                                        if (stock.isCustom) TextButton(onClick = {
                                            runCatching { selectionStore.deleteCustom(stock.symbol) }
                                                .onSuccess { saved ->
                                                    stocks.clear(); stocks.addAll(saved.catalog)
                                                    favourites.clear(); favourites.addAll(saved.active.sorted())
                                                    report = null
                                                    customStockMessage = "${stock.symbol} deleted from this phone's list. History kept."
                                                }.onFailure { customStockMessage = it.message ?: "Could not delete custom entry." }
                                        }, enabled = !scanning && !autoScanActive && !backupBusy) { Text("Delete custom") }
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
                        "My active instruments",
                        "Select up to 40 instruments in Instruments. Only these are scanned, with technical checks for every selection.",
                        Modifier.padding(inset)
                    )
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize().padding(inset),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        item {
                            Text("MY 40 · LIVE PRICES", fontWeight = FontWeight.Bold)
                            Text(livePrices.status, style = MaterialTheme.typography.bodySmall)
                            Button(onClick = { LiveMarketHub.reconnect(); liveTokenRevision++ }, enabled = tokenConfigured && priceKeys.isNotEmpty()) { Text("Refresh prices") }
                            Text("Prices stream while this app is open. Last-trade times show quote freshness. Paper signals use completed 15-minute candles.", style = MaterialTheme.typography.bodySmall)
                            Spacer(Modifier.height(12.dp))
                            Text("15-MINUTE PAPER SIGNALS", fontWeight = FontWeight.Bold)
                            Text("Volume qualifies stocks once for the day. BUY: qualified today and confirmed K above D, without an EMA filter. SELL after BUY: K is below D (including a missed crossover). Completed 15-minute candles only; K−D distance is context, not a filter. Indices keep their separate rules.", style = MaterialTheme.typography.bodySmall) }
                        items(selectedStocks, key = { it.symbol }) { stock ->
                            val row = bySymbol[stock.symbol]
                            Card(Modifier.fillMaxWidth()) {
                                Column(Modifier.padding(16.dp)) {
                                    Text(stock.symbol, fontWeight = FontWeight.Bold)
                                    LivePriceDisplay(stock, livePrices)
                                    Spacer(Modifier.height(6.dp))
                                    Text(paperSignalDisplay(row))
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
            Page.REVERSAL -> ReversalPage(reversalSnapshot,livePrices,Modifier.padding(inset))
            Page.COMMODITIES -> CommodityPage(commoditySnapshot,livePrices,Modifier.padding(inset))
            Page.SETTINGS -> SettingsPage(
                backupStatus = backupStatus,
                backupEnabled = !backupBusy && !scanning && !autoScanActive,
                onExportBackup = { exportBackup.launch("nse-paper-backup.json") },
                onImportBackup = { importBackup.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) },
                tokenConfigured = tokenConfigured,
                scanStatus = scanStatus,
                onSaveToken = { token ->
                    scanJob?.cancel()
                    context.stopService(Intent(context, PaperScanService::class.java))
                    autoScanActive = false
                    report = null
                    indexStore.clear(); indexReport = null
                    runCatching { tokenStore.save(token) }
                    tokenConfigured = tokenStore.read() != null
                    LiveMarketHub.reconnect(); liveTokenRevision++
                },
                onClearToken = {
                    scanJob?.cancel()
                    context.stopService(Intent(context, PaperScanService::class.java))
                    autoScanActive = false
                    report = null
                    indexStore.clear(); indexReport = null
                    tokenStore.clear()
                    LiveMarketHub.reconnect(); liveTokenRevision++
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
            "\nStoch RSI (14,14,3,3) K ${"%.2f".format(it.stochK)} · D ${"%.2f".format(it.stochD)}" + "\n" + stochasticGapDisplay(it)
    }.orEmpty()
    return "$time · $rvol · ${row.reason}$candle$technical"
}

@Composable
private fun Dashboard(
    indexReport: IndexMarketReport?,
    onRefreshIndices: () -> Unit,
    indexRefreshEnabled: Boolean,
    stockCount: Int,
    favouriteCount: Int,
    customStockCount: Int,
    scanStatus: String,
    report: ScanReport?,
    scanning: Boolean,
    scanProgress: String,
    autoScanActive: Boolean,
    autoScanStatus: String,
    qualifiedToday: List<QualifiedStock>,
    catalog: List<Stock>,
    livePrices: LivePriceState,
    liveStochastic: Map<String, LiveStochastic>,
    paperTrades: List<PaperTrade>,
    previewSampledAt: java.time.Instant,
    onRefreshPrices: () -> Unit,
    pricesRefreshEnabled: Boolean,
    weeklySummary: List<DailyPaperSummary>,
    weeklyOutcomes: List<PaperOutcome>,
    onStartFullDayScan: () -> Unit,
    onStopFullDayScan: () -> Unit,
    onRunScan: () -> Unit,
    onCancelScan: () -> Unit,
    modifier: Modifier = Modifier
) {
    val qualified = report?.rows?.count { (it.relativeVolume ?: 0.0) >= 1.5 } ?: 0
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        IndexOverview(indexReport, indexRefreshEnabled, onRefreshIndices, livePrices)
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
            Column(Modifier.padding(18.dp)) {
                Text("PAPER TRADING · NO ORDERS", fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text(if (scanning) "SCANNING · READ ONLY" else "15-MINUTE VOLUME-FIRST SCAN", style = MaterialTheme.typography.titleMedium)
                Text(scanStatus)
                if (scanProgress.isNotBlank()) Text(scanProgress, style = MaterialTheme.typography.bodySmall)
                Text(autoScanStatus, style = MaterialTheme.typography.bodySmall)
                Text("Full-day mode refreshes indices every 5 minutes and checks stocks on completed 15-minute candles. It keeps a stock in today's qualified list after it first reaches 1.5×.", style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(8.dp))
                if (autoScanActive) {
                    Button(onClick = onStopFullDayScan) { Text("Stop full-day scan") }
                } else {
                    Button(onClick = onStartFullDayScan, enabled = !scanning) { Text("Start full-day scan") }
                }
                Button(onClick = onRunScan, enabled = !scanning && !autoScanActive && stockCount in 1..StockCatalog.MAX_ACTIVE) {
                    Text(if (scanning) "Scanning…" else "Run one scan")
                }
                if (scanning) Button(onClick = onCancelScan) { Text("Cancel one scan") }
            }
        }
        InfoCard("Selected instrument scan", "$stockCount / 40 active instruments", "$customStockCount custom additions · $qualified stocks currently at or above 1.5× on the latest scan.")
        InfoCard("Favourites", "$favouriteCount / 40 selected", "Selected stocks use the volume-first rules. The three index cards above use separate price-based rules.")
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Qualified today · ${qualifiedToday.size}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text("A stock stays here after qualifying once during today's market session, even if its later RVOL falls.", style = MaterialTheme.typography.bodySmall)
                Text(livePrices.status, style = MaterialTheme.typography.bodySmall)
                Button(onClick = onRefreshPrices, enabled = pricesRefreshEnabled) { Text("Refresh prices") }
                Text("Prices update from the live stream; BUY/SELL checks use completed 15-minute candles.", style = MaterialTheme.typography.bodySmall)
                if (qualifiedToday.isEmpty()) Text("No stock has qualified in a verified scan today.", style = MaterialTheme.typography.bodySmall)
                qualifiedToday.forEach { stock ->
                    val row = report?.rows?.singleOrNull { it.symbol == stock.symbol }
                    Text(stock.symbol, fontWeight = FontWeight.Bold)
                    catalog.singleOrNull { it.symbol == stock.symbol }?.let { instrument -> LivePriceDisplay(instrument, livePrices) }
                    Text("Peak RVOL ${formatPrice(stock.peakRelativeVolume)}× · latest scan RVOL ${row?.relativeVolume?.let { "${formatPrice(it)}×" } ?: "unavailable"}")
                    Text(paperSignalDisplay(row), fontWeight = FontWeight.SemiBold)
                    val preview = liveStochastic[stock.symbol]
                    val instrument = catalog.singleOrNull { it.symbol == stock.symbol }
                    val quote = instrument?.let { livePrices.quotes[it.instrumentKey] }
                    val previewFresh = preview != null && quote != null && livePrices.connected &&
                        livePrices.markets[quote.instrumentKey.substringBefore('|')] == true &&
                        java.time.Duration.between(preview.sampledAt, java.time.Instant.now()).seconds in 0..20 &&
                        java.time.Duration.between(quote.tradedAt, java.time.Instant.now()).seconds in 0..30
                    if (previewFresh) {
                        Text("Live Stoch RSI · forming 15m candle · provisional", fontWeight = FontWeight.SemiBold)
                        Text("K ${formatPrice(preview!!.context.stochK)} / D ${formatPrice(preview.context.stochD)} · ${clockTime(preview.sampledAt)}", style = MaterialTheme.typography.bodySmall)
                        Text(stochasticGapDisplay(preview.context), style = MaterialTheme.typography.bodySmall)
                    } else Text("Live Stoch RSI unavailable · waiting for fresh quote / completed history", style = MaterialTheme.typography.bodySmall)
                    row?.technicals?.let {
                        Text("Confirmed 15m Stoch RSI K ${formatPrice(it.stochK)} / D ${formatPrice(it.stochD)} · candle ${row.candle?.timestamp?.plusSeconds(900)?.let(::clockTime) ?: "unavailable"}", style = MaterialTheme.typography.bodySmall)
                        Text(stochasticGapDisplay(it), style = MaterialTheme.typography.bodySmall)
                    }
                    PaperTradesTable(paperTrades.filter { it.symbol == stock.symbol }, quote?.price,
                        quote?.label(previewSampledAt, livePrices.connected, instrument?.let { livePrices.markets[it.instrumentKey.substringBefore('|')] } == true))
                    HorizontalDivider()
                }
            }
        }
        PaperTradesTable(paperTrades, null, null, allTrades = true)
        CompletedTradeSummary(paperTrades)
        Text("Legacy next-candle analysis · not BUY-to-SELL performance", fontWeight = FontWeight.Bold)
        PaperWeeklyChart(weeklySummary, weeklyOutcomes)
    }
}

@Composable
private fun PaperWeeklyChart(days: List<DailyPaperSummary>, outcomes: List<PaperOutcome>) {
    val tradeCount = outcomes.size
    val wins = outcomes.count { it.returnPercent > 0.0 }
    val average = outcomes.map { it.returnPercent }.average().takeIf { outcomes.isNotEmpty() } ?: 0.0
    val success = if (tradeCount == 0) 0.0 else wins * 100.0 / tradeCount
    val scale = days.maxOfOrNull { abs(it.averageReturnPercent) }?.coerceAtLeast(0.05) ?: 0.05
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Legacy next-candle outcome rate", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text("Saved favourites only · next 15-minute candle open-to-close · equal-weight mean return · gross before charges and slippage.", style = MaterialTheme.typography.bodySmall)
            Text("Last 7 days: ${if (average >= 0) "+" else ""}${formatPercent(average)}% average · ${formatPercent(success)}% success ($wins/$tradeCount closed)", style = MaterialTheme.typography.bodyMedium)
            if (tradeCount == 0) Text("No completed paper outcomes yet. No success rate is inferred from open or unverified signals.", style = MaterialTheme.typography.bodySmall)
            days.forEach { day ->
                Text(day.date.format(java.time.format.DateTimeFormatter.ofPattern("EEE dd", Locale.US)))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BoxWithConstraints(
                        Modifier.weight(1f).height(14.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp))
                    ) {
                        val fraction = (abs(day.averageReturnPercent) / scale).coerceIn(0.0, 1.0).toFloat() * 0.5f
                        val width = maxWidth * fraction
                        val barColor = if (day.averageReturnPercent >= 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                        Box(
                            Modifier.align(if (day.averageReturnPercent >= 0) Alignment.CenterStart else Alignment.CenterEnd)
                                .width(width).fillMaxHeight().background(barColor, RoundedCornerShape(8.dp))
                        )
                    }
                    Text("${if (day.averageReturnPercent > 0) "+" else ""}${formatPercent(day.averageReturnPercent)}%", style = MaterialTheme.typography.labelSmall)
                }
                Text("${day.closedSignals} closed · ${formatPercent(day.successPercent)}% success", style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun SettingsPage(
    backupStatus: String,
    backupEnabled: Boolean,
    onExportBackup: () -> Unit,
    onImportBackup: () -> Unit,
    tokenConfigured: Boolean,
    scanStatus: String,
    onSaveToken: (String) -> Unit,
    onClearToken: () -> Unit,
    modifier: Modifier = Modifier
) {
    var tokenInput by remember { mutableStateOf("") }
    val updateContext = LocalContext.current
    var diagnosticStatus by remember { mutableStateOf("") }
    val diagnosticScope = rememberCoroutineScope()
    val exportLog = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("text/plain")) { uri ->
        if (uri != null) diagnosticScope.launch {
            diagnosticStatus = try {
                withContext(Dispatchers.IO) {
                    val text = DiagnosticLog.export(updateContext)
                    val output = updateContext.contentResolver.openOutputStream(uri) ?: error("Could not open destination")
                    output.use { it.write(text.toByteArray(Charsets.UTF_8)) }
                }
                "Diagnostic log saved"
            } catch (_: Exception) { "Could not save file · use Copy diagnostic summary" }
        }
    }
    val updateScope = rememberCoroutineScope()
    val installedVersion = remember {
        runCatching {
            @Suppress("DEPRECATION")
            val info = updateContext.packageManager.getPackageInfo(updateContext.packageName, 0)
            info.versionName ?: "Unavailable"
        }.getOrDefault("Unavailable")
    }
    var updating by remember { mutableStateOf(false) }
    var updateStatus by remember { mutableStateOf("Updates require a privately signed release. Existing app data is preserved.") }
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("App version: $installedVersion", style = MaterialTheme.typography.titleMedium)
        Text("App updates", style = MaterialTheme.typography.titleMedium)
        Button(enabled = !updating && backupEnabled, onClick = {
            updating = true
            updateStatus = "Checking and verifying update…"
            updateScope.launch {
                try {
                    val installer = withContext(Dispatchers.IO) { ApkUpdates(updateContext).prepare() }
                    updateContext.startActivity(installer)
                    updateStatus = "Follow Android's installation prompt. If installation is not allowed, enable it for this app and retry."
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (error: Exception) {
                    updateStatus = error.message?.takeIf { it.length < 180 } ?: "Update unavailable; existing app is unchanged."
                } finally { updating = false }
            }
        }) { Text(if (updating) "Checking update…" else "Download verified update") }
        Text(updateStatus, style = MaterialTheme.typography.bodySmall)
        Text("Diagnostics", style = MaterialTheme.typography.titleMedium)
        Button(onClick = { exportLog.launch("nse-diagnostic-log.txt") }) { Text("Export diagnostic log") }
        Button(onClick = {
            diagnosticScope.launch {
                val text = withContext(Dispatchers.IO) { DiagnosticLog.export(updateContext) }
                val clipboard = updateContext.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                clipboard.setPrimaryClip(android.content.ClipData.newPlainText("NSE diagnostics",text.takeLast(60000)))
                diagnosticStatus = "Diagnostic summary copied"
            }
        }) { Text("Copy diagnostic summary") }
        Text(diagnosticStatus)
        Text("Latest 7 days, size limited · excludes tokens and authorization headers", style=MaterialTheme.typography.bodySmall)
        Text("Local backup & restore", style = MaterialTheme.typography.titleMedium)
        Text("Stop manual and full-day scans first. Export favourites, custom stocks, and paper history to a file you keep. Tokens and candle cache are excluded. This app cannot read another installed app's private data.")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(enabled = backupEnabled, onClick = onExportBackup) { Text("Export backup") }
            Button(enabled = backupEnabled, onClick = onImportBackup) { Text("Restore backup") }
        }
        Text(backupStatus)
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
