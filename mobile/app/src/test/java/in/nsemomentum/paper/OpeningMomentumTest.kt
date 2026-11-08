package com.nsemomentum.paper

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class OpeningMomentumTest {
    private val at=Instant.parse("2026-11-03T03:48:00Z") // 09:18 IST
    private fun sample(seconds:Long=0,k:Double=30.0,d:Double=20.0,price:Double=102.0)=OpeningSample(at.plusSeconds(seconds),true,price,101.0,100.0,k,d,101.5,100,130,true)
    private fun seed()=OpeningMomentum.tick(OpeningState(),sample(k=29.0))
    private fun alert()=OpeningMomentum.tick(seed(),sample(1))
    @Test fun qualifiesWithoutCrossTwentyButCannotBuyWithoutApproval() {
        val pending=alert();assertEquals("OPENING_BUY",pending.alert);assertNull(pending.buy)
        val buy=OpeningMomentum.approve(pending,sample(2,k=31.0),OpeningApproval("TEST",pending.alertAt!!,OpeningChoice.BUY,5))
        assertEquals(102.0,buy.buy!!,0.0);assertEquals(5,buy.quantity);assertTrue(buy.boughtToday)
        assertNull(buy.alert)
    }
    @Test fun openingKMustBeStrictlyBetweenTwentyAndFiftyAtAlertAndApproval() {
        for(k in listOf(0.0,19.99,20.0,50.0,50.01,100.0)) {
            val first=OpeningMomentum.tick(OpeningState(),sample(k=(k-1).coerceAtLeast(0.0),d=0.0))
            assertNull("Rejected K=$k",OpeningMomentum.tick(first,sample(1,k=k,d=0.0)).alert)
        }
        for(k in listOf(20.01,49.99)) {
            val first=OpeningMomentum.tick(OpeningState(),sample(k=k-1,d=10.0))
            assertEquals("OPENING_BUY",OpeningMomentum.tick(first,sample(1,k=k,d=10.0)).alert)
        }
        val p=alert()
        for(k in listOf(20.0,50.0)) assertNull(OpeningMomentum.approve(p,sample(2,k=k,d=10.0),OpeningApproval("TEST",p.alertAt!!,OpeningChoice.BUY,1)).buy)
    }
    @Test fun approvalLastsOneMinuteAndRejectsTheExactExpiryBoundary() {
        var p=alert()
        for(i in 2L..59L) p=OpeningMomentum.tick(p,sample(i,k=30.0))
        assertNotNull(p.alert)
        val approved=OpeningMomentum.approve(p,sample(60,k=31.0),OpeningApproval("TEST",p.alertAt!!,OpeningChoice.BUY,1))
        assertNotNull(approved.buy)
        val expired=OpeningMomentum.approve(p,sample(61,k=31.0),OpeningApproval("TEST",p.alertAt!!,OpeningChoice.BUY,1))
        assertNull(expired.buy)
    }
    @Test fun everyEntryConditionAndFreshApprovalIsRequired() {
        val samples=listOf(sample(1,k=50.0),sample(1,k=28.0),sample(1,d=35.0),sample(1).copy(open=99.0),
            sample(1).copy(fresh=false),sample(1).copy(open=null),sample(1).copy(k=null),
            sample(1).copy(at=Instant.parse("2026-11-03T03:46:59Z")),sample(1).copy(at=Instant.parse("2026-11-03T04:00:00Z")))
        samples.forEach { assertNull(OpeningMomentum.tick(seed(),it).alert) }
        val p=alert()
        assertNull(OpeningMomentum.approve(p,sample(2,k=31.0).copy(fresh=false),OpeningApproval("TEST",p.alertAt!!,OpeningChoice.BUY,1)).buy)
        assertNull(OpeningMomentum.approve(p,sample(2,k=31.0),OpeningApproval("TEST",p.alertAt!!.minusSeconds(1),OpeningChoice.BUY,1)).buy)
        for(q in listOf(0,-1,1000001)) assertNull(OpeningMomentum.approve(p,sample(2,k=31.0),OpeningApproval("TEST",p.alertAt!!,OpeningChoice.BUY,q)).buy)
    }
    @Test fun buyAllowsFallingPriceBelowOpenAndMissingPriceWindow() {
        for(s in listOf(sample(1,price=100.5).copy(price60=103.0),sample(1,price=100.0).copy(price60=null))) {
            val pending=OpeningMomentum.tick(seed(),s)
            assertEquals("OPENING_BUY",pending.alert)
            assertNotNull(OpeningMomentum.approve(pending,s.copy(at=s.at.plusSeconds(1),k=31.0),OpeningApproval("TEST",pending.alertAt!!,OpeningChoice.BUY)).buy)
        }
        assertNull(OpeningMomentum.tick(seed(),sample(1).copy(open=100.0,previousClose=100.0)).alert)
        assertNull(OpeningMomentum.tick(seed(),sample(1,k=28.0)).alert)
    }
    @Test fun buyDoesNotRequireAvailableRisingOrContinuousVolume() {
        for(s in listOf(sample(1).copy(beforeVolume=null,latestVolume=null,continuous=false),
            sample(1).copy(beforeVolume=100,latestVolume=0,continuous=true),sample(1).copy(beforeVolume=0,latestVolume=0,continuous=false))) {
            val pending=OpeningMomentum.tick(seed(),s)
            assertEquals("OPENING_BUY",pending.alert)
            assertNotNull(OpeningMomentum.approve(pending,s.copy(at=s.at.plusSeconds(1),k=31.0),OpeningApproval("TEST",pending.alertAt!!,OpeningChoice.BUY)).buy)
        }
    }
    @Test fun waitSkipExpiryAndDuplicateApprovalNeverPlaceTrade() {
        val p=alert();val command=OpeningApproval("TEST",p.alertAt!!,OpeningChoice.WAIT)
        val waited=OpeningMomentum.approve(p,sample(2,k=31.0),command)
        assertNull(waited.buy);assertNull(OpeningMomentum.tick(waited,sample(3,k=32.0)).alert)
        val skipped=OpeningMomentum.approve(p,sample(2,k=31.0),command.copy(choice=OpeningChoice.SKIP))
        assertTrue(skipped.skipped);assertNull(OpeningMomentum.tick(skipped,sample(3,k=32.0)).alert)
        assertNull(OpeningMomentum.approve(p,sample(61,k=31.0),command.copy(choice=OpeningChoice.BUY)).buy)
        val bought=OpeningMomentum.approve(p,sample(2,k=31.0),command.copy(choice=OpeningChoice.BUY,quantity=2))
        assertEquals(2,OpeningMomentum.approve(bought,sample(3,k=32.0),command.copy(choice=OpeningChoice.BUY,quantity=9)).quantity)
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

