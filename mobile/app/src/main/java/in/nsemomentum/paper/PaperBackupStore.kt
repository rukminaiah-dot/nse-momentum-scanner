package com.nsemomentum.paper

import android.content.Context

/** Local-only storage adapter. History commits first; an interrupted preferences write can be retried. */
class PaperBackupStore(context: Context, private val database: CandleDatabase, private val base: List<Stock>) {
    private val preferences = context.getSharedPreferences("paper_preferences", Context.MODE_PRIVATE)
    fun export(): String = PaperBackup.encode(PaperBackup.Snapshot(
        preferences.getStringSet("favourites", emptySet()).orEmpty().toSet(),
        StockCatalog.decodeCustom(preferences.getString("custom_stocks", null), base),
        database.exportPaperHistory()
    )).also { PaperBackup.decode(it, base) }

    fun restore(encoded: String): PaperBackup.Snapshot {
        val incoming = PaperBackup.decode(encoded, base)
        val merged = PaperBackup.merge(incoming,
            preferences.getStringSet("favourites", emptySet()).orEmpty().toSet(),
            StockCatalog.decodeCustom(preferences.getString("custom_stocks", null), base), base)
        database.importPaperHistory(merged.history)
        check(preferences.edit().putStringSet("favourites", merged.favourites)
            .putString("custom_stocks", StockCatalog.encodeCustom(merged.custom)).commit())
        return merged
    }
}
