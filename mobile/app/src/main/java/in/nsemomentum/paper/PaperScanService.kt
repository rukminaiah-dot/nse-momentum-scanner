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

    private suspend fun runMarketDay(startId: Int) {
        val database = CandleDatabase(applicationContext)
        val token = SecureTokenStore(applicationContext).read()
        if (token.isNullOrBlank()) {
            markStopped("Add an Upstox token in Settings before starting the paper scan.")
            stopSelf(startId)
            return
        }
        val scanner = UpstoxPaperScanner(database)
        while (true) {
            val universe = readUniverse()
            if (universe.size < 200) {
                markStopped("NSE 200 stock list did not load; scan was stopped.")
                stopSelf(startId)
                return
            }
            val selected = preferences.getStringSet("favourites", emptySet()).orEmpty()
            val now = Instant.now()
            if (now.atZone(zone).toLocalTime() > LocalTime.of(15, 33)) {
                markStopped("Market session scan finished.")
                stopSelf(startId)
                return
            }
            try {
                preferences.edit().putString(PREF_STATUS, "Scanning completed 15-minute NSE candles…").apply()
                showForeground("Checking completed 15-minute NSE candles…")
                val report = scanner.scan(token, universe, selected)
                database.recordScanReport(report)
                val qualified = database.qualifiedStocks(report.scanTime.let {
                    java.time.ZonedDateTime.parse(it).toLocalDate()
                }).size
                val lastTime = report.rows.firstNotNullOfOrNull { it.candleTime } ?: "no verified candle"
                showForeground("Scan saved · $qualified qualified today · $lastTime")
                preferences.edit().putString(PREF_STATUS, "Last scan: $lastTime · $qualified stocks qualified today · ${report.failedRequests} feed errors").apply()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: IOException) {
                when (error.message) {
                    "MARKET_CLOSED" -> {
                        markStopped("NSE session is closed. The scan has stopped.")
                        stopSelf(startId)
                        return
                    }
                    "UPSTOX_AUTH_REQUIRED" -> {
                        markStopped("Upstox rejected the token. Update it in Settings.")
                        stopSelf(startId)
                        return
                    }
                    "NO_COMPLETED_MARKET_CANDLE" -> showForeground("Waiting for the next completed 15-minute candle…")
                    "RATE_LIMITED", "LOCAL_RATE_BUDGET_EXHAUSTED" ->
                        showForeground("Rate limit reached · will retry at the next 15-minute candle.")
                    else -> showForeground("Temporary scan error · retrying at the next 15-minute candle.")
                }
                preferences.edit().putString(PREF_STATUS, error.message ?: "Temporary scan error").apply()
            } catch (_: Exception) {
                showForeground("Temporary scan error · retrying at the next 15-minute candle.")
                preferences.edit().putString(PREF_STATUS, "Temporary scan error · next candle retry").apply()
            }
            val next = nextBoundary(Instant.now())
            if (next == null) {
                markStopped("Market session scan finished.")
                stopSelf(startId)
                return
            }
            delay(Duration.between(Instant.now(), next).toMillis().coerceAtLeast(1_000L))
        }
    }

    private fun readUniverse(): List<Pair<String, String>> = runCatching {
        val json = assets.open("nse200.json").bufferedReader().use { it.readText() }
        val rows = JSONArray(json)
        val base = (0 until rows.length()).map { index ->
            val row = rows.getJSONObject(index)
            Stock(row.getString("symbol"), row.getString("instrumentKey"))
        }
        val customs = StockCatalog.decodeCustom(preferences.getString("custom_stocks", null), base)
        (base + customs).map { it.symbol to it.instrumentKey }
    }.getOrDefault(emptyList())

    private fun nextBoundary(after: Instant): Instant? {
        val date = after.atZone(zone).toLocalDate()
        return (0..24).asSequence()
            .map { index ->
                date.atTime(LocalTime.of(9, 30)).plusMinutes(index * 15L).atZone(zone).toInstant().plusSeconds(20)
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
