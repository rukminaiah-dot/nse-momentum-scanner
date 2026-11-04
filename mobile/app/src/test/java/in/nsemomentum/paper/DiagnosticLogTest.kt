package com.nsemomentum.paper

import android.content.Context
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
class DiagnosticLogTest {
    @Test fun fullLogStillAcceptsNewHealthAndFailureEvents() {
        val context=RuntimeEnvironment.getApplication() as Context
        val dir=java.io.File(context.filesDir,"diagnostics").apply { mkdirs() }
        java.io.File(dir,"${java.time.LocalDate.now(MarketSession.ZONE)}.log").writeText("OLD_EVENT\n".repeat(30000))
        DiagnosticLog.record(context,"REVERSAL_HEALTH","CHECKED","kd=3 volume=1")
        assertTrue(DiagnosticLog.export(context).contains("REVERSAL_HEALTH CHECKED kd=3 volume=1"))
    }
    @Test fun exportsSafeCodesAndDropsUntrustedMetadata() {
        val context = RuntimeEnvironment.getApplication() as Context
        java.io.File(context.filesDir,"diagnostics").deleteRecursively()
        DiagnosticLog.record(context,"API_REQUEST","SUCCESS","rows=3")
        DiagnosticLog.record(context,"REVERSAL_HEALTH","CHECKED","fresh=3 kd=2 volume=1")
        DiagnosticLog.record(context,"Bearer secret-one","secret-two","Authorization secret-three")
        val exported = DiagnosticLog.export(context)
        assertFalse(exported.contains("API_REQUEST SUCCESS"))
        assertTrue(exported.contains("REVERSAL_HEALTH CHECKED fresh=3 kd=2 volume=1"))
        assertFalse(exported.contains("secret-one"))
        assertFalse(exported.contains("secret-two"))
        assertFalse(exported.contains("secret-three"))
    }

    @Test fun allMissingSlotsFitExportAndDuplicateErrorsKeepTheirCode() {
        val context=RuntimeEnvironment.getApplication() as Context
        java.io.File(context.filesDir,"diagnostics").deleteRecursively()
        val date=java.time.LocalDate.parse("2026-11-03")
        val session=MarketSession(date,date.atTime(9,15).atZone(MarketSession.ZONE).toInstant(),date.atTime(15,30).atZone(MarketSession.ZONE).toInstant())
        HistoryDiagnostics.day("BLOCKED",session,emptyList(),"TCS",{e,r,n,s -> DiagnosticLog.record(context,e,r,n,s)})
        val exported=DiagnosticLog.export(context)
        assertTrue(exported.contains("date=2026-11-03 expected=25 received=0 missing=25 extra=0 invalid=0 duplicate=0 symbol=TCS"))
        val slots=session.slots().joinToString(",") { val t=it.atZone(MarketSession.ZONE); "%02d%02d".format(java.util.Locale.ROOT,t.hour,t.minute) }
        assertTrue(exported.contains("date=2026-11-03 slots=$slots symbol=TCS"))
        assertEquals("DUPLICATE_CANDLE",DiagnosticLog.errorCode(java.io.IOException("DUPLICATE_CANDLE")))
        assertEquals("REQUEST_FAILED",DiagnosticLog.errorCode(java.io.IOException("Bearer private-token")))
    }
}
