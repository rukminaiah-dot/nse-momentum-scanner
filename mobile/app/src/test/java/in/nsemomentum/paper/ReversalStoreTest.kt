package com.nsemomentum.paper

import android.content.Context
import java.time.Instant
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
class ReversalStoreTest {
    @Test fun restartKeepsPositionAndEightyLatchButDoesNotReplayOldCrossing() {
        val context=RuntimeEnvironment.getApplication() as Context
        context.getSharedPreferences("reversal_strategy_v1",0).edit().clear().commit()
        val now=Instant.parse("2026-10-30T05:00:00Z")
        val state=ReversalState(watchDate="2026-10-30",previousK=18.0,previousAt=now,buy=100.0,buyAt=now,reached80=true,symbol="TEST")
        ReversalStore(context).write(mapOf("NSE_EQ|TEST" to state))
        val restored=ReversalStore(context).read().getValue("NSE_EQ|TEST")
        assertEquals(100.0,restored.buy!!,0.0);assertTrue(restored.reached80)
        assertNull(restored.previousK);assertNull(restored.previousAt)
        assertEquals("TEST",restored.symbol)
        val exited=ReversalStrategy.tick(restored,102.0,79.0,70.0,now.plusSeconds(1))
        ReversalStore(context).write(mapOf("NSE_EQ|TEST" to exited))
        assertEquals(1,ReversalStore(context).read().getValue("NSE_EQ|TEST").trades.size)
        assertFalse(context.getSharedPreferences("paper_preferences",0).contains("reversal_state"))
    }
}
