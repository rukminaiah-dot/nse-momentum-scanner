package com.nsemomentum.paper

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class PaperBackupTest {
    private val base = listOf(Stock("BASE", "NSE_EQ|BASE"))
    private val custom = Stock("CUSTOM", "NSE_EQ|CUSTOM", true)
    private fun history() = JSONObject().apply {
        PaperBackup.tables.keys.forEach { put(it, JSONArray()) }
        getJSONArray("paper_outcomes").put(JSONObject()
            .put("symbol", "BASE").put("signal_time", "2026-10-22T04:00:00Z")
            .put("direction", 1).put("entry_time", "2026-10-22T04:15:00Z")
            .put("entry_price", 100.0).put("exit_price", 101.0).put("return_percent", 1.0))
        getJSONArray("pending_paper_signals").put(JSONObject()
            .put("symbol", "CUSTOM").put("direction", -1).put("signal_time", "2026-10-22T04:30:00Z"))
        getJSONArray("daily_qualifications").put(JSONObject()
            .put("symbol", "BASE").put("session_date", "2026-10-22")
            .put("first_seen", "2026-10-22T04:00:00Z").put("last_seen", "2026-10-22T04:30:00Z")
            .put("peak_rvol", 2.0).put("last_price", 100.0)
            .put("last_volume", JSONObject.NULL).put("average_slot_volume", 1000.0))
    }
    private fun snapshot() = PaperBackup.Snapshot(setOf("BASE", "CUSTOM"), listOf(custom), history())
    private fun rejects(block: () -> Unit) {
        try { block(); fail("Expected rejection") } catch (_: IllegalArgumentException) { }
    }
    @Test fun roundTripAllDataAndNoTokenOrCache() {
        val context = RuntimeEnvironment.getApplication() as Context
        context.deleteDatabase("paper_candles.db")
        context.getSharedPreferences("paper_preferences", 0).edit().putString("token", "SECRET_SENTINEL").commit()
        CandleDatabase(context).use { db ->
            db.importPaperHistory(snapshot().history)
            val encoded = PaperBackup.encode(snapshot().copy(history = db.exportPaperHistory()))
            assertFalse(encoded.contains("SECRET_SENTINEL"))
            assertFalse(encoded.contains("candles"))
            val decoded = PaperBackup.decode(encoded, base)
            assertEquals(snapshot().favourites, decoded.favourites)
            assertEquals(snapshot().custom, decoded.custom)
            db.clearAll()
            db.importPaperHistory(decoded.history)
            db.importPaperHistory(decoded.history)
            val exported = db.exportPaperHistory()
            PaperBackup.tables.keys.forEach { table ->
                assertEquals(1, exported.getJSONArray(table).length())
                assertTrue(history().getJSONArray(table).getJSONObject(0).similar(exported.getJSONArray(table).getJSONObject(0)))
            }
            assertEquals("SECRET_SENTINEL", context.getSharedPreferences("paper_preferences", 0).getString("token", null))
        }
    }
    @Test fun invalidAndFutureFilesAreRejectedBeforeImport() {
        val valid = PaperBackup.encode(snapshot())
        rejects { PaperBackup.decode(JSONObject(valid).put("version", 2).toString(), base) }
        rejects { PaperBackup.decode(JSONObject(valid).put("token", "not-allowed").toString(), base) }
        rejects { PaperBackup.decode(JSONObject(valid).put("favourites", JSONArray(listOf("BASE", "BASE"))).toString(), base) }
        rejects { PaperBackup.decode(" ".repeat(PaperBackup.MAX_BYTES + 1), base) }
        val bad = snapshot()
        bad.history.getJSONArray("paper_outcomes").getJSONObject(0).put("entry_price", -1)
        rejects { PaperBackup.decode(PaperBackup.encode(bad), base) }
        val duplicate = snapshot()
        val rows = duplicate.history.getJSONArray("paper_outcomes")
        rows.put(rows.getJSONObject(0))
        rejects { PaperBackup.decode(PaperBackup.encode(duplicate), base) }
    }
    @Test fun mergeIsIdempotentAndRejectsConflictsAndOverflow() {
        val incoming = snapshot()
        assertEquals(incoming.custom, PaperBackup.merge(incoming, incoming.favourites, incoming.custom, base).custom)
        rejects { PaperBackup.merge(incoming, emptySet(), listOf(custom.copy(instrumentKey = "NSE_EQ|OTHER")), base) }
        rejects { PaperBackup.merge(incoming, (1..20).map { "S$it" }.toSet(), emptyList(), base) }
    }
    @Test fun databaseImportRollsBackOnFailureAndPreservesExistingRows() {
        val context = RuntimeEnvironment.getApplication() as Context
        context.deleteDatabase("paper_candles.db")
        CandleDatabase(context).use { db ->
            db.importPaperHistory(history())
            val changed = history()
            changed.getJSONArray("paper_outcomes").getJSONObject(0).put("exit_price", 999)
            db.importPaperHistory(changed)
            assertEquals(101.0, db.exportPaperHistory().getJSONArray("paper_outcomes").getJSONObject(0).getDouble("exit_price"), 0.0)
            db.clearAll()
            val bad = history().apply { remove("paper_outcomes") }
            try { db.importPaperHistory(bad); fail("Expected failure") } catch (_: org.json.JSONException) { }
            PaperBackup.tables.keys.forEach { assertEquals(0, db.exportPaperHistory().getJSONArray(it).length()) }
        }
    }
}
