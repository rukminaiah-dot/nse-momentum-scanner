package com.nsemomentum.paper

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.util.Locale

data class SignalItem(val row:ReversalRow,val source:PaperSource) {
    val id:String get()=row.stock.instrumentKey+source.name
    val buy:Double? get()=if(source==PaperSource.OPENING) row.opening.buy else row.state.buy
    val buyAt:Instant? get()=if(source==PaperSource.OPENING) row.opening.buyAt else row.state.buyAt
    val quantity:Int get()=if(source==PaperSource.OPENING) row.opening.quantity else row.state.quantity
    val held:Boolean get()=buy!=null && (source==PaperSource.OPENING || row.state.manual)
    val latest:Instant get()=if(source==PaperSource.OPENING) listOfNotNull(row.opening.alertAt,row.opening.recordedAt,buyAt,row.opening.trades.lastOrNull()?.sellAt).maxOrNull() ?: row.signalAt ?: Instant.EPOCH
        else listOfNotNull(row.signalAt,row.state.recordedAt,buyAt,row.state.confirmationAt,row.state.trades.lastOrNull()?.sellAt).maxOrNull() ?: Instant.EPOCH
}
fun unifiedSignals(snapshot:ReversalSnapshot,now:Instant):List<SignalItem> {
    val date=now.atZone(MarketSession.ZONE).toLocalDate();val time=now.atZone(MarketSession.ZONE).toLocalTime()
    return snapshot.rows.flatMap { row ->
        val k=row.preview?.context?.stochK;val d=row.preview?.context?.stochD
        val openingWatch=row.openingSample?.fresh==true && time>=LocalTime.of(9,15) && time<LocalTime.of(9,30) && k!=null && d!=null && k>20 && k<50 && k>d
        val opening=openingWatch || row.opening.alert!=null || row.opening.buy!=null || row.opening.trades.lastOrNull()?.sellAt?.atZone(MarketSession.ZONE)?.toLocalDate()==date
        val reversal=row.state.watchDate==date.toString() || row.state.buy!=null || row.state.trades.lastOrNull()?.sellAt?.atZone(MarketSession.ZONE)?.toLocalDate()==date
        val candidates=listOfNotNull(if(opening) SignalItem(row,PaperSource.OPENING) else null,if(reversal) SignalItem(row,PaperSource.REVERSAL) else null)
        val held=candidates.filter { it.held }
        val active=candidates.filter { item -> if(item.source==PaperSource.OPENING) openingWatch || row.opening.alert!=null || row.opening.buy!=null else row.state.watchDate==date.toString() || row.state.buy!=null }
        if(held.isNotEmpty()) held else listOfNotNull((active.ifEmpty { candidates }).maxByOrNull { it.latest })
    }.sortedByDescending { it.latest }
}
data class RecordRequest(val key:String,val symbol:String,val source:PaperSource,val operation:PaperOperation,val at:Instant?,val price:Double?,val quantity:Int)
@Composable fun ReversalPage(snapshot:ReversalSnapshot,prices:LivePriceState,modifier:Modifier=Modifier) {
    val context=androidx.compose.ui.platform.LocalContext.current
    var help by remember { mutableStateOf(false) }
    var defaultQty by remember { mutableStateOf(OpeningNoticeFormatter.quantity(context)) }
    var request by remember { mutableStateOf<RecordRequest?>(null) }
    var notice by remember { mutableStateOf("") }
    val now=snapshot.updatedAt ?: Instant.now()
    val signals=unifiedSignals(snapshot,now)
    fun edit(trade:UiTrade,operation:PaperOperation) { trade.source?.let { source -> request=RecordRequest(trade.key,trade.symbol,source,operation,trade.buyAt,if(operation==PaperOperation.EDIT_BUY) trade.buy else trade.sell,trade.quantity) } }
    if(help) AlertDialog(onDismissRequest={help=false},title={Text("Rules & alerts")},text={Column(Modifier.heightIn(max=480.dp).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        Text("Opening: 09:17–09:30, 20<K<50, K>D, positive open and rising price/60s volume.")
        Text("Reversal: K>D below 20; cross above 20 with 60s volume confirmation.")
        Text("Initial stop −1%; profit protection advances in 0.25-point steps. MUST SELL flags an urgent exit; manual positions stay open until SELL is recorded.")
        Text("Prices entered here are unverified paper records. Original automatic history is retained and labelled. Records are local and are not included in the existing backup. Avg % is the mean closed-trade return; P&L includes recorded quantity, before costs.")
        OpeningNotificationPermission(showQuantity=false)
    }},confirmButton={TextButton(onClick={help=false}) { Text("Done") }})
    request?.let { r -> PaperRecordDialog(r,onDismiss={request=null},onSave={price,qty ->
        val queued=ReversalRunner.record(PaperRecordEdit(r.key,r.source,r.operation,r.at,price,qty))
        notice=if(queued) "Saving paper record…" else "Monitoring unavailable · reopen with your saved data token"
        if(queued) request=null
    }) }
    LazyColumn(modifier.fillMaxSize().testTag("signals-list"),contentPadding=PaddingValues(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
        item { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) {
            Text("Signals & trades",style=MaterialTheme.typography.headlineSmall,fontWeight=FontWeight.Medium)
            TextButton(onClick={help=true}) { Text("ⓘ") }
        };CompactHeader("Shortlist & trades","Latest first · ${signals.size}") }
        if(signals.isEmpty()) item { Text("No shortlisted stocks yet",style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        items(signals,key={it.id}) { item -> UnifiedStockCard(item,prices,onRecord={op,at,price,qty -> request=RecordRequest(item.row.stock.instrumentKey,item.row.stock.symbol,item.source,op,at,price,qty)},onWait={
            notice=if(ReversalRunner.record(PaperRecordEdit(item.row.stock.instrumentKey,item.source,PaperOperation.WAIT,item.buyAt,null,item.quantity.coerceAtLeast(1)))) "WAIT requested · no SELL" else "Monitoring unavailable"
        },defaultQuantity=defaultQty) }
        item { Text("${if(prices.connected) "Connected" else "Disconnected"} · ${compactTime(snapshot.updatedAt)}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        item { PaperQuantityBar { defaultQty=it } }
        if(snapshot.recordStatus!=null || notice.isNotEmpty()) item { Text(snapshot.recordStatus ?: notice,style=MaterialTheme.typography.bodySmall) }
        item { CompactResults(TradeResults.reversal(snapshot),::edit) }
    }
}
@Composable fun PaperRecordDialog(request:RecordRequest,onDismiss:()->Unit,onSave:(Double,Int)->Unit) {
    var price by remember(request) { mutableStateOf(request.price?.let { "%.2f".format(Locale.US,it) } ?: "") }
    var quantity by remember(request) { mutableStateOf(request.quantity.coerceAtLeast(1).toString()) }
    val p=price.toDoubleOrNull();val q=quantity.toIntOrNull()
    val sell=request.operation in listOf(PaperOperation.SELL,PaperOperation.EDIT_SELL)
    val editing=request.operation in listOf(PaperOperation.EDIT_BUY,PaperOperation.EDIT_SELL)
    AlertDialog(onDismissRequest=onDismiss,title={Text("${if(editing) "Edit" else "Record"} ${if(sell) "SELL" else "BUY"} · ${request.symbol}")},text={Column(verticalArrangement=Arrangement.spacedBy(12.dp)) {
        Text("Paper record only · no order is placed",style=MaterialTheme.typography.bodySmall)
        OutlinedTextField(value=price,onValueChange={price=it},label={Text("Executed price ₹ · entered by you")},singleLine=true,
            keyboardOptions=androidx.compose.foundation.text.KeyboardOptions(keyboardType=androidx.compose.ui.text.input.KeyboardType.Decimal))
        OutlinedTextField(value=quantity,onValueChange={quantity=it.filter(Char::isDigit).take(7)},label={Text("Quantity")},readOnly=sell,singleLine=true,
            keyboardOptions=androidx.compose.foundation.text.KeyboardOptions(keyboardType=androidx.compose.ui.text.input.KeyboardType.Number))
    }},confirmButton={TextButton(enabled=p!=null && p.isFinite() && p>0 && p<=1000000000 && q!=null && q in 1..1000000,onClick={onSave(p!!,q!!)}) { Text(if(editing) "Save price" else if(sell) "Record SELL" else "Record BUY") }},dismissButton={TextButton(onClick=onDismiss) { Text("Cancel") }})
}
@Composable fun UnifiedStockCard(item:SignalItem,prices:LivePriceState,onRecord:(PaperOperation,Instant?,Double?,Int)->Unit,onWait:()->Unit,defaultQuantity:Int) {
    var expanded by remember(item.id) { mutableStateOf(false) }
    val row=item.row;val quote=prices.quotes[row.stock.instrumentKey];val sample=row.openingSample
    val k=row.preview?.context?.stochK;val d=row.preview?.context?.stochD;val pk=row.previousPreview?.context?.stochK;val pd=row.previousPreview?.context?.stochD
    val ratio=if(sample?.continuous==true && (sample.beforeVolume ?: 0)>0 && sample.latestVolume!=null) sample.latestVolume.toDouble()/sample.beforeVolume!! else null
    val urgent=item.held && (ratio?.let { it<=.70 }==true || (k!=null && d!=null && pk!=null && k<d && k<pk))
    val required=if(item.source==PaperSource.OPENING) row.opening.alert?.takeIf { it!="OPENING_BUY" }!=null else row.state.action.contains("SELL_")
    val fresh=sample?.fresh==true
    val canBuy=if(item.source==PaperSource.OPENING) row.opening.alert=="OPENING_BUY" else row.state.buy!=null && !row.state.manual && k!=null && d!=null && k>d
    val lastTrade=TradeResults.reversal(ReversalSnapshot(listOf(row))).filter { it.source==item.source }.maxByOrNull { it.sellAt ?: Instant.EPOCH }
    val closedToday=lastTrade?.sellAt?.atZone(MarketSession.ZONE)?.toLocalDate()==LocalDate.now(MarketSession.ZONE)
    val label=when { urgent->"MUST SELL";item.held && required->"SELL SIGNAL";item.held->"BOUGHT";canBuy->"BUY SIGNAL";closedToday->"CLOSED";item.buy==null && item.latest!=Instant.EPOCH->"IDENTIFIED";else->"WATCH" }
    Surface(Modifier.fillMaxWidth(),shape=RoundedCornerShape(14.dp),color=MaterialTheme.colorScheme.surface) {
        Column(Modifier.padding(13.dp),verticalArrangement=Arrangement.spacedBy(7.dp)) {
            Row(Modifier.fillMaxWidth().clickable { expanded=!expanded }.heightIn(min=40.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) { Text(row.stock.symbol,fontWeight=FontWeight.Medium);Text(if(item.source==PaperSource.OPENING) "Opening" else "Reversal",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                Text(label,color=if(urgent) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,style=MaterialTheme.typography.labelSmall)
                Text(if(expanded) " ⌃" else " ⌄",color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                Text(compactPrice(quote?.price),style=MaterialTheme.typography.bodyMedium,fontWeight=FontWeight.Medium)
                Text(quote?.changePercent?.let { "%+.2f%% today".format(Locale.US,it) } ?: "—",style=MaterialTheme.typography.bodySmall,color=profitColor(quote?.changePercent))
            }
            Text("K ${k?.let { "%.1f".format(Locale.US,it) } ?: "—"} · D ${d?.let { "%.1f".format(Locale.US,it) } ?: "—"} · Vol ${ratio?.let { "%.2f×".format(Locale.US,it) } ?: "—"}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            if(item.held) {
                TextButton(onClick={onRecord(PaperOperation.EDIT_BUY,item.buyAt,item.buy,item.quantity)},contentPadding=PaddingValues(0.dp)) { Text("BUY ${compactPrice(item.buy)} ✎ · Qty ${item.quantity}",fontSize=12.sp) }
                val pnl=quote?.price?.let { (it-item.buy!!)*item.quantity }
                Text("Open P&L ${pnl?.let { "₹${compactMoney(it)}" } ?: "—"}",color=profitColor(pnl),style=MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    Button(onClick={onRecord(PaperOperation.SELL,item.buyAt,quote?.price,item.quantity)},colors=ButtonDefaults.buttonColors(containerColor=MaterialTheme.colorScheme.error)) { Text("SELL") }
                    OutlinedButton(onClick=onWait) { Text("WAIT") }
                }
            } else if(canBuy) {
                Button(enabled=fresh,onClick={onRecord(PaperOperation.BUY,if(item.source==PaperSource.OPENING) row.opening.alertAt else item.buyAt,quote?.price,defaultQuantity)}) { Text("⊕ BUY") }
            } else if(lastTrade!=null && lastTrade.sellAt?.atZone(MarketSession.ZONE)?.toLocalDate()==LocalDate.now(MarketSession.ZONE)) {
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick={onRecord(PaperOperation.EDIT_BUY,lastTrade.buyAt,lastTrade.buy,lastTrade.quantity)},contentPadding=PaddingValues(0.dp)) { Text("BUY ${compactPrice(lastTrade.buy)} ✎",fontSize=12.sp) }
                    TextButton(onClick={onRecord(PaperOperation.EDIT_SELL,lastTrade.buyAt,lastTrade.sell,lastTrade.quantity)},contentPadding=PaddingValues(0.dp)) { Text("SELL ${compactPrice(lastTrade.sell)} ✎",fontSize=12.sp) }
                }
            }
            Text("${compactTime(item.latest.takeIf { it!=Instant.EPOCH })}${if(!fresh) " · Last data" else ""}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            if(expanded) {
                HorizontalDivider()
                val priceChange=if(sample?.price60!=null && quote!=null) (quote.price/sample.price60-1)*100 else null
                val momentum=when { k==null || d==null -> "Unavailable";k>d -> if(pk!=null && k<pk) "Bullish · weakening" else "Bullish";k<d -> if(pk!=null && k>pk) "Bearish · weakening" else "Bearish";else->"Neutral" }
                val trend=when { priceChange==null || k==null || d==null->"Unavailable";priceChange>0 && k>d->"Bullish";priceChange<0 && k<d->"Bearish";else->"Mixed" }
                CompactHeader("Trend snapshot",trend)
                DetailLine("Momentum · 15m",momentum)
                DetailLine("Price · last 60s",priceChange?.let { "%+.2f%%".format(Locale.US,it) } ?: "—",priceChange)
                DetailLine("K / D",if(k!=null && d!=null) "%.2f / %.2f".format(Locale.US,k,d) else "—")
                DetailLine("Previous K / D",if(pk!=null && pd!=null) "%.2f / %.2f".format(Locale.US,pk,pd) else "—")
                DetailLine("Previous reading",compactTime(row.previousPreview?.sampledAt))
                DetailLine("K − D",if(k!=null && d!=null) "%+.2f".format(Locale.US,k-d) else "—")
                DetailLine("Latest / prior 60s volume",if(sample?.continuous==true) "${sample.latestVolume} / ${sample.beforeVolume} shares" else "Unavailable")
                DetailLine("Volume ratio",ratio?.let { "%.2f× (%+.0f%%)".format(Locale.US,it,(it-1)*100) } ?: "Unavailable")
                DetailLine("Open / previous close","${compactPrice(sample?.open)} / ${compactPrice(quote?.previousClose)}")
                if(item.buy!=null) {
                    val peak=if(item.source==PaperSource.OPENING) row.opening.peak else row.state.peakPrice
                    val stop=item.buy!!*(1+ReversalStrategy.stopPercent(item.buy!!,maxOf(item.buy!!,peak ?: item.buy!!))/100)
                    DetailLine("Current exit threshold",compactPrice(stop))
                }
                Text(if(item.source==PaperSource.OPENING) row.opening.alert?.replace('_',' ') ?: row.opening.status else reversalActionLabel(row.state.action),style=MaterialTheme.typography.bodySmall)
                if(row.status!=row.state.action && row.status.contains("FAILED")) Text(row.status,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.error)
                Text("Quote ${compactTime(quote?.tradedAt)} · provisional live K/D",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
fun reversalActionLabel(action: String): String = when(action) {
    "CONFIRMING_60S_VOLUME_AND_KD" -> "Checking K/D and volume for 60 seconds"
    "BUY_CONFIRMED_60S_VOLUME_INCREASE" -> "BUY · 60-second volume increased"
    "BUY_ACTIVE_INITIAL_STOP" -> "BUY active · initial 1% stop"
    "BUY_ACTIVE_PROFIT_PROTECTED" -> "BUY active · profit threshold raised"
    "SELL_STEPPED_PROFIT_STOP" -> "SELL · profit-protection threshold reached"
    "SELL_SESSION_1510" -> "SELL · 15:10 session exit"
    "NO_NEW_BUYS_AFTER_1510" -> "Session entry cutoff reached · no new BUYs"
    "SELL_STOP_1_PERCENT" -> "SELL · initial stop reached"
    "ALREADY_ABOVE_20_WAITING_FOR_NEW_CROSS" -> "K already above 20 · waiting for a new crossing"
    "CROSS_UNOBSERVED_AFTER_DATA_GAP_NEW_CROSS_REQUIRED" -> "Crossing interrupted by a data gap · new crossing required"
    "K_NOT_ABOVE_D_AT_CROSS_NEW_CROSS_REQUIRED" -> "K was not above D at crossing · new crossing required"
    "PRE_CROSS_VOLUME_UNAVAILABLE_NEW_CROSS_REQUIRED" -> "Need a complete nonzero 60-second volume baseline · new crossing required"
    "VOLUME_DID_NOT_INCREASE_NEW_CROSS_REQUIRED" -> "Volume did not increase · waiting for a new crossing"
    "CONFIRMATION_CANCELLED_KD_REVERSED" -> "Entry cancelled · K/D conditions reversed"
    "CONFIRMATION_CANCELLED_DATA_GAP" -> "Entry cancelled · data interrupted"
    "SHORTLISTED_BELOW_20_WAITING_FOR_CROSS" -> "Shortlisted below 20 · watching for upward crossing"
    "WAITING_FOR_K_ABOVE_D_BELOW_20" -> "Watching for K above D below 20"
    else -> action.replace('_',' ').lowercase()
}
