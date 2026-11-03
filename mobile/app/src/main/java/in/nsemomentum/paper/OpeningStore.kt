package com.nsemomentum.paper

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/** Pending approvals and K/D are deliberately not restored after restart. */
class OpeningStore(context:Context) {
    private val prefs=context.getSharedPreferences("opening_momentum_paper_v1",0)
    fun read():Map<String,OpeningState> = runCatching {
        val root=JSONObject(prefs.getString("state","{}")!!)
        root.keys().asSequence().associateWith { key ->
            val r=root.getJSONObject(key);val ts=r.getJSONArray("trades")
            OpeningState(recordedAt=r.optString("recordedAt").takeIf { it.isNotEmpty() }?.let(Instant::parse),day=r.optString("day"),boughtToday=r.optBoolean("boughtToday"),skipped=r.optBoolean("skipped"),
                buy=if(r.has("buy")) r.getDouble("buy") else null,buyAt=r.optString("buyAt").takeIf { it.isNotEmpty() }?.let(Instant::parse),
                quantity=r.optInt("quantity"),peak=if(r.has("peak")) r.getDouble("peak") else null,
                trades=(0 until ts.length()).map { i -> val t=ts.getJSONArray(i);OpeningTrade(Instant.parse(t.getString(0)),t.getDouble(1),Instant.parse(t.getString(2)),t.getDouble(3),t.getInt(4),t.getString(5)) })
        }.also { rows -> require(rows.values.all { (it.buy==null)==(it.buyAt==null) && (it.buy==null || it.buy.isFinite() && it.buy>0 && it.quantity in 1..1000000) }) }
    }.getOrDefault(emptyMap())
    fun write(rows:Map<String,OpeningState>) {
        val root=JSONObject()
        rows.forEach { (key,s) ->
            val r=JSONObject().put("day",s.day).put("boughtToday",s.boughtToday).put("skipped",s.skipped).put("quantity",s.quantity)
                .put("trades",JSONArray().apply { s.trades.forEach { put(JSONArray(listOf(it.buyAt.toString(),it.buy,it.sellAt.toString(),it.sell,it.quantity,it.reason))) } })
            s.recordedAt?.let { r.put("recordedAt",it.toString()) };s.buy?.let { r.put("buy",it) };s.buyAt?.let { r.put("buyAt",it.toString()) };s.peak?.let { r.put("peak",it) };root.put(key,r)
        }
        check(prefs.edit().putString("state",root.toString()).commit()) { "OPENING_SAVE_FAILED" }
    }
}
