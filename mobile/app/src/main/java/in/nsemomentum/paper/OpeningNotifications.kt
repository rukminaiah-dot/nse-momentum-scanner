package com.nsemomentum.paper

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.widget.RemoteViews
import androidx.core.app.NotificationCompat
import java.time.Duration
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Plain display model, shared by the compact and expanded notification. */
data class OpeningNotice(val title:String,val price:String,val change:String,val metrics:String,val context:String,
    val reason:String,val footer:String,val quantity:Int,val sell:Boolean,val changePositive:Boolean,val remainingMillis:Long)
object OpeningNoticeFormatter {
    private val clock=DateTimeFormatter.ofPattern("HH:mm:ss 'IST'",Locale.ENGLISH).withZone(MarketSession.ZONE)
    fun quantity(context:Context):Int=context.getSharedPreferences("opening_notification_settings",0).getInt("quantity",1).takeIf { it in 1..1000000 } ?: 1
    fun price(value:Double?):String=if(value!=null && value.isFinite() && value>0) "₹%,.2f".format(Locale.ENGLISH,value) else "Unavailable"
    private fun metric(value:Double?):String=if(value!=null && value.isFinite()) "%.2f".format(Locale.ENGLISH,value) else "—"
    fun create(row:ReversalRow,quote:LiveQuote?,now:Instant,preset:Int):OpeningNotice? {
        val state=row.opening;val at=state.alertAt ?: return null
        val reason=state.alert ?: return null
        val remaining=Duration.between(now,at.plusSeconds(60)).toMillis()
        if(remaining !in 1..60000) return null
        val sell=state.buy!=null
        val quantity=if(sell) state.quantity else preset.takeIf { it in 1..1000000 } ?: 1
        val sample=row.openingSample
        val ratio=row.candleVolume?.ratio
        val change=quote?.changePercent
        val amount=quote?.price?.takeIf { it.isFinite() && it>0 }?.let { it*quantity }
        val pnl=if(sell && quote!=null && state.buy!=null) (quote.price-state.buy)*quantity else null
        val percent=if(sell && quote!=null && state.buy!=null) (quote.price/state.buy-1)*100 else null
        val info=if(sell) "Qty $quantity · P&L ${pnl?.let { "₹%+,.2f".format(Locale.ENGLISH,it) } ?: "Unavailable"} (${percent?.let { "%+.2f%%".format(Locale.ENGLISH,it) } ?: "—"})"
            else "Qty $quantity · Est. ${price(amount)}"
        val readable=when(reason) {
            "OPENING_BUY" -> "Opening K/D · positive open"
            "VOLUME_DROP_30_PERCENT" -> "Volume fell 30% or more · review exit"
            "KD_BEARISH" -> "K is below D"
            "STOP_1_PERCENT" -> "1% stop loss reached"
            "PRICE_STOP" -> "Price stop / profit protection reached"
            "SESSION_1510" -> "15:10 exit · approval required"
            else -> reason.replace('_',' ')
        }
        val tick=quote?.tradedAt?.let(clock::format) ?: "Unavailable"
        return OpeningNotice("${row.stock.symbol}  •  ${if(sell) "SELL" else "BUY"}  •  PAPER",price(quote?.price),
            change?.let { "%+.2f%% today".format(Locale.ENGLISH,it) } ?: "Day change unavailable",
            "K ${metric(sample?.k)}    D ${metric(sample?.d)}    VOL 15m ${if(ratio==null) "—" else metric(ratio)+"×"}",
            info,readable,"Expires ${clock.format(at.plusSeconds(60))} · ${(remaining+999)/1000}s left\nPrice $tick · 15m live K/D · no real orders",
            quantity,sell,change!=null && change>=0,remaining)
    }
}

