package com.nsemomentum.updatecheck;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.*;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;

/** Local diagnostic only: no internet permission, account access, or scanner-data access. */
public class MainActivity extends Activity {
    private static final String SCANNER = "com.nsemomentum.paper.scanner";
    private TextView details;
    private Button install;
    private boolean preparing;
    private File apk() { return new File(getCacheDir(), "candidate.apk"); }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int pad = (int)(20 * getResources().getDisplayMetrics().density);
        layout.setPadding(pad, pad, pad, pad);
        ScrollView scroll = new ScrollView(this); scroll.addView(layout); setContentView(scroll);
        TextView title = new TextView(this); title.setText("Scanner update diagnosis"); title.setTextSize(24); layout.addView(title);
        TextView help = new TextView(this);
        help.setText("Checks the installed scanner and a file you select. No internet or access to your token, selections or scanner history. The scanner is never uninstalled.\n"); layout.addView(help);
        Button select = new Button(this); select.setText("1. Select app-release.apk"); layout.addView(select);
        select.setOnClickListener(v -> {
            Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/vnd.android.package-archive").addCategory(Intent.CATEGORY_OPENABLE);
            startActivityForResult(pick, 10);
        });
        install = new Button(this); install.setText("2. Request update and show result"); layout.addView(install);
        install.setOnClickListener(v -> requestUpdate());
        details = new TextView(this); details.setTextIsSelectable(true); details.setTextSize(16); layout.addView(details);
    }
    @Override public void onResume() { super.onResume(); if (!preparing) inspect(); }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != 10 || result != RESULT_OK || data == null || data.getData() == null) return;
        preparing = true; install.setEnabled(false); details.setText("Reading selected APK…");
        Uri uri = data.getData();
        new Thread(() -> {
            try (InputStream in = getContentResolver().openInputStream(uri); OutputStream out = new FileOutputStream(apk())) {
                if (in == null) throw new IOException("Cannot open selected file");
                byte[] buffer = new byte[65536]; int read; long size = 0;
                while ((read = in.read(buffer)) != -1) {
                    size += read; if (size > 100L * 1024 * 1024) throw new IOException("APK exceeds 100 MB limit");
                    out.write(buffer, 0, read);
                }
                getSharedPreferences("diagnosis", 0).edit().remove("result").apply();
                runOnUiThread(() -> { preparing = false; inspect(); });
            } catch (Exception error) {
                apk().delete();
                runOnUiThread(() -> { preparing = false; details.setText("Could not read APK: " + error.getClass().getSimpleName()); });
            }
        }, "read-selected-apk").start();
    }
    private static String fingerprints(PackageInfo info) throws Exception {
        if (info.signingInfo == null) throw new IOException("Signing information unavailable");
        List<String> values = new ArrayList<>();
        for (Signature signature : info.signingInfo.getApkContentsSigners()) {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(signature.toByteArray());
            StringBuilder hex = new StringBuilder(); for (byte b : digest) hex.append(String.format(Locale.US, "%02x", b & 255));
            values.add(hex.toString());
        }
        Collections.sort(values); if (values.isEmpty()) throw new IOException("No signing certificates");
        return String.join("\n", values);
    }
    private boolean inspect() {
        install.setEnabled(false);
        try {
            PackageInfo old = getPackageManager().getPackageInfo(SCANNER, PackageManager.GET_SIGNING_CERTIFICATES);
            String text = "Installed: " + old.versionName + " (" + old.getLongVersionCode() + ")\nInstalled certificate:\n" + fingerprints(old) + "\n\n";
            if (!apk().isFile()) { details.setText(text + "Select the downloaded 0.10.1 app-release.apk."); return false; }
            PackageInfo next = getPackageManager().getPackageArchiveInfo(apk().getPath(), PackageManager.GET_SIGNING_CERTIFICATES);
            if (next == null) { details.setText(text + "Android could not parse the selected APK."); return false; }
            boolean samePackage = SCANNER.equals(next.packageName);
            boolean sameKey = fingerprints(old).equals(fingerprints(next));
            boolean newer = next.getLongVersionCode() > old.getLongVersionCode();
            text += "Selected: " + next.versionName + " (" + next.getLongVersionCode() + ")\nSame package: " + samePackage + "\nSame installed signing key: " + sameKey + "\nHigher version code: " + newer + "\n\n";
            String last = getSharedPreferences("diagnosis", 0).getString("result", "No update requested by this diagnostic yet.");
            details.setText(text + last);
            boolean ready = samePackage && sameKey && newer;
            install.setEnabled(ready); return ready;
        } catch (PackageManager.NameNotFoundException e) {
            details.setText("The stable scanner is not visible to this tool. Leave it installed.");
        } catch (Exception e) { details.setText("Cannot inspect packages: " + e.getClass().getSimpleName()); }
        return false;
    }
    private void requestUpdate() {
        if (!inspect()) return;
        if (!getPackageManager().canRequestPackageInstalls()) {
            startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName())));
            return;
        }
        install.setEnabled(false);
        new Thread(() -> {
            PackageInstaller manager = getPackageManager().getPackageInstaller(); int sessionId = -1;
            try {
                PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                params.setAppPackageName(SCANNER); params.setSize(apk().length());
                sessionId = manager.createSession(params);
                try (PackageInstaller.Session session = manager.openSession(sessionId)) {
                    try (InputStream in = new FileInputStream(apk()); OutputStream out = session.openWrite("base.apk", 0, apk().length())) {
                        byte[] buffer = new byte[65536]; int n; while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
                        session.fsync(out);
                    }
                    Intent callback = new Intent(this, InstallResultReceiver.class).setAction(getPackageName() + ".INSTALL_RESULT");
                    PendingIntent pending = PendingIntent.getBroadcast(this, sessionId, callback, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE);
                    getSharedPreferences("diagnosis", 0).edit().putString("result", "Update submitted. Complete Android's confirmation screen.").apply();
                    session.commit(pending.getIntentSender());
                }
            } catch (Exception e) {
                if (sessionId >= 0) { try { manager.abandonSession(sessionId); } catch (Exception ignored) {} }
                getSharedPreferences("diagnosis", 0).edit().putString("result", "Update request failed: " + e.getClass().getSimpleName()).apply();
            }
            runOnUiThread(this::inspect);
        }, "update-diagnosis").start();
    }
}
