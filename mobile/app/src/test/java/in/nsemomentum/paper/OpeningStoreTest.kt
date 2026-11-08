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
@Config(sdk=[28])
class OpeningStoreTest {
    @Test fun restartKeepsQuantityPositionAndDailyLimit() {
        val context=RuntimeEnvironment.getApplication() as Context
        context.getSharedPreferences("opening_momentum_paper_v1",0).edit().clear().commit()
        val at=Instant.parse("2026-11-03T03:48:00Z")
        val s=OpeningState(day="2026-11-03",boughtToday=true,buy=100.0,buyAt=at,quantity=5,peak=101.0,automatic=true,previousK=40.0)
        OpeningStore(context).write(mapOf("TEST" to s))
        val r=OpeningStore(context).read().getValue("TEST")
        assertEquals(5,r.quantity);assertTrue(r.boughtToday);assertEquals(101.0,r.peak!!,0.0)
        assertTrue(r.automatic);assertNull(r.previousK)
        val trade=OpeningTrade(at,100.0,at.plusSeconds(60),101.0,5,"PRICE_STOP",automatic=true)
        OpeningStore(context).write(mapOf("TEST" to r.copy(buy=null,buyAt=null,quantity=0,trades=listOf(trade))))
        val closed=OpeningStore(context).read().getValue("TEST")
        assertTrue(closed.boughtToday);assertTrue(closed.trades.single().automatic);assertEquals(5.0,closed.trades.single().gross,0.0)
    }
}

