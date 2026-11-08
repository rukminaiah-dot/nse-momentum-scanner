package com.nsemomentum.paper

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.Instant
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

val PaperGreen=Color(0xFF087C62)
@Composable fun PaperUiTheme(content:@Composable ()->Unit) {
    val dark=isSystemInDarkTheme()
    MaterialTheme(colorScheme=if(dark) darkColorScheme(primary=Color(0xFF6EE3BD),onPrimary=Color(0xFF103329),background=Color(0xFF101723),surface=Color(0xFF192332),surfaceContainer=Color(0xFF192332),secondaryContainer=Color(0xFF203E38))
        else lightColorScheme(primary=Color(0xFF087C62),onPrimary=Color.White,background=Color(0xFFF5F7FA),surface=Color.White,surfaceContainer=Color.White,secondaryContainer=Color(0xFFE7F5EF)),content=content)
}
fun compactMoney(value:Double)=String.format(Locale.US,"%+,.2f",value)
fun compactPrice(value:Double?)=value?.let { "₹%,.2f".format(Locale.US,it) } ?: "—"
fun compactTime(time:Instant?)=time?.let { DateTimeFormatter.ofPattern("HH:mm:ss 'IST'",Locale.US).withZone(MarketSession.ZONE).format(it) } ?: "—"
@Composable fun profitColor(value:Double?)=when { value==null || value==0.0 -> MaterialTheme.colorScheme.onSurfaceVariant;value>0 -> if(isSystemInDarkTheme()) Color(0xFF6EE3BD) else PaperGreen;else->MaterialTheme.colorScheme.error }

