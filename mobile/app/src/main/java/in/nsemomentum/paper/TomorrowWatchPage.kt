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
                    is IllegalArgumentException -> error.message ?: "Check the session date."
                    is java.time.format.DateTimeParseException -> "Use YYYY-MM-DD for the session date."
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
            OutlinedTextField(date, { date = it }, label = { Text("NSE session date (YYYY-MM-DD)") },
                enabled = !busy, singleLine = true, modifier = Modifier.fillMaxWidth())
        }
        item {
            Text("Uses Upstox daily volume at 1.5× the previous 20-session average.")
            Button(enabled = !busy && !token.isNullOrBlank() && stocks.isNotEmpty(), onClick = {
                val sourceDate = date.trim()
                run("Checking completed daily candles…") { credential ->
                    engine.prepare(credential, stocks, LocalDate.parse(sourceDate), Instant.now()) { checked ->
                        if (checked % 10 == 0) withContext(Dispatchers.Main) {
                            status = "Checked $checked of ${stocks.size} stocks"
                        }
                    }
                }
            }) { Text("Build after close") }
            if (token.isNullOrBlank()) Text("Save your Upstox token in Settings.")
            if (status.isNotBlank()) Text(status)
        }
        watch?.let { saved ->
            item {
                Text("Session ${saved.target} · Prepared from ${saved.source}", style = MaterialTheme.typography.titleMedium)
                Text("BUY ${saved.rows.count { it.side == WatchSide.BUY }} · SELL ${saved.rows.count { it.side == WatchSide.SELL }} · SKIP ${saved.skipped}")
                if (saved.missing > 0) Text("${saved.missing} stocks waiting for daily data. Rebuild to retry.")
                if (!saved.upstoxVolume) Text("Saved from the previous manual list. Rebuild to use Upstox volume.")
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
                    row.dailyRelativeVolume?.let { ratio ->
                        val formatted = String.format(java.util.Locale.US, "%.2f", ratio)
                        val comparison = if (row.side == WatchSide.BUY) "above the previous high" else "below the previous low"
                        Text("Closed $comparison with ${formatted}× average daily volume.")
                    }
                    Text(row.result.ifBlank { "Waiting for next session" })
                }
            }
        }
    }
}
