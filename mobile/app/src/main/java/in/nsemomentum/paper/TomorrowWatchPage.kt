package com.nsemomentum.paper

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.LocalDate
import java.util.Locale
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
internal fun TomorrowWatchPage(stocks: List<Stock>, token: String?, feed: CandleFeed, modifier: Modifier) {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences("tomorrow_watch", 0) }
    var watch by remember { mutableStateOf(SavedWatch.decode(prefs.getString("saved_watch", null))) }
    var date by remember { mutableStateOf(LocalDate.now(MarketSession.ZONE).toString()) }
    var symbols by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val engine = remember(feed) { TomorrowWatch(feed) }

    fun run(message: String, action: suspend (String) -> SavedWatch) {
        val credential = token ?: return
        busy = true
        status = message
        scope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    action(credential).also { check(prefs.edit().putString("saved_watch", it.encode()).commit()) }
                }
                watch = result
                status = "Watchlist saved"
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                status = when (error) {
                    is IllegalArgumentException -> error.message ?: "Check the date and StockEdge symbols."
                    is java.time.format.DateTimeParseException -> "Use YYYY-MM-DD for the StockEdge date."
                    else -> when (error.message) {
                        "UPSTOX_AUTH_REQUIRED" -> "Update your Upstox token in Settings."
                        "LOCAL_RATE_BUDGET_EXHAUSTED", "RATE_LIMITED" -> "Request limit reached. Try again later."
                        else -> "Could not verify all required data. The saved watchlist is still available."
                    }
                }
            } finally {
                busy = false
            }
        }
    }

    LazyColumn(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text("Tomorrow Watchlist", style = MaterialTheme.typography.headlineSmall)
            Text("Nifty 200 · Paper validation")
        }
        item {
            OutlinedTextField(date, { date = it }, label = { Text("StockEdge session date (YYYY-MM-DD)") },
                enabled = !busy, singleLine = true, modifier = Modifier.fillMaxWidth())
        }
        item {
            OutlinedTextField(symbols, { symbols = it }, label = { Text("StockEdge unusual-volume symbols") },
                placeholder = { Text("Paste the complete list, one symbol per line or comma separated") },
                enabled = !busy, modifier = Modifier.fillMaxWidth())
        }
        item {
            Button(enabled = !busy && !token.isNullOrBlank() && stocks.isNotEmpty(), onClick = {
                val sourceDate = date.trim()
                val flags = symbols.uppercase(Locale.ROOT).split(Regex("[,\\s]+")).filter(String::isNotEmpty).toSet()
                run("Checking completed daily candles…") { credential ->
                    require(flags.isNotEmpty()) { "Enter the StockEdge symbols, or NONE if the list is empty." }
                    engine.prepare(credential, stocks, LocalDate.parse(sourceDate),
                        if (flags == setOf("NONE")) emptySet() else flags, Instant.now())
                }
            }) { Text("Build after close") }
            if (token.isNullOrBlank()) Text("Save your Upstox token in Settings.")
        }
        watch?.let { saved ->
            item {
                Text("Session ${saved.target} · Prepared from ${saved.source}", style = MaterialTheme.typography.titleMedium)
                Text("BUY ${saved.rows.count { it.side == WatchSide.BUY }} · SELL ${saved.rows.count { it.side == WatchSide.SELL }} · SKIP ${saved.skipped}")
                Button(enabled = !busy && !token.isNullOrBlank() && saved.rows.isNotEmpty(), onClick = {
                    run("Checking completed five-minute candles…") { credential ->
                        engine.validate(credential, saved, stocks, Instant.now())
                    }
                }) { Text("Check next-session signals") }
                Text("First check at 09:35 IST. VWAP is estimated from five-minute candles.")
            }
            items(saved.rows.sortedWith(compareBy({ it.side }, { it.symbol })), key = { it.symbol }) { row ->
                Column {
                    Text("${row.side} watch · ${row.symbol}", style = MaterialTheme.typography.titleSmall)
                    Text("Close ₹${row.close} · Previous range ₹${row.previousLow}–₹${row.previousHigh}")
                    Text(row.result.ifBlank { "Waiting for next session" })
                }
            }
        }
        if (status.isNotBlank()) item { Text(status) }
    }
}
