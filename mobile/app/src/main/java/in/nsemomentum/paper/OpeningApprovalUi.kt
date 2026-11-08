package com.nsemomentum.paper

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*

@Composable fun OpeningNotificationPermission() {
    var status by remember { mutableStateOf("") }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        status = if (it) "Opening alerts enabled" else "Opening trades are available in Signals"
    }
    TextButton(onClick = {
        if (Build.VERSION.SDK_INT >= 33) permission.launch(Manifest.permission.POST_NOTIFICATIONS)
        else status = "Check Android notification settings for Opening alerts"
    }) { Text("Enable opening paper alerts") }
    if (status.isNotEmpty()) Text(status)
}
