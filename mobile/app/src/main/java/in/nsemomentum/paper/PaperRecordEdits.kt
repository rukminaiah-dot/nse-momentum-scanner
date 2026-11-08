package com.nsemomentum.paper

import java.time.Instant

enum class PaperSource { OPENING, REVERSAL }
enum class PaperOperation { BUY, SELL, EDIT_BUY, EDIT_SELL }
data class PaperRecordEdit(val key:String,val source:PaperSource,val operation:PaperOperation,val expectedAt:Instant?,val price:Double?,val quantity:Int=1)
/** User-entered paper records. Signal timestamps remain stable identifiers. No order API is called. */
object PaperRecordEdits {
    fun valid(c:PaperRecordEdit)=c.quantity in 1..1000000 && c.price?.let { it.isFinite() && it>0 && it<=1000000000 }==true
    fun opening(s:OpeningState,c:PaperRecordEdit,now:Instant):OpeningState {
        if(!valid(c)) return s
        val price=c.price ?: 0.0
        if(s.buyAt!=null && s.buyAt==c.expectedAt && s.buy!=null) return when(c.operation) {
            PaperOperation.SELL -> s.copy(buy=null,buyAt=null,quantity=0,peak=null,automatic=false,recordedAt=now,
                trades=s.trades+OpeningTrade(s.buyAt,s.buy,now,price,s.quantity,"MANUAL_SELL"),status="Manual SELL recorded")
            PaperOperation.EDIT_BUY -> s.copy(buy=price,quantity=c.quantity,peak=maxOf(price,s.peak ?: price),automatic=false,recordedAt=now,status="BUY price corrected")
            else -> s
        }
        val index=s.trades.indexOfFirst { it.buyAt==c.expectedAt }
        if(index<0 || c.operation !in listOf(PaperOperation.EDIT_BUY,PaperOperation.EDIT_SELL)) return s
        val trades=s.trades.toMutableList();val t=trades[index]
        trades[index]=if(c.operation==PaperOperation.EDIT_BUY) t.copy(buy=price,quantity=c.quantity,automatic=false) else t.copy(sell=price,automatic=false)
        return s.copy(trades=trades,recordedAt=now,status="Recorded price corrected")
    }
    fun reversal(s:ReversalState,c:PaperRecordEdit,now:Instant,fresh:Boolean,k:Double?,d:Double?):ReversalState {
        if(!valid(c)) return s
        val price=c.price ?: 0.0
        if(s.buyAt!=null && s.buyAt==c.expectedAt && s.buy!=null) return when(c.operation) {
            PaperOperation.BUY -> if(!fresh || s.manual || StockSessionExit.entriesClosed(now) || k==null || d==null || !k.isFinite() || !d.isFinite() || k<=20 || k>100 || d !in 0.0..100.0 || k<=d) s else s.copy(buy=price,quantity=c.quantity,manual=true,recordedAt=now,peakPrice=price,action="MANUAL_BUY_RECORDED")
            PaperOperation.SELL -> if(!s.manual) s else s.copy(buy=null,buyAt=null,peakPrice=null,manual=false,recordedAt=now,action="SELL_MANUAL_RECORDED",
                trades=s.trades+ReversalTrade(s.buyAt,s.buy,now,price,"MANUAL_SELL","MANUAL_RECORD",s.beforeVolume,s.afterVolume,s.quantity,true))
            PaperOperation.EDIT_BUY -> s.copy(buy=price,quantity=c.quantity,manual=true,peakPrice=maxOf(price,s.peakPrice ?: price),recordedAt=now,action="MANUAL_BUY_CORRECTED")
            else -> s
        }
        val index=s.trades.indexOfFirst { it.buyAt==c.expectedAt }
        if(index<0 || c.operation !in listOf(PaperOperation.EDIT_BUY,PaperOperation.EDIT_SELL)) return s
        val trades=s.trades.toMutableList();val t=trades[index]
        trades[index]=if(c.operation==PaperOperation.EDIT_BUY) t.copy(buy=price,quantity=c.quantity,manual=true) else t.copy(sell=price,manual=true)
        return s.copy(trades=trades,recordedAt=now)
    }
}

