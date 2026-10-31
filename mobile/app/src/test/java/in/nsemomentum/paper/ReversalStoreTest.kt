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
    @Test fun restartKeepsPeakAndEntryVolumeButCannotReplayPendingConfirmation() {
        val context=RuntimeEnvironment.getApplication() as Context
        context.getSharedPreferences("reversal_strategy_v1",0).edit().clear().commit()
        val now=Instant.parse("2026-10-30T05:00:00Z")
        val s=ReversalState(buy=100.0,buyAt=now,peakPrice=101.0,beforeVolume=100,afterVolume=150,symbol="TEST",confirmationAt=now,previousK=25.0,previousAt=now)
        ReversalStore(context).write(mapOf("NSE_EQ|TEST" to s))
        val restored=ReversalStore(context).read().getValue("NSE_EQ|TEST")
        assertEquals(101.0,restored.peakPrice!!,0.0);assertEquals(100L,restored.beforeVolume!!)
        assertNull(restored.previousK);assertNull(restored.confirmationAt)
        assertEquals(100.75,ReversalStrategy.stopPrice(restored)!!,1e-8)
        val closed=ReversalStrategy.tick(restored,100.7,null,null,now.plusSeconds(1))
        ReversalStore(context).write(mapOf("NSE_EQ|TEST" to closed))
        val t=ReversalStore(context).read().getValue("NSE_EQ|TEST").trades.single()
        assertEquals("VOLUME_STEP_V2",t.policy);assertEquals(150L,t.afterVolume!!)
    }
    @Test fun readsOldTradeShapeWithoutInventingPastPeakProfit() {
        val context=RuntimeEnvironment.getApplication() as Context
        context.getSharedPreferences("reversal_strategy_v1",0).edit().putString("state",
            """{"NSE_EQ|TEST":{"symbol":"TEST","buy":100.0,"buyAt":"2026-10-30T05:00:00Z","reached80":true,"trades":[["2026-10-29T05:00:00Z",100.0,"2026-10-29T06:00:00Z",101.0,"K_BACK_BELOW_80"]]}}""").commit()
        val restored=ReversalStore(context).read().getValue("NSE_EQ|TEST")
        assertNull(restored.peakPrice)
        assertEquals(99.0,ReversalStrategy.stopPrice(restored)!!,0.0)
        assertEquals("LEGACY_80",restored.trades.single().policy)
    }
}
