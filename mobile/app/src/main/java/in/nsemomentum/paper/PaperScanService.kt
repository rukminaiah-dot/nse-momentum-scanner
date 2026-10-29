package com.nsemomentum.paper

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import org.json.JSONArray
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.io.IOException
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId

class PaperScanService : Service() {
    private val zone = ZoneId.of("Asia/Kolkata")
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var scanJob: Job? = null
    private val preferences by lazy { getSharedPreferences("paper_preferences", Context.MODE_PRIVATE) }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        DiagnosticLog.initialize(this)
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            scanJob?.cancel()
            markStopped("Full-day paper scan stopped.")
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf(startId)
            return START_NOT_STICKY
        }
        if (scanJob?.isActive == true) return START_STICKY
        preferences.edit().putBoolean(PREF_ACTIVE, true)
            .putString(PREF_STATUS, "Full-day scan started; waiting for completed 15-minute candles.")
            .apply()
        showForeground("Starting read-only 15-minute scan…")
        scanJob = serviceScope.launch { runMarketDay(startId) }
        return START_STICKY
    }

    private suspend fun runMarketDay(startId: Int) = kotlinx.coroutines.coroutineScope {
        val database = CandleDatabase(applicationContext)
        val token = SecureTokenStore(applicationContext).read()
        if (token.isNullOrBlank()) { markStopped("Save your Upstox token first."); database.close(); stopSelf(startId); return@coroutineScope }
        val indexJob = launch {
            while (true) { IndexRefresh.refresh(applicationContext, token); delay(10_000) }
        }
        try {
            val scanner = UpstoxPaperScanner(database)
            var lastRequest: String? = null
            var retryRequest: String? = null
            val successful = mutableMapOf<String,ScanRow>()
            var retryDelay = 10_000L
            while (true) {
                val now = Instant.now()
                if (now.atZone(zone).toLocalTime() > LocalTime.of(15,33)) break
                val universe = readUniverse()
                if (universe.size > StockCatalog.MAX_ACTIVE) { markStopped("Selection exceeds 40"); break }
                LiveMarketHub.acquire("service", token, (universe.map { it.second } + StockCatalog.indices.map { it.instrumentKey }).toSet())
                val selected = preferences.getStringSet("favourites", emptySet()).orEmpty()
                val request = "${now.epochSecond / 900}:${universe.sortedBy { it.first }}:${selected.sorted()}"
                if (universe.isNotEmpty() && request != lastRequest) {
                    try {
                        DiagnosticLog.record(applicationContext,"STOCK_SCAN","START")
                        val started = Instant.now()
                        if (retryRequest != request) { successful.clear(); retryRequest = request; retryDelay = 10_000L }
                        val pending = universe.filter { it.first !in successful }
                        val attempt = scanner.scan(token, pending, selected)
                        attempt.rows.filter { it.candle != null }.forEach { successful[it.symbol] = it }
                        val rows = (successful.values + attempt.rows.filter { it.candle == null }).sortedBy { it.symbol }
                        val report = attempt.copy(rows=rows)
                        database.recordScanReport(report)
                        val complete = report.rows.size == universe.size && report.rows.all { it.candle != null }
                        if (complete) lastRequest = request
                        val status = "Stocks checked ${report.rows.count { it.candle != null }}/${universe.size} · ${if (complete) "waiting for next 15m close" else "retrying missing data"}"
                        preferences.edit().putString(PREF_STATUS,status).apply(); showForeground(status)
                        DiagnosticLog.record(applicationContext,"STOCK_SCAN",if (complete) "SUCCESS" else "PARTIAL",
                            "seconds=${Duration.between(started,Instant.now()).seconds} rows=${report.rows.count { it.candle != null }}")
                        if (!complete) { delay(retryDelay); retryDelay = (retryDelay * 2).coerceAtMost(60_000L) }
                    } catch (error: TimeoutCancellationException) {
                        DiagnosticLog.record(applicationContext,"STOCK_SCAN","TIMEOUT")
                        preferences.edit().putString(PREF_STATUS,"Stock scan timeout · retrying; live prices and indices independent").apply()
                    } catch (cancelled: CancellationException) { throw cancelled }
                    catch (error: Exception) {
                        val code = DiagnosticLog.errorCode(error)
                        DiagnosticLog.record(applicationContext,"STOCK_SCAN",code)
                        preferences.edit().putString(PREF_STATUS,"$code · retry pending").apply()
                        if (code in setOf("MARKET_CLOSED","UPSTOX_AUTH_REQUIRED")) break
                        delay(if (code in setOf("RATE_LIMITED","LOCAL_RATE_BUDGET_EXHAUSTED")) 60_000 else 10_000)
                    }
                }
                delay(10_000)
            }
        } finally {
            indexJob.cancel(); LiveMarketHub.release("service"); database.close()
            markStopped("Full-day scan stopped · check diagnostic log for details"); stopSelf(startId)
        }
    }

    private fun readUniverse(): List<Pair<String, String>> = runCatching {
        val json = assets.open("nse200.json").bufferedReader().use { it.readText() }
        val rows = JSONArray(json)
        val base = (0 until rows.length()).map { index ->
            val row = rows.getJSONObject(index)
            Stock(row.getString("symbol"), row.getString("instrumentKey"))
        }
        val catalog = base + StockCatalog.indices
        val customs = StockCatalog.decodeCustom(preferences.getString("custom_stocks", null), catalog)
        StockCatalog.active(catalog + customs, StockCatalog.stockSelections(preferences.getStringSet("favourites", emptySet()).orEmpty()))
            .map { it.symbol to it.instrumentKey }
    }.getOrDefault(emptyList())

    private fun nextBoundary(after: Instant): Instant? {
        val date = after.atZone(zone).toLocalDate()
        return (0..74).asSequence()
            .map { index ->
                date.atTime(LocalTime.of(9, 20)).plusMinutes(index * 5L).atZone(zone).toInstant().plusSeconds(20)
            }
            .firstOrNull { it.isAfter(after) && it.atZone(zone).toLocalTime() <= LocalTime.of(15, 30).plusSeconds(20) }
    }

    private fun showForeground(text: String) {
        val notification = buildNotification(text)
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun buildNotification(text: String): Notification {
        val openApp = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val stop = PendingIntent.getService(
            this, 1, Intent(this, PaperScanService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return if (Build.VERSION.SDK_INT >= 26) {
            Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_menu_search)
                .setContentTitle("NSE Momentum · Paper scan")
                .setContentText(text)
                .setContentIntent(openApp)
                .setOngoing(true)
                .addAction(Notification.Action.Builder(null, "Stop", stop).build())
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setSmallIcon(android.R.drawable.ic_menu_search)
                .setContentTitle("NSE Momentum · Paper scan")
                .setContentText(text)
                .setContentIntent(openApp)
                .setOngoing(true)
                .addAction(android.R.drawable.ic_media_pause, "Stop", stop)
                .build()
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Paper market scan", NotificationManager.IMPORTANCE_LOW))
        }
    }

    private fun markStopped(status: String) {
        preferences.edit().putBoolean(PREF_ACTIVE, false).putString(PREF_STATUS, status).apply()
    }

    override fun onDestroy() {
        preferences.edit().putBoolean(PREF_ACTIVE, false).apply()
        scanJob?.cancel()
        serviceScope.cancel()
        super.onDestroy()
    }

    companion object {
        const val ACTION_START = "com.nsemomentum.paper.START_PAPER_SCAN"
        const val ACTION_STOP = "com.nsemomentum.paper.STOP_PAPER_SCAN"
        const val PREF_ACTIVE = "paper_scan_active"
        const val PREF_STATUS = "paper_scan_status"
        const val CHANNEL_ID = "paper_scan"
        const val NOTIFICATION_ID = 1501
    }
}