object OpeningNotifications {
    const val CHANNEL="paper-trade-actions"
    private const val ID=3101
    private val active=mutableMapOf<String,Instant>()
    private val posted=mutableMapOf<String,Instant>()
    private var updateSecond=0L
    private var updates=0
    private fun allowed(context:Context)=Build.VERSION.SDK_INT<33 || context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED
    private fun manager(context:Context)=context.getSystemService(NotificationManager::class.java)
    private fun channel(context:Context) {
        manager(context).createNotificationChannel(NotificationChannel(CHANNEL,"Paper Opening BUY approvals",NotificationManager.IMPORTANCE_HIGH).apply {
            description="One-minute Opening BUY approvals with direct BUY and SKIP buttons"
            enableVibration(true);lockscreenVisibility=android.app.Notification.VISIBILITY_PUBLIC
        })
    }
    fun actionIntent(context:Context,key:String,at:Instant,choice:OpeningChoice,quantity:Int)=Intent(context,OpeningActionReceiver::class.java)
        .setAction("com.nsemomentum.paper.OPENING_APPROVAL")
        .setData(Uri.Builder().scheme("momentum-paper").authority("approval").appendPath(key).appendPath(at.toString()).appendPath(choice.name).build())
        .putExtra("key",key).putExtra("at",at.toString()).putExtra("choice",choice.name).putExtra("quantity",quantity)
    private fun action(context:Context,row:ReversalRow,choice:OpeningChoice,quantity:Int,label:String):NotificationCompat.Action {
        val intent=actionIntent(context,row.stock.instrumentKey,row.opening.alertAt!!,choice,quantity)
        val pending=PendingIntent.getBroadcast(context,0,intent,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Action.Builder(0,label,pending).setAuthenticationRequired(false).build()
    }
    @Synchronized fun update(context:Context,row:ReversalRow,live:LivePriceState,now:Instant) {
        val key=row.stock.instrumentKey
        val notice=OpeningNoticeFormatter.create(row,live.quotes[key],now,OpeningNoticeFormatter.quantity(context))
        if(notice==null) { if(active.remove(key)!=null) manager(context).cancel(key,ID);posted.remove(key);return }
        if(!allowed(context)) return
        val isNew=active[key]!=row.opening.alertAt
        if(!isNew) {
            if(posted[key]?.let { Duration.between(it,now).seconds<10 }==true) return
            if(updateSecond!=now.epochSecond) { updateSecond=now.epochSecond;updates=0 }
            if(updates>=4) return
            updates++
        }
        runCatching {
            channel(context)
            if(isNew) manager(context).cancel(key,ID)
            val intent=PendingIntent.getActivity(context,0,Intent(context,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val expanded=RemoteViews(context.packageName,R.layout.notification_paper_expanded).apply {
                setTextViewText(R.id.signal_title,notice.title);setTextColor(R.id.signal_title,Color.parseColor(if(notice.sell) "#FFB1AA" else "#57E3B2"))
                setTextViewText(R.id.signal_price,notice.price);setTextViewText(R.id.signal_change,notice.change)
                setTextColor(R.id.signal_change,Color.parseColor(if(notice.changePositive) "#57E3B2" else "#FFB1AA"))
                setTextViewText(R.id.signal_metrics,notice.metrics);setTextViewText(R.id.signal_context,notice.context)
                setTextViewText(R.id.signal_reason,notice.reason);setTextViewText(R.id.signal_expiry,notice.footer)
            }
            val compact=RemoteViews(context.packageName,R.layout.notification_paper_compact).apply {
                setTextViewText(R.id.compact_title,notice.title);setTextColor(R.id.compact_title,Color.parseColor(if(notice.sell) "#FFB1AA" else "#57E3B2"))
                setTextViewText(R.id.compact_price,notice.price);setTextViewText(R.id.compact_detail,notice.change+" · ${((notice.remainingMillis+999)/1000)}s")
            }
            val builder=NotificationCompat.Builder(context,CHANNEL).setSmallIcon(R.drawable.ic_paper_signal)
                .setColor(Color.parseColor(if(notice.sell) "#D95B63" else "#09866A"))
                .setContentTitle(notice.title).setContentText("${notice.price} · ${notice.change}")
                .setCustomContentView(compact).setCustomBigContentView(expanded)
                .setStyle(NotificationCompat.DecoratedCustomViewStyle()).setContentIntent(intent)
                .setPriority(NotificationCompat.PRIORITY_HIGH).setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setOnlyAlertOnce(true).setAutoCancel(false).setTimeoutAfter(notice.remainingMillis)
                .addAction(action(context,row,if(notice.sell) OpeningChoice.SELL else OpeningChoice.BUY,notice.quantity,if(notice.sell) "SELL · PAPER" else "BUY ${notice.quantity} · PAPER"))
                .addAction(action(context,row,if(notice.sell) OpeningChoice.WAIT else OpeningChoice.SKIP,notice.quantity,"SKIP"))
            manager(context).notify(key,ID,builder.build());active[key]=row.opening.alertAt!!;posted[key]=now
        }.onFailure { DiagnosticLog.event("OPENING_NOTIFICATION","DISPLAY_FAILED",symbol=row.stock.symbol) }
    }
    @Synchronized fun result(context:Context,stock:Stock,previous:OpeningState,current:OpeningState,command:OpeningApproval) {
        val message=when {
            command.choice==OpeningChoice.BUY && previous.buy==null && current.buy!=null -> "Paper BUY recorded · ${current.quantity} shares at ${OpeningNoticeFormatter.price(current.buy)}"
            command.choice==OpeningChoice.SELL && current.trades.size>previous.trades.size -> current.trades.last().let { "Paper SELL recorded · ${it.quantity} shares at ${OpeningNoticeFormatter.price(it.sell)} · P&L ₹%+,.2f".format(Locale.ENGLISH,it.gross) }
            command.choice==OpeningChoice.SKIP && current.skipped && !previous.skipped -> "BUY skipped today · no paper trade"
            command.choice==OpeningChoice.WAIT && current.waitUntil!=previous.waitUntil -> if(previous.buy==null) "BUY postponed · no paper trade" else "SELL skipped · position remains open; recheck in 30s"
            else -> "Not recorded · signal expired, changed or data unavailable"
        }
        acknowledge(context,stock.instrumentKey,stock.symbol,message)
    }
    @Synchronized fun acknowledge(context:Context,key:String,symbol:String,message:String) {
        active.remove(key);posted.remove(key)
        if(!allowed(context)) return
        runCatching {
            channel(context)
            manager(context).notify(key,ID,NotificationCompat.Builder(context,CHANNEL).setSmallIcon(R.drawable.ic_paper_signal)
                .setContentTitle("$symbol · PAPER ONLY").setContentText(message).setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setSilent(true).setAutoCancel(true).setTimeoutAfter(10000).build())
        }
    }
}
/** Explicit, non-exported receiver: notification actions enqueue into the running paper actor, never launch an activity. */
class OpeningActionReceiver:BroadcastReceiver() {
    override fun onReceive(context:Context,intent:Intent) {
        if(intent.action!="com.nsemomentum.paper.OPENING_APPROVAL") return
        val key=intent.getStringExtra("key") ?: return
        val at=runCatching { Instant.parse(intent.getStringExtra("at")) }.getOrNull() ?: return
        val choice=runCatching { OpeningChoice.valueOf(intent.getStringExtra("choice") ?: "") }.getOrNull() ?: return
        if(choice !in setOf(OpeningChoice.BUY,OpeningChoice.SELL,OpeningChoice.SKIP,OpeningChoice.WAIT)) return
        val command=OpeningApproval(key,at,choice,intent.getIntExtra("quantity",1))
        if(!ReversalRunner.approveOpening(command)) {
            val symbol=ReversalRunner.state.value.rows.firstOrNull { it.stock.instrumentKey==key }?.stock?.symbol ?: "Paper signal"
            OpeningNotifications.acknowledge(context,key,symbol,"Not recorded · approval expired or monitoring stopped")
        }
    }
}

