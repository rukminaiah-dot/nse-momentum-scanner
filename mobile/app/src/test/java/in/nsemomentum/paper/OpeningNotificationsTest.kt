package com.nsemomentum.paper

import android.app.NotificationManager
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import android.widget.FrameLayout
import org.junit.Assert.*
import org.junit.Test
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
    private val row=ReversalRow(stock,ReversalState(),null,"",
        OpeningState(day="2026-11-03",buy=102.0,buyAt=at,quantity=2,boughtToday=true,automatic=true),
        OpeningSample(at,true,102.0,101.0,100.0,32.5,24.8,101.5,100,140,true),
        candleVolume=CandleVolumeComparison(at.minusSeconds(900),140.0,100.0,1.4))
    private val quote=LiveQuote(stock.instrumentKey,103.0,100.0,at.plusSeconds(1),at.plusSeconds(1))

    @Test fun noticeUsesRecordedFillPriceAndQuantity() {
        val n=OpeningNoticeFormatter.create(row,quote)!!
        assertEquals("₹102.00",n.price)
        assertTrue(n.metrics.contains("K 32.50"))
        assertTrue(n.metrics.contains("D 24.80"))
        assertTrue(n.metrics.contains("1.40×"))
        assertTrue(n.context.contains("Qty 2"))
        assertTrue(n.context.contains("₹204.00"))
        assertTrue(n.footer.contains("09:18:00 IST"))
        val missing=OpeningNoticeFormatter.create(row.copy(openingSample=null,candleVolume=null),null)!!
        assertEquals("₹102.00",missing.price)
        assertTrue(missing.metrics.contains("VOL 15m —"))
        assertNull(OpeningNoticeFormatter.create(row.copy(opening=OpeningState()),quote))
    }

    @Test fun confirmedBuyNotificationHasNoApprovalActionsAndRenders() {
        val context=RuntimeEnvironment.getApplication() as Context
        val manager=context.getSystemService(NotificationManager::class.java)
        manager.cancelAll()
        OpeningNotifications.postBuy(context,row,quote)
        val n=manager.activeNotifications.single().notification
        assertTrue(n.actions.isNullOrEmpty())
        assertNotNull(n.contentView)
        assertEquals(60000L,n.timeoutAfter)
        val view=n.bigContentView.apply(context,FrameLayout(context))
        val width=(360*context.resources.displayMetrics.density).toInt()
        view.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(0,View.MeasureSpec.UNSPECIFIED))
        view.layout(0,0,view.measuredWidth,view.measuredHeight)
        assertTrue(view.measuredHeight>0)
        val bitmap=Bitmap.createBitmap(view.measuredWidth,view.measuredHeight,Bitmap.Config.ARGB_8888)
        view.draw(Canvas(bitmap))
        assertTrue(android.graphics.Color.alpha(bitmap.getPixel(bitmap.width/2,bitmap.height/2))>0)
        val file=File("build/outputs/notification-previews/buy.png")
        file.parentFile!!.mkdirs()
        file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
    }
}
