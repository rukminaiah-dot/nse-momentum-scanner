package com.nsemomentum.paper

import android.content.Context
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class InstrumentSelectionStoreTest {
    private val base = listOf(Stock("RELIANCE", "NSE_EQ|INE002A01018")) + StockCatalog.indices
    private fun store(): InstrumentSelectionStore {
        val context = RuntimeEnvironment.getApplication() as Context
        context.getSharedPreferences("paper_preferences", 0).edit().clear().commit()
        return InstrumentSelectionStore(context, base)
    }
    private val bse = SearchInstrument("RELIANCE", "Reliance Industries", "BSE", "BSE_EQ|INE002A01018")
    @Test fun addRemoveReAddAndDeleteSurviveStoreRecreationWithoutTouchingToken() {
        val context = RuntimeEnvironment.getApplication() as Context
        val store = store()
        context.getSharedPreferences("paper_preferences", 0).edit().putString("token", "TOKEN_SENTINEL").commit()
        assertEquals(setOf("RELIANCE_BSE"), store.add(bse, 0).active)
        val reopened = InstrumentSelectionStore(context, base)
        assertEquals("BSE_EQ|INE002A01018", reopened.read().catalog.single { it.isCustom }.instrumentKey)
        assertTrue(reopened.setActive("RELIANCE_BSE", false).active.isEmpty())
        assertEquals(1, reopened.read().catalog.count { it.isCustom })
        assertEquals(setOf("RELIANCE_BSE"), reopened.add(bse, 0).active)
        val deleted = reopened.deleteCustom("RELIANCE_BSE")
        assertTrue(deleted.active.isEmpty()); assertEquals(base, deleted.catalog)
        assertEquals("TOKEN_SENTINEL", context.getSharedPreferences("paper_preferences", 0).getString("token", null))
    }
    @Test fun failedSelectionDoesNotChangeSavedList() {
        val store = store(); store.setActive("BANKNIFTY", true)
        val before = store.read()
        try { store.add(bse, 301); fail("Expected expiry rejection") } catch (_: IllegalArgumentException) { }
        assertEquals(before, store.read())
        try { store.deleteCustom("BANKNIFTY"); fail("Cannot delete built-in") } catch (_: IllegalArgumentException) { }
        assertEquals(before, store.read())
    }
    @Test fun selectedBseAndIndexRoundTripThroughBackupRules() {
        val store = store(); store.add(bse, 0); store.setActive("BANKNIFTY", true)
        val snapshot = store.read()
        val history = org.json.JSONObject().apply { PaperBackup.tables.keys.forEach { put(it, org.json.JSONArray()) } }
        val saved = PaperBackup.Snapshot(snapshot.active, snapshot.catalog.filter { it.isCustom }, history)
        assertEquals(saved.favourites, PaperBackup.decode(PaperBackup.encode(saved), base).favourites)
    }
}
