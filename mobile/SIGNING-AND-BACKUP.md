# Experimental Android updates and recovery

The original package is `com.nsemomentum.paper`; current preview is
`com.nsemomentum.paper.preview`. Different packages have separate private data.
The preview cannot back up the original app's data. Do not uninstall the original
or clear its storage to resolve a signature conflict.

An in-place update needs the same package, an increased versionCode, and the
original private signing key. The previous CI workflow generated ephemeral debug
keys; neither the APK nor its public certificate can recover the private key.
If that key was not retained securely outside the runner, an in-place update of
that installation is blocked. A new persistent key only establishes a future
update chain; it does not repair an old signature mismatch.

## Persistent signing (configuration required)

Use one privately retained keystore, with an encrypted offline recovery copy.
Do not commit it, attach it to chat, upload it as an Actions artifact/cache, or
print it in logs. Supply these environment variables from a private secret store:

- ANDROID_SIGNING_STORE_FILE: absolute path to the private keystore
- ANDROID_SIGNING_STORE_PASSWORD
- ANDROID_SIGNING_KEY_ALIAS
- ANDROID_SIGNING_KEY_PASSWORD

Build from `experiment/android-paper-scanner` using Gradle 8.9 / Java 17:

```
gradle :app:testDebugUnitTest :app:assembleRelease
```

The release task fails if signing configuration is absent. Do not use the debug
APK as a durable update channel: hosted runners generate different debug keys.
Before installation, compare public certificate SHA-256 digests with
`apksigner verify --print-certs`, package IDs and version codes with `aapt dump
badging`, then test an update on a disposable emulator with saved data.
No key has been generated or repository secret changed by this implementation.
Setting up a protected Android-only CI secret store is a separate activation step.

## Backup and restore (0.6.0 preview onward)

Stop manual and full-day scans. In Settings choose Export backup and a durable
file location. Success requires writing and reading back identical bytes. Keep
the JSON private: it contains your favourites, custom stock keys and paper history.
The token, Android Keystore material, cached candles and live scan state are excluded.

Restore backup opens a file picker, validates the entire versioned file and asks
before merging. Duplicate history keeps the existing row. Conflicting custom
symbols/keys and combined lists above 20 are rejected. Invalid files do not reach
the database. Database history merge is transactional; preferences are saved
separately afterward. If interrupted between those writes, history may already
be merged; retry is idempotent and no existing record is deleted. Imported history
is user-supplied and is not verified trading or backtest evidence.

A successful export is not permission to uninstall. First verify restore on a
separate test installation, including favourite/custom counts and history records.
If the old installed version has no export feature, adding export to a differently
signed preview does not solve old-data migration. Preserve the old installation
until an original-key update or separately validated extraction path is available.

## Validation boundary

JVM/Robolectric tests cover backup format, all history tables, idempotent merge,
conflicts, malformed/future/oversized input and SQLite rollback. They do not prove
real-phone document-provider behavior or signature-compatible installation.
Phone export/restore, update preservation, live Upstox candles and historical
cost-inclusive walk-forward evaluation remain separate pending validations.
