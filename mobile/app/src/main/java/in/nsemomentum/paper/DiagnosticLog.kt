package com.nsemomentum.paper

import android.content.Context
import java.time.Instant
import java.time.LocalDate

/** Only caller-supplied event codes and numeric metadata; never exception messages or request bodies. */
object DiagnosticLog {
    @Volatile private var app: Context? = null
    fun initialize(context: Context) { app = context.applicationContext }
    fun event(event: String, result: String, numbers: String = "", symbol: String? = null) { app?.let { record(it,event,result,numbers,symbol) } }
    fun errorCode(error: Throwable): String = error.message?.takeIf { it in setOf("NETWORK_ERROR","RATE_LIMITED","LOCAL_RATE_BUDGET_EXHAUSTED","UPSTOX_AUTH_REQUIRED","MARKET_CLOSED","NO_COMPLETED_MARKET_CANDLE","MISSING_COMPLETED_INDEX_CANDLE","INVALID_INDEX_CANDLE","UNVERIFIED_MARKET_CALENDAR","UNSUPPORTED_SPECIAL_SESSION","NO_COMMODITY_CONTRACT","UNVERIFIED_COMMODITY_SESSION","NO_COMPLETED_COMMODITY_CANDLE","MISSING_COMMODITY_CANDLE","INVALID_COMMODITY_CANDLE","INVALID_RESPONSE","UPSTOX_SERVER_ERROR") || it.matches(Regex("UPSTOX_HTTP_[0-9]{3}")) } ?: "REQUEST_FAILED"
    @Synchronized fun record(context: Context, event: String, result: String, numbers: String = "", symbol: String? = null) {
        runCatching {
            val dir = java.io.File(context.filesDir,"diagnostics").apply { mkdirs() }
            val today = LocalDate.now(MarketSession.ZONE)
            dir.listFiles()?.forEach { file ->
                val date = runCatching { LocalDate.parse(file.nameWithoutExtension) }.getOrNull()
                if (date == null || date < today.minusDays(6)) file.delete()
            }
            val file = java.io.File(dir,"$today.log")
            if (file.length() > 256_000) return
            val safeEvent = event.takeIf { it.matches(Regex("[A-Z_]{1,40}")) } ?: "EVENT"
            val safeResult = result.takeIf { it.matches(Regex("[A-Z0-9_]{1,70}")) } ?: "STATUS"
            val safeNumbers = numbers.takeIf { it.matches(Regex("[a-z0-9= .,:%+−-]{0,160}")) } ?: ""
            val safeSymbol = symbol?.takeIf { it.matches(Regex("[A-Z0-9&.\\-]{1,30}")) }?.let { " symbol=$it" } ?: ""
            file.appendText("${Instant.now()} $safeEvent $safeResult $safeNumbers$safeSymbol\n")
        }
    }
    @Synchronized fun export(context: Context): String {
        val files = java.io.File(context.filesDir,"diagnostics").listFiles().orEmpty().sortedBy { it.name }
        return "NSE Momentum diagnostic log · timestamps UTC · excludes credentials\n" + files.joinToString("\n") { it.readText().take(256_000) }
    }
}
