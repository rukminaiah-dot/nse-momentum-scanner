package com.nsemomentum.paper

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class OpeningMomentumTest {
    private val at=Instant.parse("2026-11-03T03:48:00Z") // 09:18 IST
    private fun sample(seconds:Long=0,k:Double=30.0,d:Double=20.0,price:Double=102.0)=OpeningSample(at.plusSeconds(seconds),true,price,101.0,100.0,k,d,101.5,100,130,true)
    private fun seed()=OpeningMomentum.tick(OpeningState(),sample(k=29.0))
    @Test fun qualifyingTickRecordsOneAutomaticBuyAtObservedPrice() {
        val buy = OpeningMomentum.tick(seed(),sample(1),quantity=5)
        assertEquals(102.0,buy.buy!!,0.0)
        assertEquals(at.plusSeconds(1),buy.buyAt)
        assertEquals(5,buy.quantity)
        assertTrue(buy.automatic)
        val held = OpeningMomentum.tick(buy,sample(2,k=31.0,price=101.9),quantity=7)
        assertEquals(buy.buyAt,held.buyAt)
        assertEquals(5,held.quantity)
        val sold = OpeningMomentum.tick(held,sample(3,k=30.0,d=31.0))
        assertTrue(sold.trades.single().automatic)
        assertNull(OpeningMomentum.tick(sold,sample(4,k=32.0)).buy)
    }
    @Test fun openingKMustBeStrictlyBetweenTwentyAndFifty() {
        for(k in listOf(0.0,19.99,20.0,50.0,50.01,100.0)) {
            val first=OpeningMomentum.tick(OpeningState(),sample(k=(k-1).coerceAtLeast(0.0),d=0.0))
            assertNull("Rejected K=$k",OpeningMomentum.tick(first,sample(1,k=k,d=0.0)).buy)
        }
        for(k in listOf(20.01,49.99)) {
            val first=OpeningMomentum.tick(OpeningState(),sample(k=k-1,d=10.0))
            assertNotNull(OpeningMomentum.tick(first,sample(1,k=k,d=10.0)).buy)
        }
    }
    @Test fun entryStillRequiresFreshConsecutiveReadingsAndPositiveOpenInWindow() {
        val initial=seed()
        val candidate=sample(1)
        val rejected=listOf(candidate.copy(fresh=false),candidate.copy(price=null),candidate.copy(k=null),
            candidate.copy(d=31.0),candidate.copy(open=100.0),candidate.copy(open=null),candidate.copy(k=29.0),
            candidate.copy(at=at.plusSeconds(6)))
        rejected.forEach { assertNull(OpeningMomentum.tick(initial,it).buy) }
        val gap=OpeningMomentum.tick(initial,candidate.copy(fresh=false))
        assertNull(OpeningMomentum.tick(gap,sample(2,k=31.0)).buy)
        for (time in listOf("03:46:59Z","04:00:00Z")) {
            val outside=Instant.parse("2026-11-03T$time")
            val previous=OpeningMomentum.tick(OpeningState(),sample(k=29.0).copy(at=outside.minusSeconds(1)))
            assertNull(OpeningMomentum.tick(previous,candidate.copy(at=outside)).buy)
        }
    }
    @Test fun priceRelativeToOpenAndPriorMinuteAndVolumeDoNotFilterBuy() {
        for (price in listOf(100.5,101.0,102.0)) {
            val candidate=sample(1,price=price).copy(price60=null,beforeVolume=100,latestVolume=0,volumeRatio=0.5)
            assertEquals(price,OpeningMomentum.tick(seed(),candidate).buy!!,0.0)
        }
    }
    @Test fun weakVolumeBeforeProfitReviewHoldsAndBearishReadingAutomaticallySells() {
        val active=OpeningState(day="2026-11-03",buy=102.0,buyAt=at,quantity=4,peak=102.0,boughtToday=true)
        val held=OpeningMomentum.tick(active,sample(1).copy(volumeRatio=0.8))
        assertNotNull(held.buy)
        val closed=OpeningMomentum.tick(held,sample(2,k=31.0,d=32.0))
        assertNull(closed.buy)
        assertEquals("KD_BEARISH",closed.trades.single().reason)
        assertEquals(4,closed.trades.single().quantity)
    }
    @Test fun stopAndVolumeExitAndSessionCutoffCloseAutomatically() {
        val active=OpeningState(day="2026-11-03",buy=100.0,buyAt=at,quantity=1,peak=100.75)
        val quote=sample(1,price=100.4).copy(k=null,d=null)
        assertNotNull(OpeningMomentum.tick(active,quote).buy)
        val stopped=OpeningMomentum.tick(active,quote.copy(price=99.0))
        assertEquals("STOP_1_PERCENT",stopped.trades.single().reason)
        val armed=OpeningMomentum.tick(active,quote.copy(price=102.0,volumeRatio=1.5))
        assertNotNull(armed.buy)
        val closed=OpeningMomentum.tick(armed,quote.copy(at=at.plusSeconds(2),price=101.5,volumeRatio=1.49))
        assertEquals("VOLUME_BELOW_1_5X_AFTER_2_PERCENT",closed.trades.single().reason)
        assertEquals(101.5,closed.trades.single().sell,0.0)
        val exit=OpeningMomentum.tick(active,quote.copy(at=Instant.parse("2026-11-03T09:40:00Z")))
        assertEquals("SESSION_1510",exit.trades.single().reason)
    }
    @Test fun priceWindowResetsOnReconnectAndRejectsInsufficientHistory() {
        val w=OpeningPriceWindow()
        for(i in 0L..120L) w.add(at.plusSeconds(i),100.0+i,1)
        assertEquals(160.0,w.previous(at.plusSeconds(120))!!,0.0)
        w.add(at.plusSeconds(121),221.0,2);assertNull(w.previous(at.plusSeconds(121)))
    }
}

