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
        val current=LiveStochastic(TechnicalContext(1025.0,1020.0,18.5,25.8),now,now)
        val previous=LiveStochastic(TechnicalContext(1025.0,1020.0,26.0,25.0),now.minusSeconds(1),now.minusSeconds(1))
        val row=ReversalRow(Stock("HDFCBANK","NSE_EQ|TEST"),state,current,"",opening,sample,previous,now)
        val snapshot=ReversalSnapshot(listOf(row),now)
        val live=LivePriceState(connected=true,quotes=mapOf("NSE_EQ|TEST" to LiveQuote("NSE_EQ|TEST",1030.0,1020.0,now,now)),markets=mapOf("NSE_EQ" to true))
        compose.setContent { PaperUiTheme {
            pageView=androidx.compose.ui.platform.LocalView.current
            androidx.compose.material3.Surface(color=androidx.compose.material3.MaterialTheme.colorScheme.background) {
                ReversalPage(snapshot,live)
            }
        } }
        compose.waitForIdle()
        save("signals")
        compose.onAllNodesWithText("HDFCBANK").onFirst().performClick()
        compose.onNodeWithText("Trend snapshot").assertExists()
        compose.onNodeWithText("Latest / prior 60s volume").assertExists()
        save("expanded")
        compose.onAllNodesWithText("HDFCBANK").onFirst().performClick()
        compose.onNodeWithText("SELL",useUnmergedTree=true).assertExists()
        compose.onNodeWithTag("signals-list").performScrollToIndex(unifiedSignals(snapshot,now).size+3)
        compose.waitForIdle()
        save("results")
    }
    @Test fun dashboardUsesCompactQualifiedCardsAndDayWeekRows() {
        val now=Instant.now();val key="NSE_EQ|DIXON"
        val quote=LiveQuote(key,12319.0,11000.0,now,now)
        val qualified=QualifiedStock("DIXON",now.minusSeconds(900),now,10.97,12319.0,14000.0,10000.0)
        val candle=Candle(now.minusSeconds(900),12300.0,12350.0,12290.0,12319.0,14000.0)
        val report=ScanReport(listOf(ScanRow("DIXON",relativeVolume=2.1,signal="PAPER_HOLD",reason="TEST",candle=candle)),now.toString(),0,1)
        compose.setContent { PaperUiTheme {
            pageView=androidx.compose.ui.platform.LocalView.current
            androidx.compose.material3.Surface(color=androidx.compose.material3.MaterialTheme.colorScheme.background) {
                Dashboard(indexReport=null,onRefreshIndices={},indexRefreshEnabled=false,stockCount=1,favouriteCount=1,customStockCount=0,
                    scanStatus="Ready",report=report,scanning=false,scanProgress="",autoScanActive=true,autoScanStatus="Running",
                    qualifiedToday=listOf(qualified),catalog=listOf(Stock("DIXON",key)),
                    livePrices=LivePriceState(connected=true,quotes=mapOf(key to quote),markets=mapOf("NSE_EQ" to true)),liveStochastic=mapOf("DIXON" to LiveStochastic(TechnicalContext(12400.0,11800.0,32.5,24.8),now,now)),
                    paperTrades=listOf(PaperTrade("DIXON",now.minusSeconds(3600),11463.0,now.minusSeconds(60),12278.0)),previewSampledAt=now,
                    onRefreshPrices={},pricesRefreshEnabled=true,weeklySummary=emptyList(),weeklyOutcomes=emptyList(),
                    onStartFullDayScan={},onStopFullDayScan={},onRunScan={},onCancelScan={})
            }
        } }
        compose.waitForIdle();save("dashboard")
        compose.onNodeWithText("Refresh").assertIsDisplayed()
        compose.onNodeWithText("Stop scan").assertIsDisplayed()
        compose.onNodeWithText("Market indices").assertExists()
        compose.onNodeWithText("DIXON").performScrollTo().performClick()
        compose.onNodeWithText("Confirmed K / D").assertExists()
        compose.onNodeWithText("Dashboard").assertExists()
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
