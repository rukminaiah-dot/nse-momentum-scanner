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
}
