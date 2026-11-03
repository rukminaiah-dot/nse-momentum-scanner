package com.nsemomentum.paper

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp

@Composable fun OpeningNotificationPermission() {
    val context=androidx.compose.ui.platform.LocalContext.current
    var status by remember { mutableStateOf("") }
    var preset by remember { mutableStateOf(OpeningNoticeFormatter.quantity(context).toString()) }
    val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { status=if(it) "Opening alerts enabled" else "Notifications denied · approvals remain in app" }
    TextButton(onClick={
        if(Build.VERSION.SDK_INT>=33) permission.launch(Manifest.permission.POST_NOTIFICATIONS) else status="Notifications available; check Android notification settings"
    }) { Text("Enable opening paper alerts") }
    OutlinedTextField(value=preset,onValueChange={ value ->
        preset=value.filter(Char::isDigit).take(7)
        preset.toIntOrNull()?.takeIf { it in 1..1000000 }?.let {
            context.getSharedPreferences("opening_notification_settings",0).edit().putInt("quantity",it).apply()
        }
    },label={Text("Paper quantity for notification BUY")},supportingText={Text("Default 1 share. SELL uses the full held quantity. Invalid input keeps the last saved quantity.")},
        isError=preset.toIntOrNull()?.let { it !in 1..1000000 } ?: true,keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number))
    if(status.isNotEmpty()) Text(status)
}
@Composable fun OpeningApprovalDialog(snapshot:ReversalSnapshot,prices:LivePriceState) {
    val row=snapshot.rows.firstOrNull { it.opening.alert!=null && it.opening.alertAt!=null } ?: return
    val state=row.opening
    val appContext=androidx.compose.ui.platform.LocalContext.current
    var quantity by remember(row.stock.instrumentKey,state.alertAt) { mutableStateOf(OpeningNoticeFormatter.quantity(appContext).toString()) }
    val q=quantity.toIntOrNull()
    val quote=prices.quotes[row.stock.instrumentKey]
    fun choose(choice:OpeningChoice) { state.alertAt?.let { ReversalRunner.approveOpening(OpeningApproval(row.stock.instrumentKey,it,choice,q ?: 0)) } }
    AlertDialog(onDismissRequest={choose(OpeningChoice.WAIT)},title={Text("${row.stock.symbol} · ${if(state.buy==null) "BUY" else "SELL"} · PAPER ONLY")},text={
        Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {
            quote?.let { Text("Latest price ₹%.2f · %s".format(it.price,clockTime(it.tradedAt))) }
            if(quote!=null && q!=null && q in 1..1000000 && state.buy==null) Text("Estimated paper amount ₹%.2f".format(quote.price*q))
            if(quote!=null && state.buy!=null) Text("Gross paper P&L ₹%+.2f · %+.2f%%".format((quote.price-state.buy)*state.quantity,(quote.price/state.buy-1)*100))
            Text(state.alert!!.replace('_',' '))
            Text("Approval records a simulated trade only. Upstox real orders are not connected.")
            if(state.buy==null) {
                OutlinedTextField(value=quantity,onValueChange={quantity=it.filter(Char::isDigit).take(7)},label={Text("Quantity (shares)")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number))
                if(q!=null && q in 1..1000000) Text("Price and conditions are rechecked on approval.")
            } else {
                Text("Quantity held: ${state.quantity} · BUY ₹%.2f".format(state.buy))
                Text("WAIT keeps this position open, including for stops and the 15:10 exit.")
            }
            row.preview?.let { Text("Live 15m K %.2f / D %.2f".format(it.context.stochK,it.context.stochD)) }
            Text("Approval expires after 60 seconds. Android may suppress heads-up popups depending on notification settings.")
        }
    },confirmButton={TextButton(enabled=state.buy!=null || q!=null && q in 1..1000000,onClick={choose(if(state.buy==null) OpeningChoice.BUY else OpeningChoice.SELL)}) { Text(if(state.buy==null) "BUY NOW · PAPER" else "SELL NOW · PAPER") }},dismissButton={
        Row {
            TextButton(onClick={choose(OpeningChoice.WAIT)}) { Text("WAIT") }
            if(state.buy==null) TextButton(onClick={choose(OpeningChoice.SKIP)}) { Text("SKIP TODAY") }
        }
    })
}
@Composable fun OpeningRowSummary(row:ReversalRow,prices:LivePriceState) {
    val s=row.opening
    if(s.day.isBlank() && s.trades.isEmpty()) return
    HorizontalDivider()
    Text("OPENING MOMENTUM · APPROVAL-ONLY PAPER",style=MaterialTheme.typography.titleSmall)
    Text(s.status)
    Text("${s.alert?.replace('_',' ') ?: "No pending approval"}",style=MaterialTheme.typography.bodySmall)
    s.buy?.let { buy ->
        val price=prices.quotes[row.stock.instrumentKey]?.price
        Text("${s.quantity} shares · BUY ₹%.2f".format(buy))
        if(price!=null) Text("Marked return %+.2f%% · gross P&L ₹%+.2f".format((price/buy-1)*100,(price-buy)*s.quantity))
    }
    if(s.trades.isNotEmpty()) {
        Text("Opening completed: ${s.trades.size} · gross P&L ₹%+.2f".format(s.trades.sumOf { it.gross }))
        var expanded by remember { mutableStateOf(false) }
        TextButton(onClick={expanded=!expanded}) { Text(if(expanded) "Hide opening trades" else "Show opening BUY / SELL details") }
        if(expanded) s.trades.reversed().forEach { t ->
            Text("BUY ₹%.2f · %s\nSELL ₹%.2f · %s\nQty %d · %+.2f%% · ₹%+.2f · %s".format(t.buy,clockTime(t.buyAt),t.sell,clockTime(t.sellAt),t.quantity,t.percent,t.gross,t.reason.replace('_',' ')),style=MaterialTheme.typography.bodySmall)
        }
    }
}
