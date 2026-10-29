package com.nsemomentum.paper

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

class ReversalStore(context: Context) {
    private val prefs = context.getSharedPreferences("reversal_strategy_v1",Context.MODE_PRIVATE)
    fun read(): Map<String,ReversalState> = runCatching {
        val root = JSONObject(prefs.getString("state","{}")!!)
        root.keys().asSequence().associateWith { key ->
            val row = root.getJSONObject(key)
            val closed = row.getJSONArray("trades")
            ReversalState(symbol=row.optString("symbol"),watchDate=row.optString("watch").takeIf { it.isNotEmpty() },
                buy=if (row.has("buy")) row.getDouble("buy").also { require(it.isFinite() && it > 0) } else null,
                buyAt=row.optString("buyAt").takeIf { it.isNotEmpty() }?.let(Instant::parse),
                reached80=row.optBoolean("reached80"),
                trades=(0 until closed.length()).map { i -> val t=closed.getJSONArray(i)
                    ReversalTrade(Instant.parse(t.getString(0)),t.getDouble(1),Instant.parse(t.getString(2)),t.getDouble(3),t.getString(4)) })
        }.also { states -> require(states.values.all { (it.buy == null) == (it.buyAt == null) }) }
    }.getOrDefault(emptyMap())
    fun write(states: Map<String,ReversalState>) {
        val root = JSONObject()
        states.forEach { (key,s) ->
            val row = JSONObject().put("symbol",s.symbol).put("reached80",s.reached80).put("trades",JSONArray().apply {
                s.trades.forEach { put(JSONArray(listOf(it.buyAt.toString(),it.buy,it.sellAt.toString(),it.sell,it.reason))) }
            })
            s.watchDate?.let { row.put("watch",it) }; s.buy?.let { row.put("buy",it) };s.buyAt?.let { row.put("buyAt",it.toString()) }
            root.put(key,row)
        }
        check(prefs.edit().putString("state",root.toString()).commit()) { "REVERSAL_SAVE_FAILED" }
    }
}
