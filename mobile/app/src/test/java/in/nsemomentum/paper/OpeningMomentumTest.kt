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
    @Test fun everyEntryConditionAndFreshApprovalIsRequired() {
        val samples=listOf(sample(1,k=50.0),sample(1,k=28.0),sample(1,d=35.0),sample(1).copy(open=99.0),
            sample(1,price=101.0),sample(1).copy(price60=103.0),sample(1).copy(latestVolume=100),sample(1).copy(beforeVolume=0),
            sample(1).copy(continuous=false),sample(1).copy(fresh=false),sample(1).copy(open=null),sample(1).copy(k=null),
            sample(1).copy(at=Instant.parse("2026-11-03T03:46:59Z")),sample(1).copy(at=Instant.parse("2026-11-03T04:00:00Z")))
        samples.forEach { assertNull(OpeningMomentum.tick(seed(),it).alert) }
        val p=alert()
        assertNull(OpeningMomentum.approve(p,sample(2,k=31.0).copy(fresh=false),OpeningApproval("TEST",p.alertAt!!,OpeningChoice.BUY,1)).buy)
        assertNull(OpeningMomentum.approve(p,sample(2,k=31.0),OpeningApproval("TEST",p.alertAt!!.minusSeconds(1),OpeningChoice.BUY,1)).buy)
        for(q in listOf(0,-1,1000001)) assertNull(OpeningMomentum.approve(p,sample(2,k=31.0),OpeningApproval("TEST",p.alertAt!!,OpeningChoice.BUY,q)).buy)
    }
    @Test fun waitSkipExpiryAndDuplicateApprovalNeverPlaceTrade() {
        val p=alert();val command=OpeningApproval("TEST",p.alertAt!!,OpeningChoice.WAIT)
        val waited=OpeningMomentum.approve(p,sample(2,k=31.0),command)
        assertNull(waited.buy);assertNull(OpeningMomentum.tick(waited,sample(3,k=32.0)).alert)
        val skipped=OpeningMomentum.approve(p,sample(2,k=31.0),command.copy(choice=OpeningChoice.SKIP))
        assertTrue(skipped.skipped);assertNull(OpeningMomentum.tick(skipped,sample(3,k=32.0)).alert)
        assertNull(OpeningMomentum.approve(p,sample(40,k=31.0),command.copy(choice=OpeningChoice.BUY)).buy)
        val bought=OpeningMomentum.approve(p,sample(2,k=31.0),command.copy(choice=OpeningChoice.BUY,quantity=2))
        assertEquals(2,OpeningMomentum.approve(bought,sample(3,k=32.0),command.copy(choice=OpeningChoice.BUY,quantity=9)).quantity)
    }
    @Test fun thirtyPercentVolumeDropAndBearishCrossRequestSellButWaitHolds() {
        val active=OpeningState(day="2026-11-03",buy=102.0,buyAt=at,quantity=4,peak=102.0,boughtToday=true,previousK=30.0,previousD=29.0,previousAt=at)
        val volume=OpeningMomentum.tick(active,sample(1).copy(latestVolume=70))
        assertEquals("VOLUME_DROP_30_PERCENT",volume.alert);assertNotNull(volume.buy)
        val held=OpeningMomentum.approve(volume,sample(2,k=31.0).copy(latestVolume=70),OpeningApproval("TEST",volume.alertAt!!,OpeningChoice.WAIT))
        assertNotNull(held.buy);assertTrue(held.trades.isEmpty())
        val closed=OpeningMomentum.approve(volume,sample(2,k=31.0).copy(latestVolume=70),OpeningApproval("TEST",volume.alertAt!!,OpeningChoice.SELL))
        assertNull(closed.buy);assertEquals(4,closed.trades.single().quantity)
        assertEquals("KD_BEARISH",OpeningMomentum.tick(active,sample(1,k=28.0,d=29.0)).alert)
        assertNull(OpeningMomentum.tick(active,sample(1).copy(latestVolume=71)).alert)
        assertNull(OpeningMomentum.tick(closed,sample(3,k=32.0)).alert)
    }
    @Test fun stopsAndSessionExitStillRequireApprovalWithoutKd() {
        val active=OpeningState(day="2026-11-03",buy=100.0,buyAt=at,quantity=1,peak=100.75)
        val stop=OpeningMomentum.tick(active,sample(1,price=100.4).copy(k=null,d=null))
        assertEquals("PRICE_STOP",stop.alert);assertNotNull(stop.buy)
        val exit=OpeningMomentum.tick(active,sample(1).copy(at=Instant.parse("2026-11-03T09:40:00Z"),k=null,d=null))
        assertEquals("SESSION_1510",exit.alert);assertNotNull(exit.buy)
    }
    @Test fun priceWindowResetsOnReconnectAndRejectsInsufficientHistory() {
        val w=OpeningPriceWindow()
        for(i in 0L..120L) w.add(at.plusSeconds(i),100.0+i,1)
        assertEquals(160.0,w.previous(at.plusSeconds(120))!!,0.0)
        w.add(at.plusSeconds(121),221.0,2);assertNull(w.previous(at.plusSeconds(121)))
    }
}
