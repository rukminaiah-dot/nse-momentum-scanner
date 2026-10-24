package com.nsemomentum.paper

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout

/** Explicit searches only; no request on each keystroke and no cached result silently becomes a selection. */
@Composable
fun InstrumentSearchDialog(
    enabled: Boolean,
    activeCount: Int,
    onSearch: suspend (String, String, Int) -> InstrumentSearchPage,
    onAdd: (SearchInstrument, Long) -> String,
    onDismiss: () -> Unit
) {
    var query by remember { mutableStateOf("") }
    var exchange by remember { mutableStateOf("NSE") }
    var page by remember { mutableStateOf<InstrumentSearchPage?>(null) }
    var fetchedNanos by remember { mutableStateOf(0L) }
    var loading by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Choose an exchange and search by company name or symbol.") }
    val scope = rememberCoroutineScope()
    var job by remember { mutableStateOf<Job?>(null) }
    val search: (Int) -> Unit = { number ->
        if (!loading && enabled) {
            page = null
            loading = true
            job = scope.launch {
                try {
                    val normalized = InstrumentSearchRules.query(query)
                    val result = withTimeout(45_000) { onSearch(normalized, exchange, number) }
                    page = result.copy(instruments = result.instruments.filterNot { it.isIndex })
                    fetchedNanos = System.nanoTime()
                    status = if (result.instruments.none { !it.isIndex }) "No supported instruments on this page. Try a more specific name or the next page."
                        else "Select the company and exchange below. $activeCount / 20 active."
                } catch (_: TimeoutCancellationException) { status = "Search timed out. Saved instruments are unchanged; retry." }
                catch (cancelled: CancellationException) { status = "Search cancelled."; throw cancelled }
                catch (error: Exception) {
                    status = when (error.message) {
                        "UPSTOX_AUTH_REQUIRED" -> "Upstox requires a valid token. Update it in Settings only."
                        "RATE_LIMITED", "LOCAL_RATE_BUDGET_EXHAUSTED" -> "Search rate limit reached. Wait before retrying."
                        "NETWORK_ERROR", "UPSTOX_SERVER_ERROR" -> "Upstox is temporarily unavailable. Saved instruments are unchanged."
                        "INVALID_INSTRUMENT_SEARCH_RESPONSE" -> "Upstox returned an inconsistent instrument mapping. Nothing was added."
                        "TOKEN_NOT_CONFIGURED" -> "Save your Upstox token in app Settings before searching."
                        else -> if (error is IllegalArgumentException) "Enter 2–50 characters of a company name or symbol." else "Search unavailable. Nothing was added; retry later."
                    }
                } finally { loading = false }
            }
        }
    }
    AlertDialog(
        onDismissRequest = { job?.cancel(); onDismiss() },
        title = { Text("Find an NSE / BSE instrument") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(query, onValueChange = { query = it; page = null }, enabled = !loading && enabled,
                    label = { Text("Company name or symbol") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("NSE", "BSE").forEach { item ->
                        FilterChip(selected = exchange == item, onClick = { exchange = item; page = null },
                            enabled = !loading && enabled, label = { Text(item) })
                    }
                    Button(onClick = { search(1) }, enabled = !loading && enabled && query.trim().length in 2..50) { Text("Search") }
                }
                Text(status, style = MaterialTheme.typography.bodySmall)
                if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
                page?.let { result ->
                    LazyColumn(Modifier.fillMaxWidth().heightIn(max = 240.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        items(result.instruments, key = { it.instrumentKey }) { instrument ->
                            Column {
                                Text("${instrument.symbol} · ${instrument.exchange}", style = MaterialTheme.typography.titleSmall)
                                Text(instrument.name, style = MaterialTheme.typography.bodySmall)
                                TextButton(enabled = enabled && !loading, onClick = {
                                    val age = (System.nanoTime() - fetchedNanos) / 1_000_000_000
                                    status = onAdd(instrument, age)
                                }) { Text("Add to my scan") }
                                HorizontalDivider()
                            }
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { search(result.number - 1) }, enabled = !loading && enabled && result.number > 1) { Text("Previous") }
                        Text("Page ${result.number} / ${maxOf(result.totalPages, 1)}", style = MaterialTheme.typography.bodySmall)
                        TextButton(onClick = { search(result.number + 1) }, enabled = !loading && enabled && result.number < result.totalPages) { Text("Next") }
                    }
                }
                Text("Read-only lookup. Adding an instrument does not place an order or confirm candle coverage.", style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = { TextButton(onClick = { job?.cancel(); onDismiss() }) { Text("Close") } }
    )
}