data class UiTrade(val key:String,val symbol:String,val source:PaperSource?,val buyAt:Instant,val buy:Double,val sellAt:Instant?,val sell:Double?,val quantity:Int=1,val manual:Boolean=false) {
    val pnl:Double? get()=sell?.let { (it-buy)*quantity }
    val percent:Double? get()=sell?.let { (it/buy-1)*100 }
}
data class TradeTotals(val count:Int,val wins:Int,val losses:Int,val flat:Int,val pnl:Double,val average:Double?) {
    val winRate:Double? get()=if(count==0) null else wins*100.0/count
}
object TradeResults {
    fun totals(trades:List<UiTrade>):TradeTotals {
        val closed=trades.filter { it.sellAt!=null && it.sell!=null }
        val wins=closed.count { it.pnl!!>0 };val losses=closed.count { it.pnl!!<0 }
        return TradeTotals(closed.size,wins,losses,closed.size-wins-losses,closed.sumOf { it.pnl!! },closed.mapNotNull { it.percent }.average().takeIf { closed.isNotEmpty() })
    }
    fun onDate(trades:List<UiTrade>,date:LocalDate)=trades.filter { it.sellAt?.atZone(MarketSession.ZONE)?.toLocalDate()==date }
    fun week(trades:List<UiTrade>,today:LocalDate)=trades.filter { it.sellAt?.atZone(MarketSession.ZONE)?.toLocalDate()?.let { date->date in today.minusDays(6)..today }==true }
    fun reversal(snapshot:ReversalSnapshot):List<UiTrade> = snapshot.rows.flatMap { row ->
        row.opening.trades.map { UiTrade(row.stock.instrumentKey,row.stock.symbol,PaperSource.OPENING,it.buyAt,it.buy,it.sellAt,it.sell,it.quantity,!it.automatic) }+
        row.state.trades.map { UiTrade(row.stock.instrumentKey,row.stock.symbol,PaperSource.REVERSAL,it.buyAt,it.buy,it.sellAt,it.sell,it.quantity,it.manual) }
    }
    fun volume(trades:List<PaperTrade>)=trades.map { UiTrade(it.symbol,it.symbol,null,it.boughtAt,it.buy,it.soldAt,it.sell) }
}
@Composable fun CompactHeader(title:String,right:String="") {
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) {
        Text(title,style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Medium)
        Text(right,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
@Composable fun DetailLine(label:String,value:String,tone:Double?=null) {
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
        Text(label,Modifier.weight(1f),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value,Modifier.weight(1.2f),style=MaterialTheme.typography.bodySmall,color=if(tone==null) MaterialTheme.colorScheme.onSurface else profitColor(tone),maxLines=2)
    }
}
@Composable fun MetricsHeader() {
    Row(Modifier.fillMaxWidth().padding(horizontal=10.dp,vertical=5.dp),verticalAlignment=Alignment.CenterVertically) {
        listOf("Period" to 1.05f,"P&L ₹" to 1.65f,"Avg %" to 1.15f,"Win %" to .85f,"Trades" to .75f).forEach { (label,weight) ->
            Text(label,Modifier.weight(weight),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1)
        }
    }
}
@Composable fun ResultLine(label:String,trades:List<UiTrade>,highlight:Boolean=false,onEdit:((UiTrade,PaperOperation)->Unit)?=null) {
    var expanded by remember(label) { mutableStateOf(false) }
    val t=TradeResults.totals(trades)
    Surface(shape=RoundedCornerShape(12.dp),color=if(highlight) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface) {
        Column {
            Row(Modifier.fillMaxWidth().clickable { expanded=!expanded }.padding(horizontal=10.dp,vertical=14.dp),verticalAlignment=Alignment.CenterVertically) {
                Text(label,Modifier.weight(1.05f),style=MaterialTheme.typography.labelMedium,maxLines=1)
                Text(compactMoney(t.pnl),Modifier.weight(1.65f),style=MaterialTheme.typography.labelMedium,color=profitColor(t.pnl),maxLines=1,overflow=TextOverflow.Ellipsis)
                Text(t.average?.let { "%+.2f%%".format(Locale.US,it) } ?: "—",Modifier.weight(1.15f),style=MaterialTheme.typography.labelSmall,maxLines=1)
                Text(t.winRate?.let { "%.0f%%".format(Locale.US,it) } ?: "—",Modifier.weight(.85f),style=MaterialTheme.typography.labelSmall,maxLines=1)
                Text("${t.count} ${if(expanded) "⌃" else "⌄"}",Modifier.weight(.75f),style=MaterialTheme.typography.labelSmall,maxLines=1)
            }
            if(expanded) Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                Text("${t.wins} wins · ${t.losses} losses · ${t.flat} flat",style=MaterialTheme.typography.bodySmall)
                Text("Gross P&L ₹${compactMoney(t.pnl)} · open trades excluded",style=MaterialTheme.typography.bodySmall)
                if(trades.isEmpty()) Text("No completed trades",style=MaterialTheme.typography.bodySmall)
                trades.sortedByDescending { it.sellAt }.forEach { trade ->
                    HorizontalDivider()
                    CompactHeader(trade.symbol,trade.source?.name?.lowercase()?.replaceFirstChar { it.uppercase() } ?: "Volume")
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick={onEdit?.invoke(trade,PaperOperation.EDIT_BUY)},enabled=onEdit!=null && trade.source!=null,contentPadding=PaddingValues(0.dp)) { Text("BUY ${compactPrice(trade.buy)}${if(trade.source!=null) " ✎" else ""}",fontSize=12.sp) }
                        TextButton(onClick={onEdit?.invoke(trade,PaperOperation.EDIT_SELL)},enabled=onEdit!=null && trade.source!=null,contentPadding=PaddingValues(0.dp)) { Text("SELL ${compactPrice(trade.sell)}${if(trade.source!=null) " ✎" else ""}",fontSize=12.sp) }
                    }
                    DetailLine("Qty ${trade.quantity} · ${if(trade.manual) "Recorded" else "Automatic paper"}","₹${compactMoney(trade.pnl!!)} · %+.2f%%".format(Locale.US,trade.percent),trade.pnl)
                    Text("${clockTime(trade.buyAt)} → ${trade.sellAt?.let(::clockTime)}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}
@Composable fun CompactResults(trades:List<UiTrade>,onEdit:((UiTrade,PaperOperation)->Unit)?=null) {
    val today=LocalDate.now(MarketSession.ZONE)
    CompactHeader("Today",today.format(DateTimeFormatter.ofPattern("dd MMM")))
    MetricsHeader();ResultLine("Today",TradeResults.onDate(trades,today),onEdit=onEdit)
    Spacer(Modifier.height(4.dp))
    CompactHeader("Last 7 days","${today.minusDays(6).format(DateTimeFormatter.ofPattern("dd MMM"))} – ${today.format(DateTimeFormatter.ofPattern("dd MMM"))}")
    MetricsHeader();ResultLine("7 days",TradeResults.week(trades,today),true,onEdit)
    var history by remember { mutableStateOf(false) }
    TextButton(onClick={history=!history}) { Text(if(history) "Hide previous days" else "Previous days",fontSize=12.sp) }
    if(history) (1L..6L).forEach { offset -> val date=today.minusDays(offset)
        ResultLine(date.format(DateTimeFormatter.ofPattern("dd MMM")),TradeResults.onDate(trades,date),onEdit=onEdit)
    }
    val type=if(trades.any { it.manual } && trades.any { !it.manual }) "Automatic + recorded paper" else if(trades.any { it.manual }) "Recorded paper" else "Automatic paper"
    Text("$type · closed trades · before costs",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
}
@Composable fun PaperQuantityBar(onQuantity:(Int)->Unit={}) {
    val context=androidx.compose.ui.platform.LocalContext.current
    var value by remember { mutableStateOf(OpeningNoticeFormatter.quantity(context).toString()) }
    Surface(shape=RoundedCornerShape(12.dp),color=MaterialTheme.colorScheme.surface) {
        Row(Modifier.fillMaxWidth().padding(horizontal=12.dp,vertical=6.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.SpaceBetween) {
            Text("Paper qty",style=MaterialTheme.typography.bodyMedium)
            Row(verticalAlignment=Alignment.CenterVertically) {
                fun save(v:Int) { value=v.coerceIn(1,1000000).toString();context.getSharedPreferences("opening_notification_settings",0).edit().putInt("quantity",value.toInt()).apply();onQuantity(value.toInt()) }
                TextButton(onClick={save((value.toIntOrNull() ?: 1)-1)},contentPadding=PaddingValues(8.dp)) { Text("−") }
                OutlinedTextField(value=value,onValueChange={v->value=v.filter(Char::isDigit).take(7);value.toIntOrNull()?.takeIf { it in 1..1000000 }?.let(::save)},modifier=Modifier.width(70.dp),singleLine=true,textStyle=MaterialTheme.typography.bodyLarge,keyboardOptions=androidx.compose.foundation.text.KeyboardOptions(keyboardType=androidx.compose.ui.text.input.KeyboardType.Number))
                TextButton(onClick={save((value.toIntOrNull() ?: 1)+1)},contentPadding=PaddingValues(8.dp)) { Text("+") }
            }
        }
    }
}

@Composable fun CompactVolumeCard(symbol:String,peak:Double,latest:Double?,quote:LiveQuote?,preview:LiveStochastic?,row:ScanRow?,trades:List<PaperTrade>,connected:Boolean,marketOpen:Boolean,now:Instant=Instant.now()) {
    var expanded by remember(symbol) { mutableStateOf(false) }
    val fresh=quote!=null && connected && marketOpen && java.time.Duration.between(quote.tradedAt,now).seconds in 0..30
    val lastTrade = trades.maxByOrNull { it.boughtAt }
    val candleClose = row?.candle?.timestamp?.plusSeconds(900)
    val recentExit = lastTrade?.soldAt?.takeIf { soldAt ->
        soldAt <= now && soldAt.atZone(MarketSession.ZONE).toLocalDate() == now.atZone(MarketSession.ZONE).toLocalDate() &&
            (candleClose == null || soldAt >= candleClose)
    }
    val display = if (recentExit != null) "SELL · PAPER · ${compactPrice(lastTrade?.sell)} at ${compactTime(recentExit)}"
        else paperSignalDisplay(row, now)
    val signal=when { display.startsWith("BUY ·")->"BUY";display.startsWith("SELL ·")->"SELL";display.startsWith("BUY ACTIVE")->"HOLD";else->"WAIT" }
    val live=preview?.takeIf { fresh && java.time.Duration.between(it.sampledAt,now).seconds in 0..20 }
    Surface(Modifier.fillMaxWidth(),shape=RoundedCornerShape(14.dp),color=MaterialTheme.colorScheme.surface) {
        Column(Modifier.padding(13.dp),verticalArrangement=Arrangement.spacedBy(7.dp)) {
            Row(Modifier.fillMaxWidth().clickable { expanded=!expanded }.heightIn(min=40.dp),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) {
                Text(symbol,fontWeight=FontWeight.Medium)
                Text("${signal} ${if(expanded) "⌃" else "⌄"}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.primary)
            }
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                Text(compactPrice(quote?.price),style=MaterialTheme.typography.bodyMedium)
                Text(quote?.changePercent?.let { "%+.2f%% today".format(Locale.US,it) } ?: "—",style=MaterialTheme.typography.bodySmall,color=profitColor(quote?.changePercent))
            }
            Text("K ${live?.context?.stochK?.let { "%.1f".format(Locale.US,it) } ?: "—"} · D ${live?.context?.stochD?.let { "%.1f".format(Locale.US,it) } ?: "—"} · RVOL ${latest?.let { "%.2f×".format(Locale.US,it) } ?: "—"}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Confirmed 15m · ${compactTime(row?.candle?.timestamp?.plusSeconds(900))}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Quote ${if(fresh) "live" else "unavailable / last data"} · ${compactTime(quote?.tradedAt)}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            if(expanded) {
                HorizontalDivider()
                DetailLine("Momentum · live 15m",live?.context?.let { if(it.stochK>it.stochD) "Bullish" else if(it.stochK<it.stochD) "Bearish" else "Neutral" } ?: "Unavailable")
                DetailLine("Live K / D",live?.context?.let { "%.2f / %.2f".format(Locale.US,it.stochK,it.stochD) } ?: "Unavailable")
                DetailLine("Confirmed K / D",row?.technicals?.let { "%.2f / %.2f".format(Locale.US,it.stochK,it.stochD) } ?: "Unavailable")
                DetailLine("Completed 15m volume",row?.candle?.volume?.let { "%.0f shares".format(Locale.US,it) } ?: "Unavailable")
                DetailLine("20-session same-slot average",row?.averageSlotVolume?.let { "%.0f shares".format(Locale.US,it) } ?: "Unavailable")
                DetailLine("15m RVOL",latest?.let { "%.2f×".format(Locale.US,it) } ?: "Unavailable")
                Text(display,style=MaterialTheme.typography.bodySmall)
                Text("RVOL compares completed 15m volume with the same slot in 20 prior trading sessions. Dashboard selection requires ≥1.5× once per day; selected stocks then use K>D for BUY. After +2% profit, verified RVOL below 1.5× can trigger SELL.",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                PaperTradesTable(trades,quote?.price,quote?.label(now,connected,marketOpen))
            }
        }
    }
}

