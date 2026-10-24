package com.nsemomentum.paper

import android.content.Context
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.time.Instant

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class IndexSnapshotStoreTest {
    private val now = Instant.parse("2026-10-23T05:00:01Z")
    @Test fun indexSnapshotPersistsSeparatelyAndExpiresWithoutChangingStockSelectionsOrToken() {
        val context = RuntimeEnvironment.getApplication() as Context
        val prefs = context.getSharedPreferences("paper_preferences", 0)
        prefs.edit().clear().putString("token", "PRIVATE_TOKEN_SENTINEL").putStringSet("favourites", setOf("ICICIBANK", "MARUTI")).commit()
        val store = IndexSnapshotStore(context); store.clear()
        val rows = StockCatalog.indices.map { IndexReading(it.symbol, IndexDataState.LIVE, bar(now.minusSeconds(301), 0.0), TechnicalContext(10.5, 10.5, 50.0, 50.0), 10.5, 0.0, "BULLISH", "THREE_COMPLETED_5M_CLOSES") }
        store.write(IndexMarketReport(rows, now))
        assertEquals(rows, IndexSnapshotStore(context).read(now)!!.rows)
        assertTrue(IndexSnapshotStore(context).read(now.plusSeconds(1200))!!.rows.all { it.state == IndexDataState.STALE && it.signal == "WAIT" })
        assertEquals(setOf("ICICIBANK", "MARUTI"), prefs.getStringSet("favourites", emptySet()))
        val encoded = context.getSharedPreferences("index_snapshot", 0).getString("report", "")!!
        assertFalse(encoded.contains("PRIVATE_TOKEN_SENTINEL")); assertFalse(encoded.contains("relativeVolume"))
        store.clear(); assertNull(store.read(now)); assertEquals("PRIVATE_TOKEN_SENTINEL", prefs.getString("token", null))
    }
    @Test fun corruptedOrMixedInstrumentSnapshotIsRejected() {
        val context = RuntimeEnvironment.getApplication() as Context
        val prefs = context.getSharedPreferences("index_snapshot", 0)
        prefs.edit().putString("report", "not-json").commit()
        assertNull(IndexSnapshotStore(context).read(now))
        prefs.edit().putString("report", """{"version":1,"checkedAt":"$now","rows":[]}""").commit()
        assertNull(IndexSnapshotStore(context).read(now))
    }
}
