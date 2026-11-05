package com.nsemomentum.paper

import android.app.NotificationManager
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import android.widget.FrameLayout
import org.junit.Assert.*
import org.junit.Test
import org.junit.Before
import org.robolectric.annotation.GraphicsMode
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File
import java.time.Instant

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class OpeningNotificationsTest {
    private val at=Instant.parse("2026-11-03T03:48:00Z")
    private val stock=Stock("DIXON","NSE_EQ|TEST")
    private fun row(sell:Boolean=false)=ReversalRow(stock,ReversalState(),null,"",OpeningState(day="2026-11-03",buy=if(sell) 100.0 else null,
        buyAt=if(sell) at.minusSeconds(60) else null,quantity=if(sell) 3 else 0,alert=if(sell) "KD_BEARISH" else "OPENING_BUY",alertAt=at),
        OpeningSample(at,true,102.0,101.0,100.0,32.5,24.8,101.5,100,140,true),candleVolume=CandleVolumeComparison(at.minusSeconds(900),140.0,100.0,1.4))
    private val quote=LiveQuote(stock.instrumentKey,102.0,100.0,at,at)
    @Before fun clearNotifications() {
        val context=RuntimeEnvironment.getApplication() as Context
        OpeningNotifications.update(context,row().copy(opening=OpeningState()),LivePriceState(),at)
        context.getSystemService(NotificationManager::class.java).cancelAll()
    }
    @Test fun noticeShowsPriceDailyChangeKdVolumeQuantityAndFixedExpiry() {
        val n=OpeningNoticeFormatter.create(row(),quote,at.plusSeconds(10),2)!!
        assertEquals("₹102.00",n.price);assertEquals("+2.00% today",n.change)
        assertTrue(n.metrics.contains("K 32.50"));assertTrue(n.metrics.contains("D 24.80"));assertTrue(n.metrics.contains("1.40×"))
        assertTrue(n.context.contains("₹204.00"));assertTrue(n.footer.contains("09:19:00 IST"));assertEquals(50000L,n.remainingMillis)
        assertNull(OpeningNoticeFormatter.create(row(),quote,at.plusSeconds(60),2))
        val missing=OpeningNoticeFormatter.create(row().copy(openingSample=null,candleVolume=null),null,at,1)!!
        assertEquals("Unavailable",missing.price);assertTrue(missing.metrics.contains("VOL 15m —"))
        val sell=OpeningNoticeFormatter.create(row(true),quote,at,9)!!
        assertEquals(3,sell.quantity);assertTrue(sell.context.contains("₹+6.00"));assertTrue(sell.reason.contains("K crossed below D"))
    }
    @Test fun notificationActionsArePaperBroadcastsAndUpdatesDoNotExtendOneMinuteExpiry() {
        val context=RuntimeEnvironment.getApplication() as Context
        context.getSharedPreferences("opening_notification_settings",0).edit().clear().commit()
        val live=LivePriceState(connected=true,quotes=mapOf(stock.instrumentKey to quote))
        OpeningNotifications.update(context,row(),live,at)
        val manager=context.getSystemService(NotificationManager::class.java)
        val n=manager.activeNotifications.single().notification
        assertEquals(2,n.actions.size);assertTrue(n.actions[0].title.toString().startsWith("BUY 1"));assertEquals("SKIP",n.actions[1].title)
        assertNotNull(n.contentView);assertNotNull(n.bigContentView)
        assertEquals(60000L,n.timeoutAfter)
        OpeningNotifications.update(context,row(),live,at.plusSeconds(20))
        assertEquals(40000L,manager.activeNotifications.single().notification.timeoutAfter)
        OpeningNotifications.update(context,row().copy(opening=OpeningState()),live,at.plusSeconds(21))
        assertTrue(manager.activeNotifications.isEmpty())
        val intent=OpeningNotifications.actionIntent(context,stock.instrumentKey,at,OpeningChoice.BUY,1)
        assertEquals(OpeningActionReceiver::class.java.name,intent.component!!.className)
        assertNull(intent.`package`)
        OpeningActionReceiver().onReceive(context,intent)
        assertNull(org.robolectric.Shadows.shadowOf(context as android.app.Application).nextStartedActivity)
        assertTrue(ReversalRunner.state.value.rows.isEmpty()) // stopped runner cannot replay a BUY
    }
    @Test fun expiredAndMissingIndicatorsNeverProduceFakeValues() {
        val n=OpeningNoticeFormatter.create(row().copy(candleVolume=null),quote,at,1)!!
        assertTrue(n.metrics.contains("VOL 15m —"))
        assertNull(OpeningNoticeFormatter.create(row(),quote,at.minusSeconds(1),1))
        assertNull(OpeningNoticeFormatter.create(row().copy(opening=OpeningState()),quote,at,1))
    }
    @Test fun renderExpandedBuyAndSellCardsForVisualReview() {
        val context=RuntimeEnvironment.getApplication() as Context
        val manager=context.getSystemService(NotificationManager::class.java)
        for(sell in listOf(false,true)) {
            OpeningNotifications.update(context,row(sell),LivePriceState(connected=true,quotes=mapOf(stock.instrumentKey to quote)),at)
            val n=manager.activeNotifications.single().notification
            val view=n.bigContentView.apply(context,FrameLayout(context))
            val width=(360*context.resources.displayMetrics.density).toInt()
            view.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(0,View.MeasureSpec.UNSPECIFIED))
            view.layout(0,0,view.measuredWidth,view.measuredHeight)
            assertTrue(view.measuredHeight>0)
            val bitmap=Bitmap.createBitmap(view.measuredWidth,view.measuredHeight,Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            assertTrue(android.graphics.Color.alpha(bitmap.getPixel(bitmap.width/2,bitmap.height/2))>0)
            val file=File("build/outputs/notification-previews/${if(sell) "sell" else "buy"}.png");file.parentFile!!.mkdirs()
            file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
            OpeningNotifications.update(context,row().copy(opening=OpeningState()),LivePriceState(),at)
        }
    }
}

