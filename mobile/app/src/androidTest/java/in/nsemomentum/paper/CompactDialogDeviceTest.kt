package com.nsemomentum.paper

import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.time.Instant
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
@OptIn(ExperimentalTestApi::class)
class CompactDialogDeviceTest {
    @get:Rule val compose=createComposeRule()
    @Test fun sellUsesEnteredPriceAndHeldQuantityWithoutPlacingOrder() {
        var result:Pair<Double,Int>?=null
        val request=RecordRequest("TEST","HDFCBANK",PaperSource.REVERSAL,PaperOperation.SELL,Instant.now(),1024.0,3)
        compose.setContent { PaperUiTheme { PaperRecordDialog(request,{}, {p,q->result=p to q}) } }
        compose.onNodeWithText("Record SELL · HDFCBANK").assertIsDisplayed()
        compose.onAllNodes(hasSetTextAction()).onFirst().performTextClearance()
        compose.onAllNodes(hasSetTextAction()).onFirst().performTextInput("1030.50")
        save("sell-form")
        compose.onNodeWithText("Record SELL").performClick()
        compose.runOnIdle { assertEquals(1030.5,result!!.first,0.0);assertEquals(3,result!!.second) }
    }
    @Test fun editBuyValidatesPriceAndAllowsQuantityCorrection() {
        var result:Pair<Double,Int>?=null
        val request=RecordRequest("TEST","DIXON",PaperSource.OPENING,PaperOperation.EDIT_BUY,Instant.now(),12319.0,1)
        compose.setContent { PaperUiTheme { PaperRecordDialog(request,{}, {p,q->result=p to q}) } }
        compose.onAllNodes(hasSetTextAction()).onFirst().performTextClearance()
        compose.onAllNodes(hasSetTextAction()).onFirst().performTextInput("0")
        compose.onNodeWithText("Save price").assertIsNotEnabled()
        compose.onAllNodes(hasSetTextAction()).onFirst().performTextClearance()
        compose.onAllNodes(hasSetTextAction()).onFirst().performTextInput("12320.50")
        compose.onAllNodes(hasSetTextAction()).onLast().performTextClearance()
        compose.onAllNodes(hasSetTextAction()).onLast().performTextInput("4")
        save("edit-buy-form")
        compose.onNodeWithText("Save price").performClick()
        compose.runOnIdle { assertEquals(12320.5,result!!.first,0.0);assertEquals(4,result!!.second) }
    }
    private fun save(name:String) {
        val image=compose.onAllNodes(isRoot()).onLast().captureToImage().asAndroidBitmap()
        val file=File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,"$name.png")
        file.outputStream().use { image.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it) }
    }
}
