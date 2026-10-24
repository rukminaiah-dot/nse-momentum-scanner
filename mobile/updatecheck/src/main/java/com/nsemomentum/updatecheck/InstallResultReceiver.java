package com.nsemomentum.updatecheck;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;

public class InstallResultReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirm = android.os.Build.VERSION.SDK_INT >= 33
                ? intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent.class)
                : (Intent) intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirm != null) {
                try { context.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); }
                catch (Exception e) { save(context, "Could not open Android confirmation: " + e.getClass().getSimpleName()); }
            } else save(context, "Android did not provide an update confirmation intent.");
            return;
        }
        String label;
        switch (status) {
            case PackageInstaller.STATUS_SUCCESS: label = "SUCCESS"; break;
            case PackageInstaller.STATUS_FAILURE_BLOCKED: label = "BLOCKED"; break;
            case PackageInstaller.STATUS_FAILURE_ABORTED: label = "ABORTED"; break;
            case PackageInstaller.STATUS_FAILURE_INVALID: label = "INVALID_APK"; break;
            case PackageInstaller.STATUS_FAILURE_CONFLICT: label = "PACKAGE_CONFLICT"; break;
            case PackageInstaller.STATUS_FAILURE_STORAGE: label = "STORAGE"; break;
            case PackageInstaller.STATUS_FAILURE_INCOMPATIBLE: label = "INCOMPATIBLE"; break;
            default: label = "FAILURE";
        }
        String message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
        save(context, "Android result: " + label + " (" + status + ")\n" + (message == null ? "No detailed message supplied" : message));
        // Do not start an activity from a final background callback; user returns to the diagnostic.
    }
    private void save(Context context, String text) {
        context.getSharedPreferences("diagnosis", 0).edit().putString("result", text).apply();
    }
}
