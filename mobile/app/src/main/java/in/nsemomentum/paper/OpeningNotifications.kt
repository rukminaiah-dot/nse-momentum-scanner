package com.nsemomentum.paper

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.widget.RemoteViews
import androidx.core.app.NotificationCompat
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Plain display model, shared by the compact and expanded notification. */
data class OpeningNotice(val title:String,val price:String,val change:String,val metrics:String,val context:String,
    val footer:String,val changePositive:Boolean)
object OpeningNoticeFormatter {
    private val clock=DateTimeFormatter.ofPattern("HH:mm:ss 'IST'",Locale.ENGLISH).withZone(MarketSession.ZONE)
    fun quantity(context:Context):Int=context.getSharedPreferences("opening_notification_settings",0).getInt("quantity",1).takeIf { it in 1..1000000 } ?: 1
    fun price(value:Double?):String=if(value!=null && value.isFinite() && value>0) "₹%,.2f".format(Locale.ENGLISH,value) else "Unavailable"
    private fun metric(value:Double?):String=if(value!=null && value.isFinite()) "%.2f".format(Locale.ENGLISH,value) else "—"
    fun create(row: ReversalRow, quote: LiveQuote?): OpeningNotice? {
        val state = row.opening
        val boughtAt = state.buyAt ?: return null
        val buy = state.buy ?: return null
        val sample = row.openingSample
        val ratio = row.candleVolume?.ratio
        val change = quote?.changePercent
        return OpeningNotice(
            "${row.stock.symbol}  •  BUY  •  PAPER", price(buy),
            change?.let { "%+.2f%% today".format(Locale.ENGLISH,it) } ?: "Day change unavailable",
            "K ${metric(sample?.k)}    D ${metric(sample?.d)}    VOL 15m ${if (ratio == null) "—" else metric(ratio)+"×"}",
            "Qty ${state.quantity} · ${price(buy * state.quantity)}",
            "Recorded ${clock.format(boughtAt)} · automatic paper BUY",
            change != null && change >= 0
        )
    }
}

object OpeningNotifications {
    const val CHANNEL="paper-trade-actions"
    private const val ID=3101
    private fun allowed(context:Context)=Build.VERSION.SDK_INT<33 || context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED
    private fun manager(context:Context)=context.getSystemService(NotificationManager::class.java)
    private fun channel(context:Context) {
        manager(context).createNotificationChannel(NotificationChannel(CHANNEL,"Paper Opening trade alerts",NotificationManager.IMPORTANCE_HIGH).apply {
            description="Notifications for recorded Opening paper trades"
            enableVibration(true);lockscreenVisibility=android.app.Notification.VISIBILITY_PUBLIC
        })
    }

    fun postBuy(context: Context, row: ReversalRow, quote: LiveQuote?) {
        if (!allowed(context)) return
        val notice = OpeningNoticeFormatter.create(row, quote) ?: return
        val key = row.stock.instrumentKey
        runCatching {
            channel(context)
            val intent=PendingIntent.getActivity(context,0,Intent(context,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val expanded=RemoteViews(context.packageName,R.layout.notification_paper_expanded).apply {
                setTextViewText(R.id.signal_title,notice.title);setTextColor(R.id.signal_title,Color.parseColor("#57E3B2"))
                setTextViewText(R.id.signal_price,notice.price);setTextViewText(R.id.signal_change,notice.change)
                setTextColor(R.id.signal_change,Color.parseColor(if(notice.changePositive) "#57E3B2" else "#FFB1AA"))
                setTextViewText(R.id.signal_metrics,notice.metrics);setTextViewText(R.id.signal_context,notice.context)
                setTextViewText(R.id.signal_reason,"Opening K/D · positive open");setTextViewText(R.id.signal_expiry,notice.footer)
            }
            val compact=RemoteViews(context.packageName,R.layout.notification_paper_compact).apply {
                setTextViewText(R.id.compact_title,notice.title);setTextColor(R.id.compact_title,Color.parseColor("#57E3B2"))
                setTextViewText(R.id.compact_price,notice.price);setTextViewText(R.id.compact_detail,notice.change)
            }
            val builder=NotificationCompat.Builder(context,CHANNEL).setSmallIcon(R.drawable.ic_paper_signal)
                .setColor(Color.parseColor("#09866A"))
                .setContentTitle(notice.title).setContentText("${notice.price} · ${notice.change}")
                .setCustomContentView(compact).setCustomBigContentView(expanded)
                .setStyle(NotificationCompat.DecoratedCustomViewStyle()).setContentIntent(intent)
                .setPriority(NotificationCompat.PRIORITY_HIGH).setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setAutoCancel(true).setTimeoutAfter(60_000)
            manager(context).notify(key,ID,builder.build())
        }.onFailure { DiagnosticLog.event("OPENING_NOTIFICATION","DISPLAY_FAILED",symbol=row.stock.symbol) }
    }
}
