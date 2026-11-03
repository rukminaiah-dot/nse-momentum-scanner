package com.nsemomentum.paper

import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import java.io.File
import java.time.Instant
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[35],qualifiers="w360dp-h800dp-xxhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@OptIn(androidx.compose.ui.test.ExperimentalTestApi::class)
class CompactPageTest {
    @get:Rule val compose=createComposeRule()
    private lateinit var pageView:android.view.View
    @Test fun unifiedPageExpandsAndOpensManualPriceForm() {
        val now=Instant.now()
        val sample=OpeningSample(now,true,1030.0,1026.0,1020.0,18.5,25.8,1032.0,10000,6500,true)
        val trade=OpeningTrade(now.minusSeconds(300),100.0,now.minusSeconds(100),101.0,2,"MANUAL_SELL")
        val opening=OpeningState(day=now.atZone(MarketSession.ZONE).toLocalDate().toString(),trades=listOf(trade))
        val state=ReversalState(buy=1024.0,buyAt=now.minusSeconds(60),manual=true,quantity=2,peakPrice=1034.0,action="SELL_REQUIRED_STOP_1_PERCENT")
        val row=ReversalRow(Stock("HDFCBANK","NSE_EQ|TEST"),state,null,"",opening,sample,signalAt=now)
        val live=LivePriceState(connected=true,quotes=mapOf("NSE_EQ|TEST" to LiveQuote("NSE_EQ|TEST",1030.0,1020.0,now,now)),markets=mapOf("NSE_EQ" to true))
        compose.setContent { PaperUiTheme {
            pageView=androidx.compose.ui.platform.LocalView.current
            androidx.compose.material3.Surface(color=androidx.compose.material3.MaterialTheme.colorScheme.background) {
                ReversalPage(ReversalSnapshot(listOf(row),now),live)
            }
        } }
        compose.waitForIdle()
        save("signals")
        compose.onAllNodesWithText("HDFCBANK").onFirst().performClick()
        compose.onNodeWithText("Trend snapshot").assertExists()
        compose.onNodeWithText("Latest / prior 60s volume").assertExists()
        save("expanded")
        compose.onAllNodesWithText("HDFCBANK").onFirst().performClick()
        compose.onNodeWithText("SELL",useUnmergedTree=true).performClick()
        compose.onNodeWithText("Record SELL · HDFCBANK").assertExists()
        compose.onNodeWithText("Executed price ₹ · entered by you").assertExists()

        compose.onNodeWithText("Cancel").performClick()
        compose.onNodeWithTag("signals-list").performScrollToIndex(5)
        compose.waitForIdle()
        save("results")
    }
    private fun save(name:String) {
        compose.runOnIdle {
            val image=android.graphics.Bitmap.createBitmap(pageView.width,pageView.height,android.graphics.Bitmap.Config.ARGB_8888)
            pageView.draw(android.graphics.Canvas(image))
            val file=File("build/outputs/page-previews/$name.png");file.parentFile!!.mkdirs()
            file.outputStream().use { image.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it) }
        }
    }
}
