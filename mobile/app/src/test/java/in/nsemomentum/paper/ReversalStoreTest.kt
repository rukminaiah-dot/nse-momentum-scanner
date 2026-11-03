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
        val s=ReversalState(buy=100.0,buyAt=now,identifiedAt=now,peakPrice=101.0,beforeVolume=100,afterVolume=150,symbol="TEST",confirmationAt=now,previousK=25.0,previousAt=now)
        ReversalStore(context).write(mapOf("NSE_EQ|TEST" to s))
        val restored=ReversalStore(context).read().getValue("NSE_EQ|TEST")
        assertEquals(101.0,restored.peakPrice!!,0.0);assertEquals(100L,restored.beforeVolume!!)
        assertNull(restored.previousK);assertNull(restored.confirmationAt)
        assertEquals(now,restored.identifiedAt)
        assertEquals(100.75,ReversalStrategy.stopPrice(restored)!!,1e-8)
        val closed=ReversalStrategy.tick(restored,100.7,null,null,now.plusSeconds(1))
        ReversalStore(context).write(mapOf("NSE_EQ|TEST" to closed))
        val t=ReversalStore(context).read().getValue("NSE_EQ|TEST").trades.single()
        assertEquals("VOLUME_STEP_V2",t.policy);assertEquals(150L,t.afterVolume!!)
    }
    @Test fun restartKeepsManualApprovalAndQuantitySoStopsCannotAutoCloseIt() {
        val context=RuntimeEnvironment.getApplication() as Context
        val at=Instant.parse("2026-11-03T04:00:00Z")
        val store=ReversalStore(context)
        val manual=ReversalState(buy=100.0,buyAt=at,quantity=4,manual=true,recordedAt=at,peakPrice=101.0)
        store.write(mapOf("TEST" to manual))
        val saved=store.read().getValue("TEST")
        assertTrue(saved.manual);assertEquals(4,saved.quantity);assertEquals(at,saved.recordedAt)
        val exit=ReversalStrategy.tick(saved,98.0,null,null,at.plusSeconds(1))
        assertNotNull(exit.buy);assertTrue(exit.trades.isEmpty())
        val closed=PaperRecordEdits.reversal(exit,PaperRecordEdit("TEST",PaperSource.REVERSAL,PaperOperation.SELL,at,99.0,4),at.plusSeconds(2),false,null,null)
        store.write(mapOf("TEST" to closed))
        val trade=store.read().getValue("TEST").trades.single()
        assertTrue(trade.manual);assertEquals(4,trade.quantity);assertEquals(-4.0,trade.gross,0.0)
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
