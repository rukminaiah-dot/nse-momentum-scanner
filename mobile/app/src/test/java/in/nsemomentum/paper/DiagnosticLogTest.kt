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
    @Test fun exportsSafeCodesAndDropsUntrustedMetadata() {
        val context = RuntimeEnvironment.getApplication() as Context
        java.io.File(context.filesDir,"diagnostics").deleteRecursively()
        DiagnosticLog.record(context,"API_REQUEST","SUCCESS","rows=3")
        DiagnosticLog.record(context,"Bearer secret-one","secret-two","Authorization secret-three")
        val exported = DiagnosticLog.export(context)
        assertTrue(exported.contains("API_REQUEST SUCCESS rows=3"))
        assertFalse(exported.contains("secret-one"))
        assertFalse(exported.contains("secret-two"))
        assertFalse(exported.contains("secret-three"))
    }
}
